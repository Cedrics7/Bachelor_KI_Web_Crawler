# focused_crawler

> **Eigenständiger Focused Crawler für die Bachelorthesis** – vollständig neu, kein Code aus `crawler_js` oder `Bachelor_Crawler` wird ersetzt oder überschrieben.

## Wissenschaftliche Grundlage

Dieser Crawler implementiert die vier zentralen Bausteine, die laut Thesis-Analyse dem bisherigen Artefakt fehlten:

| Baustein | Modul | Quelle |
|---|---|---|
| Domänenmodell (KRS) | `domain_model.py` | Hernandez et al. (2020) |
| Relevanzberechnung + BCW-Klassifikator | `relevance_classifier.py` | Liu et al. (2025), Joe Dhanith et al. (2024) |
| CPE-Linkpriorisierung | `link_prioritizer.py` | Liu et al. (2025) |
| Harvest Rate, Precision, Recall, F1 | `evaluation.py` | Liu et al. (2025), Kaur et al. (2023) |
| Content-Block-Segmentierung (Tunneling) | `focused_crawler.py` | Liu et al. (2025) |
| **Vollständiges Step-Logging** | **`crawler_logger.py`** | **v1.1 – neu** |
| **BFS-Baseline-Evaluationsskript** | **`baseline_eval.py`** | **v1.1 – neu** |

## Architektur

```
FocusedCrawler
├── DomainModel          – KRS: TF-IDF-gewichtete Domänenterme (7 Kategorien)
├── RelevanceClassifier  – BCW (60%) + TF-IDF/Kosinus (40%) Ensemble-Score ∈ [0,1]
├── LinkPrioritizer      – CPE: w1*Seite + w2*Anker + w3*Kontext + w4*URL
├── CrawlEvaluator       – Harvest Rate, Irrelevance Ratio, Recall, F1, Baseline
├── CrawlerLogger        – Vollständiges Step-Logging (4 Log-Kanäle)
└── FocusedCrawler       – Hauptmodul (Crawl-Loop, Content-Blöcke, PII-Filter)
```

## Logging (v1.1)

### Log-Dateien

Alle Logs werden im Verzeichnis `logs/` abgelegt:

| Datei | Inhalt | Format |
|---|---|---|
| `focused_crawler_{run_id}_{ts}.log` | Vollprotokoll aller Events | JSON-Lines |
| `relevance_{run_id}_{ts}.csv` | Jede Relevanzberechnung | CSV |
| `privacy_{run_id}_{ts}.log` | DSGVO-Events (PII, robots.txt) | JSON-Lines |
| `evaluation_{run_id}_{ts}.json` | Evaluationsbericht(e) | JSON |
| `baseline_comparison_{ts}.csv` | Focused vs. BFS-Vergleich | CSV |
| `baseline_comparison_{ts}.json` | Vollständiger Vergleichsbericht | JSON |

### Geloggte Ereignisse

Die folgenden Änderungen und Schritte werden protokolliert (eingeführt in v1.1):

#### Crawl-Schritte (`CRAWL`-Komponente)
| Event | Level | Inhalt |
|---|---|---|
| `FETCH` | DEBUG | URL, HTTP-Status, Ladezeit (ms), Content-Länge |
| `PARSE` | DEBUG | Links gefunden, Content-Blöcke, Textlänge |
| `PDF_EXTRACT` | DEBUG | PDF-URL, extrahierte Textlänge |
| `DELAY` | DEBUG | Crawl-Delay in Sekunden |
| `QUEUE_UPDATE` | DEBUG | Queue-Größe, Anzahl priorisierter Links |
| `SKIP` | DEBUG | Übersprungene URLs |
| `DUPLICATE` | DEBUG | Hash-Duplikate (via PRIVACY-Kanal) |

#### Relevanzberechnung (`RELEVANCE`-Komponente)
| Event | Level | Inhalt |
|---|---|---|
| Jede Klassifikation | INFO/OK | Score (gesamt, TF-IDF, BCW), Kategorie, Konfidenz, Keywords |
| Relevant-Marker | OK | ✅ wenn Score ≥ Schwellwert |
| Irrelevant-Marker | INFO | ⬜ wenn Score < Schwellwert |

**CSV-Format (relevance_*.csv):**
```
timestamp,url,score,tfidf_score,bayes_score,is_relevant,top_category,confidence,matched_keywords
```

#### CPE-Linkpriorisierung (`CPE`-Komponente)
| Event | Level | Inhalt |
|---|---|---|
| Pro Link | DEBUG | CPE-Score, Anchor-Score, Kontext-Score, URL-Score, Seiten-Score |
| Priorität-Flag | DEBUG | ⭐PRIO wenn CPE ≥ Schwellwert |

#### Datenschutz/DSGVO (`PRIVACY`-Komponente, AUDIT-Level)
| Event | Level | Inhalt |
|---|---|---|
| `PII_REMOVED` | AUDIT | URL, Anzahl E-Mail/Tel/IBAN entfernt |
| `SENSITIVE_URL_SKIPPED` | AUDIT | URL + erkanntes Muster |
| `ROBOTS_DISALLOWED` | AUDIT | URL + User-Agent |
| `DOMAIN_GUARD` | AUDIT | URL + externe Domain |
| `HASH_DUPLICATE` | AUDIT | URL + Hash (Duplikat-Erkennung) |

> **AUDIT-Events werden immer geschrieben**, unabhängig vom konfigurierten Log-Level.
> Sie dienen als DSGVO-Nachweis und sollten für die Thesis aufbewahrt werden.

