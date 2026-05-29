-- Migration: content_hash von crawl_results nach crawl_targets verschieben
-- Einmalig ausfuehren!

-- 1. Neue Spalte in crawl_targets anlegen
ALTER TABLE crawl_targets ADD COLUMN IF NOT EXISTS content_hash TEXT;

-- 2. Spalte aus crawl_results entfernen (optional, aber empfohlen)
-- ALTER TABLE crawl_results DROP COLUMN IF EXISTS content_hash;
