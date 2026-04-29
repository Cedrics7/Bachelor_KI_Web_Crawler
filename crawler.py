import os

from dotenv import load_dotenv, find_dotenv

import requests

from bs4 import BeautifulSoup

from urllib.parse import urljoin

import heapq

import time

import json

import google.generativeai as genai

# ==========================================

# EINSTELLUNGEN

# ==========================================

API_URL = "http://127.0.0.1:8000/termine/"

START_URL = "https://www.buxtehude.de"  # <-- HIER START-URL EINTRAGEN


# Sucht aktiv nach der .env Datei im Projektverzeichnis und lädt sie
dotenv_path = find_dotenv()
load_dotenv(dotenv_path)

# Holt den Key aus der Systemumgebung
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    print("❌ FEHLER: Kein API_KEY in der .env Datei gefunden!")
    exit()

genai.configure(api_key=GEMINI_API_KEY)

# ==========================================

# 1. DAS NAVIGATIONS-GEHIRN (Heuristik)

# ==========================================

def bewerte_link(link_text, link_url):
    """Bewertet, wie relevant ein Link für Tiefbau/Telekommunikation ist."""

    score = 0

    link_text = str(link_text).lower()

    link_url = str(link_url).lower()

    # SUPER-Treffer (Hohe Relevanz für Tiefbau)

    top_woerter = ["baumaßnahmen", "baustellen", "straßenbau", "tiefbau", "sperrung", "ausbau", "infrastruktur",
                   "erschließung", "verkehr", "bauarbeiten"]

    for wort in top_woerter:

        if wort in link_text or wort in link_url:
            score += 50

    # Gute Treffer

    gute_woerter = ["bekanntmachungen", "pressemitteilungen", "aktuelles", "stadtentwicklung", "bauen", "news"]

    for wort in gute_woerter:

        if wort in link_text or wort in link_url:
            score += 20

    # Minuspunkte (Müll vermeiden)

    schlechte_woerter = ["kultur", "tourismus", "freizeit", "sport", "schulen", "kitas", "impressum", "datenschutz",
                         "login", "karriere"]

    for wort in schlechte_woerter:

        if wort in link_text or wort in link_url:
            score -= 50

    return max(0, min(100, score))


# ==========================================

# 2. DIE INHALTS-EXTRAKTION (GEMINI KI)

# ==========================================

def extrahiere_baumassnahmen_mit_ki(sichtbarer_text, aktuelle_url):
    """Gibt den Text an Gemini und fordert ein striktes JSON-Array zurück."""

    prompt = f"""

    Du bist ein technischer Analyst für ein Telekommunikationsunternehmen. 

    Lies den folgenden Text einer behördlichen Webseite. 

    Wir suchen AUSSCHLIESSLICH nach echten physischen Baumaßnahmen, bei denen der Boden geöffnet wird (Tiefbau, Straßenbau, Leitungsbau, Rohrverlegung, Erschließung, Breitbandausbau).



    WICHTIGSTE REGEL: 

    Ignoriere reine Verkehrshinweise, Staumeldungen, Blitzer, Unfälle, Straßenfeste, "Verkehrstipps", "Verkehrsversuche" oder kurzfristige Sperrungen ohne Erdarbeiten komplett! Wenn es kein echter Bau ist, nimm es nicht auf.



    Extrahiere die Daten EXAKT in folgendes JSON-Format:

    [

        {{

            "titel": "Kurze Beschreibung (z.B. Ausbau L123)",

            "ort": "Betroffene Straße oder Ortsteil",

            "genaue_lage": "Exakte Hausnummern, Straßenabschnitte von-bis, Kreuzungen oder Koordinaten (falls im Text genannt, sonst null)",

            "art_der_massnahme": "z.B. Straßenbau, Kanalbau, Wasserleitungen",

            "startdatum": "YYYY-MM-DD oder null",

            "enddatum": "YYYY-MM-DD oder null",

            "ausfuehrende_stelle": "z.B. Stadtwerke (oder null)",

            "link": "{aktuelle_url}"

        }}

    ]

    Gib AUSSCHLIESSLICH das gültige JSON-Array zurück. Wenn im Text keine relevanten Baumaßnahmen stehen, gib zwingend [] zurück.



    Text der Webseite:

    {sichtbarer_text}

    """

    print("🧠 Sende Text an Gemini Flash zur Analyse...")

    try:

        model = genai.GenerativeModel(

            'gemini-flash-latest',

            generation_config={"response_mime_type": "application/json"}

        )

        response = model.generate_content(prompt)

        ki_antwort = response.text

        daten = json.loads(ki_antwort)

        # Kleine Filterung zur Sicherheit, falls die KI leere Objekte zurückgibt

        saubere_daten = [d for d in daten if d.get("titel") and d.get("ort")]

        return saubere_daten



    except Exception as e:

        print(f"❌ Fehler bei der KI-Verarbeitung: {e}")

        return []


