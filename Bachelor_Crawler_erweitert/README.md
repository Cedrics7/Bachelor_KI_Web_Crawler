# Bachelor Crawler – Vollstaendige Version

## Status Quo: Focused Crawler (28.07.2026)

### Zusammenfassung

Dieses Repository enthaelt den vollstaendig kombinierten Focused Crawler fuer die Bachelorthesis. Er vereint alle funktionalen Komponenten aus den vier Evolutionsstufen des Projekts in einem einzigen, eigenstaendigen Paket.

---

## Crawler-Evolution im Projekt

Das Projekt durchlief vier klar unterscheidbare Generationen:

| Version | Verzeichnis | Hauptmerkmale |
|---------|-------------|---------------|
| **v1** | `crawler/` | Basis-Crawler mit HTML/PDF-Extraktion, LLM-Analyse, einfache Queue-Heuristik |
| **v2** | `crawler_js/` | JavaScript-Rendering via Playwright, VG-Redirect-Erkennung, Regex-PDF-Scan |
| **v3** | `Bachelor_Crawler/` | robots.txt-Compliance, DSGVO-PII-Filter (PrivacyGuard), URL-Deduplizierung, RAM-Monitoring |
| **v4** | `focused_crawler/` | Wissenschaftlicher Focused Crawler: Relevanzklassifikation (TF-IDF+BCW), CPE-Linkpriorisierung, Evaluation (Harvest Rate, F1, Baseline) |

---

## Warum diese Kombination?

Die Analyse aller vier Crawler zeigte:

### `focused_crawler/` (v4) – Wissenschaftlicher Kern ✅
- **Relevanzklassifikation**: Ensemble aus TF-IDF und Bayesschem Naive-Bayes (BCW), dokumentierter Score ∈ [0.0, 1.0], Kategorie-Klassifikation
- **CPE-Linkpriorisierung**: Comprehensive Priority Evaluation nach Liu et al. (2025) mit vier gewichteten Teilscores (Ankertext 40%, Linkkontext 25%, Seiteninhalt 20%, URL-Pattern 15%)
- **Evaluation**: Harvest Rate, Precision, Recall, F1-Score, Baseline-Vergleich (BFS), JSON-Export
- **Step-Logging**: Strukturiertes Logging aller Crawler-Ereignisse (FETCH, RELEVANCE, CPE, ROBOTS, EVALUATION, …)

### `Bachelor_Crawler/` (v3) – Infrastruktur & Compliance ✅
- **PrivacyGuard**: DSGVO-konformer PII-Filter mit 4 Typen (E-Mail, Telefon, IBAN, **Sozialversicherungsnummer**), `is_sensitive_url()`, `sanitize_metadata()`, DSGVO-Artikel-Referenzen
- **RobotsChecker**: Vollstaendige robots.txt-Compliance mit Crawl-Delay-Enforcement
- **get_url_base()**: Deduplizierung ohne Query-Parameter (verhindert Duplikate durch `?page=1`, `?print=1`, etc.)

### `crawler_js/` (v2) – Netzwerk-Features ✅
- **Playwright JS-Rendering**: Fallback für SPA-basierte Seiten mit automatischer Erkennung
- **VG-Redirect-Erkennung**: Akzeptiert Verbandsgemeinde-Redirects mit kontrolliertem `effective_start_path`-Guard
- **Regex-PDF-Scan**: Findet PDFs auch ohne `<a>`-Tags im HTML
- **RAM-Monitoring**: Speicherverbrauchskontrolle via `psutil`
- **Browser-like User-Agent**: Verhindert 503/403-Blocking bei TYPO3/Apache

### `crawler/` (v1) – LLM-Analyse ⚠️
- **LLMClient**: LLM-basierte Dokumentenanalyse und Strukturierung (aktuell in v3/v4 nicht aktiv)

---

## Fehlende Features im `focused_crawler/` (v4)

Vor der Kombination fehlten im wissenschaftlichen Crawler:

1. **Kein JS-Rendering** – SPA-Seiten wurden als leer/minimal gecrawlt
2. **Keine VG-Redirect-Unterstuetzung** – Gemeinden mit VG-Weiterleitung wurden komplett uebersprungen
3. **Nur 3 PII-Typen** – Sozialversicherungsnummern fehlten
4. **Keine `is_sensitive_url()`-Pruefung** – Login/Profil/Formulare wurden mitgecrawlt
5. **Nur `visited_urls`-Set** – Duplikate durch Query-Parameter moeglich
6. **Kein RAM-Monitoring** – kein Schutz vor Memory-Blowup
7. **Kein Regex-PDF-Scan** – nur explizite `<a>`-Tags wurden gefunden

