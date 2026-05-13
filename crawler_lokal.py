"""
Haupt-Crawler-Logik. Sucht nach Baumaßnahmen auf kommunalen Webseiten
und nutzt ein lokales Ollama-LLM zur Textanalyse (statt Gemini).
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
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
import hashlib
import fitz
import warnings
from database import get_db_connection

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

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
    "min_end_datum": str(date.today()),
    "min_pdf_year": 2024,
    "max_text_chars": 500_000,
    "ollama_retries": 3,
    "ollama_retry_delays": [10, 30, 60],
    "ziel_kategorien": {
        "Sanierung": ["Sanierungsgebiet", "Stadtsanierung", "Fördergebiet"],
        "Neubau": ["Neubaugebiet", "Bebauungsplan", "B-Plan", "Erschließung"],
        "Privatisierung": ["Grundstücksverkauf", "Veräußerung", "Liegenschaften"],
        "Tiefbau": ["Tiefbau", "Straßenbau", "Kanalsanierung", "Brückenbau"]
    }
}

# Query-Parameter die als harmlos gelten und für den Dedup-Check ignoriert werden.
IGNORIERE_PARAMS = {
    "sort", "order", "view", "page", "fil",
    "lang", "style", "layout", "tab", "session", "ref",
    "utm_source", "utm_medium", "utm_campaign"
}

PDF_PRIO_KEYWORDS = [
    "bekanntmachung", "bebauungsplan", "b-plan", "bplan",
    "satzung", "erschließung", "erschliessung", "ausschreibung",
    "vergabe", "foerderung", "förderung", "sanierung", "tiefbau"
]

CONSOLE_LOG_FILE = "crawler_console.log"
SKIPPED_LOG_FILE = "crawler_skipped_urls.log"

load_dotenv()

# =====================================================================
# --- OLLAMA KONFIGURATION (ersetzt Gemini) ---
# =====================================================================
OLLAMA_URL   = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")


# =====================================================================
# --- 2. API LIMIT MANAGER (Rolling Window) ---
# Für Ollama lokal gibt es keine harten API-Limits.
# Der TokenManager bleibt als optionaler Schutz vor Überlast erhalten.
# =====================================================================
class TokenManager:
    def __init__(self, rpm=60, tpm=2_000_000, rpd=100_000):
        self.rpm_limit      = rpm
        self.tpm_limit      = tpm
        self.rpd_limit      = rpd
        self.window         = deque()
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
            log_event("!!!", f"WARNUNG: Prompt zu groß ({estimated_tokens} Tokens) – übersprungen!")
            return False
        if date.today() > self.day_start_time:
            self.requests_today = 0
            self.day_start_time = date.today()
        if self.requests_today >= self.rpd_limit:
            log_event("!!!", "Tageslimit (RPD) erreicht.")
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
            log_event("⏳", f"Lokaler Schutz ({reason}): {rpm_info}  {tpm_info}  → warte {wait_secs:.1f}s")
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


def _reset_log_if_new_month(filepath):
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


def write_skipped_urls(ort, skipped_urls: list):
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
                    _write_console_log(f"[{get_german_time()}]       - Ignoriere altes PDF ({year}): {url[:60]}")
                    return ""
            text = ""
            for page in doc[:max_pages]:
                text += page.get_text()
            return text
    except Exception as e:
        _write_console_log(f"[{get_german_time()}]   ❌  PDF-Fehler ({url[:60]}): {e}")
        return ""


def get_pdf_year(url):
    match = re.search(r'(20\d{2})', url.split("/")[-1])
    return int(match.group(1)) if match else 9999


def is_prio_pdf(url):
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
    Gibt die URL zurück, bei der nur harmlose Query-Parameter (IGNORIERE_PARAMS)
    entfernt wurden. Bedeutungsvolle Parameter bleiben erhalten.
    """
    parsed = urlparse(url)
    if not parsed.query:
        return parsed._replace(fragment="").geturl()
    params     = parse_qs(parsed.query, keep_blank_values=True)
    gefiltert  = {k: v for k, v in params.items() if k.lower() not in IGNORIERE_PARAMS}
    neue_query = urlencode(gefiltert, doseq=True)
    return parsed._replace(query=neue_query, fragment="").geturl()


