"""
config_bachelor.py
==================
Konfigurationsdatei für den Bachelor_Crawler.

Baut auf config_js.py (crawler_js) auf und erweitert sie um:
    - robots.txt-Einstellungen
    - DSGVO-Datenschutz-Einstellungen
    - Bachelor-spezifische Parameter
"""

import sys
import os

# Bestehende CONFIG aus crawler_js als Basis importieren
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "crawler_js"))
try:
    from config_js import CONFIG as _BASE_CONFIG, IGNORIERE_PARAMS
except ImportError:
    _BASE_CONFIG = {}
    IGNORIERE_PARAMS = set()

# Bachelor_Crawler CONFIG erbt alle Werte aus crawler_js und überschreibt/erweitert
CONFIG: dict = {
    **_BASE_CONFIG,

    # ------------------------------------------------------------------
    # robots.txt-Einstellungen (NEU)
    # ------------------------------------------------------------------
    "robots_respect":      True,        # robots.txt zwingend einhalten
    "robots_timeout":      10,          # Timeout für robots.txt-Download (s)
    "robots_fail_open":    True,        # Bei Ladefehler crawlen (True) oder sperren (False)
    "robots_user_agent":   "BachelorCrawler",  # Identifikation in robots.txt
    # Hinweis: robots.txt wird nach RFC 9309 (Sept. 2022) ausgewertet

    # ------------------------------------------------------------------
    # DSGVO / Datenschutz-Einstellungen (NEU)
    # ------------------------------------------------------------------
    "privacy_filter_pii":         True,  # PII aus gecrawltem Text entfernen
    "privacy_skip_sensitive_urls": True, # Sensitive URLs (Login, Formulare) überspringen
    "privacy_log_removals":        True,  # PII-Entfernungen loggen (ohne Inhalt)
    "privacy_crawl_purpose":       "Bachelorthesis – Analyse kommunaler KI-Bekanntmachungen",
    # Rechtliche Grundlage nach Art. 6 Abs. 1 lit. f DSGVO:
    # Berechtigtes Interesse an der Analyse öffentlich zugänglicher Behördendaten
    "privacy_legal_basis":         "Art. 6 Abs. 1 lit. f DSGVO – berechtigtes Interesse",

    # ------------------------------------------------------------------
    # Rate-Limiting (verstärkt gegenüber crawler_js)
    # ------------------------------------------------------------------
    "crawl_delay_default":  1.0,   # Standard-Delay wenn robots.txt keinen vorgibt (s)
    "crawl_delay_max":     10.0,   # Maximaler respektierter robots.txt Crawl-Delay (s)

    # ------------------------------------------------------------------
    # Bachelor_Crawler Identifikation
    # ------------------------------------------------------------------
    "crawler_name":     "Bachelor_Crawler",
    "crawler_version":  "1.0",
    "crawler_contact":  "Bachelorthesis – Cedric – DSGVO-konformer Web-Crawler",
}

__all__ = ["CONFIG", "IGNORIERE_PARAMS"]
