"""
FastAPI Backend zur Bereitstellung der Crawler-Daten für das Frontend-Dashboard.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from datetime import datetime, date
import os
import json
import mimetypes

# Lokaler Import
from database import get_db_connection

# MIME-Type Fixes für korrekte Auslieferung statischer Dateien
mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

load_dotenv()
app = FastAPI(title="Telekom Web Crawler API")

# Mount für statische Dateien (Telekom Scale Components)
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


@app.get("/api/stats")
def get_stats():
    """Gibt aggregierte KPIs für das Dashboard zurück."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        first_day = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        cursor.execute("SELECT COUNT(*) FROM crawl_targets")
        total = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM crawl_targets WHERE last_scanned >= %s", (first_day,))
        done = cursor.fetchone()[0]
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
    kategorie: str = Query("Alle"),
    sort: str = Query("desc")
):
    """Liest die gefundenen Maßnahmen aus."""
    try:
        conn = get_db_connection(as_dict=True)
        cur = conn.cursor()
        offset = (page - 1) * page_size
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
        order_direction = "ASC" if sort.lower() == "asc" else "DESC"

        query = f"""
            SELECT r.massnahme, r.adresse, t.ort, r.massnahme_start, r.massnahme_ende,
                   r.massnahme_url, t.bundesland, r.kategorie, r.end_time, r.gefunden_am
            FROM crawl_results r
            LEFT JOIN crawl_targets t ON r.ags::text = t.ags::text
            {where_clause}
            ORDER BY r.end_time {order_direction}
            LIMIT %s OFFSET %s
        """
        cur.execute(query, params + [page_size, offset])
        raw_items = cur.fetchall()

        items = []
        for row in raw_items:
            item = dict(row)
            for k, v in item.items():
                if isinstance(v, (datetime, date)):
                    item[k] = v.strftime('%d.%m.%Y %H:%M') if isinstance(v, datetime) else v.strftime('%d.%m.%Y')
            items.append(item)

        cur.execute(f"SELECT COUNT(*) as count FROM crawl_results r LEFT JOIN crawl_targets t ON r.ags::text = t.ags::text {where_clause}", params)
        total_count = cur.fetchone()['count']
        cur.execute("SELECT DISTINCT bundesland FROM crawl_targets WHERE bundesland IS NOT NULL ORDER BY bundesland")
        bl_list = [r['bundesland'] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT kategorie FROM crawl_results WHERE kategorie IS NOT NULL ORDER BY kategorie")
        kat_list = [r['kategorie'] for r in cur.fetchall()]
        conn.close()

        return {
            "items": items,
            "total_count": total_count,
            "total_pages": (total_count + page_size - 1) // page_size,
            "page": page,
            "filter_options": {"bundeslaender": bl_list, "kategorien": kat_list}
        }
    except Exception as e:
        print(f"Fehler Bewegungsdaten: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bestandsdaten")
def get_bestandsdaten(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=500),
        search: str = Query(None),
        status: str = Query("Alle")
):
    """Liest die Bestandsdaten inkl. Pagination und Status-Filter."""
    try:
        conn = get_db_connection(as_dict=True)
        cur = conn.cursor()
        offset = (page - 1) * page_size
        where_conditions = []
        params = []

        if search:
            where_conditions.append("(ort ILIKE %s OR ags ILIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])
        if status == "Gecrawlt":
            where_conditions.append("last_scanned IS NOT NULL")
        elif status == "Ausstehend":
            where_conditions.append("last_scanned IS NULL")

        where_clause = ""
        if where_conditions:
            where_clause = "WHERE " + " AND ".join(where_conditions)

        cur.execute(f"""
            SELECT id, ort, ags, bundesland, last_scanned, url
            FROM crawl_targets
            {where_clause} ORDER BY id ASC LIMIT %s OFFSET %s
        """, params + [page_size, offset])
        raw_items = cur.fetchall()

        items = []
        for row in raw_items:
            item = dict(row)
            if item.get('last_scanned'):
                item['last_scanned'] = item['last_scanned'].strftime('%d.%m.%Y %H:%M')
            else:
                item['last_scanned'] = '-'
            items.append(item)

        cur.execute(f"SELECT COUNT(*) as count FROM crawl_targets {where_clause}", params)
        total_count = cur.fetchone()['count']
        conn.close()

        return {
            "items": items,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size
        }
    except Exception as e:
        print(f"Fehler Bestandsdaten: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/monitoring")
def get_monitoring():
    """Liefert die Live-Logs und den aktuellen Crawler-Status."""
    try:
        live_data = {"aktueller_ort": "Unbekannt", "status": "Inaktiv", "letzte_funde": 0, "timestamp": "-"}
        if os.path.exists("crawler_live_status.json"):
            with open("crawler_live_status.json", "r", encoding="utf-8") as f:
                live_data = json.load(f)

        history_log = ""
        if os.path.exists("crawler_history.txt"):
            with open("crawler_history.txt", "r", encoding="utf-8") as f:
                history_log = "".join(f.readlines()[-20:][::-1])

        return {"live": live_data, "history": history_log}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/changelog")
def get_changelog():
    """Liefert den vollständigen Versionsverlauf aus der Datenbank."""
    try:
        conn = get_db_connection(as_dict=True)
        cur = conn.cursor()

        cur.execute("""
            SELECT c.id, c.version, c.released_at, c.summary, c.is_current,
                   json_agg(
                       json_build_object(
                           'tag',         ci.tag,
                           'description', ci.description
                       )
                   ) FILTER (WHERE ci.id IS NOT NULL) AS items
            FROM changelog c
            LEFT JOIN changelog_items ci ON ci.changelog_id = c.id
            GROUP BY c.id, c.version, c.released_at, c.summary, c.is_current
            ORDER BY c.released_at DESC, c.version DESC
        """)
        rows = cur.fetchall()
        conn.close()

        result = []
        for row in rows:
            entry = dict(row)
            if entry.get("released_at"):
                entry["released_at"] = entry["released_at"].strftime("%d.%m.%Y")
            result.append(entry)

        return {"versions": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
