"""
Datenbankanbindung für Bachelor_Crawler_erweitert.
Unterstützt SQLite (Standard) und PostgreSQL via DATABASE_URL.
Tabelle: crawl_results
"""
from __future__ import annotations
import json
import logging
from dataclasses import asdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .focused_crawler import CrawlResult

logger = logging.getLogger(__name__)

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS crawl_results (
    id              SERIAL PRIMARY KEY,      -- PostgreSQL
    run_id          TEXT        NOT NULL,
    url             TEXT        NOT NULL,
    content_hash    TEXT        NOT NULL,
    is_pdf          BOOLEAN     NOT NULL DEFAULT FALSE,
    http_status     INTEGER     NOT NULL DEFAULT 200,
    relevance_score REAL,
    relevance_label TEXT,
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
    fetch_time_ms   REAL,
    text_snippet    TEXT,
    blocks_json     TEXT,
    crawled_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class DBClient:
    """
    Leichtgewichtiger DB-Client ohne ORM-Abhängigkeit.
    Erkennt automatisch SQLite vs. PostgreSQL anhand der DATABASE_URL.
    """

    def __init__(self, db_url: str) -> None:
        self._url = db_url
        self._is_sqlite = db_url.startswith('sqlite')
        self._conn = None
        self._connect()

    # ------------------------------------------------------------------
    # Verbindung
    # ------------------------------------------------------------------
    def _connect(self) -> None:
        if self._is_sqlite:
            import sqlite3
            path = self._url.replace('sqlite:///', '').replace('sqlite://', '')
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute('PRAGMA journal_mode=WAL;')
            self._conn.execute(_CREATE_TABLE_SQLITE)
            self._conn.commit()
            logger.info('DB: SQLite verbunden → %s', path)
        else:
            try:
                import psycopg2
                import psycopg2.extras
                self._conn = psycopg2.connect(self._url)
                with self._conn.cursor() as cur:
                    cur.execute(_CREATE_TABLE_SQL)
                self._conn.commit()
                logger.info('DB: PostgreSQL verbunden')
            except ImportError:
                logger.error('DB: psycopg2 nicht installiert – pip install psycopg2-binary')
                raise

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    # ------------------------------------------------------------------
    # Schreiben
    # ------------------------------------------------------------------
    def save_result(self, run_id: str, result: 'CrawlResult') -> None:
        """
        Speichert ein CrawlResult in der Datenbank.
        """
        snippet = (result.text or '')[:2000]
        blocks_json = json.dumps(result.blocks or [], ensure_ascii=False)
        score = result.relevance.score if result.relevance else None
        label = result.relevance.label if result.relevance else None

        if self._is_sqlite:
            sql = """
                INSERT INTO crawl_results
                    (run_id, url, content_hash, is_pdf, http_status,
                     relevance_score, relevance_label, fetch_time_ms,
                     text_snippet, blocks_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
            self._conn.execute(sql, (
                run_id, result.url, result.content_hash,
                int(result.is_pdf), result.http_status,
                score, label, result.fetch_time_ms, snippet, blocks_json
            ))
            self._conn.commit()
        else:
            sql = """
                INSERT INTO crawl_results
                    (run_id, url, content_hash, is_pdf, http_status,
                     relevance_score, relevance_label, fetch_time_ms,
                     text_snippet, blocks_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            with self._conn.cursor() as cur:
                cur.execute(sql, (
                    run_id, result.url, result.content_hash,
                    result.is_pdf, result.http_status,
                    score, label, result.fetch_time_ms, snippet, blocks_json
                ))
            self._conn.commit()
        logger.debug('DB: gespeichert → %s', result.url)

    def save_results_bulk(self, run_id: str, results: list) -> None:
        for r in results:
            try:
                self.save_result(run_id, r)
            except Exception as exc:
                logger.warning('DB: Fehler beim Speichern von %s: %s', r.url, exc)
