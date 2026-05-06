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


# =====================================================================
# --- 1. CRAWLER KONFIGURATION (Anpassbare Parameter) ---
# =====================================================================
CONFIG = {
    "max_targets": 2,  # Wie viele Behörden/Städte pro Durchlauf gecrawlt werden sollen (Hauptseiten)
    "max_subpages": 5,  # Wie viele Unterseiten pro Behörde maximal gesammelt werden (inkl. Startseite)
    "timeout_seconds": 10,  # Wie lange auf die Antwort einer Webseite gewartet wird
    "sleep_between_targets": 2,  # Pause in Sekunden zwischen zwei Behörden (schont Server und API)
    "min_end_datum": str(date.today()),
    "ziel_kategorien": {
        "Sanierung": ["Sanierungsgebiet", "Stadtsanierung", "Fördergebiet"],
        "Neubau": ["Neubaugebiet", "Bebauungsplan", "B-Plan", "Erschließung"],
        "Privatisierung": ["Grundstücksverkauf", "Veräußerung", "Liegenschaften"],
        "Tiefbau": ["Tiefbau", "Straßenbau", "Kanalsanierung", "Brückenbau"]
    }
}
# =====================================================================

load_dotenv()

# Google Gemini konfigurieren
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Wir erzwingen JSON als Ausgabeformat für maximale Zuverlässigkeit
model = genai.GenerativeModel(
    'gemini-3.1-flash-lite-preview',
    generation_config={"response_mime_type": "application/json"}
)


# Datenbankverbindung
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT")
    )


# --- 2. HILFSFUNKTIONEN FÜRS SCRAPING ---
def is_relevant_url(url):
    """Filtert URLs heraus, die keine inhaltlichen Ergebnisse bringen."""
    ignore_keywords = ["impressum", "datenschutz", "kontakt", "sitemap", "login", "agb", ".pdf", ".jpg"]
    return not any(keyword in url.lower() for keyword in ignore_keywords)


def extract_main_text(html):
    """Extrahiert den reinen Text ohne Navigation, Footer und Code."""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def get_subpages(start_url, max_pages):
    """Holt die Startseite und bis zu max_pages relevante Unterseiten."""
    visited = set()
    to_visit = [start_url]
    collected_urls = []
    base_domain = urlparse(start_url).netloc

    # Header setzen, damit der Crawler nicht direkt geblockt wird
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

    while to_visit and len(collected_urls) < max_pages:
        current_url = to_visit.pop(0)

        if current_url in visited:
            continue

        visited.add(current_url)

        try:
            response = requests.get(current_url, headers=headers, timeout=CONFIG["timeout_seconds"])
            if response.status_code != 200:
                continue

            collected_urls.append((current_url, response.text))

            # Neue Links auf der Seite finden
            soup = BeautifulSoup(response.text, "html.parser")
            for link in soup.find_all('a', href=True):
                next_url = urljoin(start_url, link['href'])
                # Nur Links der gleichen Domain und relevante URLs
                if urlparse(next_url).netloc == base_domain and is_relevant_url(next_url) and next_url not in visited:
                    to_visit.append(next_url)

        except Exception as e:
            print(f"Fehler beim Laden von {current_url}: {e}")

    return collected_urls


# --- 3. KI ANALYSE ---
def analyze_with_gemini(gesammelter_text):
    kategorien_string = json.dumps(CONFIG["ziel_kategorien"], ensure_ascii=False, indent=2)

    prompt = f"""
    Du bist ein hochspezialisierter Analyst für kommunale Bau- und Infrastrukturdaten.
    Extrahiere AUSSCHLIESSLICH Maßnahmen, die in diese Kategorien passen:
    {kategorien_string}

    STRIKTE REGELN:
    - Ignoriere lokale Feste, Verwaltungsdienstleistungen, PR, Kioske, etc.

    Antworte AUSSCHLIESSLICH mit einem JSON-Objekt. Schema:
    {{
        "massnahmen": [
            {{
                "kategorie": "Die passende Hauptkategorie",
                "massnahme": "Kurzer, prägnanter Titel",
                "adresse": "Ort oder Adresse (oder null)",
                "massnahme_start": "Startdatum im Format YYYY-MM-DD (oder null)",
                "massnahme_ende": "Enddatum im Format YYYY-MM-DD (oder null)"
            }}
        ]
    }}

    Hier ist der Text:
    {gesammelter_text}
    """

    try:
        response = model.generate_content(prompt)
        data = json.loads(response.text)
        return data.get("massnahmen", [])
    except Exception as e:
        print(f"Fehler bei der Gemini API: {e}")
        return []


