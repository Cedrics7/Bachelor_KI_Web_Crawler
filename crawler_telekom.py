"""
crawler_telekom.py
==================
Crawler-Variante für die Telekom LLM API (OpenAI-kompatibler Endpunkt, LiteLLM-Backend).
Modell: gemini-2.5-pro

Unterschiede zu crawler_lokal.py:
- Kein Ollama, stattdessen POST https://llmapi.telekom.de/v1/chat/completions
- Parallele LLM-Calls pro Kommune via ThreadPoolExecutor
- Kleines Kontext-Fenster aus vorherigen Calls (rolling context window)
- Kostentracking via x-litellm-response-cost Header
"""

import os
import json
import re
import time
import threading
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from collections import deque
from datetime import datetime, date
from dotenv import load_dotenv
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
import hashlib
import fitz
import warnings
from database import get_db_connection

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# =====================================================================
# --- 1. KONFIGURATION ---
# =====================================================================
CONFIG = {
    "heartbeat":               10,
    "max_log_lines":           200,
    "max_targets":             4,
    "max_subpages":            50,
    "max_pdf_pages":           5,
    "timeout_seconds":         10,
    "sleep_between_targets":   1,
    "min_end_datum":           str(date.today()),
    "min_pdf_year":            2024,
    "max_text_chars":          5_000_000,
    "chunk_size":              400_000,
    "llm_parallel_workers":    4,
    "context_window_size":     5,
    "llm_model":               "gemini-2.5-pro",
    "llm_base_url":            "https://llmapi.telekom.de/v1",
    "llm_retries":             3,
    "llm_retry_delays":        [10, 30, 60],
    "rpm_limit":               30,
    "tpm_limit":               1_000_000,
    "rpd_limit":               500,
    "prio_region":             "",
    "ziel_kategorien": {
        "Sanierung":       ["Sanierungsgebiet", "Stadtsanierung", "Fördergebiet"],
        "Neubau":          ["Neubaugebiet", "Bebauungsplan", "B-Plan", "Erschließung"],
        "Privatisierung":  ["Grundstücksverkauf", "Veräußerung", "Liegenschaften"],
        "Tiefbau":         ["Tiefbau", "Straßenbau", "Kanalsanierung", "Brückenbau"],
        "Ausschreibung": ["Ausschreibung", "Vergabe", "Öffentliche Auftragsvergabe", "Submission", "VOB", "DTVP"],
    },
}

IGNORIERE_PARAMS = {
    "sort", "order", "view", "page", "fil", "lang", "style",
    "layout", "tab", "session", "ref",
    "utm_source", "utm_medium", "utm_campaign",
}

PDF_PRIO_KEYWORDS = [
    "bekanntmachung", "bebauungsplan", "b-plan", "bplan",
    "satzung", "erschließung", "erschliessung", "ausschreibung",
    "vergabe", "foerderung", "förderung", "sanierung", "tiefbau",
]

CONSOLE_LOG_FILE = "crawler_console.log"
SKIPPED_LOG_FILE = "crawler_skipped_urls.log"
COST_LOG_FILE    = "crawler_telekom_kosten.log"

load_dotenv()

