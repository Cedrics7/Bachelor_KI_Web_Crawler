"""
crawler_eval.py
===============
Multi-Modell-Evaluierungs-Crawler.

Zweck:  Qualitative Analyse verschiedener LLM-Modelle für den Anwendungsfall
        der kommunalen Baumaßnahmen-Extraktion.
        KEIN Datenbankschreiben – alle Ergebnisse werden als JSON/TXT gespeichert.

Output-Struktur (bei output_nested=True):
    output_eval/
        <ort-slug>/
            <modell-id>/
                raw_response.txt
                normalized.json
                meta.json
        eval_summary_<timestamp>.json   <- Gesamt-Übersicht aller Läufe

Nutzung:
    cd crawler/
    python crawler_eval.py

Für schnellen Test ohne DB (manual_targets in eval_config.py befüllen):
    EVAL_CONFIG["manual_targets"] = [{"ort": "Hamburg", "url": "https://..."}]
"""

import json
import os
import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from urllib.parse import urlparse

import requests

from Alt.crawler_lokal_test.eval_config import EVAL_MODELS, EVAL_CONFIG, get_api_key
from logger import log_event
from scraper import get_subpages, assemble_text


# ============================================================
# Hilfsfunktionen
# ============================================================

def slugify(text: str) -> str:
    """Wandelt einen Ortsnamen in einen dateisystem-sicheren Slug um.
    'Baden-Württemberg' -> 'baden-wuerttemberg'
    """
    umlaut_map = str.maketrans({
        'ä': 'ae', 'ö': 'oe', 'ü': 'ue',
        'Ä': 'ae', 'Ö': 'oe', 'Ü': 'ue', 'ß': 'ss',
    })
    text = text.translate(umlaut_map)
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[\s_-]+', '-', text)


def ensure_dir(path: str):
    os.makedirs(path, exist_ok=True)


def output_path_for(ort_slug: str, model_id: str, filename: str) -> str:
    """Gibt den vollständigen Pfad für eine Output-Datei zurück."""
    base = EVAL_CONFIG["output_dir"]
    if EVAL_CONFIG["output_nested"]:
        return os.path.join(base, ort_slug, model_id, filename)
    return os.path.join(base, f"{ort_slug}_{model_id}_{filename}")


def save_file(path: str, content: str):
    ensure_dir(os.path.dirname(path))
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    log_event("💾", f"Gespeichert: {path}")


# ============================================================
# Chunking (übernommen aus llm_client.py)
# ============================================================

def _make_chunks(text: str, chunk_size: int, overlap: int) -> list:
    if overlap >= chunk_size:
        overlap = chunk_size // 10
    chunks, step, pos, prev_end = [], chunk_size - overlap, 0, 0
    while pos < len(text):
        raw_chunk = text[pos:pos + chunk_size]
        if chunks and overlap > 0:
            ctx_block = (
                "[KONTEXT AUS VORHERIGEM CHUNK – NICHT ERNEUT AUSWERTEN]\n"
                + text[prev_end - overlap:prev_end]
                + "\n[ENDE KONTEXT]\n\n"
            )
            raw_chunk = ctx_block + raw_chunk
        chunks.append(raw_chunk)
        prev_end = pos + chunk_size
        pos += step
    return chunks


# ============================================================
# Prompt-Builder (identisch mit Produktiv-Crawler)
# ============================================================