# --- 4. HAUPT-LOGIK (CRAWLER LOOP) ---
def run_crawler():
    conn = get_db_connection()
    cursor = conn.cursor()

    max_targets = CONFIG["max_targets"]
    max_subpages = CONFIG["max_subpages"]

    print(f"Starter Crawler-Durchlauf: Max. {max_targets} Behörden, je max. {max_subpages} Seiten.")

    # Hole Behörden, die noch nie oder lange nicht gecrawlt wurden, limitiert durch CONFIG
    cursor.execute("""
        SELECT ags, url, ort FROM crawl_targets 
        ORDER BY last_scanned ASC NULLS FIRST, id ASC LIMIT %s
    """, (max_targets,))
    targets = cursor.fetchall()

    if not targets:
        print("Keine Ziele in der Datenbank gefunden.")
        return

    for ags, start_url, ort in targets:
        print(f"\nStarte Crawl für: {ort} ({start_url})")
        start_time = datetime.now()

        # 1. Sammle Unterseiten limitiert durch CONFIG
        pages_data = get_subpages(start_url, max_pages=max_subpages)
        anzahl_links = len(pages_data)
        print(f"-> {anzahl_links} Seiten gesammelt. Extrahiere Text...")

        # 2. Text aggregieren
        gesammelter_text = ""
        for url, html in pages_data:
            text = extract_main_text(html)
            gesammelter_text += f"\n\n--- INHALT VON {url} ---\n{text}"

        # 3. An Gemini schicken (nur ein einziger API Aufruf!)
        print("-> Sende Daten an Gemini 3.1 Flash Lite...")
        massnahmen_roh_liste = analyze_with_gemini(gesammelter_text)

        # --- NEU: DATUMS-FILTERUNG ---
        min_datum = datetime.strptime(CONFIG["min_end_datum"], "%Y-%m-%d").date()
        massnahmen_liste = []

        for item in massnahmen_roh_liste:
            m_start = item.get("massnahme_start")
            m_ende = item.get("massnahme_ende")

            # 1. Bedingung: Maßnahme muss ein Start- ODER Enddatum haben
            if not m_start and not m_ende:
                continue

            # 2. Bedingung: Wenn es ein Enddatum gibt, darf es nicht vor "heute" liegen
            if m_ende:
                try:
                    ende_dt = datetime.strptime(m_ende, "%Y-%m-%d").date()
                    if ende_dt < min_datum:
                        continue  # Maßnahme ist in der Vergangenheit -> ignorieren
                except ValueError:
                    pass  # Falls Gemini das Datum nicht sauber als YYYY-MM-DD formatiert hat

            massnahmen_liste.append(item)

        print(f"-> Nach Filterung (Datum): {len(massnahmen_liste)} gültige Maßnahmen gefunden.")

        end_time = datetime.now()

        # Ergebnisse in die Datenbank schreiben
        if massnahmen_liste:
            for item in massnahmen_liste:
                titel = f"[{item.get('kategorie')}] {item.get('massnahme')}"

                # Hier werden die neuen Spalten massnahme_start und massnahme_ende befüllt
                cursor.execute("""
                            INSERT INTO crawl_results 
                            (ags, start_time, end_time, status, gefundene_links, massnahme, adresse, massnahme_start, massnahme_ende)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """, (
                    ags, start_time, end_time, "Erfolgreich", anzahl_links,
                    titel, item.get("adresse"), item.get("massnahme_start"), item.get("massnahme_ende")
                ))
        else:
            cursor.execute("""
                        INSERT INTO crawl_results 
                        (ags, start_time, end_time, status, gefundene_links)
                        VALUES (%s, %s, %s, %s, %s)
                    """, (ags, start_time, end_time, "Keine validen Funde", anzahl_links))

        # 5. Timestamp in Stammdaten aktualisieren
        cursor.execute("UPDATE crawl_targets SET last_scanned = %s WHERE ags = %s", (end_time, ags))
        conn.commit()

        print(f"✓ {ort} abgeschlossen.")

        # Pause zwischen den Zielen, wie in CONFIG definiert
        time.sleep(CONFIG["sleep_between_targets"])

    cursor.close()
    conn.close()
    print("\nCrawler-Durchlauf beendet.")


if __name__ == "__main__":
    run_crawler()