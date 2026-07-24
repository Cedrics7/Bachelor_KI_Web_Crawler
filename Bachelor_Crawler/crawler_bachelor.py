"""
crawler_bachelor.py  (Bachelor_Crawler)
========================================
Haupt-Loop des Bachelor-Crawlers.
Startet per: python crawler_bachelor.py
Holt URLs aus der DB (crawl_targets), crawlt und schreibt Ergebnisse zurück.
Analog zu crawler_js/crawler_telekom.py.
"""

import time
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


# ============================================================
# Haupt-Loop
# ============================================================

def run_crawler():
    conn   = get_db_connection()
    cursor = conn.cursor()

    targets           = _fetch_targets(cursor)
    targets_processed = 0
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
                    print(f"⚠️  Kein Text für {ort}. Status-Codes: {sorted(fehler_codes, key=str)}")
                    cursor.execute(
                        "UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s",
                        (datetime.now(), ags)
                    )
                    conn.commit()
                    continue

                # --- TODO: LLM-Analyse hier einfügen ---
                # from llm_client import analyze_with_llm
                # found = analyze_with_llm(text_bulk, start_url)
                # for item in found:
                #     cursor.execute("INSERT INTO crawl_results ...", (...))

                print(f"✅ Scraping fertig: {ort} | "
                      f"{len(text_bulk):,} Zeichen | "
                      f"Laufzeit: {(datetime.now()-start_time).total_seconds():.1f}s")

                # --- last_scanned updaten ---
                cursor.execute(
                    "UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s",
                    (datetime.now(), ags)
                )
                conn.commit()
                time.sleep(CONFIG.get("sleep_between_targets", 1))

            except Exception as e:
                print(f"❌ Fehler bei {ort} ({start_url}): {e}")
                try:
                    conn.rollback()
                except Exception:
                    pass
                continue

    finally:
        laufzeit = (datetime.now() - start_zeit).total_seconds()
        print(f"\n🏁 Bachelor-Crawler beendet | "
              f"Targets: {targets_processed} | Laufzeit: {laufzeit:.1f}s")
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    run_crawler()
