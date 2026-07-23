"""
tests/test_focused_crawler_unit.py
====================================
Unit-Tests für FocusedCrawler (ohne echte HTTP-Requests).

Verwendet httpx.MockTransport zum Simulieren von HTTP-Antworten.
"""

import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from focused_crawler.focused_crawler import FocusedCrawler, DEFAULT_CONFIG
from focused_crawler.crawler_logger import CrawlerLogger


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

RELEVANT_HTML = """
<html><body>
  <h1>Öffentliche Ausschreibung – Straßensanierung</h1>
  <p>Vergabe nach VOB/A. Baubeginn 2025. Angebote bis 15.08.</p>
  <a href="/ausschreibung2">Vergabe Neubau</a>
  <a href="/impressum">Impressum</a>
</body></html>
"""

IRRELEVANT_HTML = """
<html><body>
  <h1>Willkommen auf unserer Webseite</h1>
  <p>Heute ist schönes Wetter. Kontaktieren Sie uns!</p>
  <a href="/impressum">Impressum</a>
</body></html>
"""

PII_HTML = """
<html><body>
  <p>Kontakt: max@beispiel.de, Tel: 0151 12345678</p>
  <p>IBAN: DE89 3704 0044 0532 0130 00</p>
</body></html>
"""


def make_html_response(html: str, url: str = "https://muster.de/") -> httpx.Response:
    return httpx.Response(
        status_code=200,
        content=html.encode("utf-8"),
        headers={"content-type": "text/html; charset=utf-8"},
        request=httpx.Request("GET", url),
    )


@pytest.fixture
def crawler(tmp_path):
    """FocusedCrawler mit deaktiviertem robots.txt und Logging in tmp_path."""
    return FocusedCrawler(config={
        **DEFAULT_CONFIG,
        "robots_respect":  False,
        "max_pages":       5,
        "crawl_delay_default": 0.0,
        "log_dir":         str(tmp_path),
        "log_console_level": "ERROR",
    })


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.unit
class TestFocusedCrawlerUnit:

    # ------------------------------------------------------------------
    # PII-Filter
    # ------------------------------------------------------------------

    def test_pii_filter_removes_email(self, crawler):
        text, counts = crawler._filter_pii_with_counts(
            "Kontakt: max@beispiel.de und info@test.org"
        )
        assert "@" not in text
        assert counts["email"] == 2

    def test_pii_filter_removes_phone(self, crawler):
        text, counts = crawler._filter_pii_with_counts("Tel: 0151 12345678")
        assert counts["phone"] >= 1
        assert "12345678" not in text

    def test_pii_filter_removes_iban(self, crawler):
        text, counts = crawler._filter_pii_with_counts(
            "IBAN: DE89 3704 0044 0532 0130 00"
        )
        assert counts["iban"] == 1
        assert "DE89" not in text

    def test_pii_filter_no_pii_unchanged(self, crawler):
        text = "Keine persönlichen Daten hier."
        result, counts = crawler._filter_pii_with_counts(text)
        assert counts == {"email": 0, "phone": 0, "iban": 0}
        assert result == text

    # ------------------------------------------------------------------
    # Domain-Guard
    # ------------------------------------------------------------------

    def test_strip_www(self, crawler):
        assert crawler._strip_www("www.muster.de") == "muster.de"
        assert crawler._strip_www("muster.de") == "muster.de"
        assert crawler._strip_www("www.sub.muster.de") == "sub.muster.de"

    # ------------------------------------------------------------------
    # HTML-Extraktion
    # ------------------------------------------------------------------

    def test_extract_html_returns_text_blocks_links(self, crawler):
        text, blocks, links = crawler._extract_html(
            html=RELEVANT_HTML,
            base_url="https://muster.de/",
            base_domain="muster.de",
        )
        assert isinstance(text, str)
        assert len(text) > 0
        assert isinstance(blocks, list)
        assert isinstance(links, list)

    def test_extract_html_filters_external_links(self, crawler):
        html = """
        <html><body>
          <a href="https://extern.de/page">Extern</a>
          <a href="/intern">Intern</a>
        </body></html>
        """
        _, _, links = crawler._extract_html(
            html=html,
            base_url="https://muster.de/",
            base_domain="muster.de",
        )
        urls = [l[0] for l in links]
        assert not any("extern.de" in u for u in urls), "Externer Link wurde nicht gefiltert"

    def test_extract_html_removes_script_style(self, crawler):
        html = """
        <html><body>
          <script>alert('xss')</script>
          <style>body{color:red}</style>
          <p>Echter Inhalt</p>
        </body></html>
        """
        text, _, _ = crawler._extract_html(html, "https://muster.de/", "muster.de")
        assert "alert" not in text
        assert "color:red" not in text
        assert "Echter Inhalt" in text

    # ------------------------------------------------------------------
    # Crawl mit Mock-HTTP (kein echtes Netzwerk)
    # ------------------------------------------------------------------

    def test_crawl_with_mock_returns_results(self, tmp_path):
        """Crawl-Loop gibt CrawlResult-Objekte zurück."""
        call_count = {"n": 0}

        def mock_handler(request):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return httpx.Response(
                    200, content=RELEVANT_HTML.encode(),
                    headers={"content-type": "text/html"},
                    request=request,
                )
            return httpx.Response(404, request=request)

        transport = httpx.MockTransport(mock_handler)

        with patch("httpx.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__enter__ = MagicMock(return_value=mock_client)
            mock_client.__exit__ = MagicMock(return_value=False)

            resp = httpx.Response(
                200, content=RELEVANT_HTML.encode(),
                headers={"content-type": "text/html"},
                request=httpx.Request("GET", "https://muster.de/"),
            )
            mock_client.get.return_value = resp
            mock_client_cls.return_value = mock_client

            crawler = FocusedCrawler(config={
                **DEFAULT_CONFIG,
                "robots_respect": False,
                "max_pages": 1,
                "crawl_delay_default": 0.0,
                "log_dir": str(tmp_path),
                "log_console_level": "ERROR",
            })
            results, report = crawler.crawl("https://muster.de/")

        assert isinstance(results, list)
        assert isinstance(report.harvest_rate, float)

    # ------------------------------------------------------------------
    # Konfiguration
    # ------------------------------------------------------------------

    def test_set_relevance_threshold(self, crawler):
        crawler.set_relevance_threshold(0.5)
        assert crawler._config["relevance_threshold"] == 0.5

    def test_get_domain_model(self, crawler):
        dm = crawler.get_domain_model()
        assert dm is not None
        assert len(dm.get_categories()) == 7
