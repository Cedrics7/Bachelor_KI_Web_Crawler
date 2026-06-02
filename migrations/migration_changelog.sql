-- ============================================================
-- migration_changelog.sql
-- Reiner Changelog-Import für Bachelor_KI_Web_Crawler
-- Löscht NUR changelog_items + changelog (crawl_results bleibt!)
-- Dann vollständiger INSERT aller Versionen.
-- Ausführen: psql -U <user> -d <db> -f migration_changelog.sql
-- ============================================================


-- ============================================================
-- 1. NUR CHANGELOG-TABELLEN LEEREN (Reihenfolge beachten)
-- ============================================================
DELETE FROM changelog_items;
DELETE FROM changelog;


-- ============================================================
-- 2. VERSIONEN IMPORTIEREN
-- ============================================================
INSERT INTO changelog (version, release_date, title, description, commit_sha) VALUES
('0.1.0', '2026-04-28', 'Projekt-Init',
    'Erstes grundlegendes Programm, Repository-Setup',
    '7bebcdff64a3031edc292c8dd098250c2fbb08ad'),

('0.2.0', '2026-04-29', 'Erweiterung Basis',
    'Grundlegendes Programm weiterentwickelt, erste Modul-Struktur',
    '618d2e3888cdfe9f0c6f07b81cb33538e7ea81de'),

('0.3.0', '2026-04-29', 'KI-Integration Alpha',
    'Erster KI-WebCrawler mit Gemini API Key',
    'bd8547e6ebd7879953ba534f23445b1fe4380c92'),

('0.4.0', '2026-04-29', 'KI-Integration Beta',
    'API-Key-Handling stabilisiert, erste Crawl-Ergebnisse',
    'c9a368850920e1ce3b6a26b561079f77c310baed'),

('0.5.0', '2026-04-30', 'KI-Crawler Refactor',
    'Refactoring der KI-Logik, verbessertes Prompt-Handling',
    'fdbd1c87bc32d98337d8dc5d81e9293daaf6ddc6'),

('1.0.0', '2026-05-04', 'Architektur-Redesign',
    'Neuer Ansatz: komplette Umstrukturierung der Backend-Architektur, FastAPI-Basis',
    'c1870228aecabad16515c07f83c9db0d1c750261'),

('1.1.0', '2026-05-05', 'Dashboard-Grundlage',
    'Erste statische Dashboard-Dateien, Frontend-Skeleton',
    'a6e9ea598e0a8f9e8c868674673256b35e70c625'),

('1.2.0', '2026-05-07', 'Dashboard Telekom-Stil',
    'Dashboard-Prototyp im Telekom-Design, Crawler Beta eingebunden',
    'b0cf314d3d940f3cbf85980d00aa8e08cad0d90b'),

('1.3.0', '2026-05-09', 'JS-Frontend vollwertig',
    'Vollständige JavaScript-Auslagerung, Telekom-Frontend fast komplett, Router-Grundlage',
    'a6cc9b2105b17fb7b73018b4a3850c79f1d0934f'),

('1.4.0', '2026-05-11', 'Filter, Footer & Changelog',
    'Filter-Logik verbessert, Heartbeat-Thread, Footer-Prototyp, Changelog-API-Endpoint und DB-Migration',
    '95f3238187cea3d9800b82075157dc791162c77a'),

('1.5.0', '2026-05-12', 'Crawler-Stabilität & PDF-Priorisierung',
    'Smarte PDF-Reihenfolge (HTML zuerst, Prio-PDFs vor normalen PDFs), schrittweise Seitenzahlkürzung bei Textlimit, älteste PDFs zuerst verwerfen, Warnausgaben bei Datenverlust, doppelte 500k-Grenze entfernt',
    '1dcb749c9c73f451072e79f8fd4d6b7fb00d60c3'),

('1.6.0', '2026-05-12', 'Config-Zentralisierung & UI-Fixes',
    'Filter-Parameter (min_pdf_year, min_end_datum) zentral in CONFIG, KPI-Karten Bewegungsdaten (Gesamt/Monat/Heute), Bestandsdaten: gefunden_am nutzt end_time-Zeitstempel, Bundesland-Filter optisch angeglichen, Monitoring-Übersicht entfernt, Auto-Refresh alle Panels',
    'c296addbc53a594c1fe8e15de5789ceaa6895fe8'),

