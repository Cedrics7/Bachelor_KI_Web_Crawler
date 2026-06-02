"""
eval_config.py
==============
Konfiguration für den Multi-Modell-Evaluierungs-Crawler.

Kein DB-Schreibzugriff – alle Outputs werden als JSON/TXT-Dateien
unter output_eval/ gespeichert.

Ordnerstruktur:
    output_eval/
        <ort-slug>/
            <modell-id>/
                raw_response.txt      <- Rohantwort des Modells
                normalized.json       <- Geparste Maßnahmen
                meta.json             <- Metadaten (Timestamp, Kosten, Chunks, ...)
        <ort-slug>_<modell-id>.json   <- Schnell-Zusammenfassung (optional, flat)

Beispiel: output_eval/hamburg/gemini-2.5-pro/
"""

import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Modell-Definitionen
# ---------------------------------------------------------------------------
# Jeder Eintrag beschreibt ein Modell das evaluiert werden soll.
# "api"        : "telekom"  -> Telekom LLM-Proxy  (TELEKOM_LLM_API_KEY)
#                "google"   -> Google Gemini API   (GEMINI_API_KEY)
#                "ollama"   -> lokaler Ollama-Server
# "enabled"    : False -> Modell überspringen (ohne Zeile löschen)

EVAL_MODELS = [
    {
        "id":       "gemini-2.5-pro",
        "display":  "Gemini 2.5 Pro (Telekom)",
        "api":      "telekom",
        "model":    "gemini-2.5-pro",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  True,
    },
    {
        "id":       "gemini-2.5-flash",
        "display":  "Gemini 2.5 Flash (Telekom)",
        "api":      "telekom",
        "model":    "gemini-2.5-flash",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  True,
    },
    {
        "id":       "gemini-2.0-flash-lite",
        "display":  "Gemini 2.0 Flash-Lite (Telekom)",
        "api":      "telekom",
        "model":    "gemini-2.0-flash-lite",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  True,
    },
    {
        # Lokales Modell via Ollama – kein API-Key nötig
        "id":       "mistral-local",
        "display":  "Mistral 7B (Ollama lokal)",
        "api":      "ollama",
        "model":    "mistral",
        "base_url": "http://localhost:11434/v1",
        "enabled":  False,   # auf True setzen wenn Ollama läuft
    },
    {
        "id":       "llama3-local",
        "display":  "LLaMA 3 8B (Ollama lokal)",
        "api":      "ollama",
        "model":    "llama3",
        "base_url": "http://localhost:11434/v1",
        "enabled":  False,
    },
]

# ---------------------------------------------------------------------------
# Crawling-Parameter (übernommen aus config.py, ggf. anpassen)
# ---------------------------------------------------------------------------
EVAL_CONFIG = {
    # --- Ziel-Kommunen für die Evaluation ---
    # Leer = alle crawl_targets aus DB holen
    # Befüllen mit AGS-Nummern für reproduzierbare Testläufe
    "force_ags":               [],   # Beispiel: ["09162000", "05315000"]

    # Direkteingabe URL/Ort ohne DB (für schnelle Tests ohne DB-Zugriff)
    # Beispiel: [{"ort": "Hamburg", "url": "https://www.hamburg.de/infrastruktur"}]
    "manual_targets":          [],

    "max_targets":             3,    # wie viele Kommunen evaluiert werden
    "max_subpages":            30,
    "max_pdf_pages":           3,
    "timeout_seconds":         10,
    "sleep_between_targets":   2,    # Pause zwischen Targets (Sekunden)
    "sleep_between_models":    1,    # Pause zwischen Modell-Calls (Sekunden)
    "min_end_datum":           str(date.today()),

    # Chunking
    "chunk_size":              400_000,
    "chunk_overlap":           5_000,
    "max_text_chars":          5_000_000,

    # LLM-Parallelisierung (pro Modell)
    "llm_parallel_workers":    2,
    "context_window_size":     5,
    "llm_retries":             2,
    "llm_retry_delays":        [10, 30],
    "rpm_limit":               20,
    "tpm_limit":               800_000,
    "rpd_limit":               300,

    # --- Prompt-Version (für Nachvollziehbarkeit in Ergebnissen) ---
    "prompt_version":          "v1",

    # --- Output ---
    # True  = <ort-slug>/<modell-id>/... Ordner-Struktur
    # False = flache Dateien  <ort-slug>_<modell-id>.json
    "output_nested":           True,
    "output_dir":              "../output_eval",
    "save_raw_response":       True,   # raw_response.txt speichern
    "save_normalized_json":    True,   # normalized.json speichern
    "save_meta_json":          True,   # meta.json speichern

    # --- Kategorien (identisch mit Produktiv-Crawler) ---
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

# ---------------------------------------------------------------------------
# API-Keys
# ---------------------------------------------------------------------------
TELEKOM_API_KEY = os.getenv("TELEKOM_LLM_API_KEY") or os.getenv("GEMINI_API_KEY")
GOOGLE_API_KEY  = os.getenv("GEMINI_API_KEY")
OLLAMA_API_KEY  = "ollama"   # Ollama benötigt keinen echten Key, muss aber gesetzt sein


def get_api_key(model_def: dict) -> str:
    """Gibt den passenden API-Key für ein Modell zurück."""
    api = model_def.get("api", "telekom")
    if api == "telekom":
        if not TELEKOM_API_KEY:
            raise EnvironmentError(
                "Kein Telekom-API-Key gefunden. Setze TELEKOM_LLM_API_KEY in .env"
            )
        return TELEKOM_API_KEY
    if api == "google":
        if not GOOGLE_API_KEY:
            raise EnvironmentError(
                "Kein Google-API-Key gefunden. Setze GEMINI_API_KEY in .env"
            )
        return GOOGLE_API_KEY
    if api == "ollama":
        return OLLAMA_API_KEY
    raise ValueError(f"Unbekannter API-Typ: {api}")
