-- ============================================================
-- migration_changelog.sql
-- Changelog-Datenbank für Bachelor_KI_Web_Crawler Dashboard
-- Abgeleitet aus echtem GitHub-Commit-Verlauf (Cedrics7)
-- ============================================================

CREATE TABLE IF NOT EXISTS changelog (
    id          SERIAL PRIMARY KEY,
    version     VARCHAR(20) NOT NULL UNIQUE,
    release_date DATE        NOT NULL,
    title       VARCHAR(255) NOT NULL,
    description TEXT,
    commit_sha  VARCHAR(40),
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS changelog_items (
    id           SERIAL PRIMARY KEY,
    changelog_id INTEGER     NOT NULL REFERENCES changelog(id) ON DELETE CASCADE,
    type         VARCHAR(20) NOT NULL CHECK (type IN ('feat','fix','refactor','chore','docs','style','perf')),
    scope        VARCHAR(50),
    message      TEXT        NOT NULL,
    commit_sha   VARCHAR(40),
    sort_order   SMALLINT    DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_changelog_release_date ON changelog(release_date DESC);
CREATE INDEX IF NOT EXISTS idx_changelog_items_fk      ON changelog_items(changelog_id);

-- ============================================================
-- SEED DATA — aus echtem GitHub-Verlauf
-- ============================================================

INSERT INTO changelog (version, release_date, title, description, commit_sha) VALUES
('0.1.0', '2026-04-28', 'Projekt-Init',          'Erstes grundlegendes Programm, Repository-Setup', '7bebcdff64a3031edc292c8dd098250c2fbb08ad'),
('0.2.0', '2026-04-29', 'Erweiterung Basis',      'Grundlegendes Programm weiterentwickelt, erste Modul-Struktur', '618d2e3888cdfe9f0c6f07b81cb33538e7ea81de'),
('0.3.0', '2026-04-29', 'KI-Integration Alpha',   'Erster KI-WebCrawler mit Gemini API Key', 'bd8547e6ebd7879953ba534f23445b1fe4380c92'),
('0.4.0', '2026-04-29', 'KI-Integration Beta',    'API-Key-Handling stabilisiert, erste Crawl-Ergebnisse', 'c9a368850920e1ce3b6a26b561079f77c310baed'),
('0.5.0', '2026-04-30', 'KI-Crawler Refactor',    'Refactoring der KI-Logik, verbessertes Prompt-Handling', 'fdbd1c87bc32d98337d8dc5d81e9293daaf6ddc6'),
('1.0.0', '2026-05-04', 'Architektur-Redesign',   'Neuer Ansatz: komplette Umstrukturierung der Backend-Architektur, FastAPI-Basis', 'c1870228aecabad16515c07f83c9db0d1c750261'),
('1.1.0', '2026-05-05', 'Dashboard-Grundlage',    'Erste statische Dashboard-Dateien, Frontend-Skeleton', 'a6e9ea598e0a8f9e8c868674673256b35e70c625'),
('1.2.0', '2026-05-07', 'Dashboard Telekom-Stil', 'Dashboard-Prototyp im Telekom-Design, Crawler Beta eingebunden', 'b0cf314d3d940f3cbf85980d00aa8e08cad0d90b'),
('1.3.0', '2026-05-09', 'JS-Frontend vollwertig', 'Vollständige JavaScript-Auslagerung, Telekom-Frontend fast komplett, Router-Grundlage', 'a6cc9b2105b17fb7b73018b4a3850c79f1d0934f'),
('1.4.0', '2026-05-11', 'Filter, Footer & Changelog-DB', 'Filter-Logik verbessert, Heartbeat-Thread, Footer-Prototyp, Changelog-API-Endpoint und DB-Migration', '95f3238187cea3d9800b82075157dc791162c77a');

-- ============================================================
-- ITEMS für v0.1.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore', 'project',  'Repository initialisiert, grundlegende Projektstruktur angelegt', '7bebcdff', 1 FROM changelog WHERE version = '0.1.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler',   'Erstes Crawler-Grundgerüst mit HTTP-Request-Logik', '7bebcdff', 2 FROM changelog WHERE version = '0.1.0';

-- ============================================================
-- ITEMS für v0.2.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler',   'URL-Queue und einfache Link-Extraktion implementiert', '618d2e38', 1 FROM changelog WHERE version = '0.2.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore', 'structure','Modul-Aufteilung vorbereitet', '618d2e38', 2 FROM changelog WHERE version = '0.2.0';

-- ============================================================
-- ITEMS für v0.3.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'ai',        'Gemini API Key Integration (google-generativeai)', 'bd8547e6', 1 FROM changelog WHERE version = '0.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler',   'KI-gestützte Inhaltsanalyse erster Crawl-Ergebnisse', 'bd8547e6', 2 FROM changelog WHERE version = '0.3.0';

-- ============================================================
-- ITEMS für v0.4.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',  'ai',        'API-Key-Fehlerbehandlung verbessert (env-Variable)', 'c9a36885', 1 FROM changelog WHERE version = '0.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat', 'crawler',   'Crawl-Ergebnisse strukturiert gespeichert', 'c9a36885', 2 FROM changelog WHERE version = '0.4.0';

-- ============================================================
-- ITEMS für v0.5.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'ai',    'Prompt-Handling ausgelagert, wiederverwendbare KI-Funktion', 'fdbd1c87', 1 FROM changelog WHERE version = '0.5.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'perf',  'crawler',  'Crawl-Tiefe konfigurierbar gemacht', 'fdbd1c87', 2 FROM changelog WHERE version = '0.5.0';

-- ============================================================
-- ITEMS für v1.0.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'backend', 'Komplette Neustrukturierung: FastAPI als Basis eingeführt', 'c1870228', 1 FROM changelog WHERE version = '1.0.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'api',       'REST-Endpunkte für Crawler-Steuerung (start/stop/status)', 'c1870228', 2 FROM changelog WHERE version = '1.0.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore', 'deps',      'requirements.txt aktualisiert (fastapi, uvicorn, httpx)', '15b6a50d', 3 FROM changelog WHERE version = '1.0.0';

-- ============================================================
-- ITEMS für v1.1.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'frontend',  'Statische Dashboard-HTML/CSS Grunddateien erstellt', 'a6e9ea59', 1 FROM changelog WHERE version = '1.1.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'chore', 'structure', 'Frontend- und Backend-Ordner sauber getrennt', 'a6e9ea59', 2 FROM changelog WHERE version = '1.1.0';

-- ============================================================
-- ITEMS für v1.2.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'frontend',  'Dashboard-Design an Telekom Corporate Design angenähert (Magenta, T-Logo)', 'b0cf314d', 1 FROM changelog WHERE version = '1.2.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'crawler',   'Crawler-Beta in Dashboard-Status integriert', 'b0cf314d', 2 FROM changelog WHERE version = '1.2.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'style', 'ui',        'Erste Statusanzeige (aktiv/inaktiv) im Header', '8cf0fd33', 3 FROM changelog WHERE version = '1.2.0';

-- ============================================================
-- ITEMS für v1.3.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'frontend', 'HTML → vollständige JavaScript-Auslagerung (ES Modules)', 'a6cc9b21', 1 FROM changelog WHERE version = '1.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'router',     'Client-seitiges Router-Grundgerüst (SPA-Navigation)', 'a6cc9b21', 2 FROM changelog WHERE version = '1.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'api',        'Neues Dashboard: Live-Daten-Anbindung über fetch()', '497f6f13', 3 FROM changelog WHERE version = '1.3.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'style', 'ui',         'Telekom-Frontend fast vollständig: Topbar, Cards, Tabellen', 'a6cc9b21', 4 FROM changelog WHERE version = '1.3.0';

-- ============================================================
-- ITEMS für v1.4.0
-- ============================================================
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',   'filter',     'Filter-Logik für Crawler-Ergebnisse grundlegend verbessert (zwei Iterationen)', 'd2622181', 1 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'crawler',    'Heartbeat-Thread: crawler_live_status.json alle 30s aktualisiert', '47892ba3', 2 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'refactor', 'frontend','Auslagerung und Umstrukturierung (render.js / api.js Trennung)', '2d5be1b7', 3 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'footer',     'Footer-Prototyp: schlichte Magenta-Linie, native SVG-Icons, Version-Badge', '0f79018b', 4 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'db',         'changelog + changelog_items Tabellen angelegt (PostgreSQL)', '95f3238', 5 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'feat',  'api',        'GET /api/changelog Endpoint: Versionen mit Items aus DB, absteigend sortiert', '95f3238', 6 FROM changelog WHERE version = '1.4.0';
INSERT INTO changelog_items (changelog_id, type, scope, message, commit_sha, sort_order)
SELECT id, 'fix',   'ui',         'Perfektions-Pass: Abstände, Konsistenz, Lesbarkeit', '6616c15', 7 FROM changelog WHERE version = '1.4.0';