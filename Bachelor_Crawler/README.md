# Bachelor_Crawler

> **Aufbauend auf `crawler_js` (v2.2)** – Erweitert um robots.txt-Compliance und DSGVO-konforme Datenschutzfilterung.

## Übersicht

Der `Bachelor_Crawler` ist die finale Crawler-Implementierung für die Bachelorthesis. Er übernimmt **alle Funktionen** des `crawler_js`-Moduls und ergänzt sie um zwei zentrale Komponenten:

| Modul | Funktion |
|---|---|
| `robots_checker.py` | robots.txt laden, cachen, Crawl-Delay einhalten |
| `privacy_guard.py` | PII filtern, sensitive URLs erkennen, DSGVO-Logging |
| `scraper_bachelor.py` | Haupt-Crawler (baut auf `scraper_js.py` auf) |
| `config_bachelor.py` | Konfiguration (erbt von `config_js.py`) |

## Neue Features gegenüber crawler_js

### robots.txt-Compliance (RFC 9309)
- Jede Domain wird **einmalig** über `GET /robots.txt` abgefragt
- Ergebnis wird **gecacht** (max. 500 Domains, kein wiederholter Download)
- `Crawl-Delay`-Direktiven werden automatisch eingehalten
- Bei HTTP 404 (keine robots.txt): **alles erlaubt** (RFC-konform)
- Bei Ladefehler: **fail-open** (konfigurierbar über `robots_fail_open`)
- Gesperrte URLs erscheinen im `status_log` als `ROBOTS_DISALLOWED`

### DSGVO-Datenschutz (Art. 5, 6, 25 DSGVO)
- **PII-Filterung**: E-Mail-Adressen, Telefonnummern, IBANs und Sozialversicherungsnummern werden aus gecrawltem Text **vor dem Speichern** entfernt
- **Sensitive URLs**: Login-, Formular-, Bewerbungs- und Auth-Seiten werden automatisch übersprungen
- **Datenschutz-Summary**: Nach jedem Crawl-Lauf wird die Anzahl entfernter PII-Einträge geloggt
- **Rechtsgrundlage**: Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse bei öffentlich zugänglichen Behördenseiten)

### Beibehaltene crawler_js-Funktionen
- ✅ JavaScript-Rendering via Playwright (v2.0)
- ✅ Verwaltungsgemeinschaft-Redirect-Support (v2.1)
- ✅ Browser-User-Agent für httpx – kein 503/403-Blocking (v2.2)
- ✅ Alle Hilfsfunktionen aus `scraper.py` (über Import-Kette)
- ✅ RAM-Monitoring
- ✅ Logger (`logger.py`)
- ✅ Rate-Limiter (`rate_limiter.py`)

## Konfiguration

Alle Einstellungen in `config_bachelor.py`:

```python
# robots.txt
CONFIG["robots_respect"]      = True          # robots.txt einhalten
CONFIG["robots_user_agent"]   = "BachelorCrawler"  # Identifikation
CONFIG["robots_timeout"]      = 10            # Timeout in Sekunden
CONFIG["robots_fail_open"]    = True          # Bei Fehler crawlen

# DSGVO
CONFIG["privacy_filter_pii"]         = True   # PII entfernen
CONFIG["privacy_skip_sensitive_urls"] = True  # Login/Formulare überspringen
CONFIG["privacy_log_removals"]        = True  # Entfernungen loggen

# Rate-Limiting
CONFIG["crawl_delay_default"] = 1.0    # Fallback-Delay (s)
CONFIG["crawl_delay_max"]     = 10.0   # Max. robots.txt-Delay (s)
```

## Verwendung

```python
from Alt.Bachelor_Crawler import get_subpages

html_collected, pdf_collected, skipped_urls, status_log, page_hashes =
    get_subpages("https://www.musterstadt.de", max_pages=100)
```

## Dateistruktur

```
Bachelor_Crawler/
├── __init__.py            # Exports
├── scraper_bachelor.py    # Haupt-Crawler (Erweiterung von scraper_js)
├── robots_checker.py      # robots.txt-Compliance
├── privacy_guard.py       # DSGVO-Datenschutzfilter
├── config_bachelor.py     # Konfiguration (erbt von config_js)
└── README.md
```

## DSGVO-Referenzen

| Artikel | Umsetzung |
|---|---|
| Art. 5 Abs. 1 lit. b – Zweckbindung | Sensitive URLs (Login, Formulare) werden nicht gecrawlt |
| Art. 5 Abs. 1 lit. c – Datensparsamkeit | PII wird vor dem Speichern entfernt |
| Art. 6 Abs. 1 lit. f – Berechtigtes Interesse | Crawler-Zweck dokumentiert in CONFIG |
| Art. 25 – Privacy by Design | Filter sind standardmäßig aktiviert |
| RFC 9309 – robots.txt | Vollständige robots.txt-Compliance |
