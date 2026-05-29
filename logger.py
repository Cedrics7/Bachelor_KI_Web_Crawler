"""
logger.py
=========
Logging-Hilfsfunktionen: Konsole, History, Live-Status, Heartbeat.

Hinweis zu update_live_log:
  Keys im JSON entsprechen dem Original:
    'aktueller_ort'  (nicht 'letzter_ort')
    'hash_match'     (nicht 'gespart')
"""

import os
import re
import json
import threading
from datetime import datetime
from config import CONFIG, CONSOLE_LOG_FILE, SKIPPED_LOG_FILE

_heartbeat_stop = threading.Event()


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
    log_file = "crawler_history.txt"
    zeit = get_german_time()
    log_entry = f"[{zeit}] {event_type.upper()}: {message}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_entry)
    _write_console_log(log_entry.rstrip())
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > CONFIG["max_log_lines"]:
            with open(log_file, "w", encoding="utf-8") as f:
                f.writelines(lines[-CONFIG["max_log_lines"]:])
    except FileNotFoundError:
        pass


def reset_live_log_if_new_day():
    status_file = "crawler_live_status.json"
    heute_str   = datetime.now().strftime("%Y-%m-%d")
    if not os.path.exists(status_file):
        return
    try:
        with open(status_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not data.get("timestamp", "").startswith(heute_str):
            data["letzte_funde"] = 0
            data["timestamp"]    = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            with open(status_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            log_event("🔄", "Neuer Tag erkannt – Livelog-Funde zurückgesetzt.")
    except Exception as e:
        print(f"Fehler beim Tages-Reset des Livelogs: {e}")


def update_live_log(ort: str, status: str, funde: int = 0, gespart: bool = False):
    """
    Schreibt den aktuellen Crawl-Status in crawler_live_status.json.
    Keys identisch zum Original: 'aktueller_ort', 'hash_match'.
    """
    status_file        = "crawler_live_status.json"
    heute_str          = datetime.now().strftime("%Y-%m-%d")
    gesamt_funde_heute = funde
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            if old_data.get("timestamp", "").startswith(heute_str):
                gesamt_funde_heute += old_data.get("letzte_funde", 0)
        except Exception:
            pass
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp":     datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "aktueller_ort": ort,
            "status":        status,
            "letzte_funde":  gesamt_funde_heute,
            "hash_match":    gespart,
        }, f, ensure_ascii=False, indent=4)


def _heartbeat_worker():
    status_file = "crawler_live_status.json"
    while not _heartbeat_stop.is_set():
        try:
            if os.path.exists(status_file):
                with open(status_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data["timestamp"] = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
                with open(status_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
        except Exception:
            pass
        _heartbeat_stop.wait(CONFIG["heartbeat"])


def start_heartbeat() -> threading.Thread:
    _heartbeat_stop.clear()
    t = threading.Thread(target=_heartbeat_worker, daemon=True)
    t.start()
    return t


def stop_heartbeat():
    _heartbeat_stop.set()
