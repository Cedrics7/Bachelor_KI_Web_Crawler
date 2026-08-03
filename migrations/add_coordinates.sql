-- ============================================================
-- add_coordinates.sql
-- Fügt Koordinaten-Felder zu crawl_results hinzu.
-- geo_level: 'street' = Straße gefunden, 'city' = nur Ort
-- Ausführen: psql -U <user> -d <db> -f migrations/add_coordinates.sql
-- ============================================================

ALTER TABLE crawl_results
    ADD COLUMN IF NOT EXISTS lat       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS lng       DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS geo_level TEXT CHECK (geo_level IN ('street', 'city'));

CREATE INDEX IF NOT EXISTS idx_crawl_results_coords
    ON crawl_results(lat, lng) WHERE lat IS NOT NULL;

COMMENT ON COLUMN crawl_results.lat       IS 'Breitengrad (Nominatim)';
COMMENT ON COLUMN crawl_results.lng       IS 'Längengrad (Nominatim)';
COMMENT ON COLUMN crawl_results.geo_level IS 'Präzision: street = Straße, city = nur Ort';
