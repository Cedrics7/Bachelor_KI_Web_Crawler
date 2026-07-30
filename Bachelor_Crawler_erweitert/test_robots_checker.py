"""
Unit-Tests fuer robots_checker.RobotsChecker.
Prueft robots.txt-Compliance, Crawl-Delay und Cache-Verhalten via Mocking.
Aufruf:  pytest Bachelor_Crawler_erweitert/test_robots_checker.py -v
"""
import time
import urllib.robotparser
from unittest.mock import patch

import pytest

from .robots_checker import RobotsChecker


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


def _make_checker(robots_text: str) -> RobotsChecker:
    """Checker mit vorgemocktem Parser fuer https://example.com."""
    checker = RobotsChecker(user_agent='*')
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_text.splitlines())
    checker._cache['https://example.com'] = rp
    return checker


class TestRobotsCheckerIsAllowed:
    def test_disallowed_path_blocked(self):
        assert _make_checker(DISALLOW_ROBOTS).is_allowed('https://example.com/admin/users') is False

    def test_disallowed_exact_path_blocked(self):
        assert _make_checker(DISALLOW_ROBOTS).is_allowed('https://example.com/login') is False

    def test_allowed_path_permitted(self):
        assert _make_checker(DISALLOW_ROBOTS).is_allowed('https://example.com/news/artikel') is True

    def test_allow_all_permits_any_path(self):
        assert _make_checker(ALLOW_ROBOTS).is_allowed('https://example.com/admin') is True

    def test_exception_during_fetch_returns_true(self):
        """Wenn robots.txt nicht abrufbar ist, gilt fail-open (True)."""
        checker = RobotsChecker(user_agent='*')
        with patch('urllib.robotparser.RobotFileParser.read', side_effect=Exception('Network error')):
            result = checker.is_allowed('https://nonexistent-domain-xyz.invalid/path')
        assert result is True


class TestRobotsCheckerCrawlDelay:
    def test_crawl_delay_returned(self):
        assert _make_checker(DISALLOW_ROBOTS).get_crawl_delay('https://example.com/news') == 2.0

    def test_no_crawl_delay_returns_zero(self):
        assert _make_checker(ALLOW_ROBOTS).get_crawl_delay('https://example.com/news') == 0.0

    def test_crawl_delay_exception_returns_zero(self):
        checker = _make_checker(ALLOW_ROBOTS)
        with patch.object(checker._cache['https://example.com'], 'crawl_delay', side_effect=Exception):
            assert checker.get_crawl_delay('https://example.com/page') == 0.0


class TestRobotsCheckerCache:
    def test_same_domain_uses_cache(self):
        checker = _make_checker(DISALLOW_ROBOTS)
        p1, b1 = checker._get_parser('https://example.com/page1')
        p2, b2 = checker._get_parser('https://example.com/page2')
        assert p1 is p2
        assert b1 == b2

    def test_different_domains_separate_entries(self):
        checker = RobotsChecker(user_agent='*')
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
        checker = _make_checker(ALLOW_ROBOTS)
        before = time.time()
        checker.record_access('https://example.com/page')
        after = time.time()
        last = checker._last_access.get('https://example.com')
        assert last is not None
        assert before <= last <= after

    def test_wait_no_delay_no_sleep(self):
        """Kein Crawl-Delay -> time.sleep wird nicht aufgerufen."""
        checker = _make_checker(ALLOW_ROBOTS)
        checker.record_access('https://example.com/page')
        with patch('time.sleep') as mock_sleep:
            checker.wait_for_crawl_delay('https://example.com/page2')
        mock_sleep.assert_not_called()

    def test_wait_with_delay_sleeps(self):
        """Mit Crawl-Delay und kuerzlichem Zugriff wird time.sleep aufgerufen."""
        checker = _make_checker(DISALLOW_ROBOTS)  # Crawl-delay: 2
        checker._last_access['https://example.com'] = time.time()
        with patch('time.sleep') as mock_sleep:
            checker.wait_for_crawl_delay('https://example.com/page')
        mock_sleep.assert_called_once()
        assert mock_sleep.call_args[0][0] > 0
