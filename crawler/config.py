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
    "max_targets":             1,
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
    "llm_model":               "gemini-2.5-pro",
    "llm_base_url":            "https://llmapi.telekom.de/v1",
    "llm_retries":             3,
    "llm_retry_delays":        [10, 30, 60],
    "rpm_limit":               30,
    "tpm_limit":               1_000_000,
    "rpd_limit":               500,
    "prio_region":             "",

    # Leer lassen [] für normale Crawl-Logik.
    # Beispiel: ["09162000", "05315000"]
    "force_ags":               ["03453001"],

    "ziel_kategorien": {
        "Sanierung":     ["Sanierungsgebiet", "Stadtsanierung", "Fördergebiet"],
        "Neubau":        ["Neubaugebiet", "Bebauungsplan", "B-Plan", "Erschließung"],
        "Privatisierung": ["Grundstücksverkauf", "Veräußerung", "Liegenschaften"],
        "Straßenbau":    [
            "Straßenbau", "Straßensanierung", "Fahrbahnerneuerung",
            "Kreisverkehr", "Gehweg", "Radweg", "Straßenausbau",
        ],
        "Brückenbau":    [
            "Brückenbau", "Brückensanierung", "Brückenneubau",
            "Brückeninstandsetzung", "Unterführung",
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