('1.7.0', '2026-05-29', 'Unterseiten-Hashing & Kontext-Chunking',
    'SHA-256-Hashing aller gecrawlten Unterseiten/PDFs für differenzielle Crawl-Läufe (nur geänderte Seiten ans LLM), kontextbewusstes Chunking mit konfigurierbarem Overlap (chunk_overlap in CONFIG), neue DB-Spalte subpage_hashes in crawl_targets',
    '48114232508db9eca4899ff19a108fcc8ebbb185'),

('1.8.0', '2026-05-29', 'Modularisierung & Kategorie-Erweiterung',
    'Crawler in Teilmodule aufgeteilt (config.py, logger.py, rate_limiter.py, scraper.py, llm_client.py, crawler_telekom.py), Kategorie Tiefbau aufgeteilt in Straßenbau + Brückenbau, force_ags-Option für erzwungene Crawl-Targets, Regex-Scan für JS-gerenderte PDF-Links, URL-Kontext-Hint in assemble_text()',
    'df2db7e1d89fafc572c0e23d53f616759cc13db8'),

('1.9.0', '2026-05-29', 'Frontend-Bugfixes & content_hash-Korrektur',
    'content_hash in crawl_targets verschoben (korrekte Hash-Vergleiche), Mänahmen-Modal mit direktem API-Endpunkt GET /api/bestandsdaten/{id} (kein Table-Scan mehr), Filter-Parameter-Reset beim Seitenwechsel, Prompt-Fehlerbehebungen (Zeitraum-Filter, Kosten-Summary, Live-Log-Keys)',
    '4a523410fa1af23829d3cfb2d47d56b22f110d80'),

('1.10.0', '2026-05-29', 'Crawler-Paket & Import-Fixes',
    'Crawler-Module in crawler/-Paket verschoben, alle internen Importe korrigiert (crawler.-Präfix entfernt)',
    'b6892869c600bab18a3c2b5bd326f9499c744a68'),

('1.11.0', '2026-05-30', 'HTTP-Stabilität & DNS-Robustheit',
    'requests durch httpx ersetzt (echter DNS-Timeout), httpx.Client für max_redirects-Unterstützung, max_redirects=5 gegen Redirect-Loops, httpx-Calls in ThreadPoolExecutor gegen DNS-Blocking-Kills, outer try/except gegen Absturz bei nicht erreichbaren Hosts (502/unresolvable)',
    '6982503921d747eb2ac4beba6ac0074ab4026515'),

('1.12.0', '2026-05-30', 'HTTP→HTTPS & SSL-Fixes',
    'get_url_base() normalisiert Schema auf https (verhindert doppeltes Crawlen bei Redirects), extract_pdf_text httpx.Client im Worker-Thread (kein SSL-Blocking), _safe_get() fängt alle Exceptions inkl. SSLError und RemoteProtocolError',
    'a74b31af57b61285b923fe3637b99f37921de7fe'),

('1.13.0', '2026-06-01', 'OOM-Kill-Prevention & External-Redirect-Guard',
    'RAM-Speicherleck geschlossen (soup/resp explizit gelöscht, html_pages/pdf_pages vor LLM-Call freigegeben), resp.text einmalig in Variable (verhindert gleichzeitiges resp.content + resp.text + BeautifulSoup-DOM im RAM), Domain-Redirect-Guard: EXTERNAL_REDIRECT-Erkennung bei vestenbergsgreuth.de und ähnlichen Fällen, MAX_QUEUE=300 gegen URL-Queue-Explosion, visited_full-Trim bei >2000 Einträgen, RAM-Warn-Logger ab 400 MB RSS, _safe_get shutdown(wait=False) gegen hängende Verbindungen, psutil statt unix-only resource-Modul',
    '05461ff1e7921caa43293faef09cd44c7c3a0a0d'),

('1.14.0', '2026-06-02', 'Multi-Modell-Evaluation & JS-Crawler-Modul',
    'Neues Modul crawler_eval/ für parallelen Modellvergleich (eval_config.py + crawler_eval.py), alle stabilen Telekom-API-Modelle ohne WARN-Präfix aktiviert, neues Modul crawler_js/ mit Playwright-Fallback für JavaScript-gerenderte Seiten (scraper_js.py + config_js.py)',
    '95b3f865f430c83b28eac8b33b2fc7b420f052bc'),

