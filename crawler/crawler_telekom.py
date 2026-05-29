"""
crawler_telekom.py
==================
Haupt-Loop des Telekom-Crawlers.

Fix: content_hash wird jetzt in crawl_targets gespeichert (nicht crawl_results),
     damit der Hash-Vergleich korrekt funktioniert – auch wenn 0 Massnahmen
     gefunden wurden oder sich der Text minimal aendert.
"""

import json
import time
from datetime import datetime

from crawler.config import CONFIG, CONSOLE_LOG_FILE, SKIPPED_LOG_FILE
from crawler.logger import (
    log_event, write_history_log, write_skipped_urls,
    reset_live_log_if_new_day, update_live_log,
    _reset_log_if_new_month, start_heartbeat, stop_heartbeat,
)
from crawler.scraper import get_subpages, assemble_text, get_content_hash
from crawler.llm_client import analyze_with_telekom_llm, get_session_stats
from crawler.database import get_db_connection


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


def _load_stored_page_hashes(cursor, ags: str) -> dict:
    cursor.execute(
        "SELECT subpage_hashes FROM crawl_targets WHERE ags = %s", (ags,)
    )
    row = cursor.fetchone()
    if row and row[0]:
        try:
            return json.loads(row[0]) if isinstance(row[0], str) else row[0]
        except Exception:
            pass
    return {}


def _save_page_hashes(cursor, ags: str, page_hashes: dict):
    cursor.execute(
        "UPDATE crawl_targets SET subpage_hashes = %s WHERE ags = %s",
        (json.dumps(page_hashes, ensure_ascii=False), ags)
    )


def _load_stored_content_hash(cursor, ags: str) -> str | None:
    """Liest den gespeicherten Gesamt-Hash des letzten Crawls aus crawl_targets."""
    cursor.execute(
        "SELECT content_hash FROM crawl_targets WHERE ags = %s", (ags,)
    )
    row = cursor.fetchone()
    return row[0] if row and row[0] else None


def _save_content_hash(cursor, ags: str, content_hash: str):
    """Speichert den Gesamt-Hash des aktuellen Crawls in crawl_targets."""
    cursor.execute(
        "UPDATE crawl_targets SET content_hash = %s WHERE ags = %s",
        (content_hash, ags)
    )


def _filter_changed_pages(html_pages: list, pdf_pages: list,
                          new_hashes: dict, old_hashes: dict):
    from crawler.scraper import get_url_base
    filtered_html = []
    filtered_pdf  = []
    unchanged     = 0
    for url, text in html_pages:
        url_key = get_url_base(url)
        if old_hashes.get(url_key) == new_hashes.get(url_key):
            unchanged += 1
        else:
            filtered_html.append((url, text))
    for url, text in pdf_pages:
        url_key = get_url_base(url)
        if old_hashes.get(url_key) == new_hashes.get(url_key):
            unchanged += 1
        else:
            filtered_pdf.append((url, text))
    return filtered_html, filtered_pdf, unchanged


def _fetch_targets(cursor) -> list:
    force_ags   = CONFIG.get("force_ags") or []
    max_targets = CONFIG["max_targets"]
    prio_region = CONFIG.get("prio_region", "")
    forced_rows = []
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
    return forced_rows + normal_rows


def run_crawler():
    _reset_log_if_new_month(CONSOLE_LOG_FILE)
    _reset_log_if_new_month(SKIPPED_LOG_FILE)
    reset_live_log_if_new_day()
    heartbeat = start_heartbeat()
    conn      = get_db_connection()
    cursor    = conn.cursor()
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
                   f"Chunk-Größe: {CONFIG['chunk_size']:,} | "
                   f"Overlap: {CONFIG['chunk_overlap']:,} Zeichen | "
                   f"Worker: {CONFIG['llm_parallel_workers']} | "
                   f"Targets: {len(targets)}")

    try:
        for ags, start_url, ort in targets:
            start_time   = datetime.now()
            is_forced    = ags in force_ags
            forced_label = " [FORCE]" if is_forced else ""
            log_event("🔍", f"Target: {ort} ({start_url}){forced_label}")
            update_live_log(ort, "🔍 Scraping & PDF-Analyse...")
            targets_processed += 1

            html_pages, pdf_pages, skipped_urls, status_log, page_hashes = get_subpages(
                start_url, CONFIG["max_subpages"]
            )
            write_skipped_urls(ort, skipped_urls)
            if skipped_urls:
                log_event("🔗", f"{len(skipped_urls)} URL(s) per Dedup übersprungen")

            # --- Unterseiten-Hash-Filter ---
            old_hashes = _load_stored_page_hashes(cursor, ags)
            if old_hashes and not is_forced:
                html_pages, pdf_pages, unchanged_count = _filter_changed_pages(
                    html_pages, pdf_pages, page_hashes, old_hashes
                )
                if unchanged_count:
                    log_event("🔒", f"{unchanged_count} unveränderte Unterseite(n) übersprungen.")
            _save_page_hashes(cursor, ags, page_hashes)

            text_bulk, hat_gekuerzt, hat_verworfen = assemble_text(
                ort, html_pages, pdf_pages, CONFIG["max_text_chars"]
            )

            if not text_bulk.strip():
                fehler_codes = set(status_log.values())
                fehler_info  = ", ".join(str(c) for c in sorted(fehler_codes, key=str))
                log_event("⚠️", f"Kein Text für {ort}. Status-Codes: [{fehler_info}]")
                update_live_log(ort, f"⚠️ Kein Text [{fehler_info}]")
                conn.commit()
                continue

            # --- Gesamt-Hash-Vergleich (jetzt in crawl_targets) ---
            content_hash  = get_content_hash(text_bulk)
            stored_hash   = _load_stored_content_hash(cursor, ags)

            if stored_hash == content_hash and not is_forced:
                log_event("🔒", f"Keine Änderungen in {ort} (Gesamt-Hash-Match).")
                update_live_log(ort, "✅ Stand aktuell (Hash-Match)", gespart=True)
            else:
                if is_forced:
                    log_event("📌", f"{ort}: FORCE → Analyse wird durchgeführt.")

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
                             massnahme_url)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        ags, datetime.now().strftime("%Y-%m-%d"),
                        start_time, datetime.now(), "Erfolgreich",
                        item.get("kategorie"), m_name, item.get("adresse"),
                        m_start, m_ende, item.get("quelle_url"),
                    ))

                # Hash immer nach Analyse speichern – auch bei 0 Funden
                _save_content_hash(cursor, ags, content_hash)

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
