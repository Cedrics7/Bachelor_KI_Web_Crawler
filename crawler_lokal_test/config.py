"""
config.py
=========
Zentrale Konfiguration für den Telekom-Crawler.
"""

import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    "heartbeat":               10,
    "max_log_lines":           200,
    "max_targets":             10,
    "max_subpages":            50,
    "max_pdf_pages":           5,
    "timeout_seconds":         10,
    "sleep_between_targets":   1,
    "min_end_datum":           str(date.today()),
    "min_pdf_year":            2024,
    "max_text_chars":          5_000_000,

    # Chunking
    "chunk_size":              400_000,   # Zeichen pro Chunk
    "chunk_overlap":           5_000,     # Kontext-Überlapp zum vorherigen Chunk

    "llm_parallel_workers":    4,
    "context_window_size":     5,
    "llm_model":               "claude-sonnet-4-6",
    "llm_base_url":            "https://llmapi.telekom.de/v1",
    "llm_retries":             3,
    "llm_retry_delays":        [10, 30, 60],
    "rpm_limit":               30,
    "tpm_limit":               1_000_000,
    "rpd_limit":               500,
    "prio_region":             "",

    # Scraper-Konstanten (ehemals hardcoded in scraper.py)
    "max_redirects":           5,         # Maximale Anzahl an Redirects pro Request
    "max_queue":               300,        # Maximale Größe der to_visit-Queue (Queue-Guard gegen OOM)
    "ram_warn_mb":             400,        # RAM-Warnschwelle in MB

    # HTTP-Header für alle Requests
    "http_headers": {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "de-DE,de;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
    },

    # Live-Status in der DB
    # Wenn kein Heartbeat innerhalb dieses Intervalls ankommt,
    # gilt der Crawler in crawler_status_view als 'inaktiv'.
    "heartbeat_timeout_seconds": 60,

    # Leer lassen [] für normale Crawl-Logik.
    # Beispiel: ["09162000", "05315000"]
    "force_ags":               ["09779188"],

    "ziel_kategorien": {
        "Sanierung":     ["Sanierungsgebiet", "Stadtsanierung", "Fördergebiet"],
        "Neubau":        ["Neubaugebiet", "Bebauungsplan", "B-Plan", "Erschließung"],
        "Privatisierung": ["Grundstücksverkauf", "Veräußerung", "Liegenschaften", "Entwidmung",],
        "Straßenbau":    [
            "Straßenbau", "Straßensanierung", "Fahrbahnerneuerung",
            "Kreisverkehr", "Gehweg", "Radweg", "Straßenausbau",
        ],
        "Brückenbau":    [
            "Brückenbau", "Brückensanierung", "Brückenneubau",
            "Brückeninstandsetzung", "Unterführung", "Düker",
        ],
        "Ausschreibung": [
            "Ausschreibung", "Vergabe", "Öffentliche Auftragsvergabe",
            "Submission", "VOB", "DTVP", "Bieterverfahren",
        ],
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
    "vergabe", "foerderung", "förderung", "sanierung",
    "strassenbau", "straßenbau", "brueckenbau", "brückenbau",
    "brueckensanierung", "brückensanierung", "leitungsbau",
]

CONSOLE_LOG_FILE = "../crawler_console.log"
SKIPPED_LOG_FILE = "../crawler_skipped_urls.log"
COST_LOG_FILE    = "../crawler_telekom_kosten.log"

TELEKOM_API_KEY = os.getenv("TELEKOM_LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
if not TELEKOM_API_KEY:
    raise EnvironmentError("Kein API-Key gefunden. Setze TELEKOM_LLM_API_KEY in .env")