def get_subpages(start_url, max_pages):
    visited_base   = set()
    visited_full   = set()
    to_visit       = [start_url]
    html_collected = []
    pdf_collected  = []
    skipped_urls   = []
    status_log     = {}
    base_domain    = urlparse(start_url).netloc
    prio_keywords  = ["aktuell", "news", "nachricht", "bauen", "projekt", "bebauungsplan"]

    while to_visit and (len(html_collected) + len(pdf_collected)) < max_pages:
        curr      = to_visit.pop(0)
        curr_base = get_url_base(curr)

        if curr_base in visited_base:
            skipped_urls.append(curr)
            continue
        visited_base.add(curr_base)
        visited_full.add(curr)

        try:
            resp = requests.get(curr, timeout=CONFIG["timeout_seconds"],
                                headers={'User-Agent': 'BachelorCrawler/1.0'})
            status_log[curr] = resp.status_code

            if resp.url != curr:
                final_base = get_url_base(resp.url)
                if final_base in visited_base and final_base != curr_base:
                    skipped_urls.append(curr)
                    visited_base.discard(curr_base)
                    continue
                visited_base.add(final_base)
                visited_full.add(resp.url)

            if resp.status_code == 200:
                if curr.lower().endswith(".pdf"):
                    _write_console_log(f"[{get_german_time()}]   - Scanne PDF: {curr[:70]}")
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
        except requests.exceptions.Timeout:
            status_log[curr] = "TIMEOUT"
            _write_console_log(f"[{get_german_time()}]   ⏰ TIMEOUT: {curr[:80]}")
        except requests.exceptions.ConnectionError as e:
            status_log[curr] = "CONNECTION_ERROR"
            _write_console_log(f"[{get_german_time()}]   🔌 CONNECTION_ERROR: {curr[:70]} | {str(e)[:60]}")
        except Exception as ex:
            err = f"ERROR: {str(ex)[:60]}"
            status_log[curr] = err
            _write_console_log(f"[{get_german_time()}]   ❌ {err} bei {curr[:70]}")

    return html_collected, pdf_collected, skipped_urls, status_log


def assemble_text(ort, html_pages, pdf_pages, limit):
    text_bulk = ""
    for url, content in html_pages:
        if content:
            text_bulk += f"\n--- URL: {url} ---\n{content}"

    prio_pdfs    = [(u, t) for u, t in pdf_pages if is_prio_pdf(u)]
    normale_pdfs = [(u, t) for u, t in pdf_pages if not is_prio_pdf(u)]
    normale_pdfs.sort(key=lambda x: get_pdf_year(x[0]), reverse=True)
    sortierte_pdfs = prio_pdfs + normale_pdfs

    verbleibend = limit - len(text_bulk)

    gesamt_pdf_text = sum(len(t) for _, t in sortierte_pdfs)
    if gesamt_pdf_text <= verbleibend:
        for url, content in sortierte_pdfs:
            text_bulk += f"\n--- URL: {url} ---\n{content}"
        return text_bulk, False, False

    hat_gekuerzt = False
    for reduzierte_seiten in [3, 2, 1]:
        neu_pdf_texte = []
        for url, _ in sortierte_pdfs:
            neu_text = extract_pdf_text(url, reduzierte_seiten)
            neu_pdf_texte.append((url, neu_text))
        gesamt_neu = sum(len(t) for _, t in neu_pdf_texte)
        if gesamt_neu <= verbleibend:
            log_event("⚠️", f"Textlimit bei {ort} – PDFs auf {reduzierte_seiten} Seite(n) gekürzt "
                           f"({len(neu_pdf_texte)} PDFs betroffen)")
            for url, content in neu_pdf_texte:
                if content:
                    text_bulk += f"\n--- URL: {url} ---\n{content}"
            return text_bulk, True, False
        hat_gekuerzt = True

    normale_pdfs_sortiert = sorted(normale_pdfs, key=lambda x: get_pdf_year(x[0]))
    verbleibende_pdfs     = list(prio_pdfs) + list(normale_pdfs_sortiert)
    verworfen             = 0

    while verbleibende_pdfs:
        entfernt = False
        for i in range(len(verbleibende_pdfs) - 1, -1, -1):
            url, _ = verbleibende_pdfs[i]
            if not is_prio_pdf(url):
                verbleibende_pdfs.pop(i)
                verworfen += 1
                entfernt = True
                break
        if not entfernt:
            break
        probe_texte = []
        for url, _ in verbleibende_pdfs:
            t = extract_pdf_text(url, 1)
            probe_texte.append((url, t))
        if sum(len(t) for _, t in probe_texte) <= verbleibend:
            log_event("⚠️", f"Textlimit bei {ort} – {verworfen} älteste PDF(s) verworfen (mögl. Datenverlust)")
            for url, content in probe_texte:
                if content:
                    text_bulk += f"\n--- URL: {url} ---\n{content}"
            return text_bulk, hat_gekuerzt, True

    log_event("⚠️", f"Textlimit bei {ort} – nur noch Prio-PDFs mit je 1 Seite")
    for url, _ in prio_pdfs:
        content = extract_pdf_text(url, 1)
        if content and len(text_bulk) + len(content) < limit:
            text_bulk += f"\n--- URL: {url} ---\n{content}"

    return text_bulk, True, True