TELEKOM_API_KEY = os.getenv("TELEKOM_LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
if not TELEKOM_API_KEY:
    raise EnvironmentError("Kein API-Key gefunden. Setze TELEKOM_LLM_API_KEY in .env")


# =====================================================================
# --- 2. KOSTENTRACKING ---
# =====================================================================
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


# =====================================================================
# --- 3. TOKEN / RATE-LIMIT MANAGER ---
# =====================================================================
class TokenManager:
    def __init__(self):
        self.rpm_limit      = CONFIG["rpm_limit"]
        self.tpm_limit      = CONFIG["tpm_limit"]
        self.rpd_limit      = CONFIG["rpd_limit"]
        self.window         = deque()
        self.requests_today = 0
        self.day_start      = date.today()
        self._lock          = threading.Lock()

    def _evict_old(self):
        cutoff = time.monotonic() - 60.0
        while self.window and self.window[0][0] < cutoff:
            self.window.popleft()

    def check_and_wait(self, estimated_tokens: int) -> bool:
        with self._lock:
            if estimated_tokens >= self.tpm_limit:
                log_event("!!!", f"Prompt zu groß ({estimated_tokens} Tokens) – übersprungen!")
                return False
            if date.today() > self.day_start:
                self.requests_today = 0
                self.day_start = date.today()
            if self.requests_today >= self.rpd_limit:
                log_event("!!!", "Tageslimit (RPD) erreicht.")
                return False
        while True:
            with self._lock:
                self._evict_old()
                rpm_ok = len(self.window) < self.rpm_limit
                tpm_ok = sum(t for _, t in self.window) + estimated_tokens < self.tpm_limit
                if rpm_ok and tpm_ok:
                    return True
                oldest = self.window[0][0] if self.window else time.monotonic()
                wait   = max((oldest + 61.0) - time.monotonic(), 1.0)
            reason = "RPM" if not rpm_ok else "TPM"
            log_event("⏳", f"Rate-Limit ({reason}) – warte {wait:.1f}s ...")
            time.sleep(wait)

    def update_usage(self, token_count: int):
        with self._lock:
            self.window.append((time.monotonic(), token_count))
            self.requests_today += 1


api_guard = TokenManager()


# =====================================================================
# --- 4. HILFSFUNKTIONEN ---
# =====================================================================
def get_german_time():
    return datetime.now().strftime("%d.%m.%Y, %H:%M:%S")


def _reset_log_if_new_month(filepath):
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            erste_zeile = f.readline()
        match = re.search(r'\[(\d{2}\.\d{2}\.\d{4})', erste_zeile)
        if match:
            log_monat   = datetime.strptime(match.group(1), "%d.%m.%Y").strftime("%Y-%m")
            jetzt_monat = datetime.now().strftime("%Y-%m")
            if log_monat != jetzt_monat:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"# Log-Reset: Neuer Monat ({jetzt_monat})\n")
    except Exception as e:
        print(f"Fehler beim Monats-Reset von {filepath}: {e}")


def _write_console_log(line: str):
    try:
        with open(CONSOLE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def write_skipped_urls(ort, skipped_urls: list):
    if not skipped_urls:
        return
    zeit = get_german_time()
    try:
        with open(SKIPPED_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{zeit}] ⚠️  DEDUP-SKIP für {ort} ({len(skipped_urls)} URLs):\n")
            for url in skipped_urls:
                f.write(f"  - {url}\n")
    except Exception as e:
        print(f"Fehler beim Schreiben des Skipped-Logs: {e}")


def log_event(emoji, message):
    zeit = get_german_time()
    line = f"[{zeit}] {emoji} {message}"
    print(line)
    _write_console_log(line)


def write_history_log(event_type, message):
    log_file = "crawler_history.txt"
    zeit = get_german_time()
    log_entry = f"[{zeit}] {event_type.upper()}: {message}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_entry)
    _write_console_log(log_entry.rstrip())
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > CONFIG["max_log_lines"]:
            with open(log_file, "w", encoding="utf-8") as f:
                f.writelines(lines[-CONFIG["max_log_lines"]:])
    except FileNotFoundError:
        pass


def reset_live_log_if_new_day():
    status_file = "crawler_live_status.json"
    heute_str   = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(status_file):
        return
    try:
        with open(status_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("timestamp", "").startswith(heute_str):
            data["letzte_funde"] = 0
            data["timestamp"]    = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            log_event("🔄", "Neuer Tag erkannt – Livelog-Funde zurückgesetzt.")
    except Exception as e:
        print(f"Fehler beim Tages-Reset des Livelogs: {e}")


def update_live_log(ort, status, funde=0, gespart=False):
    status_file        = "crawler_live_status.json"
    heute_str          = datetime.now().strftime("%Y-%m-%d")
    gesamt_funde_heute = funde
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            if old_data.get("timestamp", "").startswith(heute_str):
                gesamt_funde_heute += old_data.get("letzte_funde", 0)
        except Exception:
            pass
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp":     datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "aktueller_ort": ort,
            "status":        status,
            "letzte_funde":  gesamt_funde_heute,
            "hash_match":    gespart,
        }, f, ensure_ascii=False, indent=4)


# =====================================================================
# --- 4b. HEARTBEAT ---
# =====================================================================
_heartbeat_stop = threading.Event()


