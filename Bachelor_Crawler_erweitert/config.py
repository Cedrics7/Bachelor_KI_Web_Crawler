"""
Zentrale Konfiguration für Bachelor_Crawler_erweitert.
Liest Werte aus der .env-Datei (Root-Verzeichnis) via python-dotenv.
Fallback auf DEFAULT_CONFIG-Werte, wenn kein .env vorhanden.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Dict, Any

try:
    from dotenv import load_dotenv
    # .env im Root-Verzeichnis des Projekts laden
    _env_path = Path(__file__).resolve().parent.parent / '.env'
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass  # python-dotenv optional, Fallback auf OS-Umgebungsvariablen


def _bool(val: str | None, default: bool = False) -> bool:
    if val is None:
        return default
    return val.strip().lower() in ('1', 'true', 'yes')


def _float(val: str | None, default: float) -> float:
    try:
        return float(val) if val is not None else default
    except ValueError:
        return default


def _int(val: str | None, default: int) -> int:
    try:
        return int(val) if val is not None else default
    except ValueError:
        return default


# ---------------------------------------------------------------
# Datenbankverbindung
# ---------------------------------------------------------------
DATABASE_URL: str = os.getenv('DATABASE_URL', 'sqlite:///./bachelor_crawler.db')

# ---------------------------------------------------------------
# LLM-Zugang
# ---------------------------------------------------------------
OPENAI_API_KEY: str | None = os.getenv('OPENAI_API_KEY')
OPENAI_BASE_URL: str = os.getenv('OPENAI_BASE_URL', 'https://api.openai.com/v1')
LLM_MODEL: str = os.getenv('LLM_MODEL', 'gpt-4o-mini')

# ---------------------------------------------------------------
# Crawler-Verhalten
# ---------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    'user_agent': os.getenv(
        'CRAWLER_USER_AGENT',
        'Mozilla/5.0 (BachelorCrawlerVollstaendig)'
    ),
    'timeout_seconds': _int(os.getenv('CRAWLER_TIMEOUT_SECONDS'), 12),
    'max_redirects': _int(os.getenv('CRAWLER_MAX_REDIRECTS'), 5),
    'crawl_delay_default': _float(os.getenv('CRAWLER_REQUEST_DELAY'), 1.0),
    'relevance_threshold': _float(os.getenv('CRAWLER_RELEVANCE_THRESHOLD'), 0.15),
    'priority_threshold': _float(os.getenv('CRAWLER_PRIORITY_THRESHOLD'), 0.10),
    'robots_respect': _bool(os.getenv('CRAWLER_ROBOTS_RESPECT'), True),
    'robots_timeout': _int(os.getenv('CRAWLER_ROBOTS_TIMEOUT'), 8),
    'privacy_filter_pii': _bool(os.getenv('CRAWLER_PRIVACY_FILTER_PII'), True),
    'js_rendering': _bool(os.getenv('CRAWLER_JS_RENDERING'), False),
    'js_min_chars': _int(os.getenv('CRAWLER_JS_MIN_CHARS'), 500),
    'js_timeout': _int(os.getenv('CRAWLER_JS_TIMEOUT'), 20),
    'js_wait_until': os.getenv('CRAWLER_JS_WAIT_UNTIL', 'networkidle'),
    'max_pages': _int(os.getenv('CRAWLER_MAX_PAGES'), 100),
    'max_queue': _int(os.getenv('CRAWLER_MAX_QUEUE'), 300),
    'vg_max_queue': _int(os.getenv('CRAWLER_VG_MAX_QUEUE'), 80),
    'ram_warn_mb': _int(os.getenv('CRAWLER_RAM_WARN_MB'), 1500),
    'log_dir': os.getenv('CRAWLER_LOG_DIR', 'logs'),
    # LLM-Analyse – aktivierbar per .env
    'llm_enabled': _bool(os.getenv('CRAWLER_LLM_ENABLED'), False),
    'llm_model': LLM_MODEL,
    'llm_max_tokens': _int(os.getenv('CRAWLER_LLM_MAX_TOKENS'), 512),
    'llm_temperature': _float(os.getenv('CRAWLER_LLM_TEMPERATURE'), 0.0),
    # Datenbankpersistierung
    'db_enabled': _bool(os.getenv('CRAWLER_DB_ENABLED'), False),
    'db_url': DATABASE_URL,
}
