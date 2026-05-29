"""
llm_client.py
=============
Telekom LLM API: HTTP-Call, Kostentracking, Retry-Logik, Prompt-Builder,
JSON-Parser und parallele Analyse (ThreadPoolExecutor).

Neu: Chunking mit Overlap
  Jeder Chunk enthält die letzten `chunk_overlap` Zeichen des vorherigen
  Chunks als Kontext-Prefix, damit kein Kontextverlust an Chunk-Grenzen.
"""

import re
import json
import time
import threading
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from urllib.parse import urlparse

import requests

from config import CONFIG, COST_LOG_FILE, TELEKOM_API_KEY
from logger import log_event, get_german_time
from rate_limiter import api_guard

# ---------------------------------------------------------------
# Kostentracking
# ---------------------------------------------------------------
_cost_lock        = threading.Lock()
_session_cost     = 0.0
_session_requests = 0


def record_cost(response_headers: dict) -> float:
    global _session_cost, _session_requests
    try:
        cost = float(response_headers.get("x-litellm-response-cost", 0))
    except (ValueError, TypeError):
        cost = 0.0
    with _cost_lock:
        _session_cost     += cost
        _session_requests += 1
    return cost


def log_cost_event(ort: str, chunk_idx: int, cost: float):
    line = (f"[{get_german_time()}] {ort} | Chunk {chunk_idx} | "
            f"Kosten: {cost:.8f} $ | Session: {_session_cost:.6f} $ | "
            f"Requests: {_session_requests}\n")
    try:
        with open(COST_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def get_session_stats() -> tuple:
    """Gibt (_session_cost, _session_requests) zurück."""
    with _cost_lock:
        return _session_cost, _session_requests


# ---------------------------------------------------------------
# Rolling Context Window
# ---------------------------------------------------------------
class ContextWindow:
    def __init__(self, max_size: int = 5):
        self.max_size = max_size
        self._items: deque = deque(maxlen=max_size)
        self._lock = threading.Lock()

    def add(self, massnahmen: list):
        with self._lock:
            for m in massnahmen:
                name  = m.get("massnahme", "")[:120]
                start = m.get("massnahme_start") or "unbekannt"
                self._items.append(f"- {name} (Start: {start})")

    def get_context_text(self) -> str:
        with self._lock:
            if not self._items:
                return ""
            items = list(self._items)
        return (
            "\nBEREITS IN VORHERIGEN CHUNKS GEFUNDENE MAẞNAHMEN (zur Duplikatvermeidung):\n"
            + "\n".join(items)
            + "\n"
        )

    def clear(self):
        with self._lock:
            self._items.clear()


# ---------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------
def normalize_url(url: str, fallback_base: str) -> str:
    if not url:
        return fallback_base
    if url.startswith("http"):
        return url
    p = urlparse(fallback_base)
    return f"{p.scheme}://{p.netloc}/{url.lstrip('/')}"


def sanitize_date(val) -> str | None:
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    return val if re.match(r'\d{4}-\d{2}-\d{2}', val) else None


# ---------------------------------------------------------------
# Chunking mit Overlap
# ---------------------------------------------------------------
def _make_chunks(text: str, chunk_size: int, overlap: int) -> list:
    """
    Teilt `text` in Chunks der Größe `chunk_size` auf.
    Jeder Chunk (ab dem zweiten) beginnt mit den letzten `overlap`
    Zeichen des vorherigen Chunks als Kontext-Prefix.

    Beispiel (chunk_size=400_000, overlap=5_000):
      Chunk 1: text[0:400_000]
      Chunk 2: text[395_000:795_000]   (5.000 Zeichen Überlapp)
      Chunk 3: text[790_000:1_190_000]
      ...

    Der Overlap-Block wird im Prompt deutlich als
    "[KONTEXT AUS VORHERIGEM CHUNK]" markiert, damit das Modell
    ihn nicht doppelt als neue Maßnahmen interpretiert.
    """
    if overlap >= chunk_size:
        overlap = chunk_size // 10  # Fallback: max 10% Overlap

    chunks   = []
    step     = chunk_size - overlap
    pos      = 0
    prev_end = 0

    while pos < len(text):
        chunk_end = pos + chunk_size
        raw_chunk = text[pos:chunk_end]

        if chunks and overlap > 0:
            # Overlap-Block als Kontext markieren
            ctx_block = (
                "[KONTEXT AUS VORHERIGEM CHUNK – NICHT ERNEUT AUSWERTEN]\n"
                + text[prev_end - overlap:prev_end]
                + "\n[ENDE KONTEXT]\n\n"
            )
            raw_chunk = ctx_block + raw_chunk

        chunks.append(raw_chunk)
        prev_end = chunk_end
        pos     += step

    return chunks


# ---------------------------------------------------------------
# Prompt-Builder
# ---------------------------------------------------------------
def _build_prompt(chunk_text: str, start_url: str, context_window: ContextWindow,
                  chunk_idx: int) -> str:
    base_url          = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    kategorien_string = json.dumps(CONFIG["ziel_kategorien"], ensure_ascii=False, indent=2)
    ctx_hint          = context_window.get_context_text()
    today_str         = date.today().strftime("%Y-%m-%d")
    cutoff_str        = date.today().replace(year=date.today().year - 3).strftime("%Y-%m-%d")

    return f"""Du bist ein Experte für die Analyse kommunaler Ausschreibungen und Bauprojekte.

AUFGABE: Extrahiere AUSSCHLIESSLICH echte Bau-, Infrastruktur- oder Sanierungsvorhaben.

STRIKTE AUSSCHLUSSKRITERIEN - ignoriere komplett:
- Fahrzeugbeschaffung (LKW, Feuerwehrfahrzeuge, Busse)
- Kursangebote, Wellness, Thermalbad, medizinische Pläne
- Stellenausschreibungen, reine Dienstleistungen (z.B. Winterdienst)
- Kulturelle Veranstaltungen, Feste, Sitzungstermine
- Abschnitte mit der Markierung [KONTEXT AUS VORHERIGEM CHUNK] – diese nur
  zur Orientierung nutzen, NICHT erneut als neue Maßnahmen erfassen.
{ctx_hint}
KATEGORIEN:
{kategorien_string}

ZEITRAUM-FILTER (Stichtag heute: {today_str}):
- Erfasse NUR Maßnahmen die NOCH LAUFEN oder IN DER ZUKUNFT liegen.
- "massnahme_ende" vorhanden UND liegt VOR {today_str} → Maßnahme WEGLASSEN (abgeschlossen).
- Nur Startdatum vorhanden, älter als 1 Jahre (vor {cutoff_str}) → WEGLASSEN.


WICHTIG:
        - Wenn ein Text keine Baumaßnahme enthält, gib eine leere Liste zurück: {{"massnahmen": []}}
        - Jede Maßnahme MUSS ein Start- oder Enddatum haben.
        - "quelle_url": Gib IMMER eine vollständige absolute URL an, die mit http:// oder https:// beginnt.
          Die Basis-Domain lautet: {base_url}
          Bei mehreren URLs zur selben Maßnahme: wähle die mit dem konkretesten Inhalt.
        - Gibt es Dopplungen (gleiche Maßnahme, verschiedene URLs): nur einmal ausgeben.

Antworte ausschließlich als JSON:
{{
    "massnahmen": [
        {{
            "kategorie": "...",
            "massnahme": "...",
            "adresse": "...",
            "massnahme_start": "YYYY-MM-DD",
            "massnahme_ende": "YYYY-MM-DD",
            "quelle_url": "..."
        }}
    ]
}}

Texte (Chunk {chunk_idx}):
{chunk_text}
"""


# ---------------------------------------------------------------
# JSON-Bereinigung & Parsing
# ---------------------------------------------------------------
def _sanitize_json_string(raw: str) -> str:
    raw = re.sub(r'```(?:json)?\s*', '', raw)
    raw = raw.replace("```", "").strip()
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE).strip()

    match = re.search(r'(\{.*\})', raw, re.DOTALL)
    if match:
        raw = match.group(1)

    result  = []
    in_str  = False
    escaped = False
    for ch in raw:
        if escaped:
            result.append(ch)
            escaped = False
            continue
        if ch == '\\':
            result.append(ch)
            escaped = True
            continue
        if ch == '"':
            in_str = not in_str
            result.append(ch)
            continue
        if in_str and ch in ('\n', '\r', '\t'):
            result.append(' ')
            continue
        result.append(ch)
    raw = ''.join(result)

    raw = re.sub(r',\s*(\}|\])', r'\1', raw)
    raw = re.sub(
        r'("|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*\n(\s*")',
        r'\1,\n\2',
        raw
    )
    return raw


