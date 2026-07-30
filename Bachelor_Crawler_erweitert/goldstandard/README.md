# Goldstandard / Referenzkorpus

Dieser Ordner enthaelt die manuell annotierten Referenzkorpora (Goldstandards) fuer die Evaluationsdomains der Bachelorthesis.

## Zweck

Ohne Goldstandard kann nur **Precision** (= Harvest Rate) gemessen werden.  
Mit Goldstandard ist auch **Recall** und damit **F1-Score** berechenbar:

```
Recall = gefundene relevante Seiten / alle relevanten Seiten im Goldstandard
F1     = 2 * (Precision * Recall) / (Precision + Recall)
```

## Dateien

| Datei | Domain | Status |
|---|---|---|
| `leer_template.json` | leer.de | Vorlage – bitte ausfullen |
| `saarlouis_template.json` | saarlouis.de | Vorlage – bitte ausfullen |
| `barssel_template.json` | barssel.de | Vorlage – bitte ausfullen |

Nach vollstaendiger Annotation die Dateien in `leer.json`, `saarlouis.json`, `barssel.json` umbenennen.

## Annotationsanleitung

1. Starte einen BFS-Crawl der Domain (alle Seiten, kein Relevanzfilter)
2. Notiere alle besuchten URLs
3. Oeffne jede URL manuell und entscheide:
   - **relevant** (`true`): Seite enthaelt Infos zu kommunalen Projekten (Bauen, Umwelt, Wirtschaft, Infrastruktur, Verwaltung)
   - **nicht relevant** (`false`): Impressum, Kontakt, Veranstaltungen ohne Projektbezug, Datenschutz, etc.
4. Trage URL, Relevanz und Kategorie in die JSON-Datei ein
5. Ziel: **mind. 40–60 annotierte Seiten** pro Domain

## Verwendung im Code

```python
from Bachelor_Crawler_erweitert.reference_corpus import ReferenceCorpus

corpus = ReferenceCorpus.from_json("goldstandard/leer.json")
recall = corpus.compute_recall(crawled_urls=["https://leer.de/wirtschaft", ...])
f1 = corpus.compute_f1(precision=0.783, crawled_urls=[...])
print(f"Recall: {recall:.4f}, F1: {f1:.4f}")
corpus.print_summary()
```

## Wissenschaftliche Einordnung

Der Goldstandard entspricht dem in der Literatur geforderten **Referenzkorpus** fuer Focused-Crawler-Evaluation (Liu et al. 2025, Kaur et al. 2023).  
Er wird in **Kap. 6.1** der Thesis als methodische Grundlage der Recall-Berechnung dokumentiert.
