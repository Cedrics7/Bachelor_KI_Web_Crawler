"""
logger.py
=========
Logging-Hilfsfunktionen: Konsole, History, Live-Status, Heartbeat.

Neu: _heartbeat_worker schreibt per UPSERT einen DB-Heartbeat in crawler_status.
     Alle Dateipfade sind absolut (relativ zu PROJECT_ROOT) damit sie unabhaengig
     vom Arbeitsverzeichnis immer funktionieren.
"""

import os
import re
import json
import threading
from datetime import datetime
from config_js import CONFIG, CONSOLE_LOG_FILE, SKIPPED_LOG_FILE

_heartbeat_stop = threading.Event()

# Absoluter Pfad zum Projekt-Root (eine Ebene über crawler_js/)
_PROJECT_ROOT    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HISTORY_FILE     = os.path.join(_PROJECT_ROOT, "crawler_history.txt")
LIVE_STATUS_FILE = os.path.join(_PROJECT_ROOT, "crawler_live_status.json")


def get_german_time() -> str:
    return datetime.now().strftime("%d.%m.%Y, %H:%M:%S")


def _reset_log_if_new_month(filepath: str):
    if not os.path.exists(filepath):
        return
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            erste_zeile = f.readline()
        match = re.search(r'\[(\d{2}\.\d{2}\.\d{4})', erste_zeile)
        if match:
            log_monat   = datetime.strptime(match.group(1), "%d.%m.%Y").strftime("%Y-%m")
            jetzt_monat = datetime.now().strftime("%Y-%m")
            if log_monat != jetzt_monat:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(f"# Log-Reset: Neuer Monat ({jetzt_monat})\n")
    except Exception as e:
        print(f"Fehler beim Monats-Reset von {filepath}: {e}")


def _write_console_log(line: str):
    try:
        with open(CONSOLE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def write_skipped_urls(ort: str, skipped_urls: list):
    if not skipped_urls:
        return
    zeit = get_german_time()
    try:
        with open(SKIPPED_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(f"\n[{zeit}] ⚠️  DEDUP-SKIP für {ort} ({len(skipped_urls)} URLs):\n")
            for url in skipped_urls:
                f.write(f"  - {url}\n")
    except Exception as e:
        print(f"Fehler beim Schreiben des Skipped-Logs: {e}")


def log_event(emoji: str, message: str):
    zeit = get_german_time()
    line = f"[{zeit}] {emoji} {message}"
    print(line)
    _write_console_log(line)


def write_history_log(event_type: str, message: str):
    zeit      = get_german_time()
    log_entry = f"[{zeit}] {event_type.upper()}: {message}\n"
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(log_entry)
    _write_console_log(log_entry.rstrip())
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > CONFIG["max_log_lines"]:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                f.writelines(lines[-CONFIG["max_log_lines"]:])
    except FileNotFoundError:
        pass


def reset_live_log_if_new_day():
    heute_str = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(LIVE_STATUS_FILE):
        return
    try:
        with open(LIVE_STATUS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("timestamp", "").startswith(heute_str):
            data["letzte_funde"] = 0
            data["timestamp"]    = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            with open(LIVE_STATUS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            log_event("🔄", "Neuer Tag erkannt – Livelog-Funde zurückgesetzt.")
    except Exception as e:
        print(f"Fehler beim Tages-Reset des Livelogs: {e}")


def update_live_log(ort: str, status: str, funde: int = 0, gespart: bool = False):
    heute_str          = datetime.now().strftime("%Y-%m-%d")
    gesamt_funde_heute = funde
    if os.path.exists(LIVE_STATUS_FILE):
        try:
            with open(LIVE_STATUS_FILE, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            if old_data.get("timestamp", "").startswith(heute_str):
                gesamt_funde_heute += old_data.get("letzte_funde", 0)
        except Exception:
            pass
    with open(LIVE_STATUS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp":     datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "aktueller_ort": ort,
            "status":        status,
            "letzte_funde":  gesamt_funde_heute,
            "hash_match":    gespart,
        }, f, ensure_ascii=False, indent=4)


def _db_heartbeat_write():
    """Schreibt per UPSERT einen Heartbeat in crawler_status. Legt Zeile an falls noetig."""
    try:
        from database import get_db_connection
        conn = get_db_connection()
        cur  = conn.cursor()
        cur.execute("""
            INSERT INTO crawler_status (status, last_heartbeat)
            VALUES ('aktiv', %s)
            ON CONFLICT ON CONSTRAINT crawler_status_pkey
                DO UPDATE SET last_heartbeat = EXCLUDED.last_heartbeat
        """, (datetime.now(),))
        conn.commit()
        conn.close()
    except Exception:
        pass


def _heartbeat_worker():
    while not _heartbeat_stop.is_set():
        # JSON-Datei aktualisieren
        try:
            if os.path.exists(LIVE_STATUS_FILE):
                with open(LIVE_STATUS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["timestamp"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                with open(LIVE_STATUS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass

        # DB-Heartbeat
        _db_heartbeat_write()

        _heartbeat_stop.wait(CONFIG["heartbeat"])


def start_heartbeat() -> threading.Thread:
    _heartbeat_stop.clear()
    t = threading.Thread(target=_heartbeat_worker, daemon=True)
    t.start()
    return t


def stop_heartbeat():
    _heartbeat_stop.set()
