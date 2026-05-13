-- =====================================================================
-- Migration: region_mapping
-- Verknüpft Bundesländer (aus crawl_targets.bundesland) mit Regionen.
-- Geplante Regionen: Nord, Ost, West, Südwest, Süd
-- =====================================================================

CREATE TABLE IF NOT EXISTS region_mapping (
    bundesland  TEXT PRIMARY KEY,
    region      TEXT NOT NULL
);

-- ---------------------------------------------------------------------
-- Nord: Schleswig-Holstein, Hamburg, Bremen, Niedersachsen
-- ---------------------------------------------------------------------
INSERT INTO region_mapping (bundesland, region) VALUES
    ('Schleswig-Holstein', 'Nord'),
    ('Hamburg',            'Nord'),
    ('Bremen',             'Nord'),
    ('Niedersachsen',      'Nord')
ON CONFLICT (bundesland) DO UPDATE SET region = EXCLUDED.region;

-- ---------------------------------------------------------------------
-- Ost: Brandenburg, Berlin, Mecklenburg-Vorpommern,
--      Sachsen, Sachsen-Anhalt, Thüringen
-- (noch nicht aktiv – bei Bedarf einkommentieren)
-- ---------------------------------------------------------------------
-- INSERT INTO region_mapping (bundesland, region) VALUES
--     ('Brandenburg',           'Ost'),
--     ('Berlin',                'Ost'),
--     ('Mecklenburg-Vorpommern','Ost'),
--     ('Sachsen',               'Ost'),
--     ('Sachsen-Anhalt',        'Ost'),
--     ('Thüringen',             'Ost')
-- ON CONFLICT (bundesland) DO UPDATE SET region = EXCLUDED.region;

-- ---------------------------------------------------------------------
-- West: Nordrhein-Westfalen, Rheinland-Pfalz, Saarland, Hessen
-- (noch nicht aktiv – bei Bedarf einkommentieren)
-- ---------------------------------------------------------------------
-- INSERT INTO region_mapping (bundesland, region) VALUES
--     ('Nordrhein-Westfalen', 'West'),
--     ('Rheinland-Pfalz',     'West'),
--     ('Saarland',            'West'),
--     ('Hessen',              'West')
-- ON CONFLICT (bundesland) DO UPDATE SET region = EXCLUDED.region;

-- ---------------------------------------------------------------------
-- Südwest: Baden-Württemberg
-- (noch nicht aktiv – bei Bedarf einkommentieren)
-- ---------------------------------------------------------------------
-- INSERT INTO region_mapping (bundesland, region) VALUES
--     ('Baden-Württemberg', 'Südwest')
-- ON CONFLICT (bundesland) DO UPDATE SET region = EXCLUDED.region;

-- ---------------------------------------------------------------------
-- Süd: Bayern
-- (noch nicht aktiv – bei Bedarf einkommentieren)
-- ---------------------------------------------------------------------
-- INSERT INTO region_mapping (bundesland, region) VALUES
--     ('Bayern', 'Süd')
-- ON CONFLICT (bundesland) DO UPDATE SET region = EXCLUDED.region;

-- ---------------------------------------------------------------------
-- Hilfreiche Views & Queries
-- ---------------------------------------------------------------------

-- Alle Targets mit ihrer Region anzeigen:
-- SELECT ct.ort, ct.bundesland, rm.region
-- FROM crawl_targets ct
-- LEFT JOIN region_mapping rm ON ct.bundesland = rm.bundesland
-- ORDER BY rm.region, ct.bundesland, ct.ort;

-- Alle Funde gruppiert nach Region:
-- SELECT rm.region, COUNT(*) AS funde
-- FROM crawl_results cr
-- JOIN crawl_targets ct  ON cr.ags = ct.ags
-- JOIN region_mapping rm ON ct.bundesland = rm.bundesland
-- GROUP BY rm.region
-- ORDER BY rm.region;
