"""
crawler_telekom.py
==================
Haupt-Loop des Telekom-Crawlers.
Importiert alle Teilmodule und orchestriert den Ablauf.

Modulstruktur:
  config.py       – Konfiguration, API-Keys, Konstanten
  logger.py       – Logging, Live-Status, Heartbeat
  rate_limiter.py – TokenManager (RPM / TPM / RPD)
  scraper.py      – Web-Scraping, PDF-Extraktion, Textzusammenstellung
  llm_client.py   – LLM-Call, Kostentracking, JSON-Parsing, Analyse
  crawler_telekom.py (diese Datei) – DB-Abfrage, Haupt-Loop
"""

import time
from datetime import datetime

from config import CONFIG, CONSOLE_LOG_FILE, SKIPPED_LOG_FILE
from logger import (
    log_event, write_history_log, write_skipped_urls,
    reset_live_log_if_new_day, update_live_log,
    _reset_log_if_new_month, start_heartbeat, stop_heartbeat,
)
from scraper import get_subpages, assemble_text, get_content_hash
from llm_client import analyze_with_telekom_llm
from database import get_db_connection


def is_duplicate(cursor, ags: str, massnahme: str, massnahme_start) -> bool:
    if massnahme_start is None:
        cursor.execute("""
            SELECT id FROM crawl_results
            WHERE ags = %s AND massnahme = %s AND massnahme_start IS NULL
        """, (ags, massnahme))
    else:
        cursor.execute("""
            SELECT id FROM crawl_results
            WHERE ags = %s AND massnahme = %s AND massnahme_start = %s
        """, (ags, massnahme, massnahme_start))
    return cursor.fetchone() is not None


def run_crawler():
    _reset_log_if_new_month(CONSOLE_LOG_FILE)
    _reset_log_if_new_month(SKIPPED_LOG_FILE)
    reset_live_log_if_new_day()

    heartbeat = start_heartbeat()

    conn   = get_db_connection()
    cursor = conn.cursor()

    targets_processed = 0
    total_funde       = 0
    start_zeit_dt     = datetime.now()
    prio_region       = CONFIG.get("prio_region")

    write_history_log("START",
        f"Beginne Telekom-Crawler | Modell: {CONFIG['llm_model']} | "
        f"{CONFIG['llm_parallel_workers']} parallele LLM-Worker | "
        f"max. {CONFIG['max_targets']} Targets."
        + (f" Prio-Region: {prio_region}." if prio_region else ""))

    if prio_region:
        cursor.execute("""
            SELECT ct.ags, ct.url, ct.ort
            FROM crawl_targets ct
            LEFT JOIN region_mapping rm ON ct.bundesland = rm.bundesland
            ORDER BY
                CASE WHEN rm.region = %s THEN 0 ELSE 1 END ASC,
                ct.last_scanned ASC NULLS FIRST
            LIMIT %s
        """, (prio_region, CONFIG["max_targets"]))
        log_event("🎯", f"Region-Priorisierung aktiv: '{prio_region}'")
    else:
        cursor.execute(
            "SELECT ags, url, ort FROM crawl_targets ORDER BY last_scanned ASC NULLS FIRST LIMIT %s",
            (CONFIG["max_targets"],)
        )

    targets   = cursor.fetchall()
    min_datum = datetime.strptime(CONFIG["min_end_datum"], "%Y-%m-%d").date()

    log_event("ℹ️", f"Modell: {CONFIG['llm_model']} | "
                   f"Chunk-Größe: {CONFIG['chunk_size']:,} Zeichen | "
                   f"Kontext-Fenster: {CONFIG['context_window_size']} Einträge | "
                   f"Parallel-Worker: {CONFIG['llm_parallel_workers']}")

    try:
        for ags, start_url, ort in targets:
            start_time = datetime.now()
            log_event("🔍", f"Target: {ort} ({start_url})")
            update_live_log(ort, "🔍 Scraping & PDF-Analyse...")
            targets_processed += 1

            html_pages, pdf_pages, skipped_urls, status_log = get_subpages(
                start_url, CONFIG["max_subpages"]
            )
            write_skipped_urls(ort, skipped_urls)
            if skipped_urls:
                log_event("🔗", f"{len(skipped_urls)} URL(s) per Dedup übersprungen")

            text_bulk, hat_gekuerzt, hat_verworfen = assemble_text(
                ort, html_pages, pdf_pages, CONFIG["max_text_chars"]
            )

            if not text_bulk.strip():
                fehler_codes = set(status_log.values())
                fehler_info  = ", ".join(str(c) for c in sorted(fehler_codes, key=str))
                log_event("⚠️", f"Kein Text für {ort}. Status-Codes: [{fehler_info}]")
                update_live_log(ort, f"⚠️ Kein Text [{fehler_info}]")
                continue

            content_hash = get_content_hash(text_bulk)
            cursor.execute("SELECT id FROM crawl_results WHERE content_hash = %s", (content_hash,))

            if cursor.fetchone():
                log_event("🔒", f"Keine Änderungen in {ort} (Hash-Match).")
                update_live_log(ort, "✅ Stand aktuell (Hash-Match)", gespart=True)
            else:
                log_event("🤖", f"Analyse {ort} → {CONFIG['llm_model']} ...")
                update_live_log(ort, f"🤖 LLM-Analyse ({CONFIG['llm_model']})...")

                found = analyze_with_telekom_llm(text_bulk, start_url)

                valid_count  = 0
                skipped_dups = 0
                for item in found:
                    m_start = item.get("massnahme_start")
                    m_ende  = item.get("massnahme_ende")
                    m_name  = item.get("massnahme")

                    if not m_start and not m_ende:
                        continue
                    if m_ende:
                        try:
                            if datetime.strptime(m_ende, "%Y-%m-%d").date() < min_datum:
                                continue
                        except ValueError:
                            pass

                    if is_duplicate(cursor, ags, m_name, m_start):
                        skipped_dups += 1
                        log_event("🔄", f"DB-Duplikat übersprungen: {m_name}")
                        continue

                    valid_count += 1
                    cursor.execute("""
                        INSERT INTO crawl_results
                            (ags, gefunden_am, start_time, end_time, status, kategorie,
                             massnahme, adresse, massnahme_start, massnahme_ende,
                             massnahme_url, content_hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        ags, datetime.now().strftime("%Y-%m-%d"),
                        start_time, datetime.now(), "Erfolgreich",
                        item.get("kategorie"), m_name, item.get("adresse"),
                        m_start, m_ende, item.get("quelle_url"), content_hash,
                    ))

                total_funde += valid_count
                log_event("✅", f"Fertig: {valid_count} neue Funde, "
                               f"{skipped_dups} Duplikate für {ort}.")
                update_live_log(ort, f"✅ Fertig: {valid_count} Funde", funde=valid_count)

            cursor.execute(
                "UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s",
                (datetime.now(), ags)
            )
            conn.commit()
            time.sleep(CONFIG["sleep_between_targets"])

    finally:
        stop_heartbeat()
        heartbeat.join(timeout=2)
        laufzeit = (datetime.now() - start_zeit_dt).total_seconds()
        write_history_log("ENDE",
            f"Telekom-Crawler abgeschlossen. "
            f"Targets: {targets_processed} | Funde: {total_funde} | "
            f"Laufzeit: {laufzeit:.1f}s")
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    run_crawler()