def _heartbeat_worker():
    status_file = "crawler_live_status.json"
    while not _heartbeat_stop.is_set():
        try:
            if os.path.exists(status_file):
                with open(status_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["timestamp"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                with open(status_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass
        _heartbeat_stop.wait(CONFIG["heartbeat"])


# =====================================================================
# --- 5. WEB-SCRAPING & PDF ---
# =====================================================================
def extract_pdf_text(url, max_pages):
    try:
        response = requests.get(url, timeout=10)
        with fitz.open(stream=response.content, filetype="pdf") as doc:
            meta   = doc.metadata
            c_date = meta.get("creationDate", "")
            if c_date.startswith("D:"):
                year = int(c_date[2:6])
                if year < CONFIG["min_pdf_year"]:
                    return ""
            return "".join(page.get_text() for page in doc[:max_pages])
    except Exception as e:
        _write_console_log(f"[{get_german_time()}] ❌ PDF-Fehler ({url[:60]}): {e}")
        return ""


def get_pdf_year(url):
    match = re.search(r'(20\d{2})', url.split("/")[-1])
    return int(match.group(1)) if match else 9999


def is_prio_pdf(url):
    filename = url.split("/")[-1].lower()
    return any(kw in filename for kw in PDF_PRIO_KEYWORDS)


def get_content_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_main_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def is_relevant_url(url):
    ignore = ["impressum", "datenschutz", "kontakt", "sitemap", "login",
              ".jpg", ".png", ".gif", ".svg", ".webp"]
    return not any(kw in url.lower() for kw in ignore)


def get_url_base(url):
    parsed = urlparse(url)
    if not parsed.query:
        return parsed._replace(fragment="").geturl()
    params    = parse_qs(parsed.query, keep_blank_values=True)
    gefiltert = {k: v for k, v in params.items() if k.lower() not in IGNORIERE_PARAMS}
    return parsed._replace(query=urlencode(gefiltert, doseq=True), fragment="").geturl()


def get_subpages(start_url, max_pages):
    visited_base   = set()
    visited_full   = set()
    to_visit       = [start_url]
    html_collected = []
    pdf_collected  = []
    skipped_urls   = []
    status_log     = {}
    base_domain    = urlparse(start_url).netloc
    prio_keywords  = ["aktuell", "news", "nachricht", "bauen", "projekt", "bebauungsplan"]

    while to_visit and (len(html_collected) + len(pdf_collected)) < max_pages:
        curr      = to_visit.pop(0)
        curr_base = get_url_base(curr)
        if curr_base in visited_base:
            skipped_urls.append(curr)
            continue
        visited_base.add(curr_base)
        visited_full.add(curr)
        try:
            resp = requests.get(curr, timeout=CONFIG["timeout_seconds"],
                                headers={"User-Agent": "BachelorCrawler/1.0"})
            status_log[curr] = resp.status_code
            if resp.url != curr:
                final_base = get_url_base(resp.url)
                if final_base in visited_base and final_base != curr_base:
                    skipped_urls.append(curr)
                    visited_base.discard(curr_base)
                    continue
                visited_base.add(final_base)
                visited_full.add(resp.url)
            if resp.status_code == 200:
                if curr.lower().endswith(".pdf"):
                    text = extract_pdf_text(curr, CONFIG["max_pdf_pages"])
                    if text:
                        pdf_collected.append((curr, text))
                else:
                    html_collected.append((curr, extract_main_text(resp.text)))
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for link in soup.find_all("a", href=True):
                        nxt      = urljoin(start_url, link["href"])
                        nxt_base = get_url_base(nxt)
                        if (urlparse(nxt).netloc == base_domain
                                and is_relevant_url(nxt)
                                and nxt_base not in visited_base
                                and nxt not in visited_full):
                            visited_full.add(nxt)
                            if any(p in nxt.lower() for p in prio_keywords):
                                to_visit.insert(0, nxt)
                            else:
                                to_visit.append(nxt)
        except requests.exceptions.Timeout:
            status_log[curr] = "TIMEOUT"
        except requests.exceptions.ConnectionError:
            status_log[curr] = "CONNECTION_ERROR"
        except Exception as ex:
            status_log[curr] = f"ERROR: {str(ex)[:60]}"

    return html_collected, pdf_collected, skipped_urls, status_log


def assemble_text(ort, html_pages, pdf_pages, limit):
    text_bulk = ""
    for url, content in html_pages:
        if content:
            text_bulk += f"\n--- URL: {url} ---\n{content}"

    prio_pdfs    = [(u, t) for u, t in pdf_pages if is_prio_pdf(u)]
    normale_pdfs = sorted([(u, t) for u, t in pdf_pages if not is_prio_pdf(u)],
                          key=lambda x: get_pdf_year(x[0]), reverse=True)
    sortierte_pdfs = prio_pdfs + normale_pdfs
    verbleibend    = limit - len(text_bulk)

    if sum(len(t) for _, t in sortierte_pdfs) <= verbleibend:
        for url, content in sortierte_pdfs:
            text_bulk += f"\n--- URL: {url} ---\n{content}"
        return text_bulk, False, False

    for reduzierte_seiten in [3, 2, 1]:
        neu_pdf = [(u, extract_pdf_text(u, reduzierte_seiten)) for u, _ in sortierte_pdfs]
        if sum(len(t) for _, t in neu_pdf) <= verbleibend:
            log_event("⚠️", f"PDFs auf {reduzierte_seiten} Seite(n) gekürzt für {ort}")
            for url, content in neu_pdf:
                if content:
                    text_bulk += f"\n--- URL: {url} ---\n{content}"
            return text_bulk, True, False

    return text_bulk[:limit], True, True


def normalize_url(url, fallback_base):
    if not url:
        return fallback_base
    if url.startswith("http"):
        return url
    p = urlparse(fallback_base)
    return f"{p.scheme}://{p.netloc}/{url.lstrip('/')}"


def sanitize_date(val):
    if not val or not isinstance(val, str):
        return None
    val = val.strip()
    return val if re.match(r'\d{4}-\d{2}-\d{2}', val) else None


# =====================================================================
# --- 6. ROLLING CONTEXT WINDOW ---
# =====================================================================
class ContextWindow:
    """
    Merkt sich die letzten N gefundenen Maßnahmen (Kurztexte) und
    reicht sie als Hinweis in jeden Folge-Prompt ein, damit das Modell
    keine chunk-übergreifenden Duplikate produziert.
    """

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


# =====================================================================
# --- 7. TELEKOM LLM API CALL ---
# =====================================================================
def _call_telekom_llm(prompt: str, est_tokens: int, chunk_idx: int, ort: str):
    """Einzelner LLM-Call an die Telekom API. Gibt (raw_text, cost) zurück."""
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


def _build_prompt(chunk_text: str, start_url: str, context_window: ContextWindow,
                  chunk_idx: int) -> str:
    base_url          = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    kategorien_string = json.dumps(CONFIG["ziel_kategorien"], ensure_ascii=False, indent=2)
    ctx_hint          = context_window.get_context_text()
    today_str         = date.today().strftime("%Y-%m-%d")
    cutoff            = date.today().replace(year=date.today().year - 3)
    cutoff_str        = cutoff.strftime("%Y-%m-%d")

    return f"""Du bist ein Experte für die Analyse kommunaler Ausschreibungen und Bauprojekte.

AUFGABE: Extrahiere AUSSCHLIESSLICH echte Bau-, Infrastruktur- oder Sanierungsvorhaben.

STRIKTE AUSSCHLUSSKRITERIEN - ignoriere komplett:
- Fahrzeugbeschaffung (LKW, Feuerwehrfahrzeuge, Busse)
- Kursangebote, Wellness, Thermalbad, medizinische Pläne
- Stellenausschreibungen, reine Dienstleistungen (z.B. Winterdienst)
- Kulturelle Veranstaltungen, Feste, Sitzungstermine
{ctx_hint}
KATEGORIEN:
{kategorien_string}

ZEITRAUM-FILTER (Stichtag heute: {today_str}):
- Erfasse NUR Maßnahmen die NOCH LAUFEN oder IN DER ZUKUNFT liegen.
- "massnahme_ende" vorhanden UND liegt VOR {today_str} → Maßnahme WEGLASSEN (abgeschlossen).
- Nur Startdatum vorhanden, älter als 3 Jahre (vor {cutoff_str}) → WEGLASSEN.
- Laufende Maßnahmen ohne Enddatum (null) → IMMER erfassen, egal wie alt der Start ist.

WICHTIG:
- Leere Liste wenn kein Bauvorhaben: {{"massnahmen": []}}
- Jede Maßnahme MUSS mind. ein Start- oder Enddatum haben.
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


def _sanitize_json_string(raw: str) -> str:
    r"""
    Bereinigungsschritte für Gemini-2.5-pro-Ausgaben:
    1. Markdown-Fences entfernen
    2. Thinking-Tags (<think>...</think>) entfernen
    3. Ersten vollständigen JSON-Block extrahieren
    4. Echte Steuerzeichen (\\n/\\t/\\r) in String-Values durch Leerzeichen ersetzen
    5. Trailing Commas reparieren  (,  } / ,  ])
    6. Fehlende Kommas zwischen Feldern einfügen  ("val"\\n"key" → "val",\\n"key")
    """
    # 1. Markdown-Fences
    raw = re.sub(r'```(?:json)?\s*', '', raw)
    raw = raw.replace("```", "").strip()

    # 2. Thinking-Tags
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE).strip()

    # 3. JSON-Block extrahieren
    match = re.search(r'(\{.*\})', raw, re.DOTALL)
    if match:
        raw = match.group(1)

    # 4. Echte \n / \t / \r innerhalb von JSON-String-Values durch Leerzeichen ersetzen
    result   = []
    in_str   = False
    escaped  = False
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

    # 5. Trailing Commas reparieren
    raw = re.sub(r',\s*(\}|\])', r'\1', raw)

    # 6. Fehlende Kommas zwischen Feldern einfügen
    # Muster: Wert-Ende gefolgt von Whitespace+Newline+neuer Key
    # "wert"\n    "key": → "wert",\n    "key":
    raw = re.sub(
        r'("|\btrue\b|\bfalse\b|\bnull\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)\s*\n(\s*")',
        r'\1,\n\2',
        raw
    )

    return raw

def _extract_massnahmen_from_parsed(data: dict) -> list:
    """
    Unterstützt beide Varianten die Gemini zurückgeben kann:
    - {"massnahmen": [...]}   (Normalfall)
    - {"massnahme": "...", ...}  (Einzelobjekt ohne wrapper)
    """
    if "massnahmen" in data:
        v = data["massnahmen"]
        return v if isinstance(v, list) else [v]
    if "massnahme" in data:
        return [data]
    return []


def _parse_massnahmen(raw: str, start_url: str) -> list:
    """
    Robust JSON parser mit drei Fallback-Stufen:
    1. Direktes json.loads nach einfacher Bereinigung
    2. json.loads nach vollständiger Reparatur (trailing commas, think-tags)
    3. Regex-Extraktion einzelner Maßnahmen-Objekte als letzter Ausweg
    """
    if not raw:
        return []

    def _apply(massnahmen):
        for item in massnahmen:
            item["quelle_url"]      = normalize_url(item.get("quelle_url"), start_url)
            item["massnahme_start"] = sanitize_date(item.get("massnahme_start"))
            item["massnahme_ende"]  = sanitize_date(item.get("massnahme_ende"))
        return massnahmen

    # Stufe 1: Direkt parsen nach einfacher Bereinigung
    clean = re.sub(r'```(?:json)?\s*', '', raw).replace("```", "").strip()
    clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL | re.IGNORECASE).strip()
    try:
        parsed = json.loads(clean)
        result = _extract_massnahmen_from_parsed(parsed)
        if result is not None:
            return _apply(result)
    except json.JSONDecodeError:
        pass

    # Stufe 2: Vollständige Bereinigung (trailing commas, steuerzeichen, json-block)
    try:
        repaired = _sanitize_json_string(raw)
        parsed   = json.loads(repaired)
        result   = _extract_massnahmen_from_parsed(parsed)
        if result is not None:
            return _apply(result)
    except json.JSONDecodeError as e:
        log_event("⚠️", f"JSON-Repair Stufe 2 fehlgeschlagen ({e}) – versuche Regex-Extraktion")

    # Stufe 3: Regex – einzelne Maßnahmen-Objekte direkt aus dem Rohtext fischen
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

def _call_telekom_llm(prompt: str, est_tokens: int, chunk_idx: int, ort: str):
    """Einzelner LLM-Call an die Telekom API. Gibt (raw_text, cost) zurück."""
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


def _build_prompt(chunk_text: str, start_url: str, context_window: ContextWindow,
                  chunk_idx: int) -> str:
    base_url          = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    kategorien_string = json.dumps(CONFIG["ziel_kategorien"], ensure_ascii=False, indent=2)
    ctx_hint          = context_window.get_context_text()
    today_str         = date.today().strftime("%Y-%m-%d")
    cutoff            = date.today().replace(year=date.today().year - 3)
    cutoff_str        = cutoff.strftime("%Y-%m-%d")

    return f"""Du bist ein Experte für die Analyse kommunaler Ausschreibungen und Bauprojekte.

AUFGABE: Extrahiere AUSSCHLIESSLICH echte Bau-, Infrastruktur- oder Sanierungsvorhaben.

STRIKTE AUSSCHLUSSKRITERIEN - ignoriere komplett:
- Fahrzeugbeschaffung (LKW, Feuerwehrfahrzeuge, Busse)
- Kursangebote, Wellness, Thermalbad, medizinische Pläne
- Stellenausschreibungen, reine Dienstleistungen (z.B. Winterdienst)
- Kulturelle Veranstaltungen, Feste, Sitzungstermine
{ctx_hint}
KATEGORIEN:
{kategorien_string}

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


def _sanitize_json_string(raw: str) -> str:
    r"""
    Mehrere Bereinigungsschritte für Gemini-2.5-pro-Ausgaben:
    1. Markdown-Fences entfernen
    2. Thinking-Tags (<think>...</think>) entfernen
    3. Ersten vollständigen JSON-Block extrahieren
    4. Trailing Commas reparieren  (,[\\s\\n]*} und ,[\\s\\n]*])
    5. Steuerzeichen in String-Werten reparieren
    """
    # 1. Markdown-Fences
    raw = re.sub(r'```(?:json)?\s*', '', raw)
    raw = raw.replace("```", "").strip()

    # 2. Thinking-Tags (Gemini-2.5-pro gibt manchmal <think>...</think> aus)
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE)
    raw = raw.strip()

    # 3. Ersten { ... } Block extrahieren (greedy von außen)
    match = re.search(r'(\{.*\})', raw, re.DOTALL)
    if match:
        raw = match.group(1)

    # 4. Trailing Commas reparieren: ,\n} → \n}  und ,\n] → \n]
    raw = re.sub(r',\s*(\}|\])', r'\1', raw)

    # 5. Unescapte Newlines/Tabs innerhalb von String-Werten reparieren
    #    Ersetzt echte \n und \t innerhalb von JSON-Strings durch Leerzeichen
    def fix_string_values(m):
        return m.group(0).replace("\n", " ").replace("\t", " ").replace("\r", " ")
    raw = re.sub(r'"[^"\\\n]*(?:\\.[^"\\\n]*)*"', fix_string_values, raw)

    return raw