# =====================================================================
# --- 4. URL-NORMALISIERUNG ---
# =====================================================================
def normalize_url(raw_url, start_url):
    if not raw_url:
        return start_url
    parsed = urlparse(raw_url)
    if parsed.scheme in ('http', 'https'):
        return raw_url
    return urljoin(start_url, raw_url)


# =====================================================================
# --- 5. KI ANALYSE mit Ollama (ersetzt Gemini) ---
# =====================================================================
def _call_ollama_with_retry(prompt: str, est_tokens: int):
    """
    Sendet den Prompt an das lokal laufende Ollama-Modell.
    Identisches Retry-Verhalten wie der ursprüngliche Gemini-Call.
    """
    retries = CONFIG["ollama_retries"]
    delays  = CONFIG["ollama_retry_delays"]

    for versuch in range(retries + 1):
        try:
            resp = requests.post(
                OLLAMA_URL,
                json={
                    "model":  OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json"          # Ollama JSON-Modus – erzwingt gültiges JSON
                },
                timeout=300                   # großzügiges Timeout für lange Texte
            )
            resp.raise_for_status()
            api_guard.update_usage(est_tokens)
            return resp.json().get("response", "")
        except Exception as e:
            fehler_str = str(e)
            if versuch < retries:
                wait = delays[versuch]
                log_event("⚠️", f"Ollama-Fehler: {fehler_str[:60].strip()} – "
                                f"Versuch {versuch + 1}/{retries}, warte {wait}s ...")
                time.sleep(wait)
            else:
                log_event("❌", f"Ollama nach {retries} Versuchen nicht erreichbar – übersprungen.")
                return None
    return None


def analyze_with_ollama(gesammelter_text: str, start_url: str):
    """
    Ersetzt analyze_with_gemini() 1:1 – gleicher Prompt, gleiche Rückgabe.
    """
    est_tokens = len(gesammelter_text) // 4
    if not api_guard.check_limits(est_tokens):
        return []

    base_url          = f"{urlparse(start_url).scheme}://{urlparse(start_url).netloc}"
    kategorien_string = json.dumps(CONFIG["ziel_kategorien"], ensure_ascii=False, indent=2)

    prompt = f"""
        Du bist ein Experte für die Analyse kommunaler Ausschreibungen und Bauprojekte.

        AUFGABE:
        Extrahiere AUSSCHLIESSLICH echte Bau-, Infrastruktur- oder Sanierungsvorhaben.

        STRIKTE AUSSCHLUSSKRITERIEN - Ignoriere folgende Themen komplett:
        - Beschaffung von Fahrzeugen (LKW, Feuerwehrfahrzeuge, Busse etc.). Das ist KEIN Tiefbau!
        - Kursangebote, Thermalbad-Termine, Wellness-Programme oder medizinische Kurpläne (z.B. "AGES Kur").
        - Stellenausschreibungen oder reine Dienstleistungen (z.B. Winterdienst).
        - Kulturelle Veranstaltungen, Feste oder Sitzungstermine.

        KATEGORIEN:
        {kategorien_string}

        WICHTIG:
        - Wenn ein Text keine Baumaßnahme enthält, gib eine leere Liste zurück: {{"massnahmen": []}}
        - Jede Maßnahme MUSS ein Start- oder Enddatum haben.
        - "quelle_url": Gib IMMER eine vollständige absolute URL an, die mit http:// oder https:// beginnt.
          Die Basis-Domain lautet: {base_url}
          Bei mehreren URLs zur selben Maßnahme: wähle die mit dem konkretesten Inhalt.
        - Gibt es Dopplungen (gleiche Maßnahme, verschiedene URLs): nur einmal ausgeben.

        Antworte im JSON-Format:
        {{
            "massnahmen": [
                {{
                    "kategorie": "...",
                    "massnahme": "...",
                    "adresse": "...",
                    "massnahme_start": "YYYY-MM-DD",
                    "massnahme_ende": "YYYY-MM-DD",
                    "quelle_url": "..."
                }}
            ]
        }}

        Texte zum Analysieren:
        {gesammelter_text}
        """

    raw_response = _call_ollama_with_retry(prompt, est_tokens)
    if raw_response is None:
        return []

    try:
        raw        = raw_response.replace("```json", "").replace("```", "").strip()
        massnahmen = json.loads(raw).get("massnahmen", [])
        for item in massnahmen:
            item["quelle_url"] = normalize_url(item.get("quelle_url"), start_url)
        return massnahmen
    except Exception as e:
        log_event("❌", f"JSON-Parsing fehlgeschlagen: {e}")
        return []


# =====================================================================
# --- 6. DUPLIKAT-PRÜFUNG auf Maßnahmen-Ebene ---
# =====================================================================
def is_duplicate(cursor, ags, massnahme, massnahme_start):
    cursor.execute("""
        SELECT id FROM crawl_results
        WHERE ags = %s AND massnahme = %s AND massnahme_start = %s
    """, (ags, massnahme, massnahme_start))
    return cursor.fetchone() is not None


