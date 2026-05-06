import streamlit as st
import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv
from datetime import datetime

# Konfiguration
load_dotenv()
st.set_page_config(page_title="Crawler Status Dashboard", layout="wide")


# Datenbankverbindung
def get_data():
    conn = psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT")
    )
    # 1. Hauptdaten aus crawl_targets (Stammdaten)
    query_targets = "SELECT id, ort, ags, url, bundesland, last_scanned FROM crawl_targets ORDER BY id ASC"
    df_targets = pd.read_sql(query_targets, conn)

    # 2. Letzte Ergebnisse aus der neuen Ergebnistabelle (Historie)
    # Wir holen uns nur die letzten 10 Einträge für eine Kurzübersicht
    query_results = """
        SELECT r.start_time, r.end_time, r.status, t.ort 
        FROM crawl_results r 
        JOIN crawl_targets t ON r.ags = t.ags 
        ORDER BY r.end_time DESC LIMIT 10
    """
    df_results = pd.read_sql(query_results, conn)

    conn.close()
    return df_targets, df_results


# UI Design
st.title("🛡️ Crawler Target Dashboard")
st.markdown(f"Statusübersicht für den aktuellen Monat: **{datetime.now().strftime('%B %Y')}**")

try:
    df, df_history = get_data()

    # --- LOGIK: AKTUELLER MONAT ---
    # Wir definieren den 1. des aktuellen Monats als Grenze
    monats_anfang = datetime.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Konvertiere last_scanned zu datetime (falls es Strings sind)
    df['last_scanned'] = pd.to_datetime(df['last_scanned'])

    # Nur Einträge zählen, die nach dem Monatsanfang liegen
    scanned_this_month_df = df[df['last_scanned'] >= monats_anfang]
    scanned_count = len(scanned_this_month_df)
    total_count = len(df)

    # --- METRIKEN ---
    col1, col2, col3 = st.columns(3)
    col1.metric("Gesamtanzahl Orte", total_count)
    col2.metric("Bundesländer", df['bundesland'].nunique())

    # Prozentuale Abdeckung NUR für diesen Monat
    quote = (scanned_count / total_count * 100) if total_count > 0 else 0
    col3.metric("Abdeckung im Mai", f"{quote:.1f}%", delta=f"{scanned_count} Orte")

    # --- HAUPTBEREICH: FILTER & TABELLE ---
    st.divider()

    col_filter, col_table = st.columns([1, 4])

    with col_filter:
        st.header("Filter")
        search_term = st.text_input("Ort oder AGS suchen")
        selected_land = st.multiselect("Bundesland", options=df['bundesland'].unique())
        show_only_pending = st.checkbox("Nur noch nicht gecrawlte (Mai)")

    # Daten filtern
    filtered_df = df
    if search_term:
        filtered_df = filtered_df[
            filtered_df['ort'].str.contains(search_term, case=False, na=False) |
            filtered_df['ags'].str.contains(search_term, na=False)
            ]
    if selected_land:
        filtered_df = filtered_df[filtered_df['bundesland'].isin(selected_land)]
    if show_only_pending:
        # Zeige nur die, deren last_scanned NULL ist ODER vor dem Monat liegt
        filtered_df = filtered_df[(filtered_df['last_scanned'] < monats_anfang) | (filtered_df['last_scanned'].isna())]

    with col_table:
        st.subheader("Gemeindedaten")


        # Styling: Wir markieren "frische" Scans grün
        def highlight_recent(row):
            if pd.notnull(row['last_scanned']) and row['last_scanned'] >= monats_anfang:
                return ['background-color: #d4edda'] * len(row)
            return [''] * len(row)


        st.dataframe(filtered_df.style.apply(highlight_recent, axis=1), use_container_width=True, height=400)

    # --- UNTERER BEREICH: HISTORIE ---
    st.divider()
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("📈 Verteilung nach Bundesland")
        land_counts = df['bundesland'].value_counts()
        st.bar_chart(land_counts)

    with c2:
        st.subheader("🕒 Letzte Crawl-Aktivitäten")
        if not df_history.empty:
            st.table(df_history)
        else:
            st.info("Noch keine Einträge in der Tabelle 'crawl_results' vorhanden.")

except Exception as e:
    st.error(f"Fehler bei der Datenverarbeitung: {e}")