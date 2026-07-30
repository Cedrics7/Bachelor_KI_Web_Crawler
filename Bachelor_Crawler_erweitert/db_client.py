"""
Datenbankanbindung für Bachelor_Crawler_erweitert.
Unterstützt SQLite (Standard) und PostgreSQL via DATABASE_URL.

Zwei Tabellen:
  1. crawl_results_bachelor  – technisches Rohlog aller relevanten Seiten
                               (Scores, Snippets, blocks_json, LLM-Metadaten)
  2. crawl_results           – LLM-zertifizierte Ergebnisse, kompatibel mit
                               crawler_js (massnahme, kategorie, adresse, ...)

WICHTIG: Niemals DROP TABLE auf Produktionsdaten!
Fehlende Spalten werden per ALTER TABLE ADD COLUMN IF NOT EXISTS nachgerüstet.
"""
from __future__ import annotations
import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .focused_crawler import CrawlResult

logger = logging.getLogger(__name__)

TABLE_RAW    = 'crawl_results_bachelor'   # technisches Rohlog
TABLE_RESULT = 'crawl_results'             # LLM-zertifizierte Ergebnisse (wie crawler_js)

# ---------------------------------------------------------------
# DDL: crawl_results_bachelor (Rohlog)
# ---------------------------------------------------------------
_CREATE_RAW_PG = f"""
CREATE TABLE IF NOT EXISTS {TABLE_RAW} (
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

_CREATE_RAW_SQLITE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_RAW} (
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

# ---------------------------------------------------------------
# DDL: crawl_results (LLM-zertifiziert, kompatibel mit crawler_js)
# ---------------------------------------------------------------
_CREATE_RESULT_PG = f"""
CREATE TABLE IF NOT EXISTS {TABLE_RESULT} (
    id               SERIAL PRIMARY KEY,
    ags              TEXT,
    gefunden_am      DATE        NOT NULL DEFAULT CURRENT_DATE,
    start_time       TIMESTAMP,
    end_time         TIMESTAMP,
    status           TEXT,
    kategorie        TEXT,
    massnahme        TEXT,
    adresse          TEXT,
    massnahme_start  DATE,
    massnahme_ende   DATE,
    massnahme_url    TEXT,
    source           TEXT        NOT NULL DEFAULT 'bachelor_crawler'
);
"""

_CREATE_RESULT_SQLITE = f"""
CREATE TABLE IF NOT EXISTS {TABLE_RESULT} (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    ags              TEXT,
    gefunden_am      TEXT        NOT NULL DEFAULT (date('now')),
    start_time       TEXT,
    end_time         TEXT,
    status           TEXT,
    kategorie        TEXT,
    massnahme        TEXT,
    adresse          TEXT,
    massnahme_start  TEXT,
    massnahme_ende   TEXT,
    massnahme_url    TEXT,
    source           TEXT        NOT NULL DEFAULT 'bachelor_crawler'
);
"""

_MIGRATION_COLUMNS_RAW = [
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

_MIGRATION_COLUMNS_RESULT = [
    ('ags',             'TEXT'),
    ('gefunden_am',     "DATE NOT NULL DEFAULT CURRENT_DATE"),
    ('start_time',      'TIMESTAMP'),
    ('end_time',        'TIMESTAMP'),
    ('status',          'TEXT'),
    ('kategorie',       'TEXT'),
    ('massnahme',       'TEXT'),
    ('adresse',         'TEXT'),
    ('massnahme_start', 'DATE'),
    ('massnahme_ende',  'DATE'),
    ('massnahme_url',   'TEXT'),
    ('source',          "TEXT NOT NULL DEFAULT 'bachelor_crawler'"),
]


def _sanitize(text: str | None, max_len: int = 0) -> str | None:
    if text is None:
        return None
    text = text.replace('\x00', '')
    if max_len:
        text = text[:max_len]
    return text


def _extract_funde(llm: dict, fallback_url: str, fallback_kategorie: str | None) -> list[dict]:
    """
    Normalisiert das LLM-Ergebnis zu einer einheitlichen Liste von Fund-Dicts.

    Das LLM liefert Maßnahmen unter verschiedenen Keys:
      - 'massnahmen'  (Bachelor-Crawler-Standard, Liste von Dicts)
      - 'funde'       (älteres Format)
      - 'results'     (alternatives Format)
    Jedes Element der Liste wird auf die erwarteten DB-Felder gemappt.
    """
    # Priorität: massnahmen > funde > results
    raw_list = llm.get('massnahmen') or llm.get('funde') or llm.get('results') or []

    if not raw_list:
        return []

    funde = []
    for item in raw_list:
        if not isinstance(item, dict):
            # Einfacher String → als Maßnahme-Titel behandeln
            item = {'massnahme': str(item)}

        massnahme = (
            item.get('massnahme')
            or item.get('titel')
            or item.get('title')
            or item.get('beschreibung')
            or item.get('reason')
        )
        if not massnahme:
            continue

        kategorie = (
            item.get('kategorie')
            or item.get('top_category')
            or fallback_kategorie
        )
        funde.append({
            'massnahme':       massnahme,
            'kategorie':       kategorie,
            'adresse':         item.get('adresse') or item.get('address'),
            'massnahme_start': item.get('massnahme_start') or item.get('start_date'),
            'massnahme_ende':  item.get('massnahme_ende')  or item.get('end_date'),
            'massnahme_url':   item.get('massnahme_url')   or item.get('quelle_url') or fallback_url,
        })
    return funde


class DBClient:
    """
    Leichtgewichtiger DB-Client ohne ORM-Abhängigkeit.
    Schreibt in zwei Tabellen:
      - crawl_results_bachelor : Rohlog (jede relevante + LLM-bestätigte Seite)
      - crawl_results          : LLM-zertifizierte Funde (wie crawler_js)
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
            self._conn.execute(_CREATE_RAW_SQLITE)
            self._conn.execute(_CREATE_RESULT_SQLITE)
            self._conn.execute(
                f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLE_RAW}_url '
                f'ON {TABLE_RAW}(url);'
            )
            self._conn.commit()
            logger.info('DB SQLite verbunden -> %s', path)
        else:
            try:
                import psycopg2
                self._conn = psycopg2.connect(self._url)
                with self._conn.cursor() as cur:
                    cur.execute(_CREATE_RAW_PG)
                    cur.execute(_CREATE_RESULT_PG)
                    cur.execute(
                        f'CREATE UNIQUE INDEX IF NOT EXISTS idx_{TABLE_RAW}_url '
                        f'ON {TABLE_RAW}(url);'
                    )
                self._conn.commit()
                logger.info('DB PostgreSQL verbunden - Tabellen: %s, %s', TABLE_RAW, TABLE_RESULT)
            except ImportError:
                logger.error('psycopg2 nicht installiert - pip install psycopg2-binary')
                raise

    def _migrate(self) -> None:
        """Fehlende Spalten in beiden Tabellen per ALTER TABLE nachrüsten."""
        pairs = [
            (TABLE_RAW,    _MIGRATION_COLUMNS_RAW),
            (TABLE_RESULT, _MIGRATION_COLUMNS_RESULT),
        ]
        for table, columns in pairs:
            for col_name, col_type in columns:
                try:
                    if self._is_sqlite:
                        try:
                            self._conn.execute(
                                f'ALTER TABLE {table} ADD COLUMN {col_name} {col_type};'
                            )
                            self._conn.commit()
                            logger.info('DB Migration: %s.%s hinzugefügt', table, col_name)
                        except Exception as e:
                            if 'duplicate column' in str(e).lower():
                                pass
                            else:
                                logger.warning('DB Migration %s.%s: %s', table, col_name, e)
                    else:
                        with self._conn.cursor() as cur:
                            cur.execute(
                                f'ALTER TABLE {table} '
                                f'ADD COLUMN IF NOT EXISTS {col_name} {col_type};'
                            )
                        self._conn.commit()
                except Exception as e:
                    logger.warning('DB Migration Fehler %s.%s: %s', table, col_name, e)

    def close(self) -> None:
        if self._conn:
            self._conn.close()

    # ---------------------------------------------------------------
    # Rohlog: crawl_results_bachelor
    # ---------------------------------------------------------------
    def save_result(self, run_id: str, result: 'CrawlResult') -> None:
        """
        Speichert technisches Rohlog in crawl_results_bachelor.
        UPSERT auf url: mehrfaches Crawlen derselben URL überschreibt statt zu duplizieren.
        """
        snippet     = _sanitize(result.text, max_len=2000)
        blocks_json = _sanitize(json.dumps(result.blocks or [], ensure_ascii=False))
        url         = _sanitize(result.url)
        run_id      = _sanitize(run_id)

        rel             = result.relevance
        score           = rel.score if rel else None
        relevance_label = _sanitize(('relevant' if rel.is_relevant else 'nicht relevant') if rel else None)
        top_category    = _sanitize(rel.top_category if rel else None)
        confidence      = rel.confidence if rel else None

        llm            = result.llm_result or {}
        llm_relevant   = llm.get('relevant')
        llm_confidence = llm.get('confidence')
        llm_reason     = _sanitize(llm.get('reason'), max_len=500)

        if self._is_sqlite:
            sql = f"""
                INSERT INTO {TABLE_RAW}
                    (run_id, url, content_hash, is_pdf, http_status,
                     relevance_score, relevance_label, top_category, confidence,
                     llm_relevant, llm_confidence, llm_reason,
                     fetch_time_ms, text_snippet, blocks_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    run_id=excluded.run_id, content_hash=excluded.content_hash,
                    is_pdf=excluded.is_pdf, http_status=excluded.http_status,
                    relevance_score=excluded.relevance_score,
                    relevance_label=excluded.relevance_label,
                    top_category=excluded.top_category,
                    confidence=excluded.confidence,
                    llm_relevant=excluded.llm_relevant,
                    llm_confidence=excluded.llm_confidence,
                    llm_reason=excluded.llm_reason,
                    fetch_time_ms=excluded.fetch_time_ms,
                    text_snippet=excluded.text_snippet,
                    blocks_json=excluded.blocks_json,
                    crawled_at=CURRENT_TIMESTAMP
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
                INSERT INTO {TABLE_RAW}
                    (run_id, url, content_hash, is_pdf, http_status,
                     relevance_score, relevance_label, top_category, confidence,
                     llm_relevant, llm_confidence, llm_reason,
                     fetch_time_ms, text_snippet, blocks_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (url) DO UPDATE SET
                    run_id=EXCLUDED.run_id, content_hash=EXCLUDED.content_hash,
                    is_pdf=EXCLUDED.is_pdf, http_status=EXCLUDED.http_status,
                    relevance_score=EXCLUDED.relevance_score,
                    relevance_label=EXCLUDED.relevance_label,
                    top_category=EXCLUDED.top_category,
                    confidence=EXCLUDED.confidence,
                    llm_relevant=EXCLUDED.llm_relevant,
                    llm_confidence=EXCLUDED.llm_confidence,
                    llm_reason=EXCLUDED.llm_reason,
                    fetch_time_ms=EXCLUDED.fetch_time_ms,
                    text_snippet=EXCLUDED.text_snippet,
                    blocks_json=EXCLUDED.blocks_json,
                    crawled_at=CURRENT_TIMESTAMP
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
        logger.debug('DB Rohlog: gespeichert/aktualisiert -> %s', url)

    # ---------------------------------------------------------------
    # LLM-Ergebnisse: crawl_results (wie crawler_js)
    # ---------------------------------------------------------------
    def save_llm_result(self, ags: str | None, result: 'CrawlResult', start_time: datetime) -> None:
        """
        Schreibt LLM-bestätigte Funde in crawl_results (kompatibel mit crawler_js).
        Liest Maßnahmen aus llm_result['massnahmen'] (Bachelor-Standard),
        mit Fallback auf 'funde' und 'results' für ältere Formate.
        """
        llm = result.llm_result or {}
        fallback_kategorie = result.relevance.top_category if result.relevance else None

        funde = _extract_funde(llm, fallback_url=result.url, fallback_kategorie=fallback_kategorie)
        if not funde:
            logger.debug('DB crawl_results: keine Maßnahmen in llm_result für %s', result.url)
            return

        end_time = datetime.now()
        inserted = 0
        skipped  = 0

        for item in funde:
            massnahme       = _sanitize(item['massnahme'], max_len=500)
            kategorie       = _sanitize(item['kategorie'], max_len=200)
            adresse         = _sanitize(item['adresse'], max_len=500)
            massnahme_start = item['massnahme_start']
            massnahme_ende  = item['massnahme_ende']
            massnahme_url   = _sanitize(item['massnahme_url'], max_len=1000)

            if not massnahme:
                continue

            if self._is_duplicate(ags, massnahme, massnahme_start):
                skipped += 1
                logger.debug('DB crawl_results: Duplikat übersprungen -> %s', massnahme[:60])
                continue

            if self._is_sqlite:
                sql = f"""
                    INSERT INTO {TABLE_RESULT}
                        (ags, gefunden_am, start_time, end_time, status,
                         kategorie, massnahme, adresse,
                         massnahme_start, massnahme_ende, massnahme_url, source)
                    VALUES (?, date('now'), ?, ?, 'Erfolgreich', ?, ?, ?, ?, ?, ?, 'bachelor_crawler')
                """
                self._conn.execute(sql, (
                    ags, start_time, end_time,
                    kategorie, massnahme, adresse,
                    massnahme_start, massnahme_ende, massnahme_url,
                ))
                self._conn.commit()
            else:
                sql = f"""
                    INSERT INTO {TABLE_RESULT}
                        (ags, gefunden_am, start_time, end_time, status,
                         kategorie, massnahme, adresse,
                         massnahme_start, massnahme_ende, massnahme_url, source)
                    VALUES (%s, CURRENT_DATE, %s, %s, 'Erfolgreich', %s, %s, %s, %s, %s, %s, 'bachelor_crawler')
                """
                with self._conn.cursor() as cur:
                    cur.execute(sql, (
                        ags, start_time, end_time,
                        kategorie, massnahme, adresse,
                        massnahme_start, massnahme_ende, massnahme_url,
                    ))
                self._conn.commit()
            inserted += 1
            logger.debug('DB crawl_results: eingefügt -> %s', massnahme[:60])

        if inserted or skipped:
            logger.info('DB crawl_results: %d neu, %d Duplikate für %s',
                        inserted, skipped, result.url[:60])

    def _is_duplicate(self, ags: str | None, massnahme: str, massnahme_start) -> bool:
        """Prüft ob ags + massnahme + massnahme_start bereits in crawl_results existiert."""
        try:
            if self._is_sqlite:
                if massnahme_start is None:
                    row = self._conn.execute(
                        f'SELECT id FROM {TABLE_RESULT} '
                        f'WHERE ags IS ? AND massnahme=? AND massnahme_start IS NULL',
                        (ags, massnahme)
                    ).fetchone()
                else:
                    row = self._conn.execute(
                        f'SELECT id FROM {TABLE_RESULT} '
                        f'WHERE ags IS ? AND massnahme=? AND massnahme_start=?',
                        (ags, massnahme, massnahme_start)
                    ).fetchone()
                return row is not None
            else:
                with self._conn.cursor() as cur:
                    if massnahme_start is None:
                        cur.execute(
                            f'SELECT id FROM {TABLE_RESULT} '
                            f'WHERE ags IS NOT DISTINCT FROM %s AND massnahme=%s AND massnahme_start IS NULL',
                            (ags, massnahme)
                        )
                    else:
                        cur.execute(
                            f'SELECT id FROM {TABLE_RESULT} '
                            f'WHERE ags IS NOT DISTINCT FROM %s AND massnahme=%s AND massnahme_start=%s',
                            (ags, massnahme, massnahme_start)
                        )
                    return cur.fetchone() is not None
        except Exception as e:
            logger.warning('DB _is_duplicate Fehler: %s', e)
            return False

    def save_results_bulk(self, run_id: str, results: list) -> None:
        for r in results:
            try:
                self.save_result(run_id, r)
            except Exception as exc:
                logger.warning('DB Rohlog: Fehler bei %s: %s', r.url, exc)
