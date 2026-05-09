from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import psycopg2
import os
import json
import pandas as pd
from dotenv import load_dotenv
from datetime import datetime
from fastapi.staticfiles import StaticFiles
import mimetypes

# MIME-Type Fix
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

load_dotenv()

app = FastAPI()

# Statische Dateien (node_modules) mounten
script_dir = os.path.dirname(__file__)
node_path = os.path.join(script_dir, "node_modules")
if os.path.exists(node_path):
    app.mount("/node_modules", StaticFiles(directory=node_path), name="node_modules")

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
        first_day = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        df_total = pd.read_sql("SELECT COUNT(*) as count FROM crawl_targets", conn)
        df_done = pd.read_sql(f"SELECT COUNT(*) as count FROM crawl_targets WHERE last_scanned >= '{first_day}'", conn)
        total = int(df_total['count'][0])
        done = int(df_done['count'][0])
        conn.close()
        return {"total": total, "done": done, "pending": total - done}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bewegungsdaten")
def get_bewegungsdaten(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=500),
        search: str = Query(None),
        bundesland: str = Query("Alle"),
        kategorie: str = Query("Alle")
):
    try:
        conn = get_db_connection()
        offset = (page - 1) * page_size

        # Dynamische WHERE-Clause
        where_conditions = ["r.massnahme IS NOT NULL"]
        params = []

        if search:
            where_conditions.append("(r.massnahme ILIKE %s OR r.adresse ILIKE %s OR t.ort ILIKE %s)")
            p = f"%{search}%"
            params.extend([p, p, p])

        if bundesland != "Alle":
            where_conditions.append("t.bundesland = %s")
            params.append(bundesland)

        if kategorie != "Alle":
            where_conditions.append("r.kategorie = %s")
            params.append(kategorie)

        where_clause = " WHERE " + " AND ".join(where_conditions)

        # 1. Daten abrufen
        query = f"""
            SELECT r.massnahme, r.adresse, t.ort, r.massnahme_start, r.massnahme_ende, 
                   r.massnahme_url, t.bundesland, r.kategorie 
            FROM crawl_results r 
            LEFT JOIN crawl_targets t ON r.ags::text = t.ags::text 
            {where_clause}
            ORDER BY r.end_time DESC 
            LIMIT %s OFFSET %s
        """
        df = pd.read_sql(query, conn, params=params + [page_size, offset])
        df = df.where(pd.notnull(df), None)

        # 2. Gesamtanzahl für Pagination
        count_query = f"SELECT COUNT(*) FROM crawl_results r LEFT JOIN crawl_targets t ON r.ags::text = t.ags::text {where_clause}"
        cur = conn.cursor()
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        # 3. Filter-Optionen für die Dropdowns (einmalig oder bei Bedarf abrufen)
        cur.execute("SELECT DISTINCT bundesland FROM crawl_targets WHERE bundesland IS NOT NULL ORDER BY bundesland")
        bl_list = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT kategorie FROM crawl_results WHERE kategorie IS NOT NULL ORDER BY kategorie")
        kat_list = [r[0] for r in cur.fetchall()]

        conn.close()

        return {
            "items": df.to_dict(orient="records"),
            "total_count": total_count,
            "total_pages": (total_count + page_size - 1) // page_size,
            "page": page,
            "filter_options": {"bundeslaender": bl_list, "kategorien": kat_list}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bestandsdaten")
def get_bestandsdaten(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=500),
        search: str = Query(None)
):
    try:
        conn = get_db_connection()
        offset = (page - 1) * page_size

        # Basis-Query mit Filter-Logik
        where_clause = ""
        params = []
        if search:
            where_clause = "WHERE ort ILIKE %s OR ags ILIKE %s"
            search_param = f"%{search}%"
            params = [search_param, search_param]

        # 1. Daten abrufen
        query = f"""
            SELECT id, ort, ags, bundesland, last_scanned, url 
            FROM crawl_targets 
            {where_clause}
            ORDER BY id ASC 
            LIMIT %s OFFSET %s
        """
        df = pd.read_sql(query, conn, params=params + [page_size, offset])

        # 2. Gesamtanzahl für Pagination berechnen
        count_query = f"SELECT COUNT(*) FROM crawl_targets {where_clause}"
        cur = conn.cursor()
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]

        conn.close()

        # Formatierung
        if 'last_scanned' in df.columns:
            df['last_scanned'] = pd.to_datetime(df['last_scanned'], errors='coerce').dt.strftime(
                '%d.%m.%Y %H:%M').fillna('-')

        return {
            "items": json.loads(df.to_json(orient="records")),
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    except Exception as e:
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