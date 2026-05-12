-- ============================================================
-- setup_database.sql
-- Komplette PostgreSQL-Datenbankstruktur für Bachelor_KI_Web_Crawler
-- REINER IMPORT: Löscht alle Tabellen und baut sie komplett neu auf.
-- Ausführen: psql -U <user> -d <db> -f setup_database.sql
-- ============================================================


-- ============================================================
-- 1. ERWEITERUNGEN
-- ============================================================
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";


-- ============================================================
-- 2. TABELLEN LÖSCHEN (sauberer Neustart, Reihenfolge beachten)
-- ============================================================
DROP TABLE IF EXISTS changelog_items  CASCADE;
DROP TABLE IF EXISTS changelog        CASCADE;
DROP TABLE IF EXISTS crawl_results    CASCADE;
DROP TABLE IF EXISTS crawl_targets    CASCADE;


-- ============================================================
-- 3. crawl_targets
-- Enthält alle zu crawlenden Kommunen (Bestandsdaten)
-- ============================================================
CREATE TABLE crawl_targets (
    id           SERIAL PRIMARY KEY,
    url          TEXT        NOT NULL,
    ort          TEXT        NOT NULL,
    typ          TEXT,
    ags          TEXT        NOT NULL UNIQUE,
    plz          TEXT,
    landkreis    TEXT,
    bundesland   TEXT,
    last_scanned TIMESTAMP WITHOUT TIME ZONE
);

CREATE INDEX idx_crawl_targets_ags          ON crawl_targets(ags);
CREATE INDEX idx_crawl_targets_last_scanned ON crawl_targets(last_scanned ASC NULLS FIRST);
CREATE INDEX idx_crawl_targets_bundesland   ON crawl_targets(bundesland);


-- ============================================================
-- 4. crawl_results
-- Enthält alle gefundenen Baumaßnahmen (Bewegungsdaten)
-- ============================================================
CREATE TABLE crawl_results (
    id               SERIAL PRIMARY KEY,
    ags              CHARACTER VARYING(20) NOT NULL REFERENCES crawl_targets(ags) ON DELETE CASCADE,
    start_time       TIMESTAMP WITHOUT TIME ZONE,
    end_time         TIMESTAMP WITHOUT TIME ZONE,
    status           CHARACTER VARYING(50),
    gefundene_links  INTEGER,
    massnahme        TEXT,
    adresse          TEXT,
    gefunden_am      DATE,
    kategorie        TEXT,
    massnahme_start  DATE,
    massnahme_ende   DATE,
    massnahme_url    TEXT,
    content_hash     CHARACTER VARYING(64)
);

CREATE INDEX idx_crawl_results_ags          ON crawl_results(ags);
CREATE INDEX idx_crawl_results_gefunden_am  ON crawl_results(gefunden_am DESC);
CREATE INDEX idx_crawl_results_kategorie    ON crawl_results(kategorie);
CREATE INDEX idx_crawl_results_content_hash ON crawl_results(content_hash);
CREATE INDEX idx_crawl_results_massn_ende   ON crawl_results(massnahme_ende);
CREATE INDEX idx_crawl_results_end_time     ON crawl_results(end_time DESC);


-- ============================================================
-- 5. changelog
-- Versionsverlauf des Dashboards
-- ============================================================
CREATE TABLE changelog (
    id           SERIAL PRIMARY KEY,
    version      CHARACTER VARYING(20)  NOT NULL UNIQUE,
    release_date DATE                   NOT NULL,
    title        CHARACTER VARYING(255) NOT NULL,
    description  TEXT,
    commit_sha   CHARACTER VARYING(40),
    created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_changelog_release_date ON changelog(release_date DESC);


-- ============================================================
-- 6. changelog_items
-- Einzelne Änderungseinträge pro Version
-- ============================================================
CREATE TABLE changelog_items (
    id           SERIAL PRIMARY KEY,
    changelog_id INTEGER               NOT NULL REFERENCES changelog(id) ON DELETE CASCADE,
    type         CHARACTER VARYING(20) NOT NULL CHECK (type IN ('feat','fix','refactor','chore','docs','style','perf')),
    scope        CHARACTER VARYING(50),
    message      TEXT                  NOT NULL,
    commit_sha   CHARACTER VARYING(40),
    sort_order   SMALLINT DEFAULT 0
);

CREATE INDEX idx_changelog_items_fk ON changelog_items(changelog_id);


-- ============================================================
-- 7. SEED-DATEN: changelog-Versionen
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
    'c296addbc53a594c1fe8e15de5789ceaa6895fe8');


-- ============================================================
-- 8. SEED-DATEN: changelog_items
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
SELECT id, 'feat', 'ai',      'Gemini API Key Integration (google-generativeai)',         'bd8547e6', 1 FROM changelog WHERE version = '0.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'KI-gestützte Inhaltsanalyse erster Crawl-Ergebnisse',     'bd8547e6', 2 FROM changelog WHERE version = '0.3.0';

-- v0.4.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'ai',      'API-Key-Fehlerbehandlung verbessert (env-Variable)',       'c9a36885', 1 FROM changelog WHERE version = '0.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Crawl-Ergebnisse strukturiert gespeichert',                'c9a36885', 2 FROM changelog WHERE version = '0.4.0';

-- v0.5.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'ai',      'Prompt-Handling ausgelagert, wiederverwendbare KI-Funktion', 'fdbd1c87', 1 FROM changelog WHERE version = '0.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'perf',     'crawler', 'Crawl-Tiefe konfigurierbar gemacht',                          'fdbd1c87', 2 FROM changelog WHERE version = '0.5.0';