def _extract_massnahmen_from_parsed(data: dict) -> list:
    if "massnahmen" in data:
        v = data["massnahmen"]
        return v if isinstance(v, list) else [v]
    if "massnahme" in data:
        return [data]
    return []


def _parse_massnahmen(raw: str, start_url: str) -> list:
    if not raw:
        return []

    def _apply(massnahmen):
        for item in massnahmen:
            item["quelle_url"]      = normalize_url(item.get("quelle_url"), start_url)
            item["massnahme_start"] = sanitize_date(item.get("massnahme_start"))
            item["massnahme_ende"]  = sanitize_date(item.get("massnahme_ende"))
        return massnahmen

    clean = re.sub(r'```(?:json)?\s*', '', raw).replace("```", "").strip()
    clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL | re.IGNORECASE).strip()
    try:
        parsed = json.loads(clean)
        result = _extract_massnahmen_from_parsed(parsed)
        if result is not None:
            return _apply(result)
    except json.JSONDecodeError:
        pass

    try:
        repaired = _sanitize_json_string(raw)
        parsed   = json.loads(repaired)
        result   = _extract_massnahmen_from_parsed(parsed)
        if result is not None:
            return _apply(result)
    except json.JSONDecodeError as e:
        log_event("⚠️", f"JSON-Repair Stufe 2 fehlgeschlagen ({e}) – versuche Regex-Extraktion")

    try:
        obj_pattern = re.compile(r'\{[^{}]*"massnahme"\s*:\s*"[^"]*"[^{}]*\}', re.DOTALL)
        gefunden    = []
        for m in obj_pattern.finditer(raw):
            try:
                obj = json.loads(_sanitize_json_string(m.group(0)))
                if "massnahme" in obj:
                    gefunden.append(obj)
            except Exception:
                pass
        if gefunden:
            log_event("⚠️", f"Regex-Extraktion rettete {len(gefunden)} Maßnahmen-Objekte")
            return _apply(gefunden)
    except Exception as e2:
        log_event("❌", f"Regex-Extraktion fehlgeschlagen: {e2}")

    snippet = raw[:300].replace("\n", " ")
    log_event("❌", f"JSON-Parsing komplett fehlgeschlagen. Antwort-Snippet: {snippet}")
    return []