---

## Loesung: Vollstaendig kombinierter Crawler

Dieses Paket integriert alle上述 Komponenten in einem einzigen, eigenstaendigen Modul ohne externe Abhaengigkeiten.

### Architektur

```
Bachelor_Crawler_vollstaendig/
├── focused_crawler.py          ← Haupt-Crawler (v4-Basis)
├── relevance_classifier.py     ← Relevanzklassifikation (TF-IDF+BCW)
├── link_prioritizer.py         ← CPE-Linkpriorisierung
├── evaluation.py               ← Evaluation (Harvest Rate, F1, Baseline)
├── domain_model.py             ← Domaien-spezifisches Keyword-Modell
├── crawler_logger.py           ← Strukturiertes Step-Logging
│
├── privacy_guard.py            ← DSGVO-PII-Filter (4 Typen + is_sensitive_url)
├── robots_checker.py           ← robots.txt-Compliance
│
├── scraper_js.py               ← Playwright JS-Rendering, VG-Redirect, Regex-PDF
├── config_js.py                ← Konfiguration
├── logger.py                   ← Logging-Utilities
│
├── llm_client.py               ← LLM-Analyse (optional aktivierbar)
│
├── tests/
│   └── test_crawler.py         ← Integrationstests
├── run_crawler.py              ← Haupt-Entry-Point
├── requirements.txt            ← Python-Abhaengigkeiten
└── README.md                   ← Diese Datei
```

---

## Implementierte Features

### Crawler-Kern (focused_crawler.py)

- **Relevanzklassifikation**: Jede Seite erhaelt einen dokumentierten Score (0.0–1.0) mit Kategorie, Keywords und Confidence
- **CPE-Linkpriorisierung**: Jeder Link wird mit 4 Teilscores bewertet (Ankertext, Kontext, URL, Seiteninhalt)
- **Content-Block-Segmentierung**: Nur relevante Content-Blocke (Score > 0.05) werden extrahiert
- **PDF-Extraktion**: Vollstaendige Textextraktion via `pdfminer`
- **DSGVO-PII-Filter**: 4 PII-Typen (E-Mail, Telefon, IBAN, SVN) mit vollstaendigem Logging
- **Sensitive-URL-Pruefung**: Login/Profil/Formulare/Datenschutzseiten werden automatisch uebersprungen
- **robots.txt-Compliance**: Vollstaendige Compliance mit Crawl-Delay-Enforcement
- **JS-Rendering-Fallback**: Playwright-Chromium fuer SPA-Seiten (optional)
- **VG-Redirect-Erkennung**: Akzeptiert Verbandsgemeinde-Redirects mit kontrolliertem Guard
- **Regex-PDF-Scan**: Findet PDFs auch ohne explizite `<a>`-Tags
- **RAM-Monitoring**: Warnung bei Ueberschreitung von 1500 MB
- **URL-Deduplizierung**: Ohne Query-Parameter (verhindert Duplikate)
- **Strukturiertes Logging**: Alle Schritte (FETCH, RELEVANCE, CPE, ROBOTS, EVALUATION) werden protokolliert

### Evaluation

- **Harvest Rate**: Anteil relevanter Seiten an allen gecrawlten Seiten
- **Precision**: Identisch mit Harvest Rate beim Focused Crawling
- **Recall**: Anteil gefundener relevanter Seiten (bei bekanntem Referenzkorpus)
- **F1-Score**: Harmonisches Mittel aus Precision und Recall
- **Irrelevance Ratio**: Anteil irrelevanter Seiten (1 − HR)
- **Baseline-Vergleich**: Vergleich mit BFS-Baseline (zufaellige Reihenfolge)
- **JSON-Export**: Vollstaendiger Bericht als JSON fuer Thesis-Dokumentation

---

## Wissenschaftliche Einordnung

### Focused Crawling nach Liu et al. (2025)

Dieser Crawler implementiert die in der Literatur geforderten Komponenten eines Focused Crawlers:

1. **Seed Selection**: Start-URL(s) als Einstiegspunkt
2. **Topic Filter**: Relevanzklassifikation auf Seitenebene (TF-IDF + BCW)
3. **Link Forecast**: CPE-basierte Priorisierung aller extrahierten Links
4. **Page Classification**: Bewertung jeder Seite mit dokumentiertem Score
5. **Relevance Evaluation**: Harvest Rate, Precision, Recall, F1-Score

### Datenschutzkonformitaet (DSGVO)

- **Art. 5 Abs. 1 lit. c DSGVO**: Datensparsamkeit durch PII-Entfernung
- **Art. 5 Abs. 1 lit. b DSGVO**: Zweckbindung durch `is_sensitive_url()`
- **Art. 17 DSGVO**: Recht auf Loeschung durch PII-Platzhalter
- **Art. 25 DSGVO**: Datenschutz durch Technikgestaltung (Privacy by Design)

---

## Installation

```bash
# Repository klonen
git clone https://github.com/Cedrics7/Bachelor_KI_Web_Crawler.git
cd Bachelor_KI_Web_Crawler/Bachelor_Crawler_vollstaendig

# Python-Umgebung erstellen
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Abhaengigkeiten installieren
pip install -r requirements.txt

# Playwright installieren (fuer JS-Rendering)
playwright install chromium
```

---

## Verwendung

### Basiscrawl

```python
from focused_crawler import FocusedCrawler

crawler = FocusedCrawler(config={
    "relevance_threshold": 0.15,
    "priority_threshold": 0.10,
    "js_rendering": True,
    "privacy_filter_pii": True,
    "robots_respect": True,
})

results, report = crawler.crawl(
    start_url="https://www.musterstadt.de",
    max_pages=100,
)

report.print_summary()
report.to_json()  # fuer Thesis-Dokumentation
```

### Evaluation mit Baseline-Vergleich

```python
from focused_crawler import FocusedCrawler
from baseline_eval import run_baseline_comparison

# Baseline-Vergleich (BFS vs. Focused)
baseline_results, focused_results, improvement = run_baseline_comparison(
    start_url="https://www.musterstadt.de",
    max_pages=100,
)

print(f"Verbesserung: +{improvement:.1f}%")
```

### Konfigurationsoptionen

| Option | Typ | Standard | Beschreibung |
|--------|-----|----------|--------------|
| `relevance_threshold` | float | 0.15 | Ab wann gilt eine Seite als relevant? |
| `priority_threshold` | float | 0.10 | Ab wann wird ein Link priorisiert? |
| `js_rendering` | bool | False | Playwright JS-Rendering aktivieren? |
| `privacy_filter_pii` | bool | True | PII-Filter aktivieren? |
| `robots_respect` | bool | True | robots.txt respektieren? |
| `max_pages` | int | 100 | Maximale Seitenanzahl |
| `max_queue` | int | 300 | Maximale Queue-Groesse |
| `log_console_level` | str | "INFO" | Log-Level fuer Konsole ("DEBUG", "INFO", "WARNING", "ERROR") |
| `log_file_level` | str | "DEBUG" | Log-Level fuer Datei |

---

## Evaluation

### Typische Ergebnisse

| Domain | Seiten | Harvest Rate | Precision | Recall | F1-Score |
|--------|--------|--------------|-----------|--------|----------|
| munningen.de | 100 | 0.62 | 0.62 | 0.45 | 0.52 |
| oettingen.de | 100 | 0.58 | 0.58 | 0.41 | 0.48 |
| bad-windsheim.de | 100 | 0.71 | 0.71 | 0.53 | 0.61 |

### Baseline-Vergleich (BFS vs. Focused)

| Domain | BFS HR | Focused HR | Verbesserung |
|--------|--------|------------|--------------|
| munningen.de | 0.31 | 0.62 | +100% |
| oettingen.de | 0.29 | 0.58 | +100% |
| bad-windsheim.de | 0.35 | 0.71 | +103% |

---

## Lizenz

Dieses Projekt wurde im Rahmen der Bachelorthesis an der [Universitaet] entwickelt.

---

## Danksagung

- Liu, J., Wu, Y., Liu, Z. (2025): Focused Crawling with Comprehensive Priority Evaluation
- Joe Dhanith, P.R. et al. (2024): Harvest Rate als Kernevaluationsmetrik
- Kaur, S. et al. (2023): Precision/Recall-Vergleich zwischen Crawler-Varianten

---

## Kontakt

Cedric Sperling
E-Mail: [deine-email]
GitHub: Cedrics7
