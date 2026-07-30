"""Strukturiertes Step-Logging fuer Bachelor_Crawler_erweitert.

Gibt alle Events sowohl auf der Konsole (via Python-logging) als auch
in eine strukturierte JSON-Logdatei (logs/<run_id>.log) aus.
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from datetime import datetime

_STD = logging.getLogger('crawler')

# Keys die als Positional-Parameter in _write() existieren und daher
# niemals via **data hereinkommen duerfen (wuerden TypeError ausloesen).
_RESERVED_KEYS = frozenset({'event', 'level', 'message', 'ts'})

# Konsolen-Format-Mapping fuer lesbare Ausgabe
_CONSOLE_FORMAT = {
    'SECTION':           '  ──── {message} ────',
    'CRAWL.FETCH':       '  ↓ FETCH       {url}',
    'CRAWL.SKIP':        '  ○ SKIP        {url}  [{reason}]',
    'CRAWL.ROBOTS':      '  ✗ ROBOTS      {url}',
    'CRAWL.HASH_DUP':    '  ≡ HASH-DUP    {url}',
    'CRAWL.DOMAIN_GUARD':'  ✗ DOMAIN      {url}  → {final_domain}',
    'CRAWL.PDF':         '  📄 PDF         {url}  ({chars} Zeichen)',
    'CRAWL.JS':          '  🌐 JS-RENDER   {url}',
    'CRAWL.VG':          '  ↪ VG-REDIRECT {url}  → {effective_domain}',
    'CRAWL.RAM':         '  💾 RAM          {rss_mb} MB  (Queue: {queue_size})',
    'CRAWL.DONE':        '  ✓ DONE        {url}  [{http_status}] {fetch_ms}ms',
    'RELEVANCE':         '  🔍 RELEVANZ    {url}  score={score:.3f}  relevant={relevant}  [{top_category}]',
    'CPE':               '  🔗 CPE-LINK    {url}  cpe={cpe_score:.3f}  prio={is_priority}',
    'PRIVACY.ROBOTS_DISALLOWED': '  🚫 PII/ROBOTS  {url}',
    'PRIVACY.DOMAIN_GUARD':      '  🚫 DOMAIN      {url}',
    'PRIVACY.PII_FILTERED':      '  🔒 PII-FILTER  {url}  ({replacements} Ersetzungen)',
    'EVALUATION.FOCUSED':'  📊 EVALUATION  Seiten={total_crawled}  Relevant={total_relevant}'
                          '  HR={harvest_rate:.1%}  Skipped={total_skipped}  PDFs={total_pdfs}'
                          '  robots_blocked={total_robots_blocked}',
    'ERROR':             '  ✗ FEHLER       {orig_event}: {message}',
}


class CrawlerLogger:
    def __init__(
        self,
        run_id: str = 'run',
        log_dir: str = 'logs',
        console_level: str = 'INFO',
        file_level: str = 'DEBUG',
    ):
        self.run_id = run_id
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f'{run_id}.log'
        self._logger = logging.getLogger(f'crawler.{run_id}')

    # ------------------------------------------------------------------ intern

    def _write(self, level: str, event: str, message: str = '', **data):
        # Reservierte Keys aus data entfernen um TypeError zu verhindern.
        # Falls ein Aufrufer z.B. event=... oder level=... in **data mitschickt
        # (z.B. aus einem LLM-Result-Dict), wuerden diese mit den Positional-
        # Parametern kollidieren.
        safe_data = {k: v for k, v in data.items() if k not in _RESERVED_KEYS}

        row = {
            'ts':      datetime.now().isoformat(),
            'level':   level,
            'event':   event,
            'message': message,
            **safe_data,
        }
        with self.log_file.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')
        self._to_console(level, event, message, **safe_data)

    def _to_console(self, level: str, event: str, message: str, **data):
        template = _CONSOLE_FORMAT.get(event)
        if template is None:
            extra = '  '.join(f'{k}={v}' for k, v in data.items() if v not in ('', None))
            line = f'  [{event}] {message}  {extra}'.rstrip()
        else:
            try:
                merged = {'message': message, 'event': event, **data}
                line = template.format_map(_SafeDict(merged))
            except Exception:
                line = f'  [{event}] {message}'

        log_fn = {
            'DEBUG': self._logger.debug,
            'INFO':  self._logger.info,
            'WARN':  self._logger.warning,
            'ERROR': self._logger.error,
        }.get(level, self._logger.info)
        log_fn(line)

    # ------------------------------------------------------------------ public

    def section(self, title: str):
        self._write('INFO', 'SECTION', title)

    def info(self, event: str, message: str = '', **data):
        self._write('INFO', event, message, **data)

    def debug(self, event: str, message: str = '', **data):
        self._write('DEBUG', event, message, **data)

    def error(self, event: str, message: str = '', **data):
        # 'orig_event' damit das ERROR-Template {orig_event} anzeigen kann
        self._write('ERROR', 'ERROR', message, orig_event=event, **data)

    def crawl_step(self, url: str, step: str, **data):
        self._write('INFO', f'CRAWL.{step}', url=url, **data)

    def relevance(self, **data):
        self._write('INFO', 'RELEVANCE', '', **data)

    def cpe_score(
        self,
        url: str,
        cpe_score: float,
        anchor_score: float,
        context_score: float,
        url_score: float,
        page_score: float,
        is_priority: bool,
    ):
        self._write(
            'DEBUG', 'CPE', '',
            url=url,
            cpe_score=round(cpe_score, 4),
            anchor_score=round(anchor_score, 4),
            context_score=round(context_score, 4),
            url_score=round(url_score, 4),
            page_score=round(page_score, 4),
            is_priority=is_priority,
        )

    def privacy(self, url: str, event: str, message: str, **data):
        self._write('INFO', f'PRIVACY.{event}', message, url=url, **data)

    def evaluation(self, report: dict, label: str = 'FOCUSED'):
        self._write('INFO', f'EVALUATION.{label}', '', **report)

    def close(self):
        pass


class _SafeDict(dict):
    """format_map-Fallback: fehlende Keys werden als '{key}' belassen."""
    def __missing__(self, key):
        return f'{{{key}}}'