# ---------------------------------------------------------------
# Deduplizierung & parallele Analyse
# ---------------------------------------------------------------
def deduplicate_massnahmen(massnahmen: list) -> list:
    seen   = set()
    unique = []
    for m in massnahmen:
        key = (m.get("massnahme", "").strip().lower(), m.get("massnahme_start"))
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


def analyze_with_telekom_llm(gesammelter_text: str, start_url: str) -> list:
    chunk_size  = CONFIG["chunk_size"]
    overlap     = CONFIG.get("chunk_overlap", 5_000)
    max_workers = CONFIG["llm_parallel_workers"]
    chunks      = _make_chunks(gesammelter_text, chunk_size, overlap)

    if not chunks:
        return []

    if len(chunks) == 1:
        log_event("🤖", f"Einzelner Chunk ({len(gesammelter_text):,} Zeichen) → 1 LLM-Call")
    else:
        log_event("📄", f"Text ({len(gesammelter_text):,} Zeichen) → {len(chunks)} Chunks "
                       f"(Overlap: {overlap:,} Zeichen), parallel mit {max_workers} Workern")

    context_win     = ContextWindow(max_size=CONFIG["context_window_size"])
    alle_massnahmen = []
    ort_label       = urlparse(start_url).netloc

    for gruppe_start in range(0, len(chunks), max_workers):
        gruppe = list(enumerate(chunks[gruppe_start:gruppe_start + max_workers],
                                start=gruppe_start + 1))
        futures_map = {}

        with ThreadPoolExecutor(max_workers=min(max_workers, len(gruppe))) as executor:
            for chunk_idx, chunk_text in gruppe:
                est_tokens = len(chunk_text) // 4
                if not api_guard.check_and_wait(est_tokens):
                    log_event("⚠️", f"Rate-Limit: Chunk {chunk_idx} übersprungen.")
                    continue
                prompt = _build_prompt(chunk_text, start_url, context_win, chunk_idx)
                futures_map[executor.submit(
                    _call_telekom_llm, prompt, est_tokens, chunk_idx, ort_label
                )] = chunk_idx

            chunk_results = {}
            for future in as_completed(futures_map):
                cidx = futures_map[future]
                try:
                    raw, cost = future.result()
                    if raw:
                        try:
                            with open(f"llm_debug_chunk{cidx}.txt", "w", encoding="utf-8") as _dbg:
                                _dbg.write(f"=== {ort_label} | Chunk {cidx} ===\n")
                                _dbg.write(raw)
                        except Exception:
                            pass
                    massnahmen = _parse_massnahmen(raw, start_url) if raw else []
                    chunk_results[cidx] = massnahmen
                    log_event("✅", f"Chunk {cidx}: {len(massnahmen)} Maßnahmen "
                                   f"(Kosten: {cost:.8f} $)")
                except Exception as e:
                    log_event("❌", f"Chunk {cidx} Future-Fehler: {e}")
                    chunk_results[cidx] = []

        for chunk_idx, _ in gruppe:
            massnahmen = chunk_results.get(chunk_idx, [])
            alle_massnahmen.extend(massnahmen)
            context_win.add(massnahmen)

    unique = deduplicate_massnahmen(alle_massnahmen)
    log_event("🔗", f"Gesamt: {len(alle_massnahmen)} Roh-Funde → {len(unique)} nach Dedup | "
                   f"Session-Kosten bisher: {_session_cost:.6f} $")
    return unique