#### robots.txt (`ROBOTS`-Komponente)
| Event | Level | Inhalt |
|---|---|---|
| Erlaubt | DEBUG | URL |
| `DISALLOWED` | AUDIT | URL + User-Agent (→ auch in privacy.log) |

#### Evaluation (`EVALUATION`-Komponente)
| Event | Level | Inhalt |
|---|---|---|
| Focused-Lauf | OK | Harvest Rate, Recall, F1, Relevant/Gesamt, Δ_BFS |
| BFS-Baseline | OK | Harvest Rate, Relevant/Gesamt |
| Vergleich | OK | Alle Metriken + Verbesserung in % |

### Log-Level konfigurieren

```python
crawler = FocusedCrawler(config={
    "log_console_level": "INFO",   # Konsole: INFO, WARN, ERROR, OK, AUDIT
    "log_file_level":    "DEBUG",  # Datei: alles inkl. CPE-Scores
    "log_dir":           "logs",
})
```

## Relevanz-Score

Jede gecrawlte Seite erhält einen **Score ∈ [0.0, 1.0]**:

```
Score = 0.4 × TF-IDF-Kosinus-Score + 0.6 × BCW-Score
```

- **TF-IDF/Kosinus** (Hernandez et al.): Ähnlichkeit des Seitentexts mit dem KRS-Domänenvektor
- **BCW** (Liu et al.): Bayesscher Klassifikator – ordnet jede Seite einer Zielkategorie zu

Eine Seite gilt als **relevant**, wenn `Score ≥ relevance_threshold` (Standard: 0.15).

## CPE-Linkpriorisierung

```
CPE(link) = 0.20 × score_page
           + 0.40 × score_anchor_text
           + 0.25 × score_link_context
           + 0.15 × score_url_pattern
```

Links mit hohem CPE-Score werden **vorne** in die Queue eingereiht. PDFs erhalten +0.3 Bonus.

## BFS-Baseline-Evaluationsskript

### CLI-Verwendung

```bash
# Direktaufruf
python -m focused_crawler.baseline_eval --url https://www.musterstadt.de --pages 100

# Mit Schwellwert und Referenzkorpus
python -m focused_crawler.baseline_eval \
  --url https://www.musterstadt.de \
  --pages 100 \
  --threshold 0.20 \
  --reference 500
```

### Ausgabe

```
════════════════════════════════════════════════════════════════════════
  EVALUATIONSVERGLEICH: FocusedCrawler vs. BFS-Baseline
  Quelle: Liu et al. (2025), Joe Dhanith et al. (2024), Kaur et al. (2023)
════════════════════════════════════════════════════════════════════════
  Metrik                    FocusedCrawler    BFS-Baseline          Δ
────────────────────────────────────────────────────────────────────────
  Harvest Rate (Precision)          0.6500          0.3200      +0.3300  ↑ besser
  Irrelevance Ratio                 0.3500          0.6800      -0.3300  ↓ besser
  Ø Relevanz-Score                  0.3421          0.1820      +0.1601
  ...
────────────────────────────────────────────────────────────────────────
  Verbesserung HR:          +103.13%  gegenüber BFS-Baseline
════════════════════════════════════════════════════════════════════════
```

### Python-API

```python
from focused_crawler.baseline_eval import run_baseline_evaluation

result = run_baseline_evaluation(
    start_url="https://www.musterstadt.de",
    max_pages=100,
    relevance_threshold=0.15,
    reference_corpus_size=500,  # optional, für Recall
    log_dir="logs",
)
```

## Evaluationsmetriken (Literatur-Mindeststandard)

| Metrik | Formel | Beschreibung |
|---|---|---|
| **Harvest Rate** | `|relevant| / |gesamt|` | Anteil relevanter Seiten |
| **Precision** | = Harvest Rate | Bei Focused Crawling identisch |
| **Recall** | `|relevant_gefunden| / |relevant_gesamt|` | Nur mit Referenzkorpus |
| **F1-Score** | `2 × (P × R) / (P + R)` | Harmonisches Mittel |
| **Irrelevance Ratio** | `1 - Harvest Rate` | Anteil irrelevanter Seiten |
| **Baseline-Vergleich** | HR(Focused) vs HR(BFS) | Nachweis der Wirksamkeit |

## Dateistruktur

```
focused_crawler/
├── __init__.py               # Exports
├── focused_crawler.py        # Haupt-Crawl-Loop (v1.1: vollständiges Logging)
├── crawler_logger.py         # CrawlerLogger – 4 Log-Kanäle (NEU)
├── baseline_eval.py          # BFS-Baseline-Evaluationsskript (NEU)
├── domain_model.py           # KRS-Domänenmodell
├── relevance_classifier.py   # BCW + TF-IDF Ensemble
├── link_prioritizer.py       # CPE-Linkpriorisierung
├── evaluation.py             # Harvest Rate, Precision, Recall, F1
└── README.md
```

## DSGVO & robots.txt

- robots.txt-Compliance via `RobotsChecker` aus `Bachelor_Crawler/`
- PII-Filter aktiv per Standard (E-Mail, Telefon, IBAN)
- Alle Datenschutz-Events werden in `privacy_*.log` protokolliert (AUDIT-Level)
- Domain-Guard: kein Verlassen der Startdomain

## Literaturverweise

1. Liu, J., Wu, Y., Liu, Z. (2025) – BCW, CPE, Content-Block-Segmentierung, Harvest Rate
2. Joe Dhanith, P.R. et al. (2024) – Relevance Computation Module
3. Hernandez, J. et al. (2020) – KRS-Domänenmodell
4. Kaur, S. et al. (2023) – Precision/Recall-Evaluationsstandard
