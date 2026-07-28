"""Strukturiertes Step-Logging für Bachelor_Crawler_erweitert."""
from __future__ import annotations
import json
from pathlib import Path
from datetime import datetime


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

    def _write(self, level: str, event: str, message: str = '', **data):
        row = {
            'ts': datetime.now().isoformat(),
            'level': level,
            'event': event,
            'message': message,
            **data,
        }
        with self.log_file.open('a', encoding='utf-8') as f:
            f.write(json.dumps(row, ensure_ascii=False) + '\n')

    def section(self, title: str):
        self._write('INFO', 'SECTION', title)

    def info(self, event: str, message: str = '', **data):
        self._write('INFO', event, message, **data)

    def debug(self, event: str, message: str = '', **data):
        self._write('DEBUG', event, message, **data)

    def error(self, event: str, message: str = '', **data):
        self._write('ERROR', event, message, **data)

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
            cpe_score=cpe_score,
            anchor_score=anchor_score,
            context_score=context_score,
            url_score=url_score,
            page_score=page_score,
            is_priority=is_priority,
        )

    def privacy(self, url: str, event: str, message: str, **data):
        self._write('INFO', f'PRIVACY.{event}', message, url=url, **data)

    def evaluation(self, report: dict, label: str = 'FOCUSED'):
        self._write('INFO', f'EVALUATION.{label}', '', report=report)

    def close(self):
        pass
