"""
Einstiegspunkt für Bachelor_Crawler_erweitert.
Lädt alle Ziel-URLs aus der Tabelle crawl_targets (PostgreSQL)
und crawlt sie der Reihe nach (last_scanned ASC NULLS FIRST).

Alle Parameter kommen aus DEFAULT_CONFIG (config.py / .env):
    CRAWLER_DB_ENABLED=true
    CRAWLER_MAX_PAGES=50              # Seiten pro Kommune
    CRAWLER_MAX_TARGETS=100           # wie viele Kommunen pro Lauf (0 = alle)
    CRAWLER_PRIO_REGION=Bayern        # optional: Region zuerst
    CRAWLER_SLEEP_BETWEEN_TARGETS=1   # Pause zwischen Kommunen in Sekunden

DB-Status (crawler_status-Tabelle) und Heartbeat werden exakt wie in
crawler_js/crawler_telekom.py geführt.
"""
from __future__ import annotations
import logging
import time
from datetime import datetime

from Bachelor_Crawler_erweitert.focused_crawler import FocusedCrawler
from Bachelor_Crawler_erweitert.config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)


# ============================================================
# DB-Status-Hilfsfunktionen (identisch zu crawler_js)
# ============================================================

def _db_set_status(conn, cursor, status: str, current_target: str = None) -> None:
    """
    Aktualisiert die crawler_status-Tabelle.
    Zeile wird per ON CONFLICT DO NOTHING sichergestellt.
    """
    now     = datetime.now()
    timeout = DEFAULT_CONFIG.get('heartbeat_timeout_seconds', 60)

    cursor.execute("""
        INSERT INTO crawler_status (status, heartbeat_timeout_seconds)
        VALUES ('inaktiv', %s)
        ON CONFLICT DO NOTHING
    """, (timeout,))

    if status == 'aktiv':
        cursor.execute("""
            UPDATE crawler_status SET
                status                    = 'aktiv',
                started_at                = %s,
                stopped_at                = NULL,
                last_heartbeat            = %s,
                current_target            = %s,
                heartbeat_timeout_seconds = %s
        """, (now, now, current_target, timeout))
    else:
        cursor.execute("""
            UPDATE crawler_status SET
                status         = 'inaktiv',
                stopped_at     = %s,
                current_target = NULL
        """, (now,))
    conn.commit()


def _db_heartbeat(conn, cursor, current_target: str = None) -> None:
    """Aktualisiert Heartbeat-Timestamp und aktuelles Ziel."""
    cursor.execute("""
        UPDATE crawler_status SET
            last_heartbeat = %s,
            current_target = %s
    """, (datetime.now(), current_target))
    conn.commit()


# ============================================================
# Hilfsfunktionen
# ============================================================

def _fetch_targets(conn, max_targets: int, prio_region: str) -> list:
    with conn.cursor() as cur:
        if prio_region:
            cur.execute("""
                SELECT ct.ags, ct.url, ct.ort
                FROM crawl_targets ct
                LEFT JOIN region_mapping rm ON ct.bundesland = rm.bundesland
                ORDER BY
                    CASE WHEN rm.region = %s THEN 0 ELSE 1 END ASC,
                    ct.last_scanned ASC NULLS FIRST
                LIMIT %s
            """, (prio_region, max_targets or 999999))
        elif max_targets:
            cur.execute("""
                SELECT ags, url, ort FROM crawl_targets
                ORDER BY last_scanned ASC NULLS FIRST
                LIMIT %s
            """, (max_targets,))
        else:
            cur.execute("""
                SELECT ags, url, ort FROM crawl_targets
                ORDER BY last_scanned ASC NULLS FIRST
            """)
        return cur.fetchall()


def _update_last_scanned(conn, ags: str) -> None:
    with conn.cursor() as cur:
        cur.execute(
            'UPDATE crawl_targets SET last_scanned = NOW() WHERE ags = %s', (ags,)
        )
    conn.commit()


# ============================================================
# Haupt-Loop
# ============================================================

def run_all() -> None:
    if not DEFAULT_CONFIG.get('db_enabled'):
        logger.error(
            'CRAWLER_DB_ENABLED ist nicht True. '
            'Bitte in .env setzen: CRAWLER_DB_ENABLED=true'
        )
        return

    max_pages   = DEFAULT_CONFIG['max_pages']
    max_targets = DEFAULT_CONFIG['max_targets']
    prio_region = DEFAULT_CONFIG['prio_region']
    sleep_sec   = DEFAULT_CONFIG['sleep_between_targets']

    import psycopg2
    conn    = psycopg2.connect(DEFAULT_CONFIG['db_url'])
    cursor  = conn.cursor()
    targets = _fetch_targets(conn, max_targets, prio_region)
    total   = len(targets)

    logger.info(
        'Starte Crawler | %d Kommunen | max_pages=%d | prio_region=%s',
        total, max_pages, prio_region or '(keine)'
    )

    # --- DB-Status: Crawler startet ---
    try:
        _db_set_status(conn, cursor, 'aktiv')
        logger.info('🟢 Live-Status in DB: aktiv')
    except Exception as e:
        logger.warning('DB-Status (aktiv) konnte nicht gesetzt werden: %s', e)
        try:
            conn.rollback()
        except Exception:
            pass

    try:
        for idx, (ags, url, ort) in enumerate(targets, start=1):
            logger.info('[%d/%d] %s – %s', idx, total, ort, url)

            # --- DB-Heartbeat: neues Target ---
            try:
                _db_heartbeat(conn, cursor, current_target=ort)
            except Exception as e:
                logger.warning('Heartbeat fehlgeschlagen für %s: %s', ort, e)
                try:
                    conn.rollback()
                except Exception:
                    pass

            try:
                crawler = FocusedCrawler(run_id=ags)
                results, report = crawler.crawl(
                    url,
                    max_pages=max_pages,
                    ags=ags,
                )
                logger.info(
                    '  ✓ %s: %d Seiten, %d relevant (Harvest Rate: %.1f%%)',
                    ort,
                    report.total_crawled,
                    report.total_relevant,
                    report.harvest_rate * 100,
                )
                _update_last_scanned(conn, ags)
            except Exception as e:
                logger.error('  ✗ Fehler bei %s (%s): %s', ort, url, e)
                try:
                    conn.rollback()
                except Exception:
                    pass

            time.sleep(sleep_sec)

    finally:
        # --- DB-Status: Crawler beendet ---
        try:
            _db_set_status(conn, cursor, 'inaktiv')
            logger.info('🔴 Live-Status in DB: inaktiv')
        except Exception as e:
            logger.warning('DB-Status (inaktiv) konnte nicht gesetzt werden: %s', e)
            try:
                conn.rollback()
            except Exception:
                pass
        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

    logger.info('=== Fertig: %d/%d Kommunen verarbeitet ===', total, total)


if __name__ == '__main__':
    run_all()
