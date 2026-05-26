-- ============================================================
-- setup_database.sql
-- Komplette PostgreSQL-Datenbankstruktur für Bachelor_KI_Web_Crawler
-- STRUKTURAUFBAU: Löscht alle Tabellen und erstellt sie neu.
-- KEIN Seed/Import – für Daten: migration_changelog.sql ausführen.
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
-- FERTIG
-- Tabellen: crawl_targets, crawl_results, changelog, changelog_items
-- Indexes:  9 Stück
-- Seed:     keiner – migration_changelog.sql ausführen
-- ============================================================