('1.15.0', '2026-06-02', 'VG-Redirect-Support & Browser-User-Agent',
    'VG-Redirect-Erkennung (_is_vg_redirect): Verwaltungsgemeinschaft-Redirects werden akzeptiert wenn Gemeindenamen als Pfadsegment in Ziel-URL vorkommt, Subpath-Filter verhindert unkontrolliertes Crawlen aller VG-Mitgliedsgemeinden, vg_max_queue=80 reduziert Queue-Limit bei VG-Seiten, Browser-like User-Agent für httpx.Client (http_user_agent in CONFIG) behebt 503/403-Blocking durch TYPO3 und Apache',
    '6021ab6ea2b659f71b1188f737922c5f9706801d');


-- ============================================================
-- 3. ITEMS IMPORTIEREN
-- ============================================================

-- v0.1.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore', 'project', 'Repository initialisiert, grundlegende Projektstruktur angelegt', '7bebcdff', 1 FROM changelog WHERE version = '0.1.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'crawler', 'Erstes Crawler-Grundgerüst mit HTTP-Request-Logik',               '7bebcdff', 2 FROM changelog WHERE version = '0.1.0';

-- v0.2.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'crawler',   'URL-Queue und einfache Link-Extraktion implementiert', '618d2e38', 1 FROM changelog WHERE version = '0.2.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore', 'structure', 'Modul-Aufteilung vorbereitet',                         '618d2e38', 2 FROM changelog WHERE version = '0.2.0';

-- v0.3.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'ai',      'Gemini API Key Integration (google-generativeai)',     'bd8547e6', 1 FROM changelog WHERE version = '0.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'KI-gestützte Inhaltsanalyse erster Crawl-Ergebnisse', 'bd8547e6', 2 FROM changelog WHERE version = '0.3.0';

-- v0.4.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'ai',      'API-Key-Fehlerbehandlung verbessert (env-Variable)', 'c9a36885', 1 FROM changelog WHERE version = '0.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Crawl-Ergebnisse strukturiert gespeichert',           'c9a36885', 2 FROM changelog WHERE version = '0.4.0';

-- v0.5.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'ai',      'Prompt-Handling ausgelagert, wiederverwendbare KI-Funktion', 'fdbd1c87', 1 FROM changelog WHERE version = '0.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'perf',     'crawler', 'Crawl-Tiefe konfigurierbar gemacht',                          'fdbd1c87', 2 FROM changelog WHERE version = '0.5.0';

-- v1.0.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'backend', 'Komplette Neustrukturierung: FastAPI als Basis eingeführt',        'c1870228', 1 FROM changelog WHERE version = '1.0.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'api',     'REST-Endpunkte für Crawler-Steuerung (start/stop/status)',         'c1870228', 2 FROM changelog WHERE version = '1.0.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore',    'deps',    'requirements.txt aktualisiert (fastapi, uvicorn, httpx)',           '15b6a50d', 3 FROM changelog WHERE version = '1.0.0';

-- v1.1.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'frontend',  'Statische Dashboard-HTML/CSS Grunddateien erstellt', 'a6e9ea59', 1 FROM changelog WHERE version = '1.1.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore', 'structure', 'Frontend- und Backend-Ordner sauber getrennt',       'a6e9ea59', 2 FROM changelog WHERE version = '1.1.0';

-- v1.2.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'frontend', 'Dashboard-Design an Telekom Corporate Design angenähert (Magenta, T-Logo)', 'b0cf314d', 1 FROM changelog WHERE version = '1.2.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'crawler',  'Crawler-Beta in Dashboard-Status integriert',                              'b0cf314d', 2 FROM changelog WHERE version = '1.2.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'style', 'ui',       'Erste Statusanzeige (aktiv/inaktiv) im Header',                           '8cf0fd33', 3 FROM changelog WHERE version = '1.2.0';

