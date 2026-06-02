"""
config_js.py
============
Konfiguration für den JS-fähigen Crawler (crawler_js).

Erbt alle Einstellungen aus dem originalen config.py und erweitert
diese um JS-Rendering- und VG-Redirect-Parameter.
"""

import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    # -------------------------------------------------------------------------
    # Basis-Einstellungen (identisch zu config.py)
    # -------------------------------------------------------------------------
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

    "chunk_size":              400_000,
    "chunk_overlap":           5_000,

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
    "force_ags":               [],

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

    # -------------------------------------------------------------------------
    # NEU v2.2: HTTP User-Agent für httpx-Requests
    # -------------------------------------------------------------------------
    # "BachelorCrawler/1.0" wird von TYPO3- und Apache-Proxies mit 503/403
    # blockiert. Ein echter Chrome-UA umgeht diese Blocking-Regeln.
    # Betrifft: Munningen (TYPO3-Redirect), Oberottmarshausen (Apache 403)
    # und generell alle Kommunal-Sites mit UA-basiertem Bot-Blocking.
    "http_user_agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),

    # -------------------------------------------------------------------------
    # NEU v2.1: VG-Redirect-Einstellungen
    # -------------------------------------------------------------------------
    # Queue-Limit wenn der Crawler einem VG-Redirect folgt.
    # Niedrigerer Wert als _MAX_QUEUE (300) verhindert, dass der Crawler
    # alle anderen Mitgliedsgemeinden der VG-Seite mitkrawlt.
    "vg_max_queue":    80,

    # -------------------------------------------------------------------------
    # NEU v2.0: JS-Rendering-Einstellungen
    # -------------------------------------------------------------------------
    # Haupt-Schalter: False = reines httpx (wie original), True = Playwright-Fallback
    "js_rendering":    False,

    # Minimale Zeichenzahl im Response-Body, unter der JS-Rendering ausgelöst wird.
    "js_min_chars":    500,

    # Playwright page.goto() Timeout in Sekunden
    "js_timeout":      20,

    # Playwright wait_until:
    #   "networkidle"      → sicherste Option, langsamer bei Tracking-Heavy-Sites
    #   "domcontentloaded" → schneller, reicht für die meisten SPAs
    "js_wait_until":   "networkidle",

    # User-Agent für Playwright (imitiert echten Chrome)
    # Wenn nicht gesetzt, wird http_user_agent als Fallback verwendet.
    "js_user_agent":   (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
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