def _build_eval_prompt(chunk_text: str, start_url: str,
                       context_hint: str, chunk_idx: int) -> str:
    base_url          = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    kategorien_string = json.dumps(EVAL_CONFIG["ziel_kategorien"], ensure_ascii=False, indent=2)
    today_str         = date.today().strftime("%Y-%m-%d")
    cutoff_str        = date.today().replace(year=date.today().year - 3).strftime("%Y-%m-%d")
    return f"""Du bist ein Experte für die Analyse kommunaler Ausschreibungen und Bauprojekte.

AUFGABE: Extrahiere AUSSCHLIESSLICH echte Bau-, Infrastruktur- oder Sanierungsvorhaben.

STRIKTE AUSSCHLUSSKRITERIEN - ignoriere komplett:
- Fahrzeugbeschaffung (LKW, Feuerwehrfahrzeuge, Busse)
- Kursangebote, Wellness, Thermalbad, medizinische Pläne
- Stellenausschreibungen, reine Dienstleistungen (z.B. Winterdienst)
- Kulturelle Veranstaltungen, Feste, Sitzungstermine
- Abschnitte mit der Markierung [KONTEXT AUS VORHERIGEM CHUNK] – nur zur Orientierung,
  NICHT erneut als neue Maßnahmen erfassen.
{context_hint}
KATEGORIEN:
{kategorien_string}

ZEITRAUM-FILTER (Stichtag heute: {today_str}):
- Erfasse NUR Maßnahmen die NOCH LAUFEN oder IN DER ZUKUNFT liegen.
- "massnahme_ende" vorhanden UND liegt VOR {today_str} → Maßnahme WEGLASSEN.
- Nur Startdatum vorhanden, älter als 3 Jahre (vor {cutoff_str}) → WEGLASSEN.

WICHTIG:
- Wenn kein Text zu Baumaßnahmen vorhanden: gib {{"massnahmen": []}} zurück.
- Jede Maßnahme MUSS ein Start- oder Enddatum haben.
- "quelle_url": Immer vollständige absolute URL (Basis: {base_url}).
- Dopplungen (gleiche Maßnahme, verschiedene URLs): nur einmal ausgeben.

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


# ============================================================
# JSON-Parsing (übernommen aus llm_client.py)
# ============================================================

def _sanitize_json(raw: str) -> str:
    raw = re.sub(r'```(?:json)?\s*', '', raw).replace("```", "").strip()
    raw = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL | re.IGNORECASE).strip()
    match = re.search(r'(\{.*\})', raw, re.DOTALL)
    if match:
        raw = match.group(1)
    result, in_str, escaped = [], False, False
    for ch in raw:
        if escaped:
            result.append(ch); escaped = False; continue
        if ch == '\\':
            result.append(ch); escaped = True; continue
        if ch == '"':
            in_str = not in_str; result.append(ch); continue
        if in_str and ch in ('\n', '\r', '\t'):
            result.append(' '); continue
        result.append(ch)
    raw = ''.join(result)
    raw = re.sub(r',\s*(\}|\])', r'\1', raw)
    return raw


def _parse_massnahmen(raw: str, start_url: str) -> tuple:
    """Parst den Roh-Output und gibt (massnahmen_liste, parse_status) zurück."""
    if not raw:
        return [], "empty_response"

    def normalize_urls(items):
        for item in items:
            url = item.get("quelle_url", "")
            if url and not url.startswith("http"):
                p = urlparse(start_url)
                item["quelle_url"] = f"{p.scheme}://{p.netloc}/{url.lstrip('/')}"
        return items

    clean = re.sub(r'```(?:json)?\s*', '', raw).replace("```", "").strip()
    clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL | re.IGNORECASE).strip()
    try:
        parsed = json.loads(clean)
        items  = parsed.get("massnahmen", [])
        return normalize_urls(items), "ok"
    except json.JSONDecodeError:
        pass
    try:
        repaired = _sanitize_json(raw)
        parsed   = json.loads(repaired)
        items    = parsed.get("massnahmen", [])
        return normalize_urls(items), "repaired"
    except json.JSONDecodeError as e:
        log_event("⚠️", f"JSON-Parsing fehlgeschlagen: {e}")
        return [], f"parse_error: {str(e)[:80]}"


# ============================================================
# LLM-Call (modell-agnostisch)
# ============================================================

def _call_llm(prompt: str, model_def: dict, chunk_idx: int) -> tuple:
    """Führt einen LLM-Call aus und gibt (raw_content, cost, latency_s) zurück."""
    api_key  = get_api_key(model_def)
    headers  = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    payload = {
        "model":       model_def["model"],
        "messages":    [{"role": "user", "content": prompt}],
        "max_tokens":  8192,
        "temperature": 0.0,
    }
    retries = EVAL_CONFIG["llm_retries"]
    delays  = EVAL_CONFIG["llm_retry_delays"]

    for versuch in range(retries + 1):
        try:
            t0   = time.time()
            resp = requests.post(
                f"{model_def['base_url']}/chat/completions",
                headers=headers, json=payload, timeout=300,
            )
            latency = round(time.time() - t0, 2)

            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After",
                           delays[min(versuch, len(delays)-1)]))
                log_event("⏳", f"429 – warte {wait}s (Modell: {model_def['id']})")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            try:
                cost = float(resp.headers.get("x-litellm-response-cost", 0))
            except (ValueError, TypeError):
                cost = 0.0
            content = resp.json()["choices"][0]["message"]["content"]
            return content, cost, latency

        except requests.exceptions.HTTPError as e:
            if versuch < retries:
                wait = delays[min(versuch, len(delays)-1)]
                log_event("⚠️", f"HTTP {e} (Chunk {chunk_idx}) – warte {wait}s")
                time.sleep(wait)
            else:
                log_event("❌", f"LLM-Call fehlgeschlagen nach {retries} Versuchen")
        except Exception as e:
            if versuch < retries:
                wait = delays[min(versuch, len(delays)-1)]
                log_event("⚠️", f"{str(e)[:60]} – warte {wait}s")
                time.sleep(wait)
            else:
                log_event("❌", f"Unbekannter Fehler Chunk {chunk_idx}: {e}")

    return None, 0.0, 0.0


# ============================================================
# Analyse eines Targets mit einem Modell
# ============================================================

def analyze_target_with_model(
    ort: str,
    start_url: str,
    text_bulk: str,
    chunk_count: int,
    model_def: dict,
) -> dict:
    """
    Analysiert text_bulk mit dem angegebenen Modell.
    Gibt ein Ergebnis-Dict zurück, das später gespeichert wird.
    """
    model_id    = model_def["id"]
    log_event("🤖", f"{ort} | Modell: {model_id} ...")

    chunk_size = EVAL_CONFIG["chunk_size"]
    overlap    = EVAL_CONFIG["chunk_overlap"]
    workers    = EVAL_CONFIG["llm_parallel_workers"]
    chunks     = _make_chunks(text_bulk, chunk_size, overlap)

    alle_raw_outputs  = []
    alle_massnahmen   = []
    total_cost        = 0.0
    total_latency     = 0.0
    context_items     = []
    chunk_parse_stati = []

    for gruppe_start in range(0, len(chunks), workers):
        gruppe = list(enumerate(chunks[gruppe_start:gruppe_start + workers],
                                start=gruppe_start + 1))
        futures_map = {}
        with ThreadPoolExecutor(max_workers=min(workers, len(gruppe))) as executor:
            for chunk_idx, chunk_text in gruppe:
                ctx_hint = ""
                if context_items:
                    ctx_hint = (
                        "\nBEREITS IN VORHERIGEN CHUNKS GEFUNDENE MAẞNAHMEN "
                        "(zur Duplikatvermeidung):\n"
                        + "\n".join(context_items[-EVAL_CONFIG["context_window_size"]:])
                        + "\n"
                    )
                prompt = _build_eval_prompt(chunk_text, start_url, ctx_hint, chunk_idx)
                futures_map[executor.submit(
                    _call_llm, prompt, model_def, chunk_idx
                )] = chunk_idx

            chunk_results = {}
            for future in as_completed(futures_map):
                cidx = futures_map[future]
                try:
                    raw, cost, latency = future.result()
                    alle_raw_outputs.append(f"=== Chunk {cidx} ===\n{raw or '(keine Antwort)'}")
                    massnahmen, status = _parse_massnahmen(raw or "", start_url)
                    chunk_parse_stati.append({"chunk": cidx, "status": status,
                                              "count": len(massnahmen)})
                    chunk_results[cidx] = massnahmen
                    total_cost    += cost
                    total_latency += latency
                    log_event("✅", f"{model_id} Chunk {cidx}: "
                                   f"{len(massnahmen)} Maßnahmen, "
                                   f"Kosten: {cost:.8f} $, "
                                   f"Latenz: {latency:.1f}s")
                except Exception as e:
                    log_event("❌", f"{model_id} Chunk {cidx}: {e}")
                    chunk_results[cidx] = []
                    chunk_parse_stati.append({"chunk": cidx, "status": str(e), "count": 0})

        for chunk_idx, _ in gruppe:
            m = chunk_results.get(chunk_idx, [])
            alle_massnahmen.extend(m)
            for item in m:
                name  = item.get("massnahme", "")[:120]
                start = item.get("massnahme_start") or "unbekannt"
                context_items.append(f"- {name} (Start: {start})")

    # Deduplizierung
    seen, unique = set(), []
    for m in alle_massnahmen:
        key = (m.get("massnahme", "").strip().lower(), m.get("massnahme_start"))
        if key not in seen:
            seen.add(key)
            unique.append(m)

    return {
        "raw_output":       "\n\n".join(alle_raw_outputs),
        "massnahmen":       unique,
        "chunk_stati":      chunk_parse_stati,
        "total_cost":       round(total_cost, 8),
        "total_latency_s":  round(total_latency, 2),
        "chunks_processed": len(chunks),
    }


# ============================================================
# Output schreiben
# ============================================================

def write_outputs(ort: str, start_url: str, model_def: dict, result: dict,
                  run_ts: str):
    """Schreibt raw_response.txt, normalized.json und meta.json."""
    ort_slug = slugify(ort)
    mid      = model_def["id"]

    # --- raw_response.txt ---
    if EVAL_CONFIG["save_raw_response"]:
        path = output_path_for(ort_slug, mid, "raw_response.txt")
        save_file(path, result["raw_output"])

    # --- normalized.json ---
    if EVAL_CONFIG["save_normalized_json"]:
        normalized = {
            "ort":       ort,
            "url":       start_url,
            "modell":    mid,
            "timestamp": run_ts,
            "massnahmen": result["massnahmen"],
        }
        path = output_path_for(ort_slug, mid, "normalized.json")
        save_file(path, json.dumps(normalized, ensure_ascii=False, indent=2))

    # --- meta.json ---
    if EVAL_CONFIG["save_meta_json"]:
        meta = {
            "ort":              ort,
            "url":              start_url,
            "modell_id":        mid,
            "modell_display":   model_def["display"],
            "api":              model_def["api"],
            "timestamp":        run_ts,
            "prompt_version":   EVAL_CONFIG["prompt_version"],
            "chunks_processed": result["chunks_processed"],
            "funde_gesamt":     len(result["massnahmen"]),
            "total_cost_usd":   result["total_cost"],
            "total_latency_s":  result["total_latency_s"],
            "chunk_stati":      result["chunk_stati"],
        }
        path = output_path_for(ort_slug, mid, "meta.json")
        save_file(path, json.dumps(meta, ensure_ascii=False, indent=2))

    # --- flat summary file: <ort-slug>_<modell-id>.json ---
    flat_path = os.path.join(
        EVAL_CONFIG["output_dir"],
        f"{ort_slug}_{mid}.json"
    )
    flat = {
        "ort":            ort,
        "url":            start_url,
        "modell":         mid,
        "timestamp":      run_ts,
        "funde":          len(result["massnahmen"]),
        "kosten_usd":     result["total_cost"],
        "latenz_s":       result["total_latency_s"],
        "massnahmen":     result["massnahmen"],
    }
    save_file(flat_path, json.dumps(flat, ensure_ascii=False, indent=2))


# ============================================================
# Targets laden
# ============================================================

def _load_targets() -> list:
    """Lädt Targets aus manual_targets oder aus der DB (über force_ags / Standard)."""
    manual = EVAL_CONFIG.get("manual_targets", [])
    if manual:
        log_event("📋", f"{len(manual)} manuelle Target(s) konfiguriert (kein DB-Zugriff).")
        return [(t["ort"], t["url"]) for t in manual]

    # DB-Zugriff (identisch mit crawler_telekom.py Logik)
    try:
        from database import get_db_connection
        conn   = get_db_connection()
        cursor = conn.cursor()
        force_ags   = EVAL_CONFIG.get("force_ags") or []
        max_targets = EVAL_CONFIG["max_targets"]
        if force_ags:
            placeholders = ",".join(["%s"] * len(force_ags))
            cursor.execute(
                f"SELECT ort, url FROM crawl_targets WHERE ags IN ({placeholders})",
                tuple(force_ags)
            )
        else:
            cursor.execute(
                "SELECT ort, url FROM crawl_targets "
                "ORDER BY last_scanned ASC NULLS FIRST LIMIT %s",
                (max_targets,)
            )
        rows = cursor.fetchall()
        conn.close()
        log_event("🗄️", f"{len(rows)} Target(s) aus DB geladen.")
        return [(r[0], r[1]) for r in rows]
    except Exception as e:
        log_event("❌", f"DB-Zugriff fehlgeschlagen: {e}")
        log_event("ℹ️",  "Tipp: Setze EVAL_CONFIG['manual_targets'] für DB-freien Betrieb.")
        return []


# ============================================================
# Hauptloop
# ============================================================

def run_eval():
    run_ts         = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    enabled_models = [m for m in EVAL_MODELS if m.get("enabled", True)]
    targets        = _load_targets()
    summary        = []

    log_event("🚀", f"Eval-Crawler gestartet | "
                    f"{len(targets)} Target(s) | "
                    f"{len(enabled_models)} Modell(e): "
                    f"{[m['id'] for m in enabled_models]}")

    if not targets:
        log_event("⚠️", "Keine Targets. Abbruch.")
        return

    for ort, start_url in targets:
        log_event("🔍", f"Target: {ort} ({start_url})")

        # --- Scraping (einmal pro Target, für alle Modelle gleich) ---
        try:
            html_pages, pdf_pages, skipped_urls, status_log, _ = get_subpages(
                start_url, EVAL_CONFIG["max_subpages"]
            )
        except Exception as e:
            log_event("❌", f"Scraping fehlgeschlagen für {ort}: {e}")
            continue

        text_bulk, _, _ = assemble_text(
            ort, html_pages, pdf_pages, EVAL_CONFIG["max_text_chars"]
        )
        del html_pages, pdf_pages

        if not text_bulk.strip():
            log_event("⚠️", f"Kein Text für {ort} – übersprungen.")
            continue

        chunk_count = len(_make_chunks(
            text_bulk,
            EVAL_CONFIG["chunk_size"],
            EVAL_CONFIG["chunk_overlap"]
        ))
        log_event("📄", f"{ort}: {len(text_bulk):,} Zeichen, {chunk_count} Chunk(s)")

        # --- Pro Modell analysieren ---
        for model_def in enabled_models:
            try:
                result = analyze_target_with_model(
                    ort, start_url, text_bulk, chunk_count, model_def
                )
                write_outputs(ort, start_url, model_def, result, run_ts)
                summary.append({
                    "ort":         ort,
                    "modell":      model_def["id"],
                    "funde":       len(result["massnahmen"]),
                    "kosten_usd":  result["total_cost"],
                    "latenz_s":    result["total_latency_s"],
                    "timestamp":   run_ts,
                })
                time.sleep(EVAL_CONFIG["sleep_between_models"])
            except Exception as e:
                log_event("❌", f"{model_def['id']} | {ort}: {e}")
                summary.append({
                    "ort":    ort,
                    "modell": model_def["id"],
                    "fehler": str(e),
                })

        time.sleep(EVAL_CONFIG["sleep_between_targets"])

    # --- Gesamt-Summary speichern ---
    summary_path = os.path.join(
        EVAL_CONFIG["output_dir"],
        f"eval_summary_{run_ts.replace(':', '-')}.json"
    )
    ensure_dir(EVAL_CONFIG["output_dir"])
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    log_event("📊", f"Eval-Summary gespeichert: {summary_path}")

    # Kompakte Abschluss-Übersicht
    log_event("🏁", "Evaluation abgeschlossen. Ergebnisse:")
    for row in summary:
        if "fehler" in row:
            log_event("❌", f"  {row['ort']} | {row['modell']}: {row['fehler']}")
        else:
            log_event("✅", f"  {row['ort']} | {row['modell']}: "
                           f"{row['funde']} Funde | "
                           f"{row['kosten_usd']:.6f} $ | "
                           f"{row['latenz_s']:.1f}s")


if __name__ == "__main__":
    run_eval()
