"""
Datenbankanbindung für Bachelor_Crawler_erweitert.
Unterstützt SQLite (Standard) und PostgreSQL via DATABASE_URL.
Tabelle: crawl_results_bachelor  (eigener Name - kein Konflikt mit bestehenden Tabellen)

WICHTIG: Niemals DROP TABLE auf Produktionsdaten!
Fehlende Spalten werden per ALTER TABLE ADD COLUMN IF NOT EXISTS nachgerüstet.
"""
from __future__ import annotations
import json
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .focused_crawler import CrawlResult

logger = logging.getLogger(__name__)

TABLE_NAME = 'crawl_results_bachelor'

_CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
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
    llm_relevant    BOOLEAN,
    llm_confidence  REAL,
    llm_reason      TEXT,
    fetch_time_ms   REAL,
    text_snippet    TEXT,
    blocks_json     TEXT,
    crawled_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_CREATE_TABLE_SQLITE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
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
    llm_relevant    INTEGER,
    llm_confidence  REAL,
    llm_reason      TEXT,
    fetch_time_ms   REAL,
    text_snippet    TEXT,
    blocks_json     TEXT,
    crawled_at      TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

_MIGRATION_COLUMNS = [
    ('run_id',          "TEXT        NOT NULL DEFAULT 'migrated'"),
    ('url',             "TEXT        NOT NULL DEFAULT ''"),
    ('content_hash',    "TEXT        NOT NULL DEFAULT ''"),
    ('is_pdf',          'BOOLEAN     NOT NULL DEFAULT FALSE'),
    ('http_status',     'INTEGER     NOT NULL DEFAULT 200'),
    ('relevance_score', 'REAL'),
    ('relevance_label', 'TEXT'),
    ('top_category',    'TEXT'),
    ('confidence',      'REAL'),
    ('llm_relevant',    'BOOLEAN'),
    ('llm_confidence',  'REAL'),
    ('llm_reason',      'TEXT'),
    ('fetch_time_ms',   'REAL'),
    ('text_snippet',    'TEXT'),
    ('blocks_json',     'TEXT'),
]


def _sanitize(text: str | None, max_len: int = 0) -> str | None:
    """
    Entfernt NUL-Bytes (0x00) die PostgreSQL in TEXT-Spalten nicht akzeptiert.
    Optional: Kürzt auf max_len Zeichen.
    """
    if text is None:
        return None
    text = text.replace('\x00', '')
    if max_len:
        text = text[:max_len]
    return text


class DBClient:
    """
    Leichtgewichtiger DB-Client ohne ORM-Abhängigkeit.
    Sicher für Produktionsdatenbanken: niemals DROP TABLE.
    Fehlende Spalten werden automatisch nachgerüstet.
    NUL-Bytes werden vor dem Insert bereinigt.
    Duplikate werden per (url) verhindert: gleiche URL = UPDATE statt INSERT.
    """

    def __init__(self, db_url: str) -> None:
        self._url = db_url
        self._is_sqlite = db_url.startswith('sqlite')
        self._conn = None
        self._connect()
        self._migrate()

    def _connect(self) -> None:
        if self._is_sqlite:
            import sqlite3
            path = self._url.replace('sqlite:///', '').replace('sqlite://', '')
            self._conn = sqlite3.connect(path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute('PRAGMA journal_mode=WAL;')
            self._conn.execute(_CREATE_TABLE_SQLITE)
            # Unique-Index auf url für Duplikat-Schutz
            self._conn.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLE_NAME}_url '
                f'ON {TABLE_NAME}(url);'
            )
            self._conn.commit()
            logger.info('DB: SQLite verbunden -> %s', path)
        else:
            try:
                import psycopg2
                self._conn = psycopg2.connect(self._url)
                with self._conn.cursor() as cur:
                    cur.execute(_CREATE_TABLE_SQL)
                    # Unique-Index auf url für Duplikat-Schutz
                    cur.execute(
                        f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLE_NAME}_url '
                        f'ON {TABLE_NAME}(url);'
                    )
                self._conn.commit()
                logger.info('DB: PostgreSQL verbunden -> Tabelle: %s', TABLE_NAME)
            except ImportError:
                logger.error('DB: psycopg2 nicht installiert - pip install psycopg2-binary')
                raise

    def _migrate(self) -> None:
        for col_name, col_type in _MIGRATION_COLUMNS:
            try:
                if self._is_sqlite:
                    try:
                        self._conn.execute(
                            f'ALTER TABLE {TABLE_NAME} ADD COLUMN {col_name} {col_type};'
                        )
                        self._conn.commit()
                        logger.info('DB Migration: Spalte "%s" hinzugefügt', col_name)
                    except Exception as e:
                        if 'duplicate column' in str(e).lower():
                            pass
                        else:
                            logger.warning('DB Migration "%s": %s', col_name, e)
                else:
                    with self._conn.cursor() as cur:
                        cur.execute(
                            f'ALTER TABLE {TABLE_NAME} '
                            f'ADD COLUMN IF NOT EXISTS {col_name} {col_type};'
                        )
                    self._conn.commit()
            except Exception as e:
                logger.warning('DB Migration Fehler bei "%s": %s', col_name, e)

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    def save_result(self, run_id: str, result: 'CrawlResult') -> None:
        """
        Speichert ein CrawlResult. Nutzt INSERT ... ON CONFLICT (url) DO UPDATE
        damit bei erneutem Crawlen der gleichen URL kein Duplikat entsteht,
        sondern der Datensatz aktualisiert wird (neuerer run_id, frischer Score etc.).
        """
        snippet      = _sanitize(result.text, max_len=2000)
        blocks_json  = _sanitize(json.dumps(result.blocks or [], ensure_ascii=False))
        url          = _sanitize(result.url)
        run_id       = _sanitize(run_id)

        rel             = result.relevance
        score           = rel.score if rel else None
        relevance_label = _sanitize(('relevant' if rel.is_relevant else 'nicht relevant') if rel else None)
        top_category    = _sanitize(rel.top_category if rel else None)
        confidence      = rel.confidence if rel else None

        # LLM-Felder aus llm_result extrahieren
        llm = result.llm_result or {}
        llm_relevant   = llm.get('relevant')   # True/False/None
        llm_confidence = llm.get('confidence') # float/None
        llm_reason     = _sanitize(llm.get('reason'), max_len=500)

        if self._is_sqlite:
            sql = f"""
                INSERT INTO {TABLE_NAME}
                    (run_id, url, content_hash, is_pdf, http_status,
                     relevance_score, relevance_label, top_category, confidence,
                     llm_relevant, llm_confidence, llm_reason,
                     fetch_time_ms, text_snippet, blocks_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    run_id          = excluded.run_id,
                    content_hash    = excluded.content_hash,
                    is_pdf          = excluded.is_pdf,
                    http_status     = excluded.http_status,
                    relevance_score = excluded.relevance_score,
                    relevance_label = excluded.relevance_label,
                    top_category    = excluded.top_category,
                    confidence      = excluded.confidence,
                    llm_relevant    = excluded.llm_relevant,
                    llm_confidence  = excluded.llm_confidence,
                    llm_reason      = excluded.llm_reason,
                    fetch_time_ms   = excluded.fetch_time_ms,
                    text_snippet    = excluded.text_snippet,
                    blocks_json     = excluded.blocks_json,
                    crawled_at      = CURRENT_TIMESTAMP
            """
            self._conn.execute(sql, (
                run_id, url, result.content_hash,
                int(result.is_pdf), result.http_status,
                score, relevance_label, top_category, confidence,
                int(llm_relevant) if llm_relevant is not None else None,
                llm_confidence, llm_reason,
                result.fetch_time_ms, snippet, blocks_json,
            ))
            self._conn.commit()
        else:
            sql = f"""
                INSERT INTO {TABLE_NAME}
                    (run_id, url, content_hash, is_pdf, http_status,
                     relevance_score, relevance_label, top_category, confidence,
                     llm_relevant, llm_confidence, llm_reason,
                     fetch_time_ms, text_snippet, blocks_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (url) DO UPDATE SET
                    run_id          = EXCLUDED.run_id,
                    content_hash    = EXCLUDED.content_hash,
                    is_pdf          = EXCLUDED.is_pdf,
                    http_status     = EXCLUDED.http_status,
                    relevance_score = EXCLUDED.relevance_score,
                    relevance_label = EXCLUDED.relevance_label,
                    top_category    = EXCLUDED.top_category,
                    confidence      = EXCLUDED.confidence,
                    llm_relevant    = EXCLUDED.llm_relevant,
                    llm_confidence  = EXCLUDED.llm_confidence,
                    llm_reason      = EXCLUDED.llm_reason,
                    fetch_time_ms   = EXCLUDED.fetch_time_ms,
                    text_snippet    = EXCLUDED.text_snippet,
                    blocks_json     = EXCLUDED.blocks_json,
                    crawled_at      = CURRENT_TIMESTAMP
            """
            with self._conn.cursor() as cur:
                cur.execute(sql, (
                    run_id, url, result.content_hash,
                    result.is_pdf, result.http_status,
                    score, relevance_label, top_category, confidence,
                    llm_relevant, llm_confidence, llm_reason,
                    result.fetch_time_ms, snippet, blocks_json,
                ))
            self._conn.commit()
        logger.debug('DB: gespeichert/aktualisiert -> %s', url)

    def save_results_bulk(self, run_id: str, results: list) -> None:
        """Analysiert eine Liste von CrawlResults."""
        for r in results:
            try:
                self.save_result(run_id, r)
            except Exception as exc:
                logger.warning('DB: Fehler beim Speichern von %s: %s', r.url, exc)
