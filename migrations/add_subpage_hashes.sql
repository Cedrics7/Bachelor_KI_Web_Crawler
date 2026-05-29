-- ============================================================
-- add_subpage_hashes.sql
-- Migration: subpage_hashes-Spalte in crawl_targets
-- Eingeführt in v1.7.0 (Unterseiten-Hashing + Kontext-Chunking)
-- Ausführen: psql -U <user> -d <db> -f add_subpage_hashes.sql
-- ============================================================

-- Neue JSONB-Spalte für Unterseiten-Hashes
-- Speichert ein Dict { url: sha256_hash } aller gecrawlten Unterseiten.
-- Beim nächsten Crawl-Lauf werden nur geänderte/neue Unterseiten
-- an das LLM übergeben → weniger Token-Verbrauch, schnellerer Lauf.
ALTER TABLE crawl_targets
    ADD COLUMN IF NOT EXISTS subpage_hashes JSONB;

-- Kommentar zur Spalte
COMMENT ON COLUMN crawl_targets.subpage_hashes IS
    'SHA-256-Hashes aller zuletzt gecrawlten Unterseiten/PDFs als {url: hash}-JSON. '
    'Wird nach jedem Crawl-Lauf aktualisiert. NULL = noch nie gecrawlt.';

-- ============================================================
-- FERTIG
-- Betroffene Tabelle: crawl_targets
-- Neue Spalte:        subpage_hashes JSONB (nullable)
-- ============================================================
