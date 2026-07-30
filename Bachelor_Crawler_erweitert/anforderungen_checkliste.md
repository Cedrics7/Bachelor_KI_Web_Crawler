# Anforderungsliste Bachelor Crawler

Diese Liste integriert die bereits **erfüllten Anforderungen** sowie die noch **offenen Lücken** für Thesis, Evaluation und Ergebnisdarstellung. GitHub-Tasklisten verwenden `- [x]` für erledigt und `- [ ]` für offen.

## Funktionale Anforderungen

- [x] Focused Crawling mit Seed-URL — implementiert in `focused_crawler.py`.
- [x] Relevanzklassifikation auf Seitenebene — implementiert in `relevance_classifier.py` mit TF-IDF + BCW und Score 0–1.
- [x] Link-Priorisierung per Heuristik — implementiert in `link_prioritizer.py` mit CPE-Gewichtung (Ankertext 40 %, Kontext 25 %, URL 15 %, Inhalt 20 %).
- [x] Datenschutz / DSGVO-Basismaßnahmen — implementiert in `privacy_guard.py` mit PII-Filterung und Erkennung sensibler URLs.
- [x] `robots.txt`-Compliance — implementiert in `robots_checker.py` inklusive Crawl-Delay.
- [x] PDF-Extraktion — implementiert über `pdfminer` plus Regex-Fallback.
- [x] Strukturiertes Logging aller Schritte — implementiert in `crawler_logger.py` mit JSONL-Step-Events.
- [x] Evaluation von Harvest Rate, Precision, Recall und F1 — implementiert in `evaluation.py` mit JSON-Export.
- [x] Baseline-Vergleich BFS vs. Focused — implementiert in `baseline_runner.py` *(30.07.2026)*.
- [x] Domänenspezifisches Keyword-Modell — implementiert in `domain_model.py`.
- [x] Strukturiertes Ausgabeformat für LLM-Projektdaten — implementiert in `output_schema.py` (`MassnahmeRecord`, `ProjectDataExport`) *(30.07.2026)*.
- [x] Reproduzierbare Seed-Pipeline — implementiert in `seed_pipeline.py` + `seed_config.json` mit `random_seed=42` *(30.07.2026)*.
- [x] Referenzkorpus-Modul — implementiert in `reference_corpus.py`, Templates unter `goldstandard/` *(30.07.2026)*.

## Nicht-funktionale Anforderungen

- [x] DSGVO-Konformität als Gestaltungsziel — `PrivacyGuard` mit Art. 25 DSGVO (Privacy by Design).
- [x] `robots.txt`-Beachtung als technisch-rechtliche Grenze — umgesetzt im `RobotsChecker`.
- [x] URL-Deduplizierung — umgesetzt über `get_url_base()` ohne Query-Parameter.
- [x] RAM-Schutz — umgesetzt mit `psutil`-Monitoring und Warnung bei hoher Speicherauslastung.
- [x] JS-Rendering-Fallback für SPA-Seiten — umgesetzt via Playwright/Chromium.
- [x] Konfigurierbarkeit — umgesetzt in `config.py` mit zentralen Schwellwerten.

## Offene Lücken (verbleibend)

### 🔴 Muss

- [ ] **[#6](https://github.com/Cedrics7/Bachelor_KI_Web_Crawler/issues/6) Goldstandard-Dateien befüllen** — manuelle Annotation für Leer (mind. 40), Rotenburg (30), Barssel (25) → `goldstandard/*.json`. Ohne diese ist Recall in Kap. 6.1 nicht belegbar.

### 🟡 Sollte

- [ ] **[#4](https://github.com/Cedrics7/Bachelor_KI_Web_Crawler/issues/4) Kap. 5.4** — `output_schema.py` (MassnahmeRecord, Kategorie-Mapping, Beispiel-Output) in Thesis beschreiben.
- [ ] **[#5](https://github.com/Cedrics7/Bachelor_KI_Web_Crawler/issues/5) Kap. 4/6** — Seed-Pipeline (`seed_pipeline.py`, `seed_config.json`, `random_seed=42`) als Reproduzierbarkeitsbeleg dokumentieren.
- [ ] **[#7](https://github.com/Cedrics7/Bachelor_KI_Web_Crawler/issues/7) privacy_guard.py** — SVN-Filter-Vollständigkeit und `sanitize_metadata()` prüfen (Art. 25 DSGVO).
- [ ] **[#8](https://github.com/Cedrics7/Bachelor_KI_Web_Crawler/issues/8) Impressum-Filter + domain_model.py** — Legal-Notice-URLs aus LLM-Analyse ausschließen; Keyword-Abdeckung (≥10 pro Kategorie) sicherstellen.

## Erledigte Lücken ✅

| Datum | Was | Issue / Commit |
|---|---|---|
| 30.07.2026 | Baseline-Runner BFS-vs.-Focused | `baseline_runner.py` |
| 30.07.2026 | test_smoke integriert | `tests/test_smoke.py` |
| 30.07.2026 | LLM-Analyse produktiv | `llm_client.py` |
| 30.07.2026 | Referenzkorpus-Modul + Templates | `reference_corpus.py`, [#1](https://github.com/Cedrics7/Bachelor_KI_Web_Crawler/issues/1) |
| 30.07.2026 | Strukturiertes Ausgabeformat | `output_schema.py`, [#2](https://github.com/Cedrics7/Bachelor_KI_Web_Crawler/issues/2) |
| 30.07.2026 | Seed-Pipeline reproduzierbar | `seed_pipeline.py`, [#3](https://github.com/Cedrics7/Bachelor_KI_Web_Crawler/issues/3) |

## Priorisierung

- **Muss**: #6 Goldstandard-Annotation (ohne das kein F1 in Kap. 6.1)
- **Sollte**: #4 Thesis Kap. 5.4, #5 Thesis Kap. 4/6, #7 DSGVO-Prüfung, #8 Impressum + Keywords
- **Kann**: Erweiterte Testsuiten, Fine-Tuning-Pipelines, separates Rate-Limiter-Modul