# ==========================================

# 3. VERBINDUNG ZUR DATENBANK (API)

# ==========================================

def send_to_api(massnahme):
    try:

        response = requests.post(API_URL, json=massnahme)

        if response.status_code == 200:

            print(f"✅ GESPEICHERT: {massnahme.get('titel')} in {massnahme.get('ort')}")

        elif response.status_code == 400:

            print(f"⏭️ ÜBERSPRUNGEN (existiert schon): {massnahme.get('titel')}")

        else:

            print(f"❌ API-Fehler {response.status_code}: {response.text}")

    except requests.exceptions.ConnectionError:

        print("❌ Verbindungsfehler zur API. Läuft main.py auf Port 8000?")


# ==========================================

# 4. DER HAUPT-CRAWLER (Best-First Search)

# ==========================================

def run_crawler(start_url, max_seiten=10):
    besuchte_seiten = set()

    warteschlange = []

    # Start-URL in die Priority-Queue packen (Score -100 bedeutet: SEHR WICHTIG)

    heapq.heappush(warteschlange, (-100, start_url))

    seiten_besucht_count = 0

    print(f"🚀 Starte Crawler auf: {start_url}")

    while warteschlange and seiten_besucht_count < max_seiten:

        # Den vielversprechendsten Link holen (kleinster Wert zuerst, da negativ)

        score_negativ, aktuelle_url = heapq.heappop(warteschlange)

        if aktuelle_url in besuchte_seiten:
            continue

        print(f"\n--- Seite {seiten_besucht_count + 1}/{max_seiten} ---")

        print(f"🕸️ Besuche: {aktuelle_url} (Relevanz-Score: {-score_negativ})")

        besuchte_seiten.add(aktuelle_url)

        seiten_besucht_count += 1

        try:

            # HTML herunterladen (Timeout auf 10s, tun als wären wir ein Browser)

            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

            response = requests.get(aktuelle_url, headers=headers, timeout=10)

            soup = BeautifulSoup(response.text, 'html.parser')

            # 1. Text für die KI extrahieren (ohne unsichtbare Scripte)

            for script in soup(["script", "style", "nav", "footer"]):
                script.extract()

            sichtbarer_text = soup.get_text(separator=' ', strip=True)

            # 2. KI-Analyse durchführen

            if len(sichtbarer_text) > 100:  # Leere Seiten überspringen

                gefundene_massnahmen = extrahiere_baumassnahmen_mit_ki(sichtbarer_text, aktuelle_url)

                for massnahme in gefundene_massnahmen:
                    send_to_api(massnahme)

            # 3. Neue Links für die Warteschlange suchen

            for link in soup.find_all('a', href=True):

                link_text = link.text.strip()

                neuer_link = urljoin(aktuelle_url, link['href'])

                # Nur interne Links der gleichen Hauptseite beachten

                if neuer_link.startswith(start_url) and neuer_link not in besuchte_seiten:

                    link_score = bewerte_link(link_text, neuer_link)

                    # Nur Links aufnehmen, die zumindest etwas relevant sein könnten

                    if link_score > 0:
                        heapq.heappush(warteschlange, (-link_score, neuer_link))



        except Exception as e:

            print(f"⚠️ Fehler beim Laden von {aktuelle_url}: {e}")

        # Pause, um die Server der Kommunen nicht zu überlasten

        time.sleep(2)

    print("\n🏁 Crawler-Durchlauf beendet.")


if __name__ == "__main__":
    # Wir testen erstmal mit 5 Seiten. Später kannst du das auf 50 oder 100 hochstellen.

    run_crawler(START_URL, max_seiten=5)

