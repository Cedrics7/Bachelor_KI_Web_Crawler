"""
Unit-Tests fuer Bachelor_Crawler_erweitert.robots_checker.RobotsChecker.
Prüft robots.txt-Compliance, Crawl-Delay und Cache-Verhalten via Mocking.
"""
import sys
import os
import time
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Bachelor_Crawler_erweitert'))
from Bachelor_Crawler_erweitert.robots_checker import RobotsChecker


DISALLOW_ROBOTS = """
User-agent: *
Disallow: /admin/
Disallow: /login
Crawl-delay: 2
"""

ALLOW_ROBOTS = """
User-agent: *
Allow: /
"""


def _make_checker_with_robots(robots_text: str, url: str = 'https://example.com') -> RobotsChecker:
    """Erstellt einen RobotsChecker mit vorgemocktem RobotFileParser fuer die gegebene URL."""
    import urllib.robotparser
    checker = RobotsChecker(user_agent='*')
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_text.splitlines())
    base = 'https://example.com'
    checker._cache[base] = rp
    return checker


class TestRobotsCheckerIsAllowed:
    def test_disallowed_path_blocked(self):
        checker = _make_checker_with_robots(DISALLOW_ROBOTS)
        assert checker.is_allowed('https://example.com/admin/users') is False

    def test_disallowed_exact_path_blocked(self):
        checker = _make_checker_with_robots(DISALLOW_ROBOTS)
        assert checker.is_allowed('https://example.com/login') is False

    def test_allowed_path_permitted(self):
        checker = _make_checker_with_robots(DISALLOW_ROBOTS)
        assert checker.is_allowed('https://example.com/news/artikel') is True

    def test_allow_all_permits_any_path(self):
        checker = _make_checker_with_robots(ALLOW_ROBOTS)
        assert checker.is_allowed('https://example.com/admin') is True

    def test_exception_during_fetch_returns_true(self):
        """Wenn robots.txt nicht abrufbar ist, gilt: erlaubt (fail-open)."""
        checker = RobotsChecker(user_agent='*')
        # Kein Cache-Eintrag, Netz-Request faellt fehl -> soll True zurueckgeben
        with patch('urllib.robotparser.RobotFileParser.read', side_effect=Exception('Network error')):
            result = checker.is_allowed('https://nonexistent-domain-xyz.invalid/path')
        assert result is True


class TestRobotsCheckerCrawlDelay:
    def test_crawl_delay_returned(self):
        checker = _make_checker_with_robots(DISALLOW_ROBOTS)
        delay = checker.get_crawl_delay('https://example.com/news')
        assert delay == 2.0

    def test_no_crawl_delay_returns_zero(self):
        checker = _make_checker_with_robots(ALLOW_ROBOTS)
        delay = checker.get_crawl_delay('https://example.com/news')
        assert delay == 0.0

    def test_crawl_delay_exception_returns_zero(self):
        checker = _make_checker_with_robots(ALLOW_ROBOTS)
        with patch.object(checker._cache['https://example.com'], 'crawl_delay', side_effect=Exception):
            delay = checker.get_crawl_delay('https://example.com/page')
        assert delay == 0.0


class TestRobotsCheckerCache:
    def test_same_domain_uses_cache(self):
        checker = _make_checker_with_robots(DISALLOW_ROBOTS)
        # Zweiter Aufruf sollte cachedaten nutzen (kein zweiter rp.read())
        parser1, base1 = checker._get_parser('https://example.com/page1')
        parser2, base2 = checker._get_parser('https://example.com/page2')
        assert parser1 is parser2
        assert base1 == base2

    def test_different_domains_separate_cache_entries(self):
        checker = RobotsChecker(user_agent='*')
        import urllib.robotparser
        rp_a = urllib.robotparser.RobotFileParser()
        rp_a.parse(ALLOW_ROBOTS.splitlines())
        rp_b = urllib.robotparser.RobotFileParser()
        rp_b.parse(DISALLOW_ROBOTS.splitlines())
        checker._cache['https://site-a.com'] = rp_a
        checker._cache['https://site-b.com'] = rp_b
        assert checker.is_allowed('https://site-a.com/admin') is True
        assert checker.is_allowed('https://site-b.com/admin/x') is False


class TestRobotsCheckerRecordAccess:
    def test_record_access_sets_timestamp(self):
        checker = _make_checker_with_robots(ALLOW_ROBOTS)
        before = time.time()
        checker.record_access('https://example.com/page')
        after = time.time()
        last = checker._last_access.get('https://example.com')
        assert last is not None
        assert before <= last <= after

    def test_wait_for_crawl_delay_no_delay_no_sleep(self):
        """Wenn kein Crawl-Delay konfiguriert, wird time.sleep nicht aufgerufen."""
        checker = _make_checker_with_robots(ALLOW_ROBOTS)
        checker.record_access('https://example.com/page')
        with patch('time.sleep') as mock_sleep:
            checker.wait_for_crawl_delay('https://example.com/page2')
        mock_sleep.assert_not_called()

    def test_wait_for_crawl_delay_sleeps_if_needed(self):
        """Mit Crawl-Delay und kuerzlichem Zugriff wird time.sleep aufgerufen."""
        checker = _make_checker_with_robots(DISALLOW_ROBOTS)  # Crawl-Delay: 2
        checker._last_access['https://example.com'] = time.time()  # gerade eben zugegriffen
        with patch('time.sleep') as mock_sleep:
            checker.wait_for_crawl_delay('https://example.com/page')
        mock_sleep.assert_called_once()
        _, args, _ = mock_sleep.mock_calls[0]
        assert args[0] > 0
