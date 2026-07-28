# Status Quo Bericht – Bachelor_Crawler_vollstaendig

## Zielbild
Der neue Ordner bündelt die sinnvollen Komponenten aus `focused_crawler/`, `Bachelor_Crawler/` und `crawler_js/` in einem eigenständigen Paket. Grundlage ist der wissenschaftliche Kern des `focused_crawler`, ergänzt um Datenschutz, robots.txt-Compliance und Netzwerk-/Render-Fallbacks.

## Übernommene Komponenten
- Aus `focused_crawler/`: Relevanzklassifikation, CPE-Linkpriorisierung, Evaluation, Inhaltsblock-Segmentierung, strukturiertes Logging.
- Aus `Bachelor_Crawler/`: `PrivacyGuard`, `RobotsChecker`, URL-Deduplizierung ohne Query-Parameter.
- Aus `crawler_js/`: JS-Rendering-Fallback via Playwright, VG-Redirect-Erkennung, Regex-PDF-Scan, RAM-Monitoring-Idee.

## Enthaltene Module
- `focused_crawler.py`: Hauptlaufkette des kombinierten Crawlers.
- `domain_model.py`: Domänenspezifische Keywords und Scoring.
- `relevance_classifier.py`: Seitenklassifikation mit dokumentiertem Relevanzscore.
- `link_prioritizer.py`: CPE-basierte Priorisierung für die Crawl-Frontier.
- `evaluation.py`: Harvest Rate, Precision, Recall, F1 und Baseline-Struktur.
- `privacy_guard.py`: DSGVO-Filter mit sensiblen URL-Mustern.
- `robots_checker.py`: robots.txt- und Crawl-Delay-Beachtung.
- `crawler_logger.py`: JSONL-Step-Logging.
- `run_crawler.py`: einfacher Startpunkt.
- `requirements.txt`: benötigte Abhängigkeiten.

## Funktionsstand
### Bereits abgedeckt
- HTML-Crawling und PDF-Textverarbeitung.
- Relevanzentscheidung auf Seitenebene.
- Priorisierung von Links anhand von Anchor, Kontext, URL und Seiteninhalt.
- robots.txt-Respektierung und Crawl-Delay.
- PII-Filter inkl. sensibler URL-Bereiche.
- Deduplizierung über URL-Basis statt exaktem URL-String.
- JS-Fallback für vermutlich clientseitig gerenderte Seiten.
- Verbandsgemeinde-Redirect-Ausnahme.
- Regex-basierte PDF-Erkennung im HTML.
- Evaluationsbericht für Thesis-Metriken.

### Noch bewusst vereinfacht
- `RobotsChecker` ist funktional, aber einfacher als eine ausgereifte produktive Enterprise-Variante.
- LLM-Analyse ist noch nicht integriert; sie kann später als optionales `llm_client.py` ergänzt werden.
- Baseline-Ausführung ist im Berichtskern vorgesehen, aber noch nicht als separates Runner-Skript automatisiert.
- Tests sind noch nicht ausgearbeitet.

## Bewertung
Der Ordner ist als neue Zielstruktur sinnvoll, weil er die vorher verstreuten Stärken in ein einziges Paket überführt. Für das Löschen oder Archivieren der alten Crawler reicht dieser Stand fast aus; vor einem endgültigen Archivieren wären noch Smoke-Tests und ein kurzer Realcrawl auf 2–3 Gemeindedomains ratsam.