# ---------------------------------------------------------------
# LLM-Call
# ---------------------------------------------------------------
def _call_telekom_llm(prompt: str, est_tokens: int, chunk_idx: int, ort: str):
    headers = {
        "Authorization": f"Bearer {TELEKOM_API_KEY}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       CONFIG["llm_model"],
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  8192,
        "temperature": 0.0,
    }
    retries = CONFIG["llm_retries"]
    delays  = CONFIG["llm_retry_delays"]

    for versuch in range(retries + 1):
        try:
            resp = requests.post(
                f"{CONFIG['llm_base_url']}/chat/completions",
                headers=headers, json=payload, timeout=300,
            )
            cost = record_cost(dict(resp.headers))
            log_cost_event(ort, chunk_idx, cost)

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", delays[min(versuch, len(delays)-1)]))
                log_event("⏳", f"429 Too Many Requests – warte {wait}s ...")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            api_guard.update_usage(est_tokens)
            content = resp.json()["choices"][0]["message"]["content"]
            return content, cost

        except requests.exceptions.HTTPError as e:
            if versuch < retries:
                wait = delays[min(versuch, len(delays)-1)]
                log_event("⚠️", f"HTTP-Fehler {e} (Chunk {chunk_idx}) – warte {wait}s ...")
                time.sleep(wait)
            else:
                log_event("❌", f"LLM nach {retries} Versuchen fehlgeschlagen (Chunk {chunk_idx})")
        except Exception as e:
            if versuch < retries:
                wait = delays[min(versuch, len(delays)-1)]
                log_event("⚠️", f"Fehler: {str(e)[:60]} – warte {wait}s ...")
                time.sleep(wait)
            else:
                log_event("❌", f"Unbekannter Fehler Chunk {chunk_idx}: {e}")

    return None, 0.0