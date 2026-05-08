from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os
import json
import pandas as pd
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()
app = FastAPI()

# Enable CORS for frontend access
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


@app.get("/api/bestandsdaten")
def get_bestandsdaten():
    try:
        conn = get_db_connection()
        df = pd.read_sql("SELECT id, ort, ags, bundesland, last_scanned, url FROM crawl_targets ORDER BY id ASC", conn)
        conn.close()
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bewegungsdaten")
def get_bewegungsdaten():
    try:
        conn = get_db_connection()
        # Wir casten beide AGS Spalten explizit auf TEXT, um den Fehler zu vermeiden
        # Und wir nutzen die korrekten Spaltennamen aus deinem Screenshot
        query = """
            SELECT 
                r.massnahme, 
                r.adresse,
                t.ort, 
                r.massnahme_start, 
                r.massnahme_ende, 
                r.massnahme_url, 
                t.bundesland,
                r.kategorie -- Laut Screenshot existiert diese Spalte separat
            FROM crawl_results r 
            LEFT JOIN crawl_targets t ON r.ags::text = t.ags::text 
            WHERE r.massnahme IS NOT NULL
            ORDER BY r.end_time DESC 
            LIMIT 100
        """
        df = pd.read_sql(query, conn)
        conn.close()

        # Falls Datumsfelder leer sind, in Strings umwandeln für JSON
        df['massnahme_start'] = df['massnahme_start'].astype(str).replace('None', '-')
        df['massnahme_ende'] = df['massnahme_ende'].astype(str).replace('None', '-')

        return df.to_dict(orient="records")
    except Exception as e:
        print(f"DB Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)