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


def log_event(emoji, message):
    zeit = get_german_time()
    print(f"[{zeit}] {emoji} {message}")


def write_history_log(event_type, message):
    log_file = "crawler_history.txt"
    zeit = get_german_time()
    log_entry = f"[{zeit}] {event_type.upper()}: {message}\n"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(log_entry)
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


def get_subpages(start_url, max_pages):
    visited, to_visit = set(), [start_url]
    html_collected = []
    pdf_collected  = []
    base_domain    = urlparse(start_url).netloc
    prio_keywords  = ["aktuell", "news", "nachricht", "bauen", "projekt", "bebauungsplan"]

    while to_visit and (len(html_collected) + len(pdf_collected)) < max_pages:
        curr = to_visit.pop(0)
        if curr in visited:
            continue
        visited.add(curr)
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
                        nxt = urljoin(start_url, link['href'])
                        if (urlparse(nxt).netloc == base_domain
                                and is_relevant_url(nxt)
                                and nxt not in visited):
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
                  f"({len(neu_pdf_texte)} PDFs betroffen)")
            for url, content in neu_pdf_texte:
                if content:
                    text_bulk += f"\n--- URL: {url} ---\n{content}"
            return text_bulk, True, False
        hat_gekuerzt = True

    # --- Schritt 4: Älteste PDFs verwerfen bis es passt ---
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
            break  # Nur noch Prio-PDFs übrig – nicht mehr verwerfen

        probe_texte = []
        for url, _ in verbleibende_pdfs:
            t = extract_pdf_text(url, 1)
            probe_texte.append((url, t))

        if sum(len(t) for _, t in probe_texte) <= verbleibend:
            print(f"  ⚠️  Textlimit bei {ort} – {verworfen} älteste PDF(s) verworfen (mögl. Datenverlust)")
            for url, content in probe_texte:
                if content:
                    text_bulk += f"\n--- URL: {url} ---\n{content}"
            return text_bulk, hat_gekuerzt, True

    # Fallback: Prio-PDFs mit 1 Seite, Rest verworfen
    print(f"  ⚠️  Textlimit bei {ort} – nur noch Prio-PDFs mit je 1 Seite berücksichtigt")
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
# --- 5. KI ANALYSE mit Exponential Backoff ---
# =====================================================================
def _call_gemini_with_retry(prompt, est_tokens):
    """
    Führt den Gemini-API-Aufruf durch.
    Bei 503 ServiceUnavailable oder 504 GatewayTimeout wird automatisch
    mit Exponential Backoff wiederholt (nur lokaler print, kein Log/Verlauf).
    """
    retries = CONFIG["gemini_retries"]
    delays  = CONFIG["gemini_retry_delays"]

    for versuch in range(retries + 1):
        try:
            response = model.generate_content(prompt)
            used = response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else est_tokens
            api_guard.update_usage(used)
            return response
        except Exception as e:
            fehler_str = str(e)
            # 503 / 504 → Retry mit Backoff
            if any(code in fehler_str for code in ["503", "504", "ServiceUnavailable", "GatewayTimeout"]):
                if versuch < retries:
                    wait = delays[versuch]
                    print(f"  ⚠️  Gemini {fehler_str[:30].strip()} – Versuch {versuch + 1}/{retries}, warte {wait}s ...")
                    time.sleep(wait)
                else:
                    print(f"  ❌  Gemini nach {retries} Versuchen nicht erreichbar – übersprungen.")
                    return None
            else:
                # Andere Fehler (z.B. 429, JSON-Fehler) – sofort abbrechen
                print(f"  ❌  Gemini-Fehler (kein Retry): {fehler_str[:80]}")
                return None
    return None


def analyze_with_gemini(gesammelter_text, start_url):
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
          Beispiel korrekt:   {base_url}/projekte/strassenbau-2026
          Beispiel FALSCH:    /projekte/strassenbau-2026
          Beispiel FALSCH:    {base_url}
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

    response = _call_gemini_with_retry(prompt, est_tokens)
    if response is None:
        return []

    try:
        raw        = response.text.replace("```json", "").replace("```", "").strip()
        massnahmen = json.loads(raw).get("massnahmen", [])
        for item in massnahmen:
            item["quelle_url"] = normalize_url(item.get("quelle_url"), start_url)
        return massnahmen
    except Exception as e:
        print(f"  ❌  JSON-Parsing fehlgeschlagen: {e}")
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
            html_pages, pdf_pages = get_subpages(start_url, CONFIG["max_subpages"])

            text_bulk, hat_gekuerzt, hat_verworfen = assemble_text(
                ort, html_pages, pdf_pages, CONFIG["max_text_chars"]
            )

            if not text_bulk.strip():
                log_event("⚠️", f"Kein Text für {ort} gefunden.")
                update_live_log(ort, "⚠️ Kein Text gefunden")
                cursor.execute("UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s",
                               (datetime.now(), ags))
                conn.commit()
                continue

            content_hash = get_content_hash(text_bulk)
            cursor.execute("SELECT id FROM crawl_results WHERE content_hash = %s", (content_hash,))

            if cursor.fetchone():
                log_event("🔒", f"Keine Änderungen in {ort} (Hash-Match).")
                update_live_log(ort, "✅ Stand aktuell (Hash-Match)", gespart=True)
            else:
                log_event("🤖", f"Sende Daten für {ort} an Gemini...")
                update_live_log(ort, "🤖 Gemini Analyse...")
                found = analyze_with_gemini(text_bulk, start_url)

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