-- v1.3.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'frontend', 'HTML → vollständige JavaScript-Auslagerung (ES Modules)',    'a6cc9b21', 1 FROM changelog WHERE version = '1.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'router',   'Client-seitiges Router-Grundgerüst (SPA-Navigation)',        'a6cc9b21', 2 FROM changelog WHERE version = '1.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'api',      'Neues Dashboard: Live-Daten-Anbindung über fetch()',         '497f6f13', 3 FROM changelog WHERE version = '1.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'style',    'ui',       'Telekom-Frontend fast vollständig: Topbar, Cards, Tabellen', 'a6cc9b21', 4 FROM changelog WHERE version = '1.3.0';

-- v1.4.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'filter',   'Filter-Logik für Crawler-Ergebnisse grundlegend verbessert',              'd2622181', 1 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'crawler',  'Heartbeat-Thread: crawler_live_status.json alle 10s aktualisiert',        '47892ba3', 2 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'frontend', 'Auslagerung und Umstrukturierung (render.js / api.js Trennung)',           '2d5be1b7', 3 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'footer',   'Footer: SVG-Icons, Version-Badge, Changelog-Button',                      '0f79018b', 4 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'db',       'changelog + changelog_items Tabellen angelegt (PostgreSQL)',               '95f3238',  5 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'api',      'GET /api/changelog Endpoint: Versionen mit Items aus DB',                 '95f3238',  6 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'ui',       'Perfektions-Pass: Abstände, Konsistenz, Lesbarkeit',                       '6616c15',  7 FROM changelog WHERE version = '1.4.0';

-- v1.5.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'HTML-Seiten immer vollständig vor PDFs übernommen (Priorisierung)',                                '1dcb749c', 1 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'PDF-Priorisierung: Bekanntmachung, Bebauungsplan, Satzung etc. werden zuerst eingebaut',          '1dcb749c', 2 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Seitenzahl-Reduktion bei Textlimit: schrittweise 5 → 3 → 2 → 1 Seiten pro PDF',                  '1dcb749c', 3 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Älteste PDFs zuerst verwerfen wenn auch 1 Seite nicht ausreicht (Prio-PDFs geschützt)',           '1dcb749c', 4 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'crawler', 'Doppelte 500k-Zeichengrenze entfernt – nur noch assemble_text() kürzt',                           '1dcb749c', 5 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Warnausgabe im Terminal bei PDF-Kürzung oder -Verwerfung (mögl. Datenverlust)',                    '1dcb749c', 6 FROM changelog WHERE version = '1.5.0';

-- v1.6.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'crawler', 'min_pdf_year aus CONFIG ausgelagert (war hardcoded 2024 in extract_pdf_text)',                'c296addb', 1 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'crawler', 'min_end_datum mit erklärendem Kommentar versehen',                                            'c296addb', 2 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'ui',      'KPI-Karten Bewegungsdaten: Maßnahmen gesamt, diesen Monat, heute gefunden',                  'c296addb', 3 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'ui',      'Bestandsdaten: gefunden_am zeigt jetzt Zeitstempel aus end_time-Spalte',                     'c296addb', 4 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'style',    'ui',      'Bundesland-Filter Bestandsdaten optisch an Bewegungsdaten angeglichen',                      'c296addb', 5 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'ui',      'Monitoring-Übersicht vollständig entfernt',                                                   'c296addb', 6 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'ui',      'Auto-Refresh jetzt für alle Panels inkl. Orte-Gesamt-KPI',                                   'c296addb', 7 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'db',      'Index idx_crawl_results_end_time hinzugefügt (Performance)',                                  'c296addb', 8 FROM changelog WHERE version = '1.6.0';

-- v1.7.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'SHA-256-Hashing aller Unterseiten und PDFs nach jedem Crawl-Lauf',                               '4811423', 1 FROM changelog WHERE version = '1.7.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'perf', 'crawler', 'Differenzieller Crawl: nur geänderte/neue Unterseiten werden ans LLM übergeben',                 '4811423', 2 FROM changelog WHERE version = '1.7.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Kontext-Chunking: chunk_overlap (Standard 5.000 Zeichen) aus vorherigem Chunk als LLM-Kontext', '4811423', 3 FROM changelog WHERE version = '1.7.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'db',      'Neue Spalte subpage_hashes JSONB in crawl_targets (Migration: add_subpage_hashes.sql)',          '4811423', 4 FROM changelog WHERE version = '1.7.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'config',  'Neuer CONFIG-Parameter chunk_overlap für einstellbaren Kontext-Überlapp',                        '4811423', 5 FROM changelog WHERE version = '1.7.0';

-- v1.8.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'structure', 'Crawler in 6 Teilmodule aufgeteilt: config, logger, rate_limiter, scraper, llm_client, crawler_telekom (1198 → ~190 Zeilen Haupt-Loop)', 'df2db7e1', 1 FROM changelog WHERE version = '1.8.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'config',    'Kategorie Tiefbau aufgeteilt in eigenständige Kategorien Straßenbau und Brückenbau',                                                     'e92d52c5', 2 FROM changelog WHERE version = '1.8.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'config',    'force_ags-Liste in CONFIG: bestimmte AGS-Targets immer crawlen unabhängig vom Hash',                                                    'b007b0ec', 3 FROM changelog WHERE version = '1.8.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'scraper',   'Regex-Scan für PDF-Links die BeautifulSoup übersieht (JS-gerenderte Links im Raw-HTML)',                                               'eea1ed4c', 4 FROM changelog WHERE version = '1.8.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'scraper',   'URL-Kontext-Hint in assemble_text(): Quell-URL jedes Abschnitts im LLM-Eingabetext sichtbar',                                          'eea1ed4c', 5 FROM changelog WHERE version = '1.8.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'crawler',   'Zeitraum-Filter, Kosten-Summary und Live-Log-Keys (aktueller_ort, hash_match) wiederhergestellt',                                     '4e305766', 6 FROM changelog WHERE version = '1.8.0';

-- v1.9.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'db',       'content_hash in crawl_targets verschoben für korrekte seitenweise Hash-Vergleiche',                            '4a523410', 1 FROM changelog WHERE version = '1.9.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'api',      'Neuer Endpunkt GET /api/bestandsdaten/{id} für direkte ID-Abfrage ohne Table-Scan',                          '1314a5181', 2 FROM changelog WHERE version = '1.9.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'frontend', 'loadModal() nutzt direkten API-Endpunkt statt page_size=500-Scan (Modal bei aktivem Filter)',                  '1314a5181', 3 FROM changelog WHERE version = '1.9.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'frontend', 'updateUrl() setzt Filter beim Seitenwechsel zurück (bl, status, kat, search nicht mehr geteilt)',            '1e875ec1', 4 FROM changelog WHERE version = '1.9.0';

-- v1.10.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'structure', 'Alle Crawler-Module in crawler/-Paket verschoben',                          'b6892869', 1 FROM changelog WHERE version = '1.10.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'imports',   'Alle internen Importe korrigiert (crawler.-Präfix entfernt)',                '2ef61041', 2 FROM changelog WHERE version = '1.10.0';

-- v1.11.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper', 'requests durch httpx ersetzt: echter DNS-Timeout-Support',                                            'c3588c31', 1 FROM changelog WHERE version = '1.11.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper', 'httpx.Client für max_redirects-Unterstützung (v1.11)',                                              'cdaee744', 2 FROM changelog WHERE version = '1.11.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper', 'max_redirects=5 gegen Redirect-Loops (v1.10)',                                                       '6962ce46', 3 FROM changelog WHERE version = '1.11.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper', 'httpx-Calls in ThreadPoolExecutor: verhindert DNS-Blocking-Kill des Prozesses (v1.12)',              '69825039', 4 FROM changelog WHERE version = '1.11.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper', 'Outer try/except um httpx.Client-Block: kein Absturz bei 502/nicht aufgelösten Hosts',              'b7d89b24', 5 FROM changelog WHERE version = '1.11.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper', '_safe_get verwendet shutdown(wait=False): kein Process-Kill bei hängenden Verbindungen',            '8747059d', 6 FROM changelog WHERE version = '1.11.0';

-- v1.12.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix', 'scraper', 'get_url_base() normalisiert Schema auf https – verhindert doppeltes Crawlen bei HTTP→HTTPS-Redirects', 'a74b31af', 1 FROM changelog WHERE version = '1.12.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix', 'scraper', 'extract_pdf_text: httpx.Client im Worker-Thread erstellt (kein SSL-Blocking im Main-Thread)',        'a74b31af', 2 FROM changelog WHERE version = '1.12.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix', 'scraper', '_safe_get fängt alle Exceptions (SSLError, RemoteProtocolError) ab',                               'a74b31af', 3 FROM changelog WHERE version = '1.12.0';

