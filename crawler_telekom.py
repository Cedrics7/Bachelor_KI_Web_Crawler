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
from llm_client import analyze_with_telekom_llm, get_session_stats
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


def _fetch_targets(cursor) -> list:
    """
    Lädt Crawl-Targets aus der DB.

    Logik:
      - force_ags (aus CONFIG): Diese AGS-IDs werden IMMER geladen,
        unabhängig von last_scanned. Sie kommen an den Anfang der Liste.
      - Normale Targets: sortiert nach last_scanned ASC NULLS FIRST,
        begrenzt auf max_targets.
      - Wenn force_ags leer ist: nur normale Logik.
    """
    force_ags   = CONFIG.get("force_ags") or []
    max_targets = CONFIG["max_targets"]
    prio_region = CONFIG.get("prio_region", "")

    forced_rows  = []
    normal_rows  = []

    # --- 1. force_ags laden (last_scanned wird ignoriert) ---
    if force_ags:
        placeholders = ",".join(["%s"] * len(force_ags))
        cursor.execute(
            f"SELECT ags, url, ort FROM crawl_targets WHERE ags IN ({placeholders})",
            tuple(force_ags)
        )
        forced_rows = cursor.fetchall()
        if forced_rows:
            log_event("📌", f"force_ags: {len(forced_rows)} Target(s) erzwungen: "
                           f"{[r[2] for r in forced_rows]}")

    # --- 2. Normale Targets (ohne die force_ags, damit keine Dopplung) ---
    exclude_ags = list(force_ags) if force_ags else []

    if prio_region:
        if exclude_ags:
            placeholders = ",".join(["%s"] * len(exclude_ags))
            cursor.execute(f"""
                SELECT ct.ags, ct.url, ct.ort
                FROM crawl_targets ct
                LEFT JOIN region_mapping rm ON ct.bundesland = rm.bundesland
                WHERE ct.ags NOT IN ({placeholders})
                ORDER BY
                    CASE WHEN rm.region = %s THEN 0 ELSE 1 END ASC,
                    ct.last_scanned ASC NULLS FIRST
                LIMIT %s
            """, (*exclude_ags, prio_region, max_targets))
        else:
            cursor.execute("""
                SELECT ct.ags, ct.url, ct.ort
                FROM crawl_targets ct
                LEFT JOIN region_mapping rm ON ct.bundesland = rm.bundesland
                ORDER BY
                    CASE WHEN rm.region = %s THEN 0 ELSE 1 END ASC,
                    ct.last_scanned ASC NULLS FIRST
                LIMIT %s
            """, (prio_region, max_targets))
        log_event("🎯", f"Region-Priorisierung aktiv: '{prio_region}'")
    else:
        if exclude_ags:
            placeholders = ",".join(["%s"] * len(exclude_ags))
            cursor.execute(
                f"SELECT ags, url, ort FROM crawl_targets "
                f"WHERE ags NOT IN ({placeholders}) "
                f"ORDER BY last_scanned ASC NULLS FIRST LIMIT %s",
                (*exclude_ags, max_targets)
            )
        else:
            cursor.execute(
                "SELECT ags, url, ort FROM crawl_targets "
                "ORDER BY last_scanned ASC NULLS FIRST LIMIT %s",
                (max_targets,)
            )
    normal_rows = cursor.fetchall()

    # force_ags zuerst, dann normale Targets
    return forced_rows + normal_rows


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
    force_ags         = CONFIG.get("force_ags") or []

    write_history_log("START",
        f"Beginne Telekom-Crawler | Modell: {CONFIG['llm_model']} | "
        f"{CONFIG['llm_parallel_workers']} parallele LLM-Worker | "
        f"max. {CONFIG['max_targets']} Targets."
        + (f" Prio-Region: {prio_region}." if prio_region else "")
        + (f" Force-AGS: {force_ags}." if force_ags else ""))

    targets   = _fetch_targets(cursor)
    min_datum = datetime.strptime(CONFIG["min_end_datum"], "%Y-%m-%d").date()

    log_event("ℹ️", f"Modell: {CONFIG['llm_model']} | "
                   f"Chunk-Größe: {CONFIG['chunk_size']:,} Zeichen | "
                   f"Kontext-Fenster: {CONFIG['context_window_size']} Einträge | "
                   f"Parallel-Worker: {CONFIG['llm_parallel_workers']} | "
                   f"Targets geladen: {len(targets)}")

    try:
        for ags, start_url, ort in targets:
            start_time   = datetime.now()
            is_forced    = ags in force_ags
            forced_label = " [FORCE]" if is_forced else ""
            log_event("🔍", f"Target: {ort} ({start_url}){forced_label}")
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

            if cursor.fetchone() and not is_forced:
                # Hash-Match: Inhalt unverändert UND kein Force → überspringen
                log_event("🔒", f"Keine Änderungen in {ort} (Hash-Match).")
                update_live_log(ort, "✅ Stand aktuell (Hash-Match)", gespart=True)
            else:
                if is_forced and cursor.fetchone():
                    log_event("📌", f"{ort}: Hash-Match, aber FORCE → Analyse wird trotzdem durchgeführt.")

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
        gesamtkosten, gesamtrequests = get_session_stats()
        laufzeit = (datetime.now() - start_zeit_dt).total_seconds()
        write_history_log("ENDE",
            f"Telekom-Crawler abgeschlossen. "
            f"Targets: {targets_processed} | Funde: {total_funde} | "
            f"Laufzeit: {laufzeit:.1f}s | "
            f"Gesamtkosten: {gesamtkosten:.6f} $ ({gesamtrequests} Requests)")
        try:
            conn.close()
        except Exception:
            pass


if __name__ == "__main__":
    run_crawler()
