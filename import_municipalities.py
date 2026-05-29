"""
import_municipalities.py
Liest municipalities_final_master.csv und importiert alle Zeilen in crawl_targets.
Spalten CSV: Organisation;Internetadresse;AGS;Typ;PLZ;Landkreis;Bundesland
Ausführen: python import_municipalities.py
"""

import csv
from dotenv import load_dotenv
from crawler.database import get_db_connection

load_dotenv()

CSV_FILE = "municipalities_final_master.csv"


def import_municipalities():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Fehlerhaften Header-Eintrag aus vorherigem Import löschen
    cursor.execute("DELETE FROM crawl_targets WHERE ags = 'AGS'")
    conn.commit()

    inserted = 0
    skipped = 0
    errors = 0

    with open(CSV_FILE, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter=";")
        next(reader)  # Header-Zeile überspringen
        for i, row in enumerate(reader, start=2):
            if len(row) < 7:
                print(f"  Zeile {i} übersprungen (zu wenig Spalten): {row}")
                skipped += 1
                continue

            ort, url, ags, typ, plz, landkreis, bundesland = (
                row[0].strip(),
                row[1].strip(),
                row[2].strip(),
                row[3].strip(),
                row[4].strip(),
                row[5].strip(),
                row[6].strip(),
            )

            if not ags or not url:
                print(f"  Zeile {i} übersprungen (AGS oder URL leer): {row}")
                skipped += 1
                continue

            try:
                cursor.execute("""
                    INSERT INTO crawl_targets (ort, url, ags, typ, plz, landkreis, bundesland)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (ags) DO UPDATE SET
                        ort        = EXCLUDED.ort,
                        url        = EXCLUDED.url,
                        typ        = EXCLUDED.typ,
                        plz        = EXCLUDED.plz,
                        landkreis  = EXCLUDED.landkreis,
                        bundesland = EXCLUDED.bundesland
                """, (ort, url, ags, typ, plz, landkreis, bundesland))
                inserted += 1
            except Exception as e:
                print(f"  Fehler in Zeile {i} ({ags}): {e}")
                errors += 1

    conn.commit()
    cursor.close()
    conn.close()

    print(f"\n Import abgeschlossen:")
    print(f"   Importiert / aktualisiert : {inserted}")
    print(f"   Übersprungen             : {skipped}")
    print(f"   Fehler                   : {errors}")


if __name__ == "__main__":
    import_municipalities()
