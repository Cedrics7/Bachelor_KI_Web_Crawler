-- =============================================================
-- Migration: changelog Tabellen
-- Ausführen mit: psql -U <user> -d <db> -f migration_changelog.sql
-- =============================================================

CREATE TABLE IF NOT EXISTS changelog (
    id           SERIAL       PRIMARY KEY,
    version      VARCHAR(20)  NOT NULL UNIQUE,
    released_at  DATE         NOT NULL DEFAULT CURRENT_DATE,
    summary      TEXT,
    is_current   BOOLEAN      NOT NULL DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS changelog_items (
    id           SERIAL       PRIMARY KEY,
    changelog_id INTEGER      NOT NULL REFERENCES changelog(id) ON DELETE CASCADE,
    tag          VARCHAR(20)  NOT NULL CHECK (tag IN ('new', 'fix', 'improve')),
    description  TEXT         NOT NULL,
    sort_order   SMALLINT     NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_changelog_current ON changelog (is_current);
CREATE INDEX IF NOT EXISTS idx_changelog_items_fk ON changelog_items (changelog_id);

CREATE OR REPLACE FUNCTION set_single_current_changelog()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.is_current = TRUE THEN
        UPDATE changelog SET is_current = FALSE WHERE id <> NEW.id;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_single_current ON changelog;
CREATE TRIGGER trg_single_current
    BEFORE INSERT OR UPDATE ON changelog
    FOR EACH ROW EXECUTE FUNCTION set_single_current_changelog();

-- Seed-Daten
INSERT INTO changelog (version, released_at, is_current) VALUES
    ('0.1.0', '2026-04-28', FALSE),
    ('0.2.0', '2026-04-29', FALSE),
    ('0.3.0', '2026-04-30', FALSE),
    ('0.4.0', '2026-05-04', FALSE),
    ('1.0.0', '2026-05-05', FALSE),
    ('1.1.0', '2026-05-08', FALSE),
    ('1.2.0', '2026-05-11', FALSE),
    ('1.3.0', '2026-05-11', FALSE),
    ('1.4.0', '2026-05-11', TRUE)
ON CONFLICT (version) DO NOTHING;

WITH v AS (SELECT id, version FROM changelog)
INSERT INTO changelog_items (changelog_id, tag, description, sort_order)
SELECT v.id, i.tag, i.description, i.sort_order FROM v
JOIN (VALUES
    ('0.1.0','new','Initiales Commit: Grundlegendes Programm-Gerüst',0),
    ('0.2.0','new','Grundlegendes Crawler-Programm',0),
    ('0.2.0','new','PostgreSQL-Datenbankanbindung (crawl_targets, crawl_results)',1),
    ('0.2.0','new','BeautifulSoup HTML-Parser',2),
    ('0.2.0','new','crawler_history.txt und crawler_live_status.json Logging',3),
    ('0.3.0','new','Gemini AI Integration für Textanalyse',0),
    ('0.3.0','new','API-Key Management über .env',1),
    ('0.3.0','new','TokenManager für Gemini Rate-Limit-Schutz (RPM/TPM/RPD)',2),
    ('0.3.0','improve','Crawler-Konfiguration zentralisiert (CONFIG-Dict)',3),
    ('0.4.0','new','Neuer Crawler-Ansatz mit verbesserter Subpage-Erkennung',0),
    ('0.4.0','new','PDF-Analyse mit PyMuPDF (fitz) integriert',1),
    ('0.4.0','improve','Hash-basierte Duplikaterkennung (SHA-256)',2),
    ('1.0.0','new','Erstes Dashboard (Prototyp-Versuch)',0),
    ('1.0.0','new','FastAPI Backend mit PostgreSQL-Anbindung',1),
    ('1.0.0','new','Initiale Scale Design System Integration',2),
    ('1.1.0','new','Neues Dashboard mit Telekom Scale-Komponenten',0),
    ('1.1.0','new','Bestandsdaten-Tabelle mit Suche und Status-Filter',1),
    ('1.1.0','new','Bewegungsdaten-Tabelle mit Bundesland/Kategorie-Filter',2),
    ('1.1.0','new','Monitoring-Seite mit Live-Status und Crawler-History',3),
    ('1.1.0','new','Detail-Modal für Einzelansicht',4),
    ('1.1.0','new','Pagination für alle Tabellen',5),
    ('1.1.0','improve','Dashboard-Annäherung an Telekom Brand-Design',6),
    ('1.2.0','new','CSS in separate Module ausgelagert (tokens, base, components, layout)',0),
    ('1.2.0','new','Theme-Toggle mit animiertem Icon (schwarz/weiß)',1),
    ('1.2.0','new','Vollwertiges JavaScript Telekom-Frontend mit Scale Design System',2),
    ('1.2.0','new','URL-basierter Router mit pushState (page, id, filter, pagination)',3),
    ('1.2.0','improve','Verlinkung der Seiten verbessert',4),
    ('1.3.0','fix','Filter reagieren jetzt auf Light/Dark Mode',0),
    ('1.3.0','fix','Icons für Quelle/Aktion-Buttons (Inline-SVG)',1),
    ('1.3.0','fix','API-Pfade korrigiert (/api/-Prefix für alle Endpoints)',2),
    ('1.3.0','fix','Monitoring-Felder korrekt auf api.py Response gemappt',3),
    ('1.3.0','improve','Fehlerbehebung und Umstrukturierung der JS-Module',4),
    ('1.3.0','improve','Filter-Logik verbessert (bundesland, kategorie Parameter)',5),
    ('1.4.0','new','Footer mit Copyright, Versions-Button und Seitenanfang',0),
    ('1.4.0','new','Versionsverlauf-Seite mit Changelog-Datenbanktabelle',1),
    ('1.4.0','new','API-Endpoint GET /api/changelog',2),
    ('1.4.0','fix','Heartbeat-Thread: crawler_live_status.json alle 30s aktualisiert',3),
    ('1.4.0','fix','Monitoring-Refresh: dedizierter Start/Stop beim Navigieren',4),
    ('1.4.0','fix','Modal-Close: scale-close-Event entfernt ?id= korrekt aus URL',5),
    ('1.4.0','fix','Timestamp-Format ISO 8601 (T-Separator) für alle Browser',6)
) AS i(version, tag, description, sort_order) ON v.version = i.version;