# =====================================================================
# --- 7. MAIN LOOP ---
# =====================================================================
def run_crawler():
    _reset_log_if_new_month(CONSOLE_LOG_FILE)
    _reset_log_if_new_month(SKIPPED_LOG_FILE)
    reset_live_log_if_new_day()

    _heartbeat_stop.clear()
    heartbeat = threading.Thread(target=_heartbeat_worker, daemon=True)
    heartbeat.start()

    conn   = get_db_connection()
    cursor = conn.cursor()

    targets_processed = 0
    total_funde       = 0
    start_zeit_dt     = datetime.now()

    write_history_log("START", f"Beginne Durchlauf mit max. {CONFIG['max_targets']} Targets.")

    cursor.execute(
        "SELECT ags, url, ort FROM crawl_targets ORDER BY last_scanned ASC NULLS FIRST LIMIT %s",
        (CONFIG["max_targets"],)
    )
    targets   = cursor.fetchall()
    min_datum = datetime.strptime(CONFIG["min_end_datum"], "%Y-%m-%d").date()

    try:
        for ags, start_url, ort in targets:
            start_time = datetime.now()

            log_event("🔍", f"Target: {ort} ({start_url})")
            update_live_log(ort, "🔍 Scraping & PDF-Analyse...")

            targets_processed += 1
            html_pages, pdf_pages, skipped_urls, status_log = get_subpages(start_url, CONFIG["max_subpages"])

            write_skipped_urls(ort, skipped_urls)
            if skipped_urls:
                log_event("🔗", f"{len(skipped_urls)} URL(s) per Dedup übersprungen für {ort} → siehe {SKIPPED_LOG_FILE}")

            text_bulk, hat_gekuerzt, hat_verworfen = assemble_text(
                ort, html_pages, pdf_pages, CONFIG["max_text_chars"]
            )

            if not text_bulk.strip():
                fehler_codes = set(status_log.values())
                fehler_info  = ", ".join(str(c) for c in sorted(fehler_codes, key=str))
                log_event("⚠️", f"Kein Text für {ort} – kein Timestamp gesetzt. Status-Codes: [{fehler_info}]")
                update_live_log(ort, f"⚠️ Kein Text [{fehler_info}]")
                continue

            content_hash = get_content_hash(text_bulk)
            cursor.execute("SELECT id FROM crawl_results WHERE content_hash = %s", (content_hash,))

            if cursor.fetchone():
                log_event("🔒", f"Keine Änderungen in {ort} (Hash-Match).")
                update_live_log(ort, "✅ Stand aktuell (Hash-Match)", gespart=True)
            else:
                log_event("🤖", f"Sende Daten für {ort} an Ollama ({OLLAMA_MODEL})...")
                update_live_log(ort, f"🤖 Ollama Analyse ({OLLAMA_MODEL})...")
                found = analyze_with_ollama(text_bulk, start_url)

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
                        except:
                            pass

                    if is_duplicate(cursor, ags, m_name, m_start):
                        skipped_dups += 1
                        log_event("🔄", f"Duplikat übersprungen: {m_name}")
                        continue

                    valid_count += 1
                    cursor.execute("""
                        INSERT INTO crawl_results
                            (ags, gefunden_am, start_time, end_time, status, kategorie,
                             massnahme, adresse, massnahme_start, massnahme_ende,
                             massnahme_url, content_hash)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        ags, datetime.now().strftime("%x"), start_time, datetime.now(),
                        "Erfolgreich",
                        item.get('kategorie'), m_name,
                        item.get("adresse"), m_start, m_ende,
                        item.get("quelle_url"), content_hash
                    ))

                total_funde += valid_count
                log_event("✅", f"Analyse beendet: {valid_count} neue Funde, "
                               f"{skipped_dups} Duplikate übersprungen für {ort}.")
                update_live_log(ort, f"✅ Fertig: {valid_count} Funde", funde=valid_count)

            cursor.execute("UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s",
                           (datetime.now(), ags))
            conn.commit()
            time.sleep(CONFIG["sleep_between_targets"])

    finally:
        _heartbeat_stop.set()
        heartbeat.join(timeout=5)

    dauer = datetime.now() - start_zeit_dt
    minuten, sekunden = divmod(dauer.seconds, 60)
    summary = (f"Beendet. {targets_processed} Orte gescannt, "
               f"{total_funde} Funde. Dauer: {minuten}m {sekunden}s.")

    write_history_log("ENDE ", summary)
    log_event("🏁", summary)
    update_live_log("Standby", f"🏁 Letzter Scan: {summary}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    run_crawler()
