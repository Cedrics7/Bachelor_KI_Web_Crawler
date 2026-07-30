"""
Smoke-Test (End-to-End-Integration) fuer den FocusedCrawler.

Verwendet unittest.mock, sodass kein echter HTTP-Request noetig ist.
Prueft, dass alle Kernkomponenten zusammenarbeiten:
  - FocusedCrawler instanziiert sich ohne Fehler
  - crawl() gibt CrawlResult-Liste und EvaluationReport zurueck
  - Relevanzklassifikation laeuft durch
  - DSGVO-PII-Filter greift (E-Mail wird entfernt)
  - EvaluationReport enthaelt sinnvolle Kennzahlen

Die Tests sind offline-faehig (kein Netz, kein LLM, keine DB noetig).
Aufruf:  pytest Bachelor_Crawler_erweitert/test_smoke.py -v
"""
from __future__ import annotations
import unittest.mock as mock

import httpx
import pytest

from .focused_crawler import FocusedCrawler, CrawlResult
from .evaluation import EvaluationReport
from .domain_model import DomainModel
from .relevance_classifier import RelevanceClassifier
from .link_prioritizer import LinkPrioritizer
from .privacy_guard import PrivacyGuard
from .robots_checker import RobotsChecker
from .crawler_logger import CrawlerLogger

# ---------------------------------------------------------------------------
# Hilfsdaten
# ---------------------------------------------------------------------------

ROBOTS_ALLOW_ALL = b"User-agent: *\nAllow: /\n"

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

_BASE_CONFIG = {
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


def _run_crawl(pages: dict, start: str = 'https://test.local/') -> tuple:
    """Startet einen Crawl mit gemocktem httpx.Client."""
    crawler = FocusedCrawler(config=_BASE_CONFIG, run_id='smoke_test')
    with mock.patch('httpx.Client') as MockClient:
        mock_instance = MockClient.return_value.__enter__.return_value

        def side_effect(url):
            path = httpx.URL(url).path
            content = ROBOTS_ALLOW_ALL if path == '/robots.txt' \
                else pages.get(path, b'<html><body>Leer</body></html>')
            resp = mock.MagicMock()
            resp.status_code = 200
            resp.content = content
            resp.text = content.decode('utf-8', errors='replace')
            resp.url = httpx.URL(url)
            return resp

        mock_instance.get.side_effect = side_effect
        return crawler.crawl(start, max_pages=5)


# ---------------------------------------------------------------------------
# TestFocusedCrawlerSmoke
# ---------------------------------------------------------------------------

class TestFocusedCrawlerSmoke:
    """End-to-End-Smoke-Tests fuer den FocusedCrawler."""

    def test_crawler_instantiation(self):
        """FocusedCrawler instanziiert sich ohne Exception."""
        crawler = FocusedCrawler(config=_BASE_CONFIG, run_id='inst_test')
        assert crawler is not None

    def test_crawl_returns_correct_types(self):
        results, report = _run_crawl({'/': _RELEVANT_PAGE})
        assert isinstance(results, list)
        assert isinstance(report, EvaluationReport)

    def test_relevant_page_classified(self):
        """Relevante Seite (Glasfaser, Breitband) bekommt score > 0."""
        results, _ = _run_crawl({'/': _RELEVANT_PAGE})
        assert len(results) >= 1
        assert max(r.relevance.score for r in results) > 0

    def test_evaluation_report_total_crawled(self):
        """EvaluationReport zaehlt mind. 1 gecrawlte Seite (total_crawled)."""
        _, report = _run_crawl({'/': _RELEVANT_PAGE})
        assert report.total_crawled >= 1

    def test_privacy_pii_filter_removes_email(self):
        """E-Mail-Adressen werden aus dem gespeicherten Text entfernt."""
        results, _ = _run_crawl({'/': _PII_PAGE})
        assert len(results) >= 1
        for r in results:
            assert 'max.mustermann@gemeinde.de' not in r.text

    def test_privacy_pii_filter_placeholder_present(self):
        """Nach PII-Filterung steht [E-MAIL ENTFERNT] im Text."""
        results, _ = _run_crawl({'/': _PII_PAGE})
        all_text = ' '.join(r.text for r in results)
        assert '[E-MAIL ENTFERNT]' in all_text

    def test_irrelevant_page_low_score(self):
        """Generische Seite bekommt niedrigen Relevanzwert."""
        results, _ = _run_crawl({'/': _IRRELEVANT_PAGE})
        if results:
            assert results[0].relevance.score < 0.5

    def test_crawl_result_has_url(self):
        """Jedes CrawlResult hat eine nicht-leere URL."""
        results, _ = _run_crawl({'/': _RELEVANT_PAGE})
        for r in results:
            assert r.url

    def test_crawl_result_has_content_hash(self):
        """Jedes CrawlResult hat einen SHA-256-Hash (64 Zeichen)."""
        results, _ = _run_crawl({'/': _RELEVANT_PAGE})
        for r in results:
            assert len(r.content_hash) == 64


# ---------------------------------------------------------------------------
# TestComponentSmoke
# ---------------------------------------------------------------------------

class TestComponentSmoke:
    """Offline-Smoke-Tests fuer Einzelkomponenten."""

    def test_domain_model_scores_keywords(self):
        score, kws = DomainModel().score_text(
            'Der Bebauungsplan und die Sanierung der Strase wurden beschlossen'
        )
        assert score > 0
        assert kws

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
