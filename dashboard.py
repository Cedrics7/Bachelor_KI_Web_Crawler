import streamlit as st
import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

# Konfiguration
load_dotenv()
st.set_page_config(page_title="Crawler Status Dashboard", layout="wide")


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
except Exception as e:
    st.error(f"Fehler bei der Datenverarbeitung: {e}")
    st.stop()

# --- ROUTING & NAVIGATION (Sicherer Weg via Dropdown) ---

# 1. Dropdown für die Auswahl bauen
orte_liste = ["-- Hauptübersicht --"] + list(df_targets['ort'].unique())
st.markdown("### 🧭 Navigation")
gewaehlter_ort = st.selectbox("Wähle einen Ort aus, um die Bewegungsdaten zu sehen:", options=orte_liste)

st.divider()

# =====================================================================
# ANSICHT 2: DETAILANSICHT EINER STADT (Bewegungsdaten)
# =====================================================================
if gewaehlter_ort != "-- Hauptübersicht --":

    # AGS für den gewählten Ort heraussuchen
    target_info = df_targets[df_targets['ort'] == gewaehlter_ort].iloc[0]
    gewaehlte_ags = target_info['ags']

    st.title(f"🏢 Crawl-Ergebnisse für: {gewaehlter_ort}")

    # Daten filtern
    stadt_daten = df_results[df_results['ags'] == gewaehlte_ags].copy()

    if not stadt_daten.empty:
        # Hier rufen wir jetzt die ECHTEN Baudaten ab
        anzeige_df = stadt_daten[['massnahme_start', 'massnahme_ende', 'massnahme', 'adresse']]

        st.dataframe(
            anzeige_df,
            column_config={
                "massnahme_start": st.column_config.DateColumn("Start der Maßnahme", format="DD.MM.YYYY"),
                "massnahme_ende": st.column_config.DateColumn("Ende der Maßnahme", format="DD.MM.YYYY"),
                "massnahme": "Gefundene Maßnahme",
                "adresse": "Adresse"
            },
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info(f"Noch keine Crawl-Ergebnisse für {gewaehlter_ort} vorhanden.")

# =====================================================================
# ANSICHT 1: HAUPT-DASHBOARD (Stammdaten)
# =====================================================================
else:
    st.title("🛡️ Crawler Target Dashboard")
    st.markdown(f"Statusübersicht für den aktuellen Monat: **{datetime.now().strftime('%B %Y')}**")

    # --- LOGIK: AKTUELLER MONAT ---
    df = df_targets.copy()
    monats_anfang = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    df['last_scanned'] = pd.to_datetime(df['last_scanned'])

    scanned_this_month_df = df[df['last_scanned'] >= monats_anfang]
    scanned_count = len(scanned_this_month_df)
    total_count = len(df)

    # --- METRIKEN ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Gesamtanzahl Orte", total_count)
    col2.metric("Bundesländer", df['bundesland'].nunique())
    quote = (scanned_count / total_count * 100) if total_count > 0 else 0
    col3.metric("Abdeckung in diesem Monat", f"{quote:.1f}%", delta=f"{scanned_count} Orte")

    # --- HAUPTBEREICH: FILTER & TABELLE ---
    st.divider()
    col_filter, col_table = st.columns([1, 4])

    with col_filter:
        st.header("Filter")
        search_term = st.text_input("Ort oder AGS suchen")
        selected_land = st.multiselect("Bundesland", options=df['bundesland'].unique())
        show_only_pending = st.checkbox("Nur noch nicht gecrawlte (in diesem Monat)")

    filtered_df = df
    if search_term:
        filtered_df = filtered_df[
            filtered_df['ort'].str.contains(search_term, case=False, na=False) |
            filtered_df['ags'].str.contains(search_term, na=False)
            ]
    if selected_land:
        filtered_df = filtered_df[filtered_df['bundesland'].isin(selected_land)]
    if show_only_pending:
        filtered_df = filtered_df[(filtered_df['last_scanned'] < monats_anfang) | (filtered_df['last_scanned'].isna())]

    with col_table:
        st.subheader("Stammdaten Übersicht")

        anzeige_spalten = ['id', 'ort', 'ags', 'bundesland', 'last_scanned', 'url']


        def highlight_recent(row):
            if pd.notnull(row['last_scanned']) and row['last_scanned'] >= monats_anfang:
                return ['background-color: #004d00'] * len(row)  # Dunkleres Grün für Darkmode-Lesbarkeit
            return [''] * len(row)


        st.dataframe(
            filtered_df[anzeige_spalten].style.apply(highlight_recent, axis=1),
            column_config={
                "url": st.column_config.LinkColumn("Webseite")
            },
            use_container_width=True,
            height=400
        )

    # --- UNTERER BEREICH: HISTORIE ---
    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("📈 Verteilung nach Bundesland")
        land_counts = df['bundesland'].value_counts()
        st.bar_chart(land_counts)

    with c2:
        st.subheader("🕒 Letzte Crawl-Aktivitäten")
        if not df_results.empty:
            history_df = df_results.head(10).merge(df_targets[['ags', 'ort']], on='ags', how='left')
            # Auch in der Historie Start- und Enddatum ergänzt!
            anzeige_history = history_df[['start_time', 'end_time', 'ort', 'status']]
            st.dataframe(anzeige_history, use_container_width=True)
        else:
            st.info("Noch keine Einträge in der Tabelle 'crawl_results' vorhanden.")