def _parse_massnahmen(raw: str, start_url: str) -> list:
    """
    Robust JSON parser mit mehreren Fallback-Stufen:
    1. Direktes json.loads nach Bereinigung
    2. json.loads mit repariertem String (Trailing Commas, Steuerzeichen)
    3. Regex-Extraktion einzelner Maßnahmen-Objekte als letzter Ausweg
    """
    if not raw:
        return []

    def _apply(massnahmen):
        for item in massnahmen:
            item["quelle_url"]      = normalize_url(item.get("quelle_url"), start_url)
            item["massnahme_start"] = sanitize_date(item.get("massnahme_start"))
            item["massnahme_ende"]  = sanitize_date(item.get("massnahme_ende"))
        return massnahmen

    # Stufe 1: Direkt parsen nach einfacher Bereinigung
    clean = re.sub(r'```(?:json)?\s*', '', raw).replace("```", "").strip()
    clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL | re.IGNORECASE).strip()
    try:
        return _apply(json.loads(clean).get("massnahmen", []))
    except json.JSONDecodeError:
        pass

    # Stufe 2: Vollständige Bereinigung (trailing commas, steuerzeichen, json-block)
    try:
        repaired = _sanitize_json_string(raw)
        return _apply(json.loads(repaired).get("massnahmen", []))
    except json.JSONDecodeError as e:
        log_event("⚠️", f"JSON-Repair Stufe 2 fehlgeschlagen ({e}) – versuche Regex-Extraktion")

    # Stufe 3: Regex – einzelne Maßnahmen-Objekte extrahieren
    #  Sucht alle {...}-Blöcke die "massnahme" als Key enthalten
    try:
        obj_pattern = re.compile(
            r'\{[^{}]*"massnahme"\s*:\s*"[^"]*"[^{}]*\}',
            re.DOTALL
        )
        gefunden = []
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

    # Alle Stufen gescheitert → Raw-Response ins Log schreiben für Debugging
    snippet = raw[:300].replace("\n", " ")
    log_event("❌", f"JSON-Parsing komplett fehlgeschlagen. Antwort-Snippet: {snippet}")
    return []


def deduplicate_massnahmen(massnahmen: list) -> list:
    seen, unique = set(), []
    for item in massnahmen:
        key = (item.get("massnahme", "").strip().lower(), item.get("massnahme_start"))
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


# =====================================================================
# --- 8. PARALLELE LLM-ANALYSE PRO KOMMUNE ---
# =====================================================================
def analyze_with_telekom_llm(gesammelter_text: str, start_url: str) -> list:
    """
    1. Text → Chunks
    2. Chunks in Gruppen parallel an Telekom LLM senden (ThreadPoolExecutor)
    3. Nach jeder Gruppe: ContextWindow mit Ergebnissen befüllen
    4. Ergebnisse mergen + deduplizieren
    """
    chunk_size  = CONFIG["chunk_size"]
    max_workers = CONFIG["llm_parallel_workers"]
    chunks = [gesammelter_text[i:i + chunk_size]
              for i in range(0, len(gesammelter_text), chunk_size)]

    if not chunks:
        return []

    if len(chunks) == 1:
        log_event("🤖", f"Einzelner Chunk ({len(gesammelter_text):,} Zeichen) → 1 LLM-Call")
    else:
        log_event("📄", f"Text ({len(gesammelter_text):,} Zeichen) → {len(chunks)} Chunks, "
                       f"parallel mit {max_workers} Workern")

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
                    # Debug-Log: rohe LLM-Antwort für Analyse speichern
                    if raw:
                        try:
                            debug_path = f"llm_debug_chunk{cidx}.txt"
                            with open(debug_path, "w", encoding="utf-8") as _dbg:
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

        # Ergebnisse in Reihenfolge verarbeiten → Context konsistent befüllen
        for chunk_idx, _ in gruppe:
            massnahmen = chunk_results.get(chunk_idx, [])
            alle_massnahmen.extend(massnahmen)
            context_win.add(massnahmen)

    unique = deduplicate_massnahmen(alle_massnahmen)
    log_event("🔗", f"Gesamt: {len(alle_massnahmen)} Roh-Funde → {len(unique)} nach Dedup | "
                   f"Session-Kosten bisher: {_session_cost:.6f} $")
    return unique


