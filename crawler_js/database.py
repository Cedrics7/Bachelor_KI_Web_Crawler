"""
Zentrale Datenbankverwaltung für Crawler und API.
"""
import os
import psycopg2
from psycopg2.extras import RealDictCursor


def get_db_connection(as_dict: bool = False):
    """
    Baut eine Verbindung zur PostgreSQL-Datenbank auf.

    Args:
        as_dict (bool): Wenn True, gibt der Cursor Ergebnisse als Dictionaries zurück.

    Returns:
        connection: Die psycopg2 Datenbankverbindung.
    """
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASS"),
        port=os.getenv("DB_PORT"),
        cursor_factory=RealDictCursor if as_dict else None
    )