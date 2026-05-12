"""
Haupt-Crawler-Logik. Sucht nach Baumaßnahmen auf kommunalen Webseiten
und nutzt Gemini AI zur Textanalyse.
"""
import os
import json
import re
import time
import threading
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from collections import deque
from datetime import datetime, date
from dotenv import load_dotenv
import google.generativeai as genai
from urllib.parse import urljoin, urlparse
import hashlib
import fitz
import warnings
from database import get_db_connection

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

#todo Patchnotes

# =====================================================================
# --- 1. CRAWLER KONFIGURATION ---
# =====================================================================
CONFIG = {
    "heartbeat": 10,
    "max_log_lines": 200,
    "max_targets": 4,
    "max_subpages": 50,
    "max_pdf_pages": 5,
    "timeout_seconds": 10,
    "sleep_between_targets": 2,
    # Filter: Maßnahmen deren Enddatum vor diesem Datum liegt werden ignoriert
    "min_end_datum": str(date.today()),
    # Filter: PDFs deren Erstellungsjahr älter als dieser Wert ist werden ignoriert
    "min_pdf_year": 2024,
    "max_text_chars": 500_000,
    "gemini_retries": 3,           # Maximale Wiederholungen bei 503/504
    "gemini_retry_delays": [10, 30, 60],  # Wartezeit in Sekunden pro Versuch
    "ziel_kategorien": {
        "Sanierung": ["Sanierungsgebiet", "Stadtsanierung", "Fördergebiet"],
        "Neubau": ["Neubaugebiet", "Bebauungsplan", "B-Plan", "Erschließung"],
        "Privatisierung": ["Grundstücksverkauf", "Veräußerung", "Liegenschaften"],
        "Tiefbau": ["Tiefbau", "Straßenbau", "Kanalsanierung", "Brückenbau"]
    }
}

# Keywords im Dateinamen → PDF ist besonders relevant
PDF_PRIO_KEYWORDS = [
    "bekanntmachung", "bebauungsplan", "b-plan", "bplan",
    "satzung", "erschließung", "erschliessung", "ausschreibung",
    "vergabe", "foerderung", "förderung", "sanierung", "tiefbau"
]

CONSOLE_LOG_FILE = "crawler_console.log"

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(
    'gemini-3.1-flash-lite-preview',
    generation_config={"response_mime_type": "application/json"}
)

# =====================================================================
# --- 2. API LIMIT MANAGER (Rolling Window) ---
# =====================================================================
class TokenManager:
    """
    Verwaltet Gemini API-Limits mit echtem Rolling-Window (60s).
    """
    def __init__(self, rpm=12, tpm=200_000, rpd=480):
        self.rpm_limit      = rpm
        self.tpm_limit      = tpm
        self.rpd_limit      = rpd
        self.window         = deque()  # (float timestamp, int tokens)
        self.requests_today = 0
        self.day_start_time = date.today()

    def _evict_old(self):
        cutoff = time.monotonic() - 60.0
        while self.window and self.window[0][0] < cutoff:
            self.window.popleft()

    def _current_rpm(self):
        return len(self.window)

    def _current_tpm(self):
        return sum(tokens for _, tokens in self.window)

    def check_limits(self, estimated_tokens):
        if estimated_tokens >= self.tpm_limit:
            print(f"!!! WARNUNG: Prompt zu groß ({estimated_tokens} Tokens) – übersprungen!")
            return False

        if date.today() > self.day_start_time:
            self.requests_today = 0
            self.day_start_time = date.today()
        if self.requests_today >= self.rpd_limit:
            print("!!! Tageslimit (RPD) erreicht.")
            return False

        while True:
            self._evict_old()
            rpm_ok = self._current_rpm() < self.rpm_limit
            tpm_ok = self._current_tpm() + estimated_tokens < self.tpm_limit

            if rpm_ok and tpm_ok:
                return True

            oldest_ts = self.window[0][0] if self.window else time.monotonic()
            wait_secs = max((oldest_ts + 61.0) - time.monotonic(), 1.0)
            reason    = "RPM" if not rpm_ok else "TPM"
            rpm_info  = f"{self._current_rpm()}/{self.rpm_limit} RPM"
            tpm_info  = f"{self._current_tpm():,}/{self.tpm_limit:,} TPM"
            print(f"--- API Schutz ({reason}): {rpm_info}  {tpm_info}  → warte {wait_secs:.1f}s ---")
            time.sleep(wait_secs)

    def update_usage(self, token_count):
        self.window.append((time.monotonic(), token_count))
        self.requests_today += 1


