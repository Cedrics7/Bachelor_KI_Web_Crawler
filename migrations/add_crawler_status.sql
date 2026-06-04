-- ============================================================
-- add_crawler_status.sql
-- Neue Tabelle: crawler_status
-- Speichert den Live-Status des Crawlers (aktiv/inaktiv).
-- Der Crawler schreibt regelmäßig einen Heartbeat-Timestamp.
-- Das Dashboard liest den Status über die View crawler_status_view.
-- ============================================================

CREATE TABLE IF NOT EXISTS crawler_status (
    id               SERIAL PRIMARY KEY,
    status           VARCHAR(20)  NOT NULL DEFAULT 'inaktiv'
                         CHECK (status IN ('aktiv', 'inaktiv')),
    last_heartbeat   TIMESTAMP WITHOUT TIME ZONE,
    started_at       TIMESTAMP WITHOUT TIME ZONE,
    stopped_at       TIMESTAMP WITHOUT TIME ZONE,
    current_target   TEXT,
    heartbeat_timeout_seconds  INTEGER NOT NULL DEFAULT 60
);

-- Nur eine Zeile erlaubt (Singleton-Pattern)
CREATE UNIQUE INDEX IF NOT EXISTS idx_crawler_status_singleton
    ON crawler_status ((TRUE));

-- Initialer Datensatz
INSERT INTO crawler_status (status, heartbeat_timeout_seconds)
VALUES ('inaktiv', 60)
ON CONFLICT DO NOTHING;

-- View: gibt den Status zurück und berechnet 'inaktiv' dynamisch
-- falls der letzte Heartbeat zu lange her ist.
CREATE OR REPLACE VIEW crawler_status_view AS
SELECT
    id,
    CASE
        WHEN status = 'aktiv'
         AND last_heartbeat IS NOT NULL
         AND EXTRACT(EPOCH FROM (NOW() - last_heartbeat)) > heartbeat_timeout_seconds
        THEN 'inaktiv'
        ELSE status
    END AS status,
    last_heartbeat,
    started_at,
    stopped_at,
    current_target,
    heartbeat_timeout_seconds,
    CASE
        WHEN last_heartbeat IS NOT NULL
        THEN EXTRACT(EPOCH FROM (NOW() - last_heartbeat))::INTEGER
        ELSE NULL
    END AS seconds_since_heartbeat
FROM crawler_status
LIMIT 1;
