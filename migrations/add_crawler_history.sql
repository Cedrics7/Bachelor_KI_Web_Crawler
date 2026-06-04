-- ============================================================
-- add_crawler_history.sql
-- Neue Tabelle: crawler_history
-- Ersetzt crawler_history.txt – Eintraege werden in der DB
-- gespeichert und automatisch auf MAX_ROWS begrenzt.
-- Einmalig ausfuehren: psql -d <db> -f add_crawler_history.sql
-- ============================================================

CREATE TABLE IF NOT EXISTS crawler_history (
    id         SERIAL PRIMARY KEY,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    event_type VARCHAR(20) NOT NULL,
    message    TEXT        NOT NULL
);

-- Index fuer schnelles Sortieren
CREATE INDEX IF NOT EXISTS idx_crawler_history_created_at
    ON crawler_history (created_at DESC);
