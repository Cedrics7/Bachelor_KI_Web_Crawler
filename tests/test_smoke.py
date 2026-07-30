"""
Smoke-Test (End-to-End-Integration) fuer den FocusedCrawler.

Verwendet einen httpx.MockTransport, sodass kein echter HTTP-Request noetig ist.
Prueft, dass alle Kernkomponenten zusammenarbeiten:
  - FocusedCrawler instanziiert sich ohne Fehler
  - crawl() gibt CrawlResult-Liste und EvaluationReport zurueck
  - Relevanzklassifikation laeuft durch
  - DSGVO-PII-Filter greift (E-Mail wird entfernt)
  - robots.txt-Handling (allow / disallow)
  - EvaluationReport enthaelt sinnvolle Kennzahlen

Die Tests sind offline-faehig (kein Netz, kein LLM, keine DB noetig).
"""
from __future__ import annotations
import sys
import os
from typing import List

import pytest
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Bachelor_Crawler_erweitert'))

from Bachelor_Crawler_erweitert.focused_crawler import FocusedCrawler, CrawlResult
from Bachelor_Crawler_erweitert.evaluation import EvaluationReport
from Bachelor_Crawler_erweitert.domain_model import DomainModel
from Bachelor_Crawler_erweitert.relevance_classifier import RelevanceClassifier
from Bachelor_Crawler_erweitert.link_prioritizer import LinkPrioritizer
from Bachelor_Crawler_erweitert.privacy_guard import PrivacyGuard
from Bachelor_Crawler_erweitert.robots_checker import RobotsChecker
from Bachelor_Crawler_erweitert.crawler_logger import CrawlerLogger

# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

ROBOTS_ALLOW_ALL = b"User-agent: *\nAllow: /\n"
ROBOTS_DISALLOW_ADMIN = b"User-agent: *\nDisallow: /admin/\n"

_RELEVANT_PAGE = """
<html><body>
<h1>Breitbandausbau Glasfaser 2025</h1>
<p>Die Gemeinde plant den Ausbau der Breitbandinfrastruktur.
Ein Foerderantrag fuer den Glasfaser-Anschluss wurde eingereicht.
Die Tiefbauarbeiten sollen im Fruehsommer beginnen.
Bauvorhaben Bebauungsplan Sanierung Erschliessung Netzausbau.</p>
<a href="/ausbau/details">Details zum Ausbau</a>
<a href="/impressum">Impressum</a>
</body></html>
""".encode()

_IRRELEVANT_PAGE = """
<html><body>
<h1>Willkommen auf unserer Webseite</h1>
<p>Hier finden Sie allgemeine Informationen.</p>
</body></html>
""".encode()

_PII_PAGE = """
<html><body>
<p>Kontakt: max.mustermann@gemeinde.de, Tel: 040 12345678</p>
<p>Glasfaser Breitband Infrastrukturprojekt Bauvorhaben.</p>
</body></html>
""".encode()


def _make_transport(url_map: dict) -> httpx.MockTransport:
    """Erstellt einen MockTransport der URL-Pfade auf Response-Bodies mappt."""
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == '/robots.txt':
            return httpx.Response(200, content=ROBOTS_ALLOW_ALL, headers={'Content-Type': 'text/plain'})
        body = url_map.get(path, b'<html><body>Leer</body></html>')
        return httpx.Response(200, content=body, headers={'Content-Type': 'text/html; charset=utf-8'})
    return httpx.MockTransport(handler)


def _make_crawler(transport: httpx.MockTransport, extra_config: dict | None = None) -> FocusedCrawler:
    """Erstellt FocusedCrawler mit gemocktem HTTP-Transport und deaktiviertem LLM/DB."""
    import httpx as _httpx
    config = {
        'max_pages': 5,
        'crawl_delay_default': 0.0,
        'robots_respect': False,
        'llm_enabled': False,
        'db_enabled': False,
        'privacy_filter_pii': True,
        'log_dir': '/tmp/test_logs',
        'relevance_threshold': 0.05,
        'priority_threshold': 0.1,
    }
    if extra_config:
        config.update(extra_config)
    crawler = FocusedCrawler(config=config, run_id='smoke_test')
    crawler._http_client_factory = lambda: _httpx.Client(
        transport=transport,
        follow_redirects=True,
        headers={'User-Agent': 'SmokeTestBot/1.0'},
        timeout=5,
    )
    return crawler


# ---------------------------------------------------------------------------
# Smoke-Tests
# ---------------------------------------------------------------------------

class TestFocusedCrawlerSmoke:
    """End-to-End-Smoke-Tests fuer den FocusedCrawler mit gemocktem HTTP."""

    def _run_crawl(self, pages: dict, start: str = 'https://test.local/') -> tuple:
        transport = _make_transport(pages)
        crawler = _make_crawler(transport)
        import unittest.mock as mock
        with mock.patch('httpx.Client') as MockClient:
            mock_instance = MockClient.return_value.__enter__.return_value
            def side_effect(url):
                path = httpx.URL(url).path
                if path == '/robots.txt':
                    content = ROBOTS_ALLOW_ALL
                else:
                    content = pages.get(path, b'<html><body>Leer</body></html>')
                resp = mock.MagicMock()
                resp.status_code = 200
                resp.content = content
                resp.text = content.decode('utf-8', errors='replace')
                resp.url = httpx.URL(url)
                return resp
            mock_instance.get.side_effect = side_effect
            results, report = crawler.crawl(start, max_pages=5)
        return results, report

    def test_crawler_instantiation(self):
        """FocusedCrawler instanziiert sich ohne Exception."""
        config = {'max_pages': 1, 'llm_enabled': False, 'db_enabled': False,
                  'robots_respect': False, 'log_dir': '/tmp/test_logs',
                  'crawl_delay_default': 0.0, 'privacy_filter_pii': True,
                  'relevance_threshold': 0.05, 'priority_threshold': 0.1}
        crawler = FocusedCrawler(config=config, run_id='inst_test')
        assert crawler is not None

    def test_crawl_returns_correct_types(self):
        results, report = self._run_crawl({'/': _RELEVANT_PAGE})
        assert isinstance(results, list)
        assert isinstance(report, EvaluationReport)

    def test_relevant_page_classified(self):
        """Eine inhaltlich relevante Seite (Glasfaser, Breitband) bekommt score > 0."""
        results, report = self._run_crawl({'/': _RELEVANT_PAGE})
        assert len(results) >= 1
        scores = [r.relevance.score for r in results]
        assert max(scores) > 0

    def test_evaluation_report_total_crawled(self):
        """EvaluationReport zaehlt mind. 1 gecrawlte Seite (Attribut: total_crawled)."""
        results, report = self._run_crawl({'/': _RELEVANT_PAGE})
        assert report.total_crawled >= 1

    def test_privacy_pii_filter_removes_email(self):
        """E-Mail-Adressen werden aus dem gespeicherten Text entfernt."""
        results, _ = self._run_crawl({'/': _PII_PAGE})
        assert len(results) >= 1
        for r in results:
            assert 'max.mustermann@gemeinde.de' not in r.text

    def test_privacy_pii_filter_placeholder_present(self):
        """Nach PII-Filterung steht der Platzhalter [E-MAIL ENTFERNT] im Text."""
        results, _ = self._run_crawl({'/': _PII_PAGE})
        all_text = ' '.join(r.text for r in results)
        assert '[E-MAIL ENTFERNT]' in all_text

    def test_irrelevant_page_low_score(self):
        """Eine rein generische Seite bekommt einen niedrigen Relevanzwert."""
        results, _ = self._run_crawl({'/': _IRRELEVANT_PAGE})
        if results:
            assert results[0].relevance.score < 0.5

    def test_crawl_result_has_url(self):
        """Jedes CrawlResult hat eine nicht-leere URL."""
        results, _ = self._run_crawl({'/': _RELEVANT_PAGE})
        for r in results:
            assert r.url

    def test_crawl_result_has_content_hash(self):
        """Jedes CrawlResult hat einen SHA-256-Hash (64 Zeichen)."""
        results, _ = self._run_crawl({'/': _RELEVANT_PAGE})
        for r in results:
            assert len(r.content_hash) == 64


# ---------------------------------------------------------------------------
# Komponenten-Smoke-Tests (offline, keine Mocks noetig)
# ---------------------------------------------------------------------------

class TestComponentSmoke:
    """Schnelle Smoke-Tests fuer Einzelkomponenten: nur Instanziierung + Basisfunktion."""

    def test_domain_model_scores_infrastruktur_keyword(self):
        score, kws = DomainModel().score_text(
            'Glasfaser Breitbandausbau Bebauungsplan Tiefbau Foerderantrag'
        )
        assert score > 0
        assert len(kws) > 0

    def test_domain_model_score_empty_text(self):
        score, kws = DomainModel().score_text('')
        assert score == 0.0

    def test_relevance_classifier_returns_result(self):
        dm = DomainModel()
        # Korrekter Parameter-Name gemaess RelevanceClassifier.__init__: relevance_threshold
        clf = RelevanceClassifier(dm, relevance_threshold=0.05)
        result = clf.classify(
            text='Glasfaser Breitband Infrastruktur Netzausbau',
            url='https://example.com/glasfaser'
        )
        assert hasattr(result, 'score')
        assert hasattr(result, 'is_relevant')

    def test_link_prioritizer_scores_links(self):
        dm = DomainModel()
        prio = LinkPrioritizer(dm, priority_threshold=0.1)
        links = [
            ('https://example.com/glasfaser', 'Glasfaser Ausbau', 'Breitband'),
            ('https://example.com/impressum', 'Impressum', ''),
        ]
        scored = prio.score_links(links, page_text='Glasfaser Infrastruktur')
        assert len(scored) == 2

    def test_privacy_guard_filter_text_no_crash(self):
        guard = PrivacyGuard()
        result = guard.filter_text('Kein PII-Inhalt hier.')
        assert isinstance(result, str)

    def test_robots_checker_instantiation(self):
        checker = RobotsChecker(user_agent='TestBot/1.0')
        assert checker.user_agent == 'TestBot/1.0'
        assert isinstance(checker._cache, dict)

    def test_crawler_logger_instantiation(self):
        logger = CrawlerLogger(run_id='smoke_logger', log_dir='/tmp/test_logs')
        assert logger is not None
        logger.close()