api_guard = TokenManager()


# =====================================================================
# --- 3. HILFSFUNKTIONEN & HASHING ---
# =====================================================================
def get_german_time():
    return datetime.now().strftime("%d.%m.%Y, %H:%M:%S")


def _reset_console_log_if_new_month():
    """
    Setzt crawler_console.log am Monatsanfang zurück.
    Schreibt einen Reset-Header in die neue Datei.
    """
    if not os.path.exists(CONSOLE_LOG_FILE):
        return
    try:
        with open(CONSOLE_LOG_FILE, "r", encoding="utf-8") as f:
            erste_zeile = f.readline()
        # Ersten Zeitstempel aus dem Log lesen
        match = re.search(r'\[(\d{2}\.\d{2}\.\d{4})', erste_zeile)
        if match:
            log_monat = datetime.strptime(match.group(1), "%d.%m.%Y").strftime("%Y-%m")
            jetzt_monat = datetime.now().strftime("%Y-%m")
            if log_monat != jetzt_monat:
                with open(CONSOLE_LOG_FILE, "w", encoding="utf-8") as f:
                    f.write(f"# Log-Reset: Neuer Monat ({jetzt_monat})\n")
    except Exception as e:
        print(f"Fehler beim Monats-Reset des Console-Logs: {e}")


