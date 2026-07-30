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
        <ort-slug>_<modell-id>.json   <- Schnell-Zusammenfassung (flat)

Beispiel: output_eval/hamburg/gemini-2.5-pro/

Modell-Gruppen (für die qualitative Analyse):
    Gruppe A – Gemini-Familie (Qualitätsstufen):
        gemini-2.5-pro, gemini-2.5-flash, gemini-2.5-flash-lite,
        gemini-3.1-flash-lite, gemini-3.5-flash

    Gruppe B – OpenAI-Familie:
        gpt-4.1, gpt-5.1, gpt-5-mini, gpt-5-nano, o4-mini

    Gruppe C – Anthropic-Familie:
        claude-sonnet-4-5, claude-haiku-4-5, claude-sonnet-4-6

    Gruppe D – Mistral:
        mistral-large-3

    Gruppe E – Ollama lokal (optional, kein API-Key):
        mistral, llama3

Hinweis: Modelle mit Prefix "WARN-GLOBAL_" (gemini-3-*-preview,
deepseek-*, kimi-*, glm-*, gpt-5.3/5.4, gpt-oss-*) sind auf der
Telekom-Plattform mit einem Warnlabel versehen und werden
für die Evaluation nicht verwendet.
"""

import os
from datetime import date
from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Modell-Definitionen
# ---------------------------------------------------------------------------
# "api"     : "telekom" -> Telekom LLM-Proxy  (TELEKOM_LLM_API_KEY)
#             "ollama"  -> lokaler Ollama-Server (kein Key nötig)
# "enabled" : False -> Modell überspringen (ohne Zeile löschen)
# "group"   : Anbieter-Gruppe für spätere Auswertung

EVAL_MODELS = [

    # ── Gruppe A: Gemini-Familie ───────────────────────────────────────────
    {
        "id":       "gemini-2.5-pro",
        "display":  "Gemini 2.5 Pro",
        "group":    "A_Gemini",
        "api":      "telekom",
        "model":    "gemini-2.5-pro",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        "id":       "gemini-2.5-flash",
        "display":  "Gemini 2.5 Flash",
        "group":    "A_Gemini",
        "api":      "telekom",
        "model":    "gemini-2.5-flash",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        "id":       "gemini-2.5-flash-lite",
        "display":  "Gemini 2.5 Flash-Lite",
        "group":    "A_Gemini",
        "api":      "telekom",
        "model":    "gemini-2.5-flash-lite",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        # Neue Generation: Vergleich 2.x vs. 3.x
        "id":       "gemini-3.1-flash-lite",
        "display":  "Gemini 3.1 Flash-Lite",
        "group":    "A_Gemini",
        "api":      "telekom",
        "model":    "gemini-3.1-flash-lite",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        "id":       "gemini-3.5-flash",
        "display":  "Gemini 3.5 Flash",
        "group":    "A_Gemini",
        "api":      "telekom",
        "model":    "gemini-3.5-flash",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },

    # ── Gruppe B: OpenAI-Familie ───────────────────────────────────────────
    {
        "id":       "gpt-4.1",
        "display":  "GPT-4.1",
        "group":    "B_OpenAI",
        "api":      "telekom",
        "model":    "gpt-4.1",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        "id":       "gpt-5.1",
        "display":  "GPT-5.1",
        "group":    "B_OpenAI",
        "api":      "telekom",
        "model":    "gpt-5.1",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        "id":       "gpt-5-mini",
        "display":  "GPT-5 Mini",
        "group":    "B_OpenAI",
        "api":      "telekom",
        "model":    "gpt-5-mini",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        "id":       "gpt-5-nano",
        "display":  "GPT-5 Nano",
        "group":    "B_OpenAI",
        "api":      "telekom",
        "model":    "gpt-5-nano",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        # Reasoning-Modell – langsamer, aber interessant für strukturierte Extraktion
        "id":       "o4-mini",
        "display":  "o4-mini (Reasoning)",
        "group":    "B_OpenAI",
        "api":      "telekom",
        "model":    "o4-mini",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },

    # ── Gruppe C: Anthropic / Claude ──────────────────────────────────────
    {
        "id":       "claude-sonnet-4-5",
        "display":  "Claude Sonnet 4.5",
        "group":    "C_Anthropic",
        "api":      "telekom",
        "model":    "claude-sonnet-4-5@20250929",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        "id":       "claude-haiku-4-5",
        "display":  "Claude Haiku 4.5",
        "group":    "C_Anthropic",
        "api":      "telekom",
        "model":    "claude-haiku-4-5@20251001",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },
    {
        "id":       "claude-sonnet-4-6",
        "display":  "Claude Sonnet 4.6",
        "group":    "C_Anthropic",
        "api":      "telekom",
        "model":    "claude-sonnet-4-6",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },

    # ── Gruppe D: Mistral ─────────────────────────────────────────────────
    {
        "id":       "mistral-large-3",
        "display":  "Mistral Large 3",
        "group":    "D_Mistral",
        "api":      "telekom",
        "model":    "mistral-large-3",
        "base_url": "https://llmapi.telekom.de/v1",
        "enabled":  False,
    },

    # ── Gruppe E: Ollama lokal (optional) ─────────────────────────────────
    {
        "id":       "gemma3_4b",
        "display":  "Gemma 3 4B (Ollama lokal)",
        "group":    "E_Lokal",
        "api":      "ollama",
        "model":    "gemma3:4b",
        "base_url": "http://localhost:11434/v1",
        "enabled":  True,   # auf True setzen wenn Ollama läuft
    },
    {
        "id":       "llama3-local",
        "display":  "LLaMA 3 8B (Ollama lokal)",
        "group":    "E_Lokal",
        "api":      "ollama",
        "model":    "llama3",
        "base_url": "http://localhost:11434/v1",
        "enabled":  False,
    },
]

# ---------------------------------------------------------------------------
# Crawling-Parameter
# ---------------------------------------------------------------------------
EVAL_CONFIG = {
    # --- Ziel-Kommunen ---
    # Leer = alle crawl_targets aus DB (bis max_targets)
    # AGS-Liste für reproduzierbare Testläufe empfohlen
    "force_ags":               [],   # z.B. ["09162000", "05315000"]

    # Direkteingabe ohne DB:
    # [{"ort": "Hamburg", "url": "https://www.hamburg.de/infrastruktur"}]
    "manual_targets":          [{"ort": "Hamburg", "url": "https://www.hamburg.de"}],

    "max_targets":             3,
    "max_subpages":            50,
    "max_pdf_pages":           5,
    "timeout_seconds":         10,
    "sleep_between_targets":   2,
    "sleep_between_models":    1,
    "min_end_datum":           str(date.today()),

    # Chunking
    "chunk_size":              5_000,
    "chunk_overlap":           5_000,
    "max_text_chars":          5_000_000,

    # LLM
    "llm_parallel_workers":    2,
    "context_window_size":     5,
    "llm_retries":             2,
    "llm_retry_delays":        [10, 30],
    "rpm_limit":               20,
    "tpm_limit":               800_000,
    "rpd_limit":               300,

    # Prompt-Version (für Nachvollziehbarkeit in Thesis)
    "prompt_version":          "v1",

    # Output
    "output_nested":           True,
    "output_dir":              "../output_eval",
    "save_raw_response":       True,
    "save_normalized_json":    True,
    "save_meta_json":          True,

    # Kategorien (identisch mit Produktiv-Crawler)
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
OLLAMA_API_KEY  = "ollama"


def get_api_key(model_def: dict) -> str:
    """Gibt den passenden API-Key für ein Modell zurück."""
    api = model_def.get("api", "telekom")
    if api == "telekom":
        if not TELEKOM_API_KEY:
            raise EnvironmentError(
                "Kein Telekom-API-Key gefunden. Setze TELEKOM_LLM_API_KEY in .env"
            )
        return TELEKOM_API_KEY
    if api == "ollama":
        return OLLAMA_API_KEY
    raise ValueError(f"Unbekannter API-Typ: {api}")
