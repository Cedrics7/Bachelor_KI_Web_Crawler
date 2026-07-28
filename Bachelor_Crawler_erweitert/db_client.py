"""
Datenbankanbindung für Bachelor_Crawler_erweitert.
Unterstützt SQLite (Standard) und PostgreSQL via DATABASE_URL.
Tabelle: crawl_results
"""
from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .focused_crawler import CrawlResult

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS crawl_results (
    id              SERIAL PRIMARY KEY,
    run_id          TEXT        NOT NULL,
    url             TEXT        NOT NULL,
    content_hash    TEXT        NOT NULL,
    is_pdf          BOOLEAN     NOT NULL DEFAULT FALSE,
    http_status     INTEGER     NOT NULL DEFAULT 200,
    relevance_score REAL,
    relevance_label TEXT,
    top_category    TEXT,
    confidence      REAL,
    fetch_time_ms   REAL,
    text_snippet    TEXT,
    blocks_json     TEXT,
    crawled_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_TABLE_SQLITE = """
CREATE TABLE IF NOT EXISTS crawl_results (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          TEXT        NOT NULL,
    url             TEXT        NOT NULL,
    content_hash    TEXT        NOT NULL,
    is_pdf          INTEGER     NOT NULL DEFAULT 0,
    http_status     INTEGER     NOT NULL DEFAULT 200,
    relevance_score REAL,
    relevance_label TEXT,
    top_category    TEXT,
    confidence      REAL,
    fetch_time_ms   REAL,
    text_snippet    TEXT,
    blocks_json     TEXT,
    crawled_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# Alle Spalten die in der finalen Tabelle existieren müssen
_REQUIRED_COLUMNS = {
    'run_id', 'url', 'content_hash', 'is_pdf', 'http_status',
    'relevance_score', 'relevance_label', 'top_category', 'confidence',
    'fetch_time_ms', 'text_snippet', 'blocks_json', 'crawled_at',
}


class DBClient:
    """
    Leichtgewichtiger DB-Client ohne ORM-Abhängigkeit.
    Erkennt automatisch SQLite vs. PostgreSQL anhand der DATABASE_URL.
    Prüft beim Start ob das Schema vollständig ist - rebuildet bei Bedarf.
    """

    def __init__(self, db_url: str) -> None:
        self._url = db_url
        self._is_sqlite = db_url.startswith('sqlite')
        self._conn = None
        self._connect()

    def _connect(self) -> None:
        if self._is_sqlite:
            import sqlite3
            path = self._url.replace('sqlite:///', '').replace('sqlite://', '')
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute('PRAGMA journal_mode=WAL;')
            self._ensure_schema_sqlite()
            logger.info('DB: SQLite verbunden -> %s', path)
        else:
            try:
                import psycopg2
                self._conn = psycopg2.connect(self._url)
                self._ensure_schema_pg()
                logger.info('DB: PostgreSQL verbunden')
            except ImportError:
                logger.error('DB: psycopg2 nicht installiert - pip install psycopg2-binary')
                raise

    def _get_existing_columns_pg(self) -> set:
        with self._conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'crawl_results'
            """)
            return {row[0] for row in cur.fetchall()}

    def _ensure_schema_pg(self) -> None:
        """Prüft ob alle Pflicht-Spalten vorhanden sind. Falls nicht: Tabelle droppen und neu anlegen."""
        with self._conn.cursor() as cur:
            cur.execute(_CREATE_TABLE_SQL)
        self._conn.commit()

        existing = self._get_existing_columns_pg()
        missing = _REQUIRED_COLUMNS - existing

        if missing:
            logger.warning(
                'DB: Tabelle crawl_results hat veraltetes Schema (fehlen: %s). '
                'Tabelle wird neu aufgebaut - bestehende Daten gehen verloren!',
                ', '.join(sorted(missing))
            )
            with self._conn.cursor() as cur:
                cur.execute('DROP TABLE IF EXISTS crawl_results;')
                cur.execute(_CREATE_TABLE_SQL)
            self._conn.commit()
            logger.info('DB: Tabelle crawl_results neu angelegt.')
        else:
            # Optional fehlende neue Spalten nachruesten (non-breaking)
            for col in sorted(_REQUIRED_COLUMNS - existing):
                try:
                    with self._conn.cursor() as cur:
                        cur.execute(f'ALTER TABLE crawl_results ADD COLUMN IF NOT EXISTS {col} TEXT;')
                    self._conn.commit()
                except Exception as e:
                    logger.debug('Migration %s: %s', col, e)

    def _ensure_schema_sqlite(self) -> None:
        """Für SQLite: Tabelle anlegen, bei fehlendem Schema neu aufbauen."""
        self._conn.execute(_CREATE_TABLE_SQLITE)
        self._conn.commit()

        cur = self._conn.execute("PRAGMA table_info(crawl_results)")
        existing = {row[1] for row in cur.fetchall()}
        missing = _REQUIRED_COLUMNS - existing

        if missing:
            logger.warning('DB SQLite: Schema veraltet (%s fehlen) - neu aufbauen.', ', '.join(sorted(missing)))
            self._conn.execute('DROP TABLE IF EXISTS crawl_results;')
            self._conn.execute(_CREATE_TABLE_SQLITE)
            self._conn.commit()
            logger.info('DB SQLite: Tabelle neu angelegt.')

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def save_result(self, run_id: str, result: 'CrawlResult') -> None:
        snippet = (result.text or '')[:2000]
        blocks_json = json.dumps(result.blocks or [], ensure_ascii=False)

        rel = result.relevance
        score = rel.score if rel else None
        relevance_label = ('relevant' if rel.is_relevant else 'nicht relevant') if rel else None
        top_category = rel.top_category if rel else None
        confidence = rel.confidence if rel else None

        if self._is_sqlite:
            sql = """
                INSERT INTO crawl_results
                    (run_id, url, content_hash, is_pdf, http_status,
                     relevance_score, relevance_label, top_category, confidence,
                     fetch_time_ms, text_snippet, blocks_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self._conn.execute(sql, (
                run_id, result.url, result.content_hash,
                int(result.is_pdf), result.http_status,
                score, relevance_label, top_category, confidence,
                result.fetch_time_ms, snippet, blocks_json,
            ))
            self._conn.commit()
        else:
            sql = """
                INSERT INTO crawl_results
                    (run_id, url, content_hash, is_pdf, http_status,
                     relevance_score, relevance_label, top_category, confidence,
                     fetch_time_ms, text_snippet, blocks_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            with self._conn.cursor() as cur:
                cur.execute(sql, (
                    run_id, result.url, result.content_hash,
                    result.is_pdf, result.http_status,
                    score, relevance_label, top_category, confidence,
                    result.fetch_time_ms, snippet, blocks_json,
                ))
            self._conn.commit()
        logger.debug('DB: gespeichert -> %s', result.url)

    def save_results_bulk(self, run_id: str, results: list) -> None:
        for r in results:
            try:
                self.save_result(run_id, r)
            except Exception as exc:
                logger.warning('DB: Fehler beim Speichern von %s: %s', r.url, exc)
