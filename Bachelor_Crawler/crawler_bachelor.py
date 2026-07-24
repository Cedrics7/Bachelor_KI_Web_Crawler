"""
crawler_bachelor.py  (Bachelor_Crawler)
========================================
Haupt-Loop des Bachelor-Crawlers.
Startet per: python crawler_bachelor.py
Holt URLs aus der DB (crawl_targets), crawlt und schreibt Ergebnisse zurück.
Analog zu crawler_js/crawler_telekom.py.

Changelog:
    v1.1 – Fehler-Tracking: DNS_TIMEOUT / 404 / sonstige Fehler werden
           in crawl_targets.crawl_error_code + crawl_error_count gespeichert.
           Session-Zusammenfassung am Ende (Erfolge / Fehler / Laufzeit).
"""

import time
from collections import Counter
from datetime import datetime

from config_bachelor import CONFIG
from database import get_db_connection
from scraper_bachelor import get_subpages, assemble_text


# ============================================================
# DB-Hilfsfunktionen
# ============================================================

def _fetch_targets(cursor) -> list:
    """
    Lädt die nächsten Targets aus crawl_targets.
    Sortierung: älteste last_scanned zuerst (NULLS FIRST = noch nie gecrawlt).
    """
    max_targets = CONFIG.get("max_targets", 50)
    force_ags   = CONFIG.get("force_ags") or []

    forced_rows = []
    if force_ags:
        placeholders = ",".join(["%s"] * len(force_ags))
        cursor.execute(
            f"SELECT ags, url, ort FROM crawl_targets WHERE ags IN ({placeholders})",
            tuple(force_ags)
        )
        forced_rows = cursor.fetchall()
        print(f"📌 force_ags: {len(forced_rows)} Target(s) erzwungen")

    exclude = list(force_ags)
    if exclude:
        placeholders = ",".join(["%s"] * len(exclude))
        cursor.execute(
            f"SELECT ags, url, ort FROM crawl_targets "
            f"WHERE ags NOT IN ({placeholders}) "
            f"ORDER BY last_scanned ASC NULLS FIRST LIMIT %s",
            (*exclude, max_targets)
        )
    else:
        cursor.execute(
            "SELECT ags, url, ort FROM crawl_targets "
            "ORDER BY last_scanned ASC NULLS FIRST LIMIT %s",
            (max_targets,)
        )

    normal_rows = cursor.fetchall()
    return forced_rows + normal_rows


def _dominant_error(status_log: dict) -> str:
    """Gibt den häufigsten Fehler-Code aus status_log zurück."""
    if not status_log:
        return "UNKNOWN"
    counts = Counter(str(v) for v in status_log.values())
    return counts.most_common(1)[0][0]


def _update_error(cursor, ags: str, error_code: str):
    """
    Schreibt Fehler-Code und erhöht crawl_error_count in crawl_targets.
    Spalten werden per ALTER TABLE angelegt falls nicht vorhanden (idempotent).
    """
    try:
        cursor.execute("""
            ALTER TABLE crawl_targets
                ADD COLUMN IF NOT EXISTS crawl_error_code  TEXT,
                ADD COLUMN IF NOT EXISTS crawl_error_count INT DEFAULT 0
        """)
    except Exception:
        pass  # Spalten existieren bereits

    cursor.execute("""
        UPDATE crawl_targets SET
            last_scanned      = %s,
            crawl_error_code  = %s,
            crawl_error_count = COALESCE(crawl_error_count, 0) + 1
        WHERE ags = %s
    """, (datetime.now(), error_code, ags))


def _clear_error(cursor, ags: str):
    """Setzt Fehler-Counter zurück, wenn ein Target erfolgreich gecrawlt wurde."""
    try:
        cursor.execute("""
            UPDATE crawl_targets SET
                crawl_error_code  = NULL,
                crawl_error_count = 0
            WHERE ags = %s
        """, (ags,))
    except Exception:
        pass


# ============================================================
# Haupt-Loop
# ============================================================

def run_crawler():
    conn   = get_db_connection()
    cursor = conn.cursor()

    targets           = _fetch_targets(cursor)
    targets_processed = 0
    total_success     = 0
    total_fehler      = 0
    fehler_counter    = Counter()
    start_zeit        = datetime.now()

    print(f"▶ Bachelor-Crawler gestartet | {len(targets)} Targets | "
          f"Modell: {CONFIG.get('llm_model', 'n/a')}")

    try:
        for row in targets:
            # Kompatibel mit RealDictCursor (dict) und normalem Cursor (tuple)
            if isinstance(row, dict):
                ags, start_url, ort = row["ags"], row["url"], row["ort"]
            else:
                ags, start_url, ort = row[0], row[1], row[2]

            try:
                start_time = datetime.now()
                targets_processed += 1
                print(f"🔍 [{targets_processed}/{len(targets)}] {ort} ({start_url})")

                # --- Scraping ---
                html_pages, pdf_pages, skipped_urls, status_log, page_hashes = get_subpages(
                    start_url, CONFIG.get("max_subpages", 20)
                )

                text_bulk, hat_gekuerzt, hat_verworfen = assemble_text(
                    ort, html_pages, pdf_pages, CONFIG.get("max_text_chars", 50_000)
                )
                del html_pages, pdf_pages

                if not text_bulk.strip():
                    fehler_codes = set(status_log.values())
                    error_code   = _dominant_error(status_log)
                    print(f"⚠️  Kein Text für {ort}. Status-Codes: {sorted(fehler_codes, key=str)}")
                    total_fehler += 1
                    fehler_counter[error_code] += 1
                    _update_error(cursor, ags, error_code)
                    conn.commit()
                    continue

                # --- TODO: LLM-Analyse hier einfügen ---
                # from llm_client import analyze_with_llm
                # found = analyze_with_llm(text_bulk, start_url)
                # for item in found:
                #     cursor.execute("INSERT INTO crawl_results ...", (...))

                laufzeit_target = (datetime.now() - start_time).total_seconds()
                print(f"✅ Scraping fertig: {ort} | "
                      f"{len(text_bulk):,} Zeichen | "
                      f"Laufzeit: {laufzeit_target:.1f}s")
                total_success += 1

                # --- last_scanned updaten + Fehler-Counter zurücksetzen ---
                cursor.execute(
                    "UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s",
                    (datetime.now(), ags)
                )
                _clear_error(cursor, ags)
                conn.commit()
                time.sleep(CONFIG.get("sleep_between_targets", 1))

            except Exception as e:
                print(f"❌ Fehler bei {ort} ({start_url}): {e}")
                total_fehler += 1
                fehler_counter["EXCEPTION"] += 1
                try:
                    conn.rollback()
                except Exception:
                    pass
                continue

    finally:
        laufzeit_gesamt = (datetime.now() - start_zeit).total_seconds()

        print(f"\n{'='*60}")
        print(f"🏁 Bachelor-Crawler beendet")
        print(f"   Targets gesamt : {targets_processed}")
        print(f"   ✅ Erfolge      : {total_success}")
        print(f"   ⚠️  Fehler       : {total_fehler}")
        if fehler_counter:
            for code, count in fehler_counter.most_common():
                print(f"      └─ {code}: {count}x")
        print(f"   ⏱  Laufzeit     : {laufzeit_gesamt:.1f}s")
        print(f"{'='*60}")

        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    run_crawler()
