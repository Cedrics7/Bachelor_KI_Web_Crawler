import psycopg2
import pandas as pd
import numpy as np


def import_master_to_db(file_path):
    # Datenbank-Verbindung
    conn = psycopg2.connect(
        host="127.0.0.1",
        port="5432",
        database="bachelor_crawler",
        user="postgres",
        password=""  # <--- DEIN PASSWORT HIER
    )
    cursor = conn.cursor()

    # CSV laden
    # Wir laden alles als String, um Probleme mit führenden Nullen beim AGS zu vermeiden
    df = pd.read_csv(file_path, sep=';', encoding='utf-8-sig', dtype=str)

    # Ersetze NaN/Null Werte durch None (wird in SQL zu NULL)
    df = df.replace({np.nan: None})

    print(f"Starte Import von {len(df)} Datensätzen...")

    for i, row in df.iterrows():
        try:
            cursor.execute("""
                INSERT INTO crawl_targets (url, organisation, typ, ags, plz, landkreis, bundesland)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (ags) DO UPDATE SET 
                    url = EXCLUDED.url,
                    organisation = EXCLUDED.organisation,
                    typ = EXCLUDED.typ,
                    plz = EXCLUDED.plz,
                    landkreis = EXCLUDED.landkreis,
                    bundesland = EXCLUDED.bundesland
            """, (
                row['Internetadresse'],
                row['Organisation'],
                row['Typ'],
                row['AGS'],
                row['PLZ'],
                row['Landkreis'],
                row['Bundesland']
            ))

            # Alle 500 Zeilen ein Commit für die Performance
            if i % 500 == 0:
                conn.commit()
                print(f"{i} Zeilen verarbeitet...")

        except Exception as e:
            print(f"Fehler bei AGS {row['AGS']} ({row['Organisation']}): {e}")
            conn.rollback()

    conn.commit()
    cursor.close()
    conn.close()
    print("\n--- IMPORT ERFOLGREICH ABGESCHLOSSEN ---")


if __name__ == "__main__":
    # Pfad zu deiner eben erstellten Master-Datei
    import_master_to_db('municipalities_final_master.csv')
