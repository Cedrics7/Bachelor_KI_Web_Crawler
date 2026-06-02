# crawler_js – JS-fähiger Crawler

Dieses Modul erweitert den originalen `crawler/` um **optionales JavaScript-Rendering** via [Playwright](https://playwright.dev/python/).

## Struktur

```
crawler_js/
├── config_js.py        # Konfiguration (erweitert config.py um JS-Parameter)
├── scraper_js.py       # Neues scraper-Modul mit Playwright-Fallback
├── __init__.py
├── README.md
│
│   ── Aus crawler/ kopieren (unverändert) ──
├── crawler_telekom.py  # Nur Import-Pfade anpassen (siehe unten)
├── llm_client.py
├── logger.py
├── database.py
└── rate_limiter.py
```

## Setup

```bash
# Playwright installieren
pip install playwright
playwright install chromium

# Alternativ nur Chromium-Abhängigkeiten (Ubuntu/Debian)
playwright install-deps chromium
```

## JS-Rendering aktivieren

In `config_js.py`:

```python
"js_rendering": True   # Standard: False
```

Oder gezielt für bestimmte Targets über die DB ohne Code-Änderung:
```python
"force_ags": ["09162000"],  # Nur diese AGS mit JS-Rendering testen
"js_rendering": True,
```

## Notwendige Änderungen in kopierten Dateien

Nach dem Kopieren der übrigen Dateien aus `crawler/` müssen folgende
**Import-Zeilen** in `crawler_telekom.py` angepasst werden:

```python
# ALT (oben in crawler_telekom.py)
from config import CONFIG, CONSOLE_LOG_FILE, SKIPPED_LOG_FILE
from scraper import get_subpages, assemble_text, get_content_hash

# NEU
from config_js import CONFIG, CONSOLE_LOG_FILE, SKIPPED_LOG_FILE
from scraper_js import get_subpages, assemble_text, get_content_hash
```

Alle anderen Dateien (`llm_client.py`, `logger.py`, `database.py`, `rate_limiter.py`)
können 1:1 kopiert werden – keine weiteren Änderungen nötig.

## Wie der JS-Fallback funktioniert

```
Für jede URL:
  1. httpx-Request (schnell, ~0.5s)
  2. Seite JS-rendered? (_is_js_rendered prüft Textlänge + SPA-Marker)
     → Nein: normaler Pfad wie bisher
     → Ja:   Playwright-Fallback (~3-10s)
              Chromium lädt Seite, wartet auf networkidle
              Bilder/Fonts/Media werden geblockt (RAM-Ersparnis)
              Wenn gerenderte Version länger → ersetze raw_html
  3. extract_main_text(raw_html) – unverändert
```

## Performance-Erwartung

| Modus | Ø Zeit/Seite | RAM |
|---|---|---|  
| `js_rendering: False` | ~0.5s | minimal |
| `js_rendering: True` (wenige JS-Seiten) | ~0.7s | +150 MB (Chromium) |
| `js_rendering: True` (viele JS-Seiten) | ~3-10s | +150-300 MB |

## Hinweis für die Bachelor-Thesis

Da die meisten deutschen Kommunal-Websites serverseitiges CMS (Typo3, Civento) nutzen,
wird `js_rendering` selten aktiv. Das Modul kann in der Thesis als
**optionale Erweiterungskomponente** dokumentiert werden – aktiviert per Konfigurationsschalter,
ohne den stabilen Basis-Crawler zu verändern.
