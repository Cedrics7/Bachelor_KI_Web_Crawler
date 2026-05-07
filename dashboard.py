import streamlit as st
import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

# Konfiguration
load_dotenv()
# --- NEU: Hier wird das Telekom-Logo als Browser-Icon gesetzt ---
TELEKOM_LOGO_URL = "https:/upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Deutsche_Telekom_2022.svg/330px-Deutsche_Telekom_2022.svg.png?utm_source=commons.wikimedia.org&utm_campaign=index&utm_content=thumbnail&_=20220513094037"

st.set_page_config(
    page_title="Crawler Dashboard",
    layout="wide",
    page_icon= TELEKOM_LOGO_URL
)



# --- DATENBANKVERBINDUNG (mit Cache für hohe Geschwindigkeit) ---
@st.cache_data(ttl=60)  # Lädt die Daten alle 60 Sek neu (anpassbar)
def get_data():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT")
    )

    # 1. Hauptdaten (Stammdaten) laden
    query_targets = "SELECT * FROM crawl_targets ORDER BY id ASC"
    df_targets = pd.read_sql(query_targets, conn)

    # 2. ALLE Ergebnisse (Bewegungsdaten) laden
    query_results = "SELECT * FROM crawl_results ORDER BY end_time DESC"
    df_results = pd.read_sql(query_results, conn)

    conn.close()
    return df_targets, df_results


try:
    df_targets, df_results = get_data()
    # Datumsformat sicherstellen, damit wir später filtern können
    df_targets['last_scanned'] = pd.to_datetime(df_targets['last_scanned'])
except Exception as e:
    st.error(f"Fehler bei der Datenverarbeitung: {e}")
    st.stop()

# =====================================================================
# --- SEITEN-NAVIGATION ---
# =====================================================================
st.sidebar.title("Navigation")
ansicht = st.sidebar.radio("Bereich auswählen", [
    "Bestandsdaten (Targets)",
    "Bewegungsdaten (Results)"
])

st.sidebar.divider()
st.sidebar.caption("Crawler Status")
st.sidebar.success("System bereit")

# =====================================================================
# ANSICHT 1: BESTANDSDATEN (Stammdaten der Orte)
# =====================================================================
if ansicht == "Bestandsdaten (Targets)":
    st.title("Bestandsdaten")

    # --- LOGIK: AKTUELLER MONAT ---
    # Wir nehmen den 1. Tag des aktuellen Monats als Grenze
    monats_anfang = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    st.markdown(f"Statusübersicht für den aktuellen Monat: **{monats_anfang.strftime('%B %Y')}**")

    # --- METRIKEN (Monatsbasiert) ---
    total_count = len(df_targets)
    # Zählt nur die Orte, deren Scan-Datum im aktuellen Monat liegt
    gecrawlt_count = df_targets[df_targets['last_scanned'] >= monats_anfang].shape[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Orte Gesamt", total_count)
    c2.metric("In diesem Monat gecrawlt", gecrawlt_count)
    c3.metric("Diesen Monat ausstehend", total_count - gecrawlt_count)

    st.divider()

    # --- FILTER ---
    st.subheader("Filter")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        such_ort = st.text_input("Suche (Ort oder AGS):", placeholder="z.B. Barßel")
    with col_f2:
        status_filter = st.selectbox("Crawl-Status (aktueller Monat):", [
            "Alle anzeigen",
            "Nur diesen Monat ausstehend",
            "Diesen Monat bereits gecrawlt"
        ])

    # Filtern anwenden
    df_anzeige = df_targets.copy()

    if such_ort:
        df_anzeige = df_anzeige[
            df_anzeige['ort'].str.contains(such_ort, case=False, na=False) |
            df_anzeige['ags'].str.contains(such_ort, na=False)
            ]

    if status_filter == "Nur diesen Monat ausstehend":
        # Ausstehend ist alles, was VOR diesem Monat gecrawlt wurde ODER noch nie (NaT) gecrawlt wurde
        df_anzeige = df_anzeige[(df_anzeige['last_scanned'] < monats_anfang) | (df_anzeige['last_scanned'].isna())]
    elif status_filter == "Diesen Monat bereits gecrawlt":
        # Bereits gecrawlt ist alles, was AB dem Monatsersten gecrawlt wurde
        df_anzeige = df_anzeige[df_anzeige['last_scanned'] >= monats_anfang]

    # --- TABELLE ---
    st.dataframe(
        df_anzeige[['id', 'ort', 'ags', 'bundesland', 'last_scanned', 'url']],
        column_config={
            "url": st.column_config.LinkColumn("Startseite"),
            "last_scanned": st.column_config.DatetimeColumn("Letzter Crawl", format="DD.MM.YYYY HH:mm")
        },
        use_container_width=True,
        hide_index=True,
        height=500
    )

# =====================================================================
# ANSICHT 2: BEWEGUNGSDATEN (Gefundene Maßnahmen)
# =====================================================================
elif ansicht == "Bewegungsdaten (Results)":
    st.title("Bewegungsdaten")
    st.markdown("Extrahierte Baumaßnahmen und Infrastrukturprojekte.")

    if df_results.empty:
        st.info("Noch keine Crawler-Ergebnisse vorhanden.")
    else:
        # 1. HIER GEÄNDERT: Wir laden zusätzlich 'bundesland' aus den Stammdaten
        # (Wichtig: Prüfe, ob deine Spalte 'bundesland' oder 'Bundesland' heißt!)
        df_merged = df_results.merge(df_targets[['ags', 'ort', 'bundesland']], on='ags', how='left')

        # Nur erfolgreiche Funde anzeigen
        df_merged = df_merged[df_merged['massnahme'].notna()]

        # --- FILTER ---
        st.subheader("Filter")
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            such_massnahme = st.text_input("Suche (Stichwort):", placeholder="z.B. Brücke")

        with col_f2:
            # 2. HIER GEÄNDERT: Filter für Bundesland statt Gemeinde
            bundeslaender_mit_funden = ["Alle"] + sorted(list(df_merged['bundesland'].dropna().unique()))
            bundesland_filter = st.selectbox("Bundesland:", bundeslaender_mit_funden)

        with col_f3:
            # Extrahiere die Kategorien aus dem Titel (z.B. "[Neubau]...")
            df_merged['kategorie_extract'] = df_merged['massnahme'].str.extract(r'\[(.*?)\]')
            kategorien = ["Alle"] + sorted(list(df_merged['kategorie_extract'].dropna().unique()))
            kat_filter = st.selectbox("Kategorie:", kategorien)

        # Filtern anwenden
        if such_massnahme:
            df_merged = df_merged[df_merged['massnahme'].str.contains(such_massnahme, case=False, na=False) | df_merged[
                'ort'].str.contains(such_massnahme, case=False, na=False)]

        # 3. HIER GEÄNDERT: Filter-Logik wendet das Bundesland an
        if bundesland_filter != "Alle":
            df_merged = df_merged[df_merged['bundesland'] == bundesland_filter]

        if kat_filter != "Alle":
            df_merged = df_merged[df_merged['kategorie_extract'] == kat_filter]

        st.divider()

        # --- TABELLE ---
        # 4. HIER GEÄNDERT: Ich habe 'bundesland' ganz vorne zur Tabelle hinzugefügt,
        # damit der Nutzer direkt sieht, dass der Filter funktioniert hat.
        st.dataframe(
            df_merged[
                ['bundesland', 'ort', 'massnahme_start', 'massnahme_ende', 'massnahme', 'adresse', 'massnahme_url']],
            column_config={
                "bundesland": "Bundesland",
                "ort": "Gemeinde",
                "massnahme_start": st.column_config.DateColumn("Start", format="DD.MM.YYYY"),
                "massnahme_ende": st.column_config.DateColumn("Ende", format="DD.MM.YYYY"),
                "massnahme": "Maßnahme",
                "adresse": "Adresse",
                "massnahme_url": st.column_config.LinkColumn("Quelle öffnen")
            },
            use_container_width=True,
            hide_index=True,
            height=600
        )