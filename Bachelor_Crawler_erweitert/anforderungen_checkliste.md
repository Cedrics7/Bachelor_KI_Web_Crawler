# Anforderungsliste Bachelor Crawler

Diese Liste integriert die bereits **erfüllten Anforderungen** sowie die noch **offenen Lücken** für Thesis, Evaluation und Ergebnisdarstellung. GitHub-Tasklisten verwenden `- [x]` für erledigt und `- [ ]` für offen.

## Funktionale Anforderungen

- [x] Focused Crawling mit Seed-URL — implementiert in `focused_crawler.py`.
- [x] Relevanzklassifikation auf Seitenebene — implementiert in `relevance_classifier.py` mit TF-IDF + BCW und Score 0–1.
- [x] Link-Priorisierung per Heuristik — implementiert in `link_prioritizer.py` mit CPE-Gewichtung (Ankertext 40 %, Kontext 25 %, URL 15 %, Inhalt 20 %).
- [x] Datenschutz / DSGVO-Basismaßnahmen — implementiert in `privacy_guard.py` mit PII-Filterung und Erkennung sensibler URLs.
- [x] `robots.txt`-Compliance — implementiert in `robots_checker.py` inklusive Crawl-Delay.
- [x] PDF-Extraktion — implementiert über `pdfminer` plus Regex-Fallback.
- [x] Strukturiertes Logging aller Schritte — implementiert in `crawler_logger.py` mit JSONL-Step-Events.
- [x] Evaluation von Harvest Rate, Precision, Recall und F1 — implementiert in `evaluation.py` mit JSON-Export.
- [x] Baseline-Vergleich BFS vs. Focused — im Evaluationsbericht vorgesehen.
- [x] Domänenspezifisches Keyword-Modell — implementiert in `domain_model.py`.

## Nicht-funktionale Anforderungen

- [x] DSGVO-Konformität als Gestaltungsziel — `PrivacyGuard` mit Bezug auf datenschutzfreundliche Schutzmaßnahmen; Art. 25 DSGVO verlangt Datenschutz durch Technikgestaltung und datenschutzfreundliche Voreinstellungen.
- [x] `robots.txt`-Beachtung als technisch-rechtliche Grenze — umgesetzt im `RobotsChecker`.
- [x] URL-Deduplizierung — umgesetzt über `get_url_base()` ohne Query-Parameter.
- [x] RAM-Schutz — umgesetzt mit `psutil`-Monitoring und Warnung bei hoher Speicherauslastung.
- [x] JS-Rendering-Fallback für SPA-Seiten — umgesetzt via Playwright/Chromium.
- [x] Konfigurierbarkeit — umgesetzt in `config.py` mit zentralen Schwellwerten.

## Offene Lücken

### RQ3 Evaluation

- [x] Separater Baseline-Runner für automatisierte BFS-vs.-Focused-Testläufe. *(implementiert am 30.07.2026)*
- [x] Dokumentierte Testläufe über `test_smoke.py` hinaus; die aktuelle Testbasis ist für Kap. 6.1 zu klein. *(test_smoke integriert am 30.07.2026)*
- [ ] Referenzkorpus / Goldstandard für belastbare Recall-Berechnung pro Testdomain.
- [ ] Reproduzierbare Evaluationsszenarien mit festen Seed-Listen, Seitenlimits und Metrik-Export.

### LLM und Extraktion

- [x] LLM-Komponente als schaltbares und evaluierbares Feature in der Thesis systematisch dokumentieren. *(LLM-Analyse produktiv am 30.07.2026)*
- [ ] Strukturiertes Ausgabeformat für Projektdaten ergänzen, insbesondere Projekttyp, Ort, Zeitraum und Quelle.
- [ ] Extraktionslogik für Projekttypen, Orte und Zeiträume explizit an Kap. 5.4 der Thesis ausrichten.

### Zielquellen und Seeds

- [x] Automatisierte Seed-Selektion aus `municipalities_final_master.csv` architektonisch dokumentieren. (DB Verbindung löst das Problem)
- [ ] Seed-Pipeline so beschreiben, dass Auswahl, Priorisierung und Startbedingungen nachvollziehbar reproduzierbar sind.

### Datenschutz und Architektur

- [ ] Prüfen, ob `privacy_guard.py` gegenüber der Alt-Version um expliziten SVN-Filter ergänzt werden muss; Art. 25 DSGVO spricht für technische Minimierungsmaßnahmen.
- [ ] Prüfen, ob `sanitize_metadata()` oder ein Äquivalent für Metadatenbereinigung wieder aufgenommen werden sollte, falls Metadaten weiterverarbeitet werden.
- [ ] Prüfen, ob Impressums-/Datenschutzseiten wieder getrennt behandelt werden sollten, damit sie nicht unnötig in nachgelagerte KI-Analysen gelangen.
- [ ] Prüfen, ob das verkleinerte `domain_model.py` fehlende Keywords oder Kategorien verursacht und damit die Relevanzklassifikation schwächt.

## Priorisierung

- **Muss**: Referenzkorpus, strukturierte Projektdaten-Extraktion, Seed-Pipeline dokumentieren.
- **Sollte**: Metadaten-Sanitization prüfen, Legal-Notice-Behandlung prüfen.
- **Kann**: Erweiterte Testsuiten, zusätzliche Fine-Tuning- oder Forschungs-Pipelines, separates Rate-Limiter-Modul.
