"""
Zentrale Konfiguration für Bachelor_Crawler_erweitert.
Kompatibel mit der .env aus crawler_js (DB_HOST, DB_NAME, DB_USER, DB_PASS, DB_PORT).
Fallback auf DATABASE_URL falls vorhanden, sonst SQLite.

ALLE Parameter werden hier zentral verwaltet - kein os.getenv() in anderen Modulen.
"""
from __future__ import annotations
import os
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# .env laden - mehrere Fallback-Pfade
# ---------------------------------------------------------------
def _load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.warning('python-dotenv nicht installiert. Bitte: pip install python-dotenv')
        return
    candidates = [
        Path(__file__).resolve().parent.parent / '.env',
        Path(__file__).resolve().parent / '.env',
        Path.cwd() / '.env',
        Path.cwd().parent / '.env',
    ]
    for candidate in candidates:
        if candidate.exists():
            load_dotenv(dotenv_path=candidate, override=True)
            logger.debug('Config: .env geladen von %s', candidate)
            return
    logger.warning(
        'Config: Keine .env gefunden. Gesuchte Pfade:\n%s',
        '\n'.join(f'  {c}' for c in candidates)
    )


_load_env()


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
# DATABASE_URL aufbauen:
# Priorität 1: DATABASE_URL direkt in .env
# Priorität 2: Einzelvariablen DB_HOST/DB_NAME/DB_USER/DB_PASS/DB_PORT (wie crawler_js)
# Fallback:    SQLite lokal
# ---------------------------------------------------------------
def _build_database_url() -> str:
    url = os.getenv('DATABASE_URL')
    if url and not url.startswith('sqlite'):
        return url
    host     = os.getenv('DB_HOST')
    name     = os.getenv('DB_NAME')
    user     = os.getenv('DB_USER')
    password = os.getenv('DB_PASS')
    port     = os.getenv('DB_PORT', '5432')
    if host and name and user and password:
        return f'postgresql://{user}:{password}@{host}:{port}/{name}'
    return url or 'sqlite:///./bachelor_crawler.db'


DATABASE_URL: str = _build_database_url()

# ---------------------------------------------------------------
# LLM-Zugang
# ---------------------------------------------------------------
OPENAI_API_KEY: str        = os.getenv('OPENAI_API_KEY')
OPENAI_BASE_URL: str       = os.getenv('OPENAI_BASE_URL', 'https://llmapi.telekom.de/v1')
LLM_MODEL: str             = os.getenv('LLM_MODEL', 'gpt-5.1')

# ---------------------------------------------------------------
# Crawler-Konfiguration (alle Parameter zentral hier)
# ---------------------------------------------------------------
DEFAULT_CONFIG: Dict[str, Any] = {
    # HTTP
    'user_agent':               os.getenv('CRAWLER_USER_AGENT', 'Mozilla/5.0 (BachelorCrawlerVollstaendig)'),
    'timeout_seconds':          _int(os.getenv('CRAWLER_TIMEOUT_SECONDS'), 12),
    'max_redirects':            _int(os.getenv('CRAWLER_MAX_REDIRECTS'), 5),
    'crawl_delay_default':      _float(os.getenv('CRAWLER_REQUEST_DELAY'), 1.0),

    # Relevanz
    'relevance_threshold':      _float(os.getenv('CRAWLER_RELEVANCE_THRESHOLD'), 0.15),
    'priority_threshold':       _float(os.getenv('CRAWLER_PRIORITY_THRESHOLD'), 0.10),

    # robots.txt
    'robots_respect':           _bool(os.getenv('CRAWLER_ROBOTS_RESPECT'), True),
    'robots_timeout':           _int(os.getenv('CRAWLER_ROBOTS_TIMEOUT'), 8),

    # DSGVO
    'privacy_filter_pii':       _bool(os.getenv('CRAWLER_PRIVACY_FILTER_PII'), True),

    # JS-Rendering
    'js_rendering':             _bool(os.getenv('CRAWLER_JS_RENDERING'), True),
    'js_min_chars':             _int(os.getenv('CRAWLER_JS_MIN_CHARS'), 500),
    'js_timeout':               _int(os.getenv('CRAWLER_JS_TIMEOUT'), 20),
    'js_wait_until':            os.getenv('CRAWLER_JS_WAIT_UNTIL', 'networkidle'),

    # Queue & Limits
    'max_pages':                _int(os.getenv('CRAWLER_MAX_PAGES'), 50),
    'max_queue':                _int(os.getenv('CRAWLER_MAX_QUEUE'), 300),
    'vg_max_queue':             _int(os.getenv('CRAWLER_VG_MAX_QUEUE'), 80),
    'ram_warn_mb':              _int(os.getenv('CRAWLER_RAM_WARN_MB'), 1500),

    # Multi-Target-Lauf (run_crawler.py)
    'max_targets':              _int(os.getenv('CRAWLER_MAX_TARGETS'), 1),     # 0 = alle
    'prio_region':              os.getenv('CRAWLER_PRIO_REGION', ''),          # z.B. 'Bayern'
    'sleep_between_targets':    _float(os.getenv('CRAWLER_SLEEP_BETWEEN_TARGETS'), 1.0),

    # Logging
    'log_dir':                  os.getenv('CRAWLER_LOG_DIR', 'logs'),

    # LLM
    'llm_enabled':              _bool(os.getenv('CRAWLER_LLM_ENABLED'), True),
    'llm_model':                LLM_MODEL,
    'llm_max_tokens':           _int(os.getenv('CRAWLER_LLM_MAX_TOKENS'), 400000),
    'llm_temperature':          _float(os.getenv('CRAWLER_LLM_TEMPERATURE'), 0.0),

    # Datenbank
    'db_enabled':               _bool(os.getenv('CRAWLER_DB_ENABLED'), True),
    'db_url':                   DATABASE_URL,
}

# ---------------------------------------------------------------
# Startup-Log
# ---------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)

_db_log = DATABASE_URL
if '@' in _db_log:
    try:
        scheme, rest = _db_log.split('://', 1)
        userinfo, hostpart = rest.split('@', 1)
        _db_log = f'{scheme}://{userinfo.split(":")[0]}:***@{hostpart}'
    except Exception:
        _db_log = '(konnte nicht maskiert werden)'

logger.info('=== Crawler Config geladen ===')
logger.info('  DATABASE_URL         : %s', _db_log)
logger.info('  db_enabled           : %s', DEFAULT_CONFIG['db_enabled'])
logger.info('  llm_enabled          : %s', DEFAULT_CONFIG['llm_enabled'])
logger.info('  max_pages            : %s', DEFAULT_CONFIG['max_pages'])
logger.info('  max_targets          : %s (0=alle)', DEFAULT_CONFIG['max_targets'])
logger.info('  prio_region          : %s', DEFAULT_CONFIG['prio_region'] or '(keine)')
logger.info('  sleep_between_targets: %ss', DEFAULT_CONFIG['sleep_between_targets'])
logger.info('  js_rendering         : %s', DEFAULT_CONFIG['js_rendering'])
