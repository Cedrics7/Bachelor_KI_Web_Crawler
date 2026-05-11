import os
import json
import time
import requests
from bs4 import BeautifulSoup
import psycopg2
from datetime import datetime, date
from dotenv import load_dotenv
import google.generativeai as genai
from urllib.parse import urljoin, urlparse
import hashlib
import fitz
from bs4 import XMLParsedAsHTMLWarning
import warnings

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

#todo Patchnotes

# =====================================================================
# --- 1. CRAWLER KONFIGURATION ---
# =====================================================================
CONFIG = {
    "max_log_lines": 200,
    "max_targets": 3,
    "max_subpages": 50,
    "max_pdf_pages": 5,
    "timeout_seconds": 10,
    "sleep_between_targets": 2,
    "min_end_datum": str(date.today()),
    "ziel_kategorien": {
        "Sanierung": ["Sanierungsgebiet", "Stadtsanierung", "Fördergebiet"],
        "Neubau": ["Neubaugebiet", "Bebauungsplan", "B-Plan", "Erschließung"],
        "Privatisierung": ["Grundstücksverkauf", "Veräußerung", "Liegenschaften"],
        "Tiefbau": ["Tiefbau", "Straßenbau", "Kanalsanierung", "Brückenbau"]
    }
}

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
model = genai.GenerativeModel(
    'gemini-3.1-flash-lite-preview',
    generation_config={"response_mime_type": "application/json"}
)


def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT")
    )


# =====================================================================
# --- 2. API LIMIT MANAGER ---
# =====================================================================
class TokenManager:
    def __init__(self, rpm=12, tpm=200000, rpd=480):
        self.rpm_limit = rpm
        self.tpm_limit = tpm
        self.rpd_limit = rpd
        self.requests_this_minute = 0
        self.tokens_this_minute = 0
        self.requests_today = 0
        self.minute_start_time = datetime.now()
        self.day_start_time = date.today()

    def check_limits(self, estimated_tokens):
        if estimated_tokens >= self.tpm_limit:
            print(f"!!! WARNUNG: Prompt zu groß ({estimated_tokens} Tokens)!")
            return True

        while True:
            now = datetime.now()
            if date.today() > self.day_start_time:
                self.requests_today = 0
                self.day_start_time = date.today()
            if (now - self.minute_start_time).seconds >= 60:
                self.requests_this_minute = 0
                self.tokens_this_minute = 0
                self.minute_start_time = now

            if self.requests_today >= self.rpd_limit:
                print("!!! Tageslimit erreicht.")
                return False

            if (self.requests_this_minute < self.rpm_limit) and \
                    (self.tokens_this_minute + estimated_tokens < self.tpm_limit):
                return True

            wait_time = 65 - (now - self.minute_start_time).seconds
            print(f"--- API Schutz: Pause für {wait_time}s ---")
            time.sleep(max(wait_time, 1))

    def update_usage(self, token_count):
        self.requests_this_minute += 1
        self.tokens_this_minute += token_count
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

    # Datei auf 100 Zeilen begrenzen
    try:
        with open(log_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > CONFIG["max_log_lines"]:
            with open(log_file, "w", encoding="utf-8") as f:
                f.writelines(lines[-CONFIG["max_log_lines"]:])
    except FileNotFoundError:
        pass


def update_live_log(ort, status, funde=0, gespart=False):
    log_data = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "aktueller_ort": ort,
        "status": status,
        "letzte_funde": funde,
        "hash_match": gespart
    }
    with open("crawler_live_status.json", "w", encoding="utf-8") as f:
        json.dump(log_data, f, ensure_ascii=False, indent=2)

def extract_pdf_text(url, max_pages):
    try:
        response = requests.get(url, timeout=10)
        with fitz.open(stream=response.content, filetype="pdf") as doc:
            meta = doc.metadata
            c_date = meta.get("creationDate", "")
            if c_date.startswith("D:"):
                year = int(c_date[2:6])
                if year < 2024:
                    print(f"      - Ignoriere altes PDF ({year})")
                    return ""

            text = ""
            for page in doc[:max_pages]:
                text += page.get_text()
            return text
    except Exception as e:
        return ""