-- v1.13.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper',  'RAM-Speicherleck: soup und resp nach Link-Extraktion sofort gelöscht (del soup / del resp)',                       '4aed4031', 1 FROM changelog WHERE version = '1.13.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'crawler',  'html_pages + pdf_pages vor LLM-Call freigegeben (˜4 GB RAM gespart)',                                            '4aed4031', 2 FROM changelog WHERE version = '1.13.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper',  'resp.text einmalig in raw_html Variable gespeichert – verhindert gleichzeitiges content + text + DOM im RAM',    '4aef7f3b', 3 FROM changelog WHERE version = '1.13.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper',  'Domain-Redirect-Guard: EXTERNAL_REDIRECT-Erkennung nach erstem Request (vestenbergsgreuth.de-Fall)',              '1c29c4ff', 4 FROM changelog WHERE version = '1.13.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper',  'MAX_QUEUE=300: begrenzt URL-Queue gegen unkontrolliertes Anwachsen (OOM-Hauptursache)',                          '05461ff1', 5 FROM changelog WHERE version = '1.13.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper',  'visited_full-Trim bei >2000 Einträgen: Reset auf visited_base spart RAM',                                      '05461ff1', 6 FROM changelog WHERE version = '1.13.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'scraper',  'RAM-Warn-Logger: Warnung ab 400 MB RSS mit queue/visited-Größen (Debugging-Hilfe)',                            '05461ff1', 7 FROM changelog WHERE version = '1.13.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper',  'psutil ersetzt unix-only resource-Modul (plattformübergreifende RAM-Überwachung)',                            '22221f12', 8 FROM changelog WHERE version = '1.13.0';

-- v1.14.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'eval',    'Neues Modul crawler_eval/ für parallelen Modellvergleich mehrerer LLMs',                              '95b3f865', 1 FROM changelog WHERE version = '1.14.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'eval',    'eval_config.py: alle stabilen Telekom-API-Modelle ohne WARN-Präfix aktiviert',                       'c336c5d3', 2 FROM changelog WHERE version = '1.14.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Neues Modul crawler_js/: Playwright-Fallback für JS-gerenderte Seiten (scraper_js.py)',             '40a00970', 3 FROM changelog WHERE version = '1.14.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'config_js.py: alle JS-Rendering-Parameter konfigurierbar (js_rendering, js_min_chars, js_timeout)', '40a00970', 4 FROM changelog WHERE version = '1.14.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Playwright blockiert Bilder/Fonts/Media für schnelleres JS-Rendering (Ressourcen-Filter)',          '40a00970', 5 FROM changelog WHERE version = '1.14.0';

-- v1.15.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'scraper', '_is_vg_redirect(): erkennt VG-Sammelseiten-Redirects anhand Gemeindeslug im Zielpfad',                        '8ac906b9', 1 FROM changelog WHERE version = '1.15.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'scraper', 'effective_start_path-Filter: nur Links unterhalb des Gemeinde-Subpfads werden gecrawlt',                      '8ac906b9', 2 FROM changelog WHERE version = '1.15.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'config',  'vg_max_queue=80 in CONFIG: reduziertes Queue-Limit bei VG-Redirects verhindert VG-Übercrawling',              '8ac906b9', 3 FROM changelog WHERE version = '1.15.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper', 'Browser-like User-Agent für httpx.Client (http_user_agent): behebt 503-Blocking durch TYPO3-Proxies',        '6021ab6e', 4 FROM changelog WHERE version = '1.15.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'scraper', 'Munningen (TYPO3 308-Redirect über vg-oettingen.de) wird jetzt korrekt gecrawlt',                           '6021ab6e', 5 FROM changelog WHERE version = '1.15.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'config',  'http_user_agent als zentraler CONFIG-Parameter in config_js.py',                                              '6021ab6e', 6 FROM changelog WHERE version = '1.15.0';


-- ============================================================
-- FERTIG
-- Nur changelog + changelog_items befüllt.
-- crawl_targets und crawl_results wurden NICHT angefasst.
-- Versionen: 21 (0.1.0 – 1.15.0) | Items: 75
-- ============================================================
