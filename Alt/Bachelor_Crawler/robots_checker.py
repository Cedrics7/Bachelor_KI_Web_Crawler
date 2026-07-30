"""
robots_checker.py
=================
DSGVO- und robots.txt-konforme URL-Prüfung für den Bachelor_Crawler.

Funktionen:
    - RobotsChecker.is_allowed(url): Prüft ob eine URL gecrawlt werden darf
    - Respektiert Crawl-Delay aus robots.txt
    - Cacht robots.txt pro Domain (kein wiederholter Download)
    - Loggt alle Ablehnungen über das bestehende logger-Modul
    - User-Agent: wird aus CONFIG["http_user_agent"] gelesen (konsistent zu scraper_js)

DSGVO-Relevanz:
    Das Einhalten von robots.txt ist kein DSGVO-Pflichtbestandteil, aber ein
    anerkanntes ethisches Minimum beim Web-Crawling. Seiten, die robots.txt
    Crawling untersagen, könnten personenbezogene Daten schützen wollen.
    Das Ignorieren wäre datenschutzrechtlich kritisch zu bewerten.
"""

import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from typing import Optional

import httpx

# Logger aus bestehendem Modul verwenden (Konsistenz zu crawler_js)
try:
    from logger import log_event
except ImportError:
    def log_event(emoji: str, msg: str) -> None:
        print(f"[Bachelor_Crawler] {emoji} {msg}")


class RobotsChecker:
    """
    Prüft URLs gegen robots.txt und verwaltet den Crawl-Delay.

    Verwendung:
        checker = RobotsChecker(user_agent="MyCrawler/1.0")
        if checker.is_allowed("https://example.com/page"):
            # crawlen erlaubt
        checker.wait_for_crawl_delay("https://example.com")
    """

    # Maximale Anzahl gecachter robots.txt (verhindert RAM-Anstieg bei vielen Domains)
    _MAX_CACHE = 500

    def __init__(self, user_agent: str = "*", timeout: int = 10) -> None:
        self._user_agent = user_agent
        self._timeout = timeout
        # Cache: domain → (RobotFileParser, crawl_delay_seconds, last_access_time)
        self._cache: dict[str, tuple[RobotFileParser, float, float]] = {}

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def is_allowed(self, url: str) -> bool:
        """
        Gibt True zurück, wenn der User-Agent die URL gemäß robots.txt crawlen darf.
        Bei Fehler beim Laden der robots.txt wird True zurückgegeben (fail-open),
        um technische Ausfälle nicht als Verbot zu werten.
        """
        rp = self._get_parser(url)
        if rp is None:
            return True  # fail-open
        allowed = rp.can_fetch(self._user_agent, url)
        if not allowed:
            log_event(
                "🚫",
                f"robots.txt verbietet Crawling: {url[:80]} "
                f"(UA: {self._user_agent})"
            )
        return allowed

    def get_crawl_delay(self, url: str) -> float:
        """
        Gibt den Crawl-Delay für die Domain zurück (in Sekunden).
        Wenn kein Delay definiert: 0.0
        """
        domain = self._extract_domain(url)
        if domain in self._cache:
            _, delay, _ = self._cache[domain]
            return delay
        rp = self._get_parser(url)
        if rp is None:
            return 0.0
        raw_delay = rp.crawl_delay(self._user_agent)
        return float(raw_delay) if raw_delay is not None else 0.0

    def wait_for_crawl_delay(self, url: str) -> None:
        """
        Wartet die restliche Crawl-Delay-Zeit seit dem letzten Zugriff auf diese Domain.
        Sollte VOR jedem Request aufgerufen werden.
        """
        domain = self._extract_domain(url)
        if domain not in self._cache:
            return
        _, delay, last_access = self._cache[domain]
        if delay <= 0:
            return
        elapsed = time.time() - last_access
        remaining = delay - elapsed
        if remaining > 0:
            log_event(
                "⏳",
                f"Crawl-Delay {delay:.1f}s für {domain} – warte noch {remaining:.1f}s"
            )
            time.sleep(remaining)
        # Zugriffszeit aktualisieren
        rp, _, _ = self._cache[domain]
        self._cache[domain] = (rp, delay, time.time())

    def record_access(self, url: str) -> None:
        """Aktualisiert den last_access-Timestamp für die Domain."""
        domain = self._extract_domain(url)
        if domain in self._cache:
            rp, delay, _ = self._cache[domain]
            self._cache[domain] = (rp, delay, time.time())

    # ------------------------------------------------------------------
    # Interne Hilfsmethoden
    # ------------------------------------------------------------------

    def _get_parser(self, url: str) -> Optional[RobotFileParser]:
        """Gibt den gecachten oder neu geladenen RobotFileParser zurück."""
        domain = self._extract_domain(url)
        if domain in self._cache:
            rp, _, _ = self._cache[domain]
            return rp

        robots_url = self._build_robots_url(url)
        rp = RobotFileParser()
        rp.set_url(robots_url)

        try:
            # robots.txt manuell laden – httpx statt urllib für einheitliches Verhalten
            with httpx.Client(timeout=self._timeout, follow_redirects=True) as client:
                resp = client.get(robots_url, headers={"User-Agent": self._user_agent})
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                    log_event("🤖", f"robots.txt geladen: {robots_url}")
                elif resp.status_code == 404:
                    # Keine robots.txt → alles erlaubt
                    log_event("✅", f"Keine robots.txt ({resp.status_code}): {robots_url}")
                    rp.parse([])  # leere Regeln = alles erlaubt
                else:
                    log_event(
                        "⚠️",
                        f"robots.txt nicht erreichbar ({resp.status_code}): {robots_url} – fail-open"
                    )
                    return None
        except httpx.RequestError as e:
            log_event("⚠️", f"robots.txt Fehler ({robots_url}): {str(e)[:60]} – fail-open")
            return None

        # Crawl-Delay extrahieren
        raw_delay = rp.crawl_delay(self._user_agent)
        delay = float(raw_delay) if raw_delay is not None else 0.0

        # Cache begrenzen
        if len(self._cache) >= self._MAX_CACHE:
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        self._cache[domain] = (rp, delay, 0.0)  # last_access=0 → kein Warten beim ersten Call
        return rp

    @staticmethod
    def _extract_domain(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @staticmethod
    def _build_robots_url(url: str) -> str:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}/robots.txt"
