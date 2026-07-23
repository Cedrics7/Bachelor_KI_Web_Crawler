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

## Architektur

```
FocusedCrawler
├── DomainModel          – KRS: TF-IDF-gewichtete Domänenterme (7 Kategorien)
├── RelevanceClassifier  – BCW (60%) + TF-IDF/Kosinus (40%) Ensemble-Score ∈ [0,1]
├── LinkPrioritizer      – CPE: w1*Seite + w2*Anker + w3*Kontext + w4*URL
├── CrawlEvaluator       – Harvest Rate, Irrelevance Ratio, Recall, F1, Baseline
└── FocusedCrawler       – Hauptmodul (Crawl-Loop, Content-Blöcke, PII-Filter)
```

## Relevanz-Score

Jede gecrawlte Seite erhält einen **Score ∈ [0.0, 1.0]**:

```
Score = 0.4 × TF-IDF-Kosinus-Score + 0.6 × BCW-Score
```

- **TF-IDF/Kosinus** (Hernandez et al.): Ähnlichkeit des Seitentexts mit dem KRS-Domänenvektor
- **BCW** (Liu et al.): Bayesscher Klassifikator mit Kategorie-Gewichtung – ordnet jede Seite einer Zielkategorie zu

Eine Seite gilt als **relevant**, wenn `Score ≥ relevance_threshold` (Standard: 0.15).

## CPE-Linkpriorisierung

```
CPE(link) = 0.20 × score_page
           + 0.40 × score_anchor_text
           + 0.25 × score_link_context
           + 0.15 × score_url_pattern
```

Links mit hohem CPE-Score werden **vorne** in die Queue eingereiht (Prioritätswarteschlange). PDFs erhalten automatisch einen URL-Score-Bonus (+0.3).

## Evaluationsmetriken (Mindeststandard der Literatur)

| Metrik | Formel | Beschreibung |
|---|---|---|
| **Harvest Rate** | `|relevant| / |gesamt|` | Anteil relevanter Seiten |
| **Precision** | = Harvest Rate | Bei Focused Crawling identisch |
| **Recall** | `|relevant_gefunden| / |relevant_gesamt|` | Nur mit Referenzkorpus |
| **F1-Score** | `2 × (P × R) / (P + R)` | Harmonisches Mittel |
| **Irrelevance Ratio** | `1 - Harvest Rate` | Anteil irrelevanter Seiten |
| **Baseline-Vergleich** | HR(Focused) vs HR(BFS) | Nachweis der Wirksamkeit |

## Verwendung

```python
from focused_crawler import FocusedCrawler

crawler = FocusedCrawler(config={
    "relevance_threshold": 0.15,   # Mindest-Score für "relevant"
    "max_pages": 100,
    "crawl_delay_default": 1.0,
})

results, report = crawler.crawl(
    start_url="https://www.musterstadt.de",
    max_pages=100,
    reference_corpus_size=500,     # Optional: für Recall-Berechnung
)

# Bericht ausgeben
report.print_summary()
print(report.to_json())            # JSON für Thesis-Dokumentation

# Relevante Seiten filtern
relevant = [r for r in results if r.relevance.is_relevant]
for r in relevant:
    print(f"{r.relevance.score:.3f} | {r.relevance.top_category} | {r.url}")
```

## Dateistruktur

```
focused_crawler/
├── __init__.py               # Exports
├── focused_crawler.py        # Haupt-Crawl-Loop
├── domain_model.py           # KRS-Domänenmodell (7 kommunale Kategorien)
├── relevance_classifier.py   # BCW + TF-IDF Ensemble-Klassifikator
├── link_prioritizer.py       # CPE-Linkpriorisierung
├── evaluation.py             # Harvest Rate, Precision, Recall, F1
└── README.md
```

## DSGVO & robots.txt

- robots.txt-Compliance via `RobotsChecker` aus `Bachelor_Crawler/` (falls vorhanden)
- PII-Filter (E-Mail, Telefon, IBAN) aktiv per Standard
- Domain-Guard: kein Verlassen der Startdomain

## Literaturverweise

1. Liu, J., Wu, Y., Liu, Z. (2025) – BCW-Klassifikator, CPE-Priorisierung, Content-Block-Segmentierung
2. Joe Dhanith, P.R. et al. (2024) – Relevance Computation Module (GRU + Manhattan-Distanz)
3. Hernandez, J., Marin-Castro, H.M., Morales-Sandoval, M. (2020) – KRS-Domänenmodell
4. Kaur, S., Singh, A., Geetha, G., Cheng, X. (2023) – Precision/Recall-Evaluationsstandard
