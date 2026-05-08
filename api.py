from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os
import json
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT")
    )


@app.get("/api/stats")
def get_stats():
    try:
        conn = get_db_connection()
        # Monatsanfang berechnen
        first_day = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # 1. Orte Gesamt
        df_total = pd.read_sql("SELECT COUNT(*) as count FROM crawl_targets", conn)
        # 2. In diesem Monat gecrawlt
        df_done = pd.read_sql(f"SELECT COUNT(*) as count FROM crawl_targets WHERE last_scanned >= '{first_day}'", conn)

        total = int(df_total['count'][0])
        done = int(df_done['count'][0])
        conn.close()

        return {
            "total": total,
            "done": done,
            "pending": total - done
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bestandsdaten")
def get_bestandsdaten():
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT id, ort, ags, bundesland, last_scanned, url FROM crawl_targets ORDER BY id ASC", conn)
        conn.close()

        # 1. Datumsobjekte zu Strings konvertieren (behebt NaT-Fehler)
        if 'last_scanned' in df.columns:
            # Wir nutzen errors='coerce', um ungültige Daten zu NaT zu machen und dann zu '-'
            df['last_scanned'] = pd.to_datetime(df['last_scanned'], errors='coerce').dt.strftime('%d.%m.%Y %H:%M').fillna('-')

        # 2. DER FIX: Alle NaN (Not a Number) durch None ersetzen
        # JSON akzeptiert None (wird zu null), aber kein NaN
        df = df.replace({pd.NA: None, float('nan'): None})
        df = df.where(pd.notnull(df), None)

        return df.to_dict(orient="records")
    except Exception as e:
        print(f"Error Bestandsdaten: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bewegungsdaten")
def get_bewegungsdaten():
    try:
        conn = get_db_connection()
        query = """
            SELECT r.massnahme, r.adresse, t.ort, r.massnahme_start, r.massnahme_ende, 
                   r.massnahme_url, t.bundesland, r.kategorie 
            FROM crawl_results r 
            LEFT JOIN crawl_targets t ON r.ags::text = t.ags::text 
            WHERE r.massnahme IS NOT NULL
            ORDER BY r.end_time DESC 
            LIMIT 100
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # Datumsspalten bereinigen
        for col in ['massnahme_start', 'massnahme_ende']:
            if col in df.columns:
                df[col] = df[col].astype(str).replace(['None', 'NaT', 'nan'], '-')

        # Auch hier: Alle NaNs entfernen
        df = df.where(pd.notnull(df), None)

        return df.to_dict(orient="records")
    except Exception as e:
        print(f"Error Bewegungsdaten: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/monitoring")
def get_monitoring():
    try:
        # Load JSON status
        live_data = {"aktueller_ort": "Unbekannt", "status": "Inaktiv", "letzte_funde": 0, "timestamp": "-"}
        if os.path.exists("crawler_live_status.json"):
            with open("crawler_live_status.json", "r", encoding="utf-8") as f:
                live_data = json.load(f)

        # Load History TXT
        history_log = ""
        if os.path.exists("crawler_history.txt"):
            with open("crawler_history.txt", "r", encoding="utf-8") as f:
                history_log = "".join(f.readlines()[-20:][::-1])

        return {"live": live_data, "history": history_log}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)