def _write_console_log(line: str):
    """Schreibt eine Zeile in das Konsolen-Logfile."""
    try:
        with open(CONSOLE_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def log_event(emoji, message):
    zeit = get_german_time()
    line = f"[{zeit}] {emoji} {message}"
    print(line)
    _write_console_log(line)


def write_history_log(event_type, message):
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


def update_live_log(ort, status, funde=0, gespart=False):
    status_file        = "crawler_live_status.json"
    heute_str          = datetime.now().strftime("%Y-%m-%d")
    gesamt_funde_heute = funde
    if os.path.exists(status_file):
        try:
            with open(status_file, "r", encoding="utf-8") as f:
                old_data = json.load(f)
            if old_data.get("timestamp", "").startswith(heute_str):
                gesamt_funde_heute += old_data.get("letzte_funde", 0)
        except Exception as e:
            print(f"Fehler beim Lesen des Status-Files: {e}")
    with open(status_file, "w", encoding="utf-8") as f:
        json.dump({
            "timestamp":     datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "aktueller_ort": ort,
            "status":        status,
            "letzte_funde":  gesamt_funde_heute,
            "hash_match":    gespart
        }, f, ensure_ascii=False, indent=4)


# =====================================================================
# --- 3b. HEARTBEAT-THREAD ---
# =====================================================================
_heartbeat_stop = threading.Event()


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


def extract_pdf_text(url, max_pages):
    try:
        response = requests.get(url, timeout=10)
        with fitz.open(stream=response.content, filetype="pdf") as doc:
            meta   = doc.metadata
            c_date = meta.get("creationDate", "")
            if c_date.startswith("D:"):
                year = int(c_date[2:6])
                if year < CONFIG["min_pdf_year"]:
                    print(f"      - Ignoriere altes PDF ({year})")
                    return ""
            text = ""
            for page in doc[:max_pages]:
                text += page.get_text()
            return text
    except Exception:
        return ""


def get_pdf_year(url):
    """Extrahiert das Jahr aus dem PDF-Dateinamen (z.B. 2026_05_08_... → 2026)."""
    match = re.search(r'(20\d{2})', url.split("/")[-1])
    return int(match.group(1)) if match else 9999


def is_prio_pdf(url):
    """Gibt True zurück wenn der Dateiname ein Relevanz-Keyword enthält."""
    filename = url.split("/")[-1].lower()
    return any(kw in filename for kw in PDF_PRIO_KEYWORDS)


def get_content_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def extract_main_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def is_relevant_url(url):
    ignore = ["impressum", "datenschutz", "kontakt", "sitemap", "login", ".jpg", ".png"]
    return not any(kw in url.lower() for kw in ignore)


def get_url_base(url):
    """
    Gibt die URL ohne Query-Parameter und Fragment zurück.
    Verhindert, dass dieselbe Seite mit verschiedenen ?filter=... mehrfach gecrawlt wird.
    Beispiel: https://example.de/baugebiete.html?fil=1 → https://example.de/baugebiete.html
    """
    parsed = urlparse(url)
    return parsed._replace(query="", fragment="").geturl()


def get_subpages(start_url, max_pages):
    visited_base = set()   # Normalisierte Basis-URLs (ohne Query/Fragment)
    visited_full = set()   # Vollständige URLs für to_visit-Deduplikation
    to_visit     = [start_url]
    html_collected = []
    pdf_collected  = []
    base_domain    = urlparse(start_url).netloc
    prio_keywords  = ["aktuell", "news", "nachricht", "bauen", "projekt", "bebauungsplan"]

    while to_visit and (len(html_collected) + len(pdf_collected)) < max_pages:
        curr = to_visit.pop(0)
        curr_base = get_url_base(curr)

        # Überspringe wenn Basis-URL bereits besucht
        if curr_base in visited_base:
            continue
        visited_base.add(curr_base)
        visited_full.add(curr)

        try:
            resp = requests.get(curr, timeout=CONFIG["timeout_seconds"],
                                headers={'User-Agent': 'BachelorCrawler/1.0'})
            if resp.status_code == 200:
                if curr.lower().endswith(".pdf"):
                    print(f"  - Scanne PDF: {curr[:50]}...")
                    text = extract_pdf_text(curr, CONFIG["max_pdf_pages"])
                    if text:
                        pdf_collected.append((curr, text))
                else:
                    text = extract_main_text(resp.text)
                    html_collected.append((curr, text))
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for link in soup.find_all('a', href=True):
                        nxt      = urljoin(start_url, link['href'])
                        nxt_base = get_url_base(nxt)
                        if (urlparse(nxt).netloc == base_domain
                                and is_relevant_url(nxt)
                                and nxt_base not in visited_base
                                and nxt not in visited_full):
                            visited_full.add(nxt)
                            if any(p in nxt.lower() for p in prio_keywords):
                                to_visit.insert(0, nxt)
                            else:
                                to_visit.append(nxt)
        except:
            continue
    return html_collected, pdf_collected


def assemble_text(ort, html_pages, pdf_pages, limit):
    """
    Baut den Gesamttext mit klarer Priorisierung:
    1. HTML-Seiten immer vollständig
    2. PDFs mit Relevanz-Keywords zuerst
    3. Nur bei Platzmangel: Seitenzahl reduzieren, dann älteste PDFs verwerfen
    Gibt (text, hat_gekuerzt, hat_verworfen) zurück.
    """
    text_bulk = ""

    # --- Schritt 1: HTML komplett einbauen ---
    for url, content in html_pages:
        if content:
            text_bulk += f"\n--- URL: {url} ---\n{content}"

    # --- Schritt 2: PDFs sortieren (Prio-PDFs zuerst, dann nach Jahr absteigend) ---
    prio_pdfs    = [(u, t) for u, t in pdf_pages if is_prio_pdf(u)]
    normale_pdfs = [(u, t) for u, t in pdf_pages if not is_prio_pdf(u)]
    normale_pdfs.sort(key=lambda x: get_pdf_year(x[0]), reverse=True)
    sortierte_pdfs = prio_pdfs + normale_pdfs

    verbleibend = limit - len(text_bulk)

    # Prüfen ob alle PDFs reinpassen
    gesamt_pdf_text = sum(len(t) for _, t in sortierte_pdfs)
    if gesamt_pdf_text <= verbleibend:
        for url, content in sortierte_pdfs:
            text_bulk += f"\n--- URL: {url} ---\n{content}"
        return text_bulk, False, False

    # --- Schritt 3: Seitenzahl schrittweise reduzieren ---
    hat_gekuerzt = False
    for reduzierte_seiten in [3, 2, 1]:
        neu_pdf_texte = []
        for url, _ in sortierte_pdfs:
            neu_text = extract_pdf_text(url, reduzierte_seiten)
            neu_pdf_texte.append((url, neu_text))

        gesamt_neu = sum(len(t) for _, t in neu_pdf_texte)
        if gesamt_neu <= verbleibend:
            print(f"  ⚠️  Textlimit bei {ort} – PDFs auf {reduzierte_seiten} Seite(n) gekürzt "
                  f"({len(neu_pdf_texte)} PD