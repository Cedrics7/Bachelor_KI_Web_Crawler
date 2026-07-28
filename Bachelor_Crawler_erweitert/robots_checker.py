"""
Vereinfachte robots.txt-Compliance mit Crawl-Delay.
"""
from __future__ import annotations
import time
import urllib.robotparser
from urllib.parse import urlparse

class RobotsChecker:
    def __init__(self, user_agent: str = '*', timeout: int = 8) -> None:
        self.user_agent = user_agent
        self.timeout = timeout
        self._cache = {}
        self._last_access = {}

    def _get_parser(self, url: str):
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._cache:
            rp = urllib.robotparser.RobotFileParser()
            rp.set_url(base + '/robots.txt')
            try:
                rp.read()
            except Exception:
                pass
            self._cache[base] = rp
        return self._cache[base], base

    def is_allowed(self, url: str) -> bool:
        rp, _ = self._get_parser(url)
        try:
            return rp.can_fetch(self.user_agent, url)
        except Exception:
            return True

    def get_crawl_delay(self, url: str) -> float:
        rp, _ = self._get_parser(url)
        try:
            delay = rp.crawl_delay(self.user_agent)
            return float(delay) if delay else 0.0
        except Exception:
            return 0.0

    def wait_for_crawl_delay(self, url: str) -> None:
        _, base = self._get_parser(url)
        delay = self.get_crawl_delay(url)
        last = self._last_access.get(base)
        if delay and last:
            wait = delay - (time.time() - last)
            if wait > 0:
                time.sleep(wait)

    def record_access(self, url: str) -> None:
        _, base = self._get_parser(url)
        self._last_access[base] = time.time()