# =====================================================================
# --- 9. DUPLIKAT-PRÜFUNG (DB) ---
# =====================================================================
def is_duplicate(cursor, ags, massnahme, massnahme_start):
    if massnahme_start is None:
        cursor.execute("""
            SELECT id FROM crawl_results
            WHERE ags = %s AND massnahme = %s AND massnahme_start IS NULL
        """, (ags, massnahme))
    else:
        cursor.execute("""
            SELECT id FROM crawl_results
            WHERE ags = %s AND massnahme = %s AND massnahme_start = %s
        """, (ags, massnahme, massnahme_start))
    return cursor.fetchone() is not None


# =====================================================================
# --- 10. MAIN LOOP ---
# =====================================================================
def run_crawler():
    _reset_log_if_new_month(CONSOLE_LOG_FILE)
    _reset_log_if_new_month(SKIPPED_LOG_FILE)
    reset_live_log_if_new_day()

    _heartbeat_stop.clear()
    heartbeat = threading.Thread(target=_heartbeat_worker, daemon=True)
    heartbeat.start()

    conn   = get_db_connection()
    cursor = conn.cursor()

    targets_processed = 0
    total_funde       = 0
    start_zeit_dt     = datetime.now()
    prio_region       = CONFIG.get("prio_region")

    write_history_log("START",
        f"Beginne Telekom-Crawler | Modell: {CONFIG['llm_model']} | "
        f"{CONFIG['llm_parallel_workers']} parallele LLM-Worker | "
        f"max. {CONFIG['max_targets']} Targets."
        + (f" Prio-Region: {prio_region}." if prio_region else ""))

    if prio_region:
        cursor.execute("""
            SELECT ct.ags, ct.url, ct.ort
            FROM crawl_targets ct
            LEFT JOIN region_mapping rm ON ct.bundesland = rm.bundesland
            ORDER BY
                CASE WHEN rm.region = %s THEN 0 ELSE 1 END ASC,
                ct.last_scanned ASC NULLS FIRST
            LIMIT %s
        """, (prio_region, CONFIG["max_targets"]))
        log_event("🎯", f"Region-Priorisierung aktiv: '{prio_region}'")
    else:
        cursor.execute(
            "SELECT ags, url, ort FROM crawl_targets ORDER BY last_scanned ASC NULLS FIRST LIMIT %s",
            (CONFIG["max_targets"],)
        )

    targets   = cursor.fetchall()
    min_datum = datetime.strptime(CONFIG["min_end_datum"], "%Y-%m-%d").date()

    log_event("ℹ️", f"Modell: {CONFIG['llm_model']} | "
                   f"Chunk-Größe: {CONFIG['chunk_size']:,} Zeichen | "
                   f"Kontext-Fenster: {CONFIG['context_window_size']} Einträge | "
                   f"Parallel-Worker: {CONFIG['llm_parallel_workers']}")

    try:
        for ags, start_url, ort in targets:
            start_time = datetime.now()
            log_event("🔍", f"Target: {ort} ({start_url})")
            update_live_log(ort, "🔍 Scraping & PDF-Analyse...")
            targets_processed += 1

            html_pages, pdf_pages, skipped_urls, status_log = get_subpages(
                start_url, CONFIG["max_subpages"]
            )
            write_skipped_urls(ort, skipped_urls)
            if skipped_urls:
                log_event("🔗", f"{len(skipped_urls)} URL(s) per Dedup übersprungen")

            text_bulk, hat_gekuerzt, hat_verworfen = assemble_text(
                ort, html_pages, pdf_pages, CONFIG["max_text_chars"]
            )

            if not text_bulk.strip():
                fehler_codes = set(status_log.values())
                fehler_info  = ", ".join(str(c) for c in sorted(fehler_codes, key=str))
                log_event("⚠️", f"Kein Text für {ort}. Status-Codes: [{fehler_info}]")
                update_live_log(ort, f"⚠️ Kein Text [{fehler_info}]")
                continue

            content_hash = get_content_hash(text_bulk)
            cursor.execute("SELECT id FROM crawl_results WHERE content_hash = %s", (content_hash,))

            if cursor.fetchone():
                log_event("🔒", f"Keine Änderungen in {ort} (Hash-Match).")
                update_live_log(ort, "✅ Stand aktuell (Hash-Match)", gespart=True)
            else:
                log_event("🤖", f"Analyse {ort} → {CONFIG['llm_model']} ...")
                update_live_log(ort, f"🤖 LLM-Analyse ({CONFIG['llm_model']})...")

                found = analyze_with_telekom_llm(text_bulk, start_url)

                valid_count  = 0
                skipped_dups = 0
                for item in found:
                    m_start = item.get("massnahme_start")
                    m_ende  = item.get("massnahme_ende")
                    m_name  = item.get("massnahme")

                    if not m_start and not m_ende:
                        continue
                    if m_ende:
                        try:
                            if datetime.strptime(m_ende, "%Y-%m-%d").date() < min_datum:
                                continue
                        except ValueError:
                            pass

                    if is_duplicate(cursor, ags, m_name, m_start):
                        skipped_dups += 1
                        log_event("🔄", f"DB-Duplikat übersprungen: {m_name}")
                        continue

                    valid_count += 1
                    cursor.execute("""
                        INSERT INTO crawl_results
                            (ags, gefunden_am, start_time, end_time, status, kategorie,
                             massnahme, adresse, massnahme_start, massnahme_ende,
                             massnahme_url, content_hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        ags, datetime.now().strftime("%Y-%m-%d"),
                        start_time, datetime.now(), "Erfolgreich",
                        item.get("kategorie"), m_name, item.get("adresse"),
                        m_start, m_ende, item.get("quelle_url"), content_hash,
                    ))

                total_funde += valid_count
                log_event("✅", f"Fertig: {valid_count} neue Funde, "
                               f"{skipped_dups} Duplikate für {ort}.")
                update_live_log(ort, f"✅ Fertig: {valid_count} Funde", funde=valid_count)

            cursor.execute(
                "UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s",
                (datetime.now(), ags)
            )
            conn.commit()
            time.sleep(CONFIG["sleep_between_targets"])

    finally:
        _heartbeat_stop.set()
        heartbeat.join(timeout=5)

    dauer = datetime.now() - start_zeit_dt
    minuten, sekunden = divmod(dauer.seconds, 60)
    summary = (
        f"Beendet. {targets_processed} Orte, {total_funde} Funde. "
        f"Dauer: {minuten}m {sekunden}s. "
        f"Gesamtkosten: {_session_cost:.6f} $ ({_session_requests} Requests)"
    )
    write_history_log("ENDE ", summary)
    log_event("🏁", summary)
    update_live_log("Standby", f"🏁 Letzter Scan: {summary}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    run_crawler()