def get_content_hash(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def extract_main_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def is_relevant_url(url):
    # .pdf hier NICHT ignorieren, da wir sie in get_subpages explizit verarbeiten
    ignore = ["impressum", "datenschutz", "kontakt", "sitemap", "login", ".jpg", ".png"]
    return not any(kw in url.lower() for kw in ignore)


def get_subpages(start_url, max_pages):
    visited, to_visit = set(), [start_url]
    html_collected = []
    pdf_collected = []
    base_domain = urlparse(start_url).netloc

    # FIX: prio_keywords innerhalb der Funktion definiert
    prio_keywords = ["aktuell", "news", "nachricht", "bauen", "projekt", "bebauungsplan"]

    while to_visit and (len(html_collected) + len(pdf_collected)) < max_pages:
        curr = to_visit.pop(0)
        if curr in visited: continue
        visited.add(curr)

        try:
            resp = requests.get(curr, timeout=CONFIG["timeout_seconds"], headers={'User-Agent': 'BachelorCrawler/1.0'})
            if resp.status_code == 200:
                if curr.lower().endswith(".pdf"):
                    print(f"  - Scanne PDF: {curr[:50]}...")
                    # Aufruf mit max_pages aus CONFIG
                    text = extract_pdf_text(curr, CONFIG["max_pdf_pages"])
                    if text:
                        pdf_collected.append((curr, text))
                else:
                    text = extract_main_text(resp.text)
                    html_collected.append((curr, text))

                    soup = BeautifulSoup(resp.text, "html.parser")
                    for link in soup.find_all('a', href=True):
                        nxt = urljoin(start_url, link['href'])
                        if urlparse(nxt).netloc == base_domain and is_relevant_url(nxt) and nxt not in visited:
                            if any(p in nxt.lower() for p in prio_keywords):
                                to_visit.insert(0, nxt)
                            else:
                                to_visit.append(nxt)
        except:
            continue

    return html_collected + pdf_collected


# =====================================================================
# --- 4. KI ANALYSE ---
# =====================================================================

def analyze_with_gemini(gesammelter_text):
    est_tokens = len(gesammelter_text) // 4
    if not api_guard.check_limits(est_tokens): return []

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
    try:
        response = model.generate_content(prompt)
        used = response.usage_metadata.prompt_token_count if hasattr(response, 'usage_metadata') else est_tokens
        api_guard.update_usage(used)

        raw = response.text.replace("```json", "").replace("```", "").strip()
        return json.loads(raw).get("massnahmen", [])
    except:
        return []


# --- 5. MAIN LOOP ---
def run_crawler():
    conn = get_db_connection()
    cursor = conn.cursor()

    targets_processed = 0
    total_funde = 0
    start_zeit_dt = datetime.now()

    write_history_log("START", f"Beginne Durchlauf mit max. {CONFIG['max_targets']} Targets.")

    cursor.execute("SELECT ags, url, ort FROM crawl_targets ORDER BY last_scanned ASC NULLS FIRST LIMIT %s",
                   (CONFIG["max_targets"],))
    targets = cursor.fetchall()

    min_datum = datetime.strptime(CONFIG["min_end_datum"], "%Y-%m-%d").date()

    for ags, start_url, ort in targets:
        start_time = datetime.now()

        log_event("🔍", f"Target: {ort} ({start_url})")
        update_live_log(ort, "🔍 Scraping & PDF-Analyse...")

        targets_processed += 1
        pages = get_subpages(start_url, CONFIG["max_subpages"])

        text_bulk = ""
        for url, content in pages:
            if content and len(text_bulk) + len(content) < 500000:
                text_bulk += f"\n--- URL: {url} ---\n{content}"

        if not text_bulk.strip():
            log_event("⚠️", f"Kein Text für {ort} gefunden.")
            update_live_log(ort, "⚠️ Kein Text gefunden")
            cursor.execute("UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s", (datetime.now(), ags))
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
            found = analyze_with_gemini(text_bulk)

            valid_count = 0
            for item in found:
                m_start = item.get("massnahme_start")
                m_ende = item.get("massnahme_ende")
                if not m_start and not m_ende: continue
                if m_ende:
                    try:
                        if datetime.strptime(m_ende, "%Y-%m-%d").date() < min_datum: continue
                    except:
                        pass

                valid_count += 1
                cursor.execute("""
                    INSERT INTO crawl_results (ags, start_time, end_time, status, massnahme, adresse, massnahme_start, massnahme_ende, massnahme_url, content_hash)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (ags, start_time, datetime.now(), "Erfolgreich",
                      f"[{item.get('kategorie')}] {item.get('massnahme')}",
                      item.get("adresse"), item.get("massnahme_start"), item.get("massnahme_ende"),
                      item.get("quelle_url"), content_hash))

            total_funde += valid_count
            log_event("✅", f"Analyse beendet: {valid_count} neue Funde für {ort}.")
            update_live_log(ort, f"✅ Fertig: {valid_count} Funde", funde=valid_count)

        cursor.execute("UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s", (datetime.now(), ags))
        conn.commit()
        time.sleep(CONFIG["sleep_between_targets"])

    dauer = datetime.now() - start_zeit_dt
    minuten, sekunden = divmod(dauer.seconds, 60)
    summary = f"Beendet. {targets_processed} Orte gescannt, {total_funde} Funde. Dauer: {minuten}m {sekunden}s."

    write_history_log("ENDE ", summary)
    log_event("🏁", summary)
    update_live_log("Standby", f"🏁 Letzter Scan: {summary}")

    cursor.close()
    conn.close()


if __name__ == "__main__":
    run_crawler()