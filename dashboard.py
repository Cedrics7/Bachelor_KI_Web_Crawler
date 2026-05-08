import streamlit as st
import pandas as pd
import psycopg2
import os
import json
from dotenv import load_dotenv
from datetime import datetime
import time

# =====================================================================
# 1. KONFIGURATION & LOGO
# =====================================================================
load_dotenv()
TELEKOM_LOGO_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Deutsche_Telekom_2022.svg/330px-Deutsche_Telekom_2022.svg.png"

st.set_page_config(
    page_title="Crawler Dashboard",
    layout="wide",
    page_icon=TELEKOM_LOGO_URL
)


# =====================================================================
# 2. DATENBANKVERBINDUNG (mit Cache)
# =====================================================================
@st.cache_data(ttl=60)
def get_data():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT")
    )
    df_targets = pd.read_sql("SELECT * FROM crawl_targets ORDER BY id ASC", conn)
    df_results = pd.read_sql("SELECT * FROM crawl_results ORDER BY end_time DESC", conn)
    conn.close()
    return df_targets, df_results


try:
    df_targets, df_results = get_data()
    df_targets['last_scanned'] = pd.to_datetime(df_targets['last_scanned'])
except Exception as e:
    st.error(f"Fehler bei der Datenverarbeitung: {e}")
    st.stop()

# =====================================================================
# 3. DEEP LINKING LOGIK (Query Params)
# =====================================================================
# Parameter aus der URL lesen
query_params = st.query_params

# Mapping für interne Namen zu Anzeigenamen
seiten_options = ["Bestandsdaten (Targets)", "Bewegungsdaten (Results)", "Crawler Monitoring"]

# Initialisierung des Session States aus der URL oder Default
if "aktuelle_seite" not in st.session_state:
    st.session_state.aktuelle_seite = query_params.get("seite", seiten_options[0])

if "filter_bundesland" not in st.session_state:
    st.session_state.filter_bundesland = query_params.get("bundesland", "Alle")


# Funktion zum Aktualisieren der URL
def sync_url():
    st.query_params["seite"] = st.session_state.aktuelle_seite
    if st.session_state.filter_bundesland != "Alle":
        st.query_params["bundesland"] = st.session_state.filter_bundesland
    else:
        if "bundesland" in st.query_params:
            del st.query_params["bundesland"]


# =====================================================================
# 4. SIDEBAR NAVIGATION
# =====================================================================
st.sidebar.title("Navigation")

# Wir berechnen den Index für das Radio-Widget basierend auf der URL
try:
    current_index = seiten_options.index(st.session_state.aktuelle_seite)
except ValueError:
    current_index = 0

ansicht = st.sidebar.radio(
    "Bereich auswählen",
    seiten_options,
    index=current_index,
    key="nav_radio"
)

# Wenn sich die Seite ändert, URL updaten
if ansicht != st.session_state.aktuelle_seite:
    st.session_state.aktuelle_seite = ansicht
    sync_url()
    st.rerun()

st.sidebar.divider()
st.sidebar.caption("Crawler Status")
st.sidebar.success("System bereit")

# =====================================================================
# ANSICHT 1: BESTANDSDATEN
# =====================================================================
if st.session_state.aktuelle_seite == "Bestandsdaten (Targets)":
    st.title("Bestandsdaten")
    monats_anfang = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    st.markdown(f"Statusübersicht für den aktuellen Monat: **{monats_anfang.strftime('%B %Y')}**")

    # Metriken
    total_count = len(df_targets)
    gecrawlt_count = df_targets[df_targets['last_scanned'] >= monats_anfang].shape[0]

    c1, c2, c3 = st.columns(3)
    c1.metric("Orte Gesamt", total_count)
    c2.metric("In diesem Monat gecrawlt", gecrawlt_count)
    c3.metric("Diesen Monat ausstehend", total_count - gecrawlt_count)

    st.divider()

    # Filter
    st.subheader("Filter")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        such_ort = st.text_input("Suche (Ort oder AGS):", placeholder="z.B. Barßel")
    with col_f2:
        status_filter = st.selectbox("Crawl-Status (aktueller Monat):", [
            "Alle anzeigen", "Nur diesen Monat ausstehend", "Diesen Monat bereits gecrawlt"
        ])

    df_anzeige = df_targets.copy()
    if such_ort:
        df_anzeige = df_anzeige[
            df_anzeige['ort'].str.contains(such_ort, case=False, na=False) | df_anzeige['ags'].str.contains(such_ort,
                                                                                                            na=False)]

    if status_filter == "Nur diesen Monat ausstehend":
        df_anzeige = df_anzeige[(df_anzeige['last_scanned'] < monats_anfang) | (df_anzeige['last_scanned'].isna())]
    elif status_filter == "Diesen Monat bereits gecrawlt":
        df_anzeige = df_anzeige[df_anzeige['last_scanned'] >= monats_anfang]

    st.dataframe(
        df_anzeige[['id', 'ort', 'ags', 'bundesland', 'last_scanned', 'url']],
        column_config={
            "url": st.column_config.LinkColumn("Startseite"),
            "last_scanned": st.column_config.DatetimeColumn("Letzter Crawl", format="DD.MM.YYYY HH:mm")
        },
        use_container_width=True, hide_index=True, height=500
    )

# =====================================================================
# ANSICHT 2: BEWEGUNGSDATEN
# =====================================================================
elif st.session_state.aktuelle_seite == "Bewegungsdaten (Results)":
    st.title("Bewegungsdaten")
    st.markdown("Extrahierte Baumaßnahmen und Infrastrukturprojekte.")

    if df_results.empty:
        st.info("Noch keine Crawler-Ergebnisse vorhanden.")
    else:
        df_merged = df_results.merge(df_targets[['ags', 'ort', 'bundesland']], on='ags', how='left')
        df_merged = df_merged[df_merged['massnahme'].notna()]
        df_merged['kategorie_extract'] = df_merged['massnahme'].str.extract(r'\[(.*?)\]')

        st.subheader("Filter")
        col_f1, col_f2, col_f3 = st.columns(3)
        with col_f1:
            such_massnahme = st.text_input("Suche (Stichwort):", placeholder="z.B. Brücke")

        with col_f2:
            bundeslaender = ["Alle"] + sorted(list(df_merged['bundesland'].dropna().unique()))

            # Index für Selectbox aus URL/Session State bestimmen
            try:
                bl_index = bundeslaender.index(st.session_state.filter_bundesland)
            except ValueError:
                bl_index = 0

            bundesland_filter = st.selectbox("Bundesland:", bundeslaender, index=bl_index)

            # Wenn Filter geändert wird: Session State & URL updaten
            if bundesland_filter != st.session_state.filter_bundesland:
                st.session_state.filter_bundesland = bundesland_filter
                sync_url()
                st.rerun()

        with col_f3:
            kategorien = ["Alle"] + sorted(list(df_merged['kategorie_extract'].dropna().unique()))
            kat_filter = st.selectbox("Kategorie:", kategorien)

        # Filter anwenden
        if such_massnahme:
            df_merged = df_merged[df_merged['massnahme'].str.contains(such_massnahme, case=False, na=False) | df_merged[
                'ort'].str.contains(such_massnahme, case=False, na=False)]
        if bundesland_filter != "Alle":
            df_merged = df_merged[df_merged['bundesland'] == bundesland_filter]
        if kat_filter != "Alle":
            df_merged = df_merged[df_merged['kategorie_extract'] == kat_filter]

        st.divider()
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
            use_container_width=True, hide_index=True, height=600
        )

# =====================================================================
# ANSICHT 3: CRAWLER MONITORING
# =====================================================================
elif st.session_state.aktuelle_seite == "Crawler Monitoring":
    st.title("Crawler Live-Monitoring")


    # Wir definieren ein Fragment für den Live-Bereich
    # run_every=5 sorgt dafür, dass NUR dieser Teil alle 5 Sek. neu läuft
    @st.fragment(run_every=5)
    def render_live_content():
        # --- 1. LIVE-DATEN LADEN ---
        live_file = "crawler_live_status.json"
        if os.path.exists(live_file):
            try:
                with open(live_file, "r", encoding="utf-8") as f:
                    live_data = json.load(f)

                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Aktuelles Ziel", live_data["aktueller_ort"])
                with c2:
                    st.metric("Letzte Funde", live_data.get("letzte_funde", 0))
                with c3:
                    msg = live_data["status"]
                    if "✅" in msg:
                        st.success(msg)
                    elif "⚠️" in msg:
                        st.warning(msg)
                    else:
                        st.info(msg)

                st.caption(f"Letztes Update: {datetime.now().strftime('%H:%M:%S')}")
            except:
                st.info("🔄 Synchronisiere Daten...")

        st.divider()

        # --- 2. HISTORIE LADEN ---
        st.subheader("Durchlauf-Historie")
        if os.path.exists("crawler_history.txt"):
            with open("crawler_history.txt", "r", encoding="utf-8") as f:
                lines = f.readlines()
                log_content = "".join(lines[-15:][::-1])
            st.text_area("Live-Log (History)", value=log_content, height=300)


    # Jetzt rufen wir das Fragment einfach auf
    render_live_content()