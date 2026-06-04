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
import uvicorn

from crawler.database import get_db_connection

mimetypes.add_type('application/javascript', '.js')
mimetypes.add_type('text/css', '.css')

load_dotenv()
app = FastAPI(title="Telekom Web Crawler API")

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
def get_stats(
    status: str = Query("Alle"),
    bundesland: str = Query("Alle")
):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        first_day = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        base_conds = []
        base_params = []
        if status == "Gecrawlt":
            base_conds.append("last_scanned IS NOT NULL")
        elif status == "Ausstehend":
            base_conds.append("last_scanned IS NULL")
        if bundesland != "Alle":
            base_conds.append("bundesland = %s")
            base_params.append(bundesland)
        where = ("WHERE " + " AND ".join(base_conds)) if base_conds else ""
        cursor.execute(f"SELECT COUNT(*) FROM crawl_targets {where}", base_params)
        total = cursor.fetchone()[0]
        done_conds = base_conds + ["last_scanned >= %s"]
        done_params = base_params + [first_day]
        done_where = "WHERE " + " AND ".join(done_conds)
        cursor.execute(f"SELECT COUNT(*) FROM crawl_targets {done_where}", done_params)
        done = cursor.fetchone()[0]
        conn.close()
        return {"total": total, "done": done, "pending": total - done}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bewegung_stats")
def get_bewegung_stats(
    bundesland: str = Query("Alle"),
    kategorie: str = Query("Alle")
):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now()
        first_day_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        base_conds = ["r.massnahme IS NOT NULL"]
        base_params = []
        join = "LEFT JOIN crawl_targets t ON r.ags::text = t.ags::text"
        if bundesland != "Alle":
            base_conds.append("t.bundesland = %s")
            base_params.append(bundesland)
        if kategorie != "Alle":
            base_conds.append("r.kategorie = %s")
            base_params.append(kategorie)
        where = "WHERE " + " AND ".join(base_conds)
        cursor.execute(f"SELECT COUNT(*) FROM crawl_results r {join} {where}", base_params)
        total = cursor.fetchone()[0]
        cursor.execute(
            f"SELECT COUNT(*) FROM crawl_results r {join} {where} AND r.gefunden_am >= %s",
            base_params + [first_day_month]
        )
        month = cursor.fetchone()[0]
        cursor.execute(
            f"SELECT COUNT(*) FROM crawl_results r {join} {where} AND r.gefunden_am >= %s",
            base_params + [today_start]
        )
        today = cursor.fetchone()[0]
        conn.close()
        return {"total": total, "month": month, "today": today}
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
            SELECT r.id, r.massnahme, r.adresse, t.ort, r.massnahme_start, r.massnahme_ende,
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
                if isinstance(v, datetime):
                    item[k] = v.strftime('%Y-%m-%dT%H:%M:%S')
                elif isinstance(v, date):
                    item[k] = v.strftime('%Y-%m-%d')
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


@app.get("/api/bestandsdaten/{item_id}")
def get_bestandsdaten_by_id(item_id: int):
    try:
        conn = get_db_connection(as_dict=True)
        cur = conn.cursor()
        cur.execute(
            "SELECT id, ort, ags, bundesland, last_scanned, url FROM crawl_targets WHERE id = %s",
            (item_id,)
        )
        row = cur.fetchone()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")
        item = dict(row)
        if item.get('last_scanned'):
            item['last_scanned'] = item['last_scanned'].strftime('%d.%m.%Y %H:%M')
        else:
            item['last_scanned'] = '-'
        return item
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/bestandsdaten")
def get_bestandsdaten(
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=500),
        search: str = Query(None),
        status: str = Query("Alle"),
        bundesland: str = Query("Alle")
):
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
        if bundesland != "Alle":
            where_conditions.append("bundesland = %s")
            params.append(bundesland)
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
        cur.execute("SELECT DISTINCT bundesland FROM crawl_targets WHERE bundesland IS NOT NULL ORDER BY bundesland")
        bl_list = [r['bundesland'] for r in cur.fetchall()]
        conn.close()
        return {
            "items": items,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size,
            "filter_options": {"bundeslaender": bl_list}
        }
    except Exception as e:
        print(f"Fehler Bestandsdaten: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/monitoring")
def get_monitoring():
    """
    Liefert den Live-Status des Crawlers aus der DB (crawler_status_view)
    sowie Funde heute aus crawl_results und die Crawler-History aus der Logdatei.

    Response-Struktur (kompatibel mit bestehendem Frontend):
    {
        "live": {
            "aktueller_ort":  str,   # current_target aus crawler_status_view
            "status":         str,   # 'aktiv' | 'inaktiv'
            "letzte_funde":   int,   # Funde heute aus crawl_results
            "timestamp":      str,   # last_heartbeat als lesbarer String
            "started_at":     str | None,
            "stopped_at":     str | None,
            "seconds_since_heartbeat": int | None
        },
        "history": str   # letzte 20 Zeilen der Logdatei (umgekehrt)
    }
    """
    try:
        conn = get_db_connection(as_dict=True)
        cur  = conn.cursor()

        # --- Live-Status aus DB-View ---
        cur.execute("SELECT * FROM crawler_status_view")
        row = cur.fetchone()

        if row:
            status         = row['status']
            current_target = row['current_target'] or '-'
            last_hb        = row['last_heartbeat']
            started_at     = row['started_at']
            stopped_at     = row['stopped_at']
            seconds_since  = row['seconds_since_heartbeat']
            timestamp      = last_hb.strftime('%d.%m.%Y %H:%M:%S') if last_hb else '-'
            started_str    = started_at.strftime('%d.%m.%Y %H:%M:%S') if started_at else None
            stopped_str    = stopped_at.strftime('%d.%m.%Y %H:%M:%S') if stopped_at else None
        else:
            # Tabelle existiert noch nicht oder leer (Migration noch nicht ausgeführt)
            status, current_target, timestamp = 'inaktiv', '-', '-'
            started_str = stopped_str = seconds_since = None

        # --- Funde heute aus crawl_results ---
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        cur.execute(
            "SELECT COUNT(*) AS cnt FROM crawl_results WHERE gefunden_am >= %s",
            (today_start,)
        )
        funde_heute = cur.fetchone()['cnt']
        conn.close()

        live_data = {
            "aktueller_ort":           current_target,
            "status":                  status,
            "letzte_funde":            funde_heute,
            "timestamp":               timestamp,
            "started_at":              started_str,
            "stopped_at":              stopped_str,
            "seconds_since_heartbeat": seconds_since,
        }

    except Exception as e:
        # Fallback: DB nicht erreichbar – Fehlerstatus statt 500
        live_data = {
            "aktueller_ort":  "-",
            "status":         "inaktiv",
            "letzte_funde":   0,
            "timestamp":      "-",
            "started_at":     None,
            "stopped_at":     None,
            "seconds_since_heartbeat": None,
        }

    # --- Crawler-History aus Logdatei (unveraendert) ---
    history_log = ""
    if os.path.exists("crawler_history.txt"):
        with open("crawler_history.txt", "r", encoding="utf-8") as f:
            history_log = "".join(f.readlines()[-20:][::-1])

    return {"live": live_data, "history": history_log}


@app.get("/api/changelog")
def get_changelog():
    try:
        conn = get_db_connection(as_dict=True)
        cur = conn.cursor()
        cur.execute("""
            SELECT
                c.id, c.version,
                c.release_date   AS released_at,
                c.title          AS summary,
                c.description, c.commit_sha,
                json_agg(
                    json_build_object(
                        'tag',         ci.type,
                        'scope',       ci.scope,
                        'description', ci.message
                    )
                    ORDER BY ci.sort_order
                ) FILTER (WHERE ci.id IS NOT NULL) AS items
            FROM changelog c
            LEFT JOIN changelog_items ci ON ci.changelog_id = c.id
            GROUP BY c.id, c.version, c.release_date, c.title, c.description, c.commit_sha
            ORDER BY c.release_date DESC, c.version DESC
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
    uvicorn.run(app, host="0.0.0.0", port=8000)
