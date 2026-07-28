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
"""
from __future__ import annotations
import logging
import time

from Bachelor_Crawler_erweitert.focused_crawler import FocusedCrawler
from Bachelor_Crawler_erweitert.config import DEFAULT_CONFIG

logger = logging.getLogger(__name__)


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
    targets = _fetch_targets(conn, max_targets, prio_region)
    total   = len(targets)

    logger.info(
        'Starte Crawler | %d Kommunen | max_pages=%d | prio_region=%s',
        total, max_pages, prio_region or '(keine)'
    )

    for idx, (ags, url, ort) in enumerate(targets, start=1):
        logger.info('[%d/%d] %s – %s', idx, total, ort, url)
        try:
            crawler = FocusedCrawler(run_id=ags)
            results, report = crawler.crawl(url, max_pages=max_pages)
            logger.info(
                '  ✓ %s: %d Seiten, %d relevant (Harvest Rate: %.1f%%)',
                ort,
                report.total_crawled,
                report.total_relevant,      # korrekter Attributname
                report.harvest_rate * 100,
            )
            _update_last_scanned(conn, ags)
        except Exception as e:
            logger.error('  ✗ Fehler bei %s (%s): %s', ort, url, e)

        time.sleep(sleep_sec)

    conn.close()
    logger.info('=== Fertig: %d/%d Kommunen verarbeitet ===', total, total)


if __name__ == '__main__':
    run_all()