-- v1.0.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'backend', 'Komplette Neustrukturierung: FastAPI als Basis eingeführt',           'c1870228', 1 FROM changelog WHERE version = '1.0.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'api',     'REST-Endpunkte für Crawler-Steuerung (start/stop/status)',            'c1870228', 2 FROM changelog WHERE version = '1.0.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore',    'deps',    'requirements.txt aktualisiert (fastapi, uvicorn, httpx)',              '15b6a50d', 3 FROM changelog WHERE version = '1.0.0';

-- v1.1.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'frontend',  'Statische Dashboard-HTML/CSS Grunddateien erstellt',    'a6e9ea59', 1 FROM changelog WHERE version = '1.1.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore', 'structure', 'Frontend- und Backend-Ordner sauber getrennt',           'a6e9ea59', 2 FROM changelog WHERE version = '1.1.0';

-- v1.2.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'frontend', 'Dashboard-Design an Telekom Corporate Design angenähert (Magenta, T-Logo)', 'b0cf314d', 1 FROM changelog WHERE version = '1.2.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'crawler',  'Crawler-Beta in Dashboard-Status integriert',                              'b0cf314d', 2 FROM changelog WHERE version = '1.2.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'style', 'ui',       'Erste Statusanzeige (aktiv/inaktiv) im Header',                           '8cf0fd33', 3 FROM changelog WHERE version = '1.2.0';

-- v1.3.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'frontend', 'HTML → vollständige JavaScript-Auslagerung (ES Modules)',   'a6cc9b21', 1 FROM changelog WHERE version = '1.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'router',   'Client-seitiges Router-Grundgerüst (SPA-Navigation)',     'a6cc9b21', 2 FROM changelog WHERE version = '1.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'api',      'Neues Dashboard: Live-Daten-Anbindung über fetch()',      '497f6f13', 3 FROM changelog WHERE version = '1.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'style',    'ui',       'Telekom-Frontend fast vollständig: Topbar, Cards, Tabellen','a6cc9b21', 4 FROM changelog WHERE version = '1.3.0';

-- v1.4.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'filter',   'Filter-Logik für Crawler-Ergebnisse grundlegend verbessert',            'd2622181', 1 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'crawler',  'Heartbeat-Thread: crawler_live_status.json alle 10s aktualisiert',       '47892ba3', 2 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'frontend', 'Auslagerung und Umstrukturierung (render.js / api.js Trennung)',          '2d5be1b7', 3 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'footer',   'Footer: SVG-Icons, Version-Badge, Changelog-Button',                     '0f79018b', 4 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'db',       'changelog + changelog_items Tabellen angelegt (PostgreSQL)',              '95f3238',  5 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'api',      'GET /api/changelog Endpoint: Versionen mit Items aus DB',                '95f3238',  6 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'ui',       'Perfektions-Pass: Abstände, Konsistenz, Lesbarkeit',                      '6616c15',  7 FROM changelog WHERE version = '1.4.0';

-- v1.5.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'HTML-Seiten immer vollständig vor PDFs übernommen (Priorisierung)',                                               '1dcb749c', 1 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'PDF-Priorisierung: Bekanntmachung, Bebauungsplan, Satzung etc. werden zuerst eingebaut',                          '1dcb749c', 2 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Seitenzahl-Reduktion bei Textlimit: schrittweise 5 → 3 → 2 → 1 Seiten pro PDF',                                 '1dcb749c', 3 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Älteste PDFs zuerst verwerfen wenn auch 1 Seite nicht ausreicht (Prio-PDFs geschützt)',                           '1dcb749c', 4 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'crawler', 'Doppelte 500k-Zeichengrenze entfernt – nur noch assemble_text() kürzt',                                          '1dcb749c', 5 FROM changelog WHERE version = '1.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler', 'Warnausgabe im Terminal bei PDF-Kürzung oder -Verwerfung (mögl. Datenverlust)',                                  '1dcb749c', 6 FROM changelog WHERE version = '1.5.0';

-- v1.6.0
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'crawler', 'min_pdf_year aus CONFIG ausgelagert (war hardcoded 2024 in extract_pdf_text)',                                 'c296addb', 1 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'crawler', 'min_end_datum mit erklärendem Kommentar versehen',                                                            'c296addb', 2 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'ui',      'KPI-Karten Bewegungsdaten: Maßnahmen gesamt, diesen Monat, heute gefunden',                                    'c296addb', 3 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'ui',      'Bestandsdaten: gefunden_am zeigt jetzt Zeitstempel aus end_time-Spalte',                                       'c296addb', 4 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'style',    'ui',      'Bundesland-Filter Bestandsdaten optisch an Bewegungsdaten angeglichen',                                        'c296addb', 5 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'ui',      'Monitoring-Übersicht vollständig entfernt',                                                                    'c296addb', 6 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',      'ui',      'Auto-Refresh jetzt für alle Panels inkl. Orte-Gesamt-KPI (nicht nur Bestandsdaten)',                           'c296addb', 7 FROM changelog WHERE version = '1.6.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',     'db',      'Index idx_crawl_results_end_time hinzugefügt (Performance)',                                                   'c296addb', 8 FROM changelog WHERE version = '1.6.0';


-- ============================================================
-- FERTIG
-- Tabellen:  crawl_targets, crawl_results, changelog, changelog_items
-- Indexes:   9 Stück
-- Versionen: 12 (0.1.0 – 1.6.0)
-- Items:     38
-- ============================================================
