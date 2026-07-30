"""
tests/test_link_prioritizer.py
===============================
Unit-Tests für LinkPrioritizer (CPE-Linkpriorisierung).

Alle Tests laufen offline.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from Alt.focused_crawler.domain_model import DomainModel
from Alt.focused_crawler.link_prioritizer import LinkPrioritizer, ScoredLink


@pytest.fixture
def prioritizer():
    return LinkPrioritizer(
        domain_model=DomainModel(),
        priority_threshold=0.10,
    )


@pytest.mark.unit
class TestLinkPrioritizer:

    # ------------------------------------------------------------------
    # Rückgabetypen
    # ------------------------------------------------------------------

    def test_score_links_returns_list(self, prioritizer):
        links = [("https://muster.de/ausschreibung", "Ausschreibung", "Vergabe")]
        result = prioritizer.score_links(links, page_text="Vergabe Straßenbau")
        assert isinstance(result, list)

    def test_returns_scored_link_objects(self, prioritizer):
        links = [("https://muster.de/ausschreibung", "Ausschreibung", "")]
        result = prioritizer.score_links(links, page_text="")
        assert all(isinstance(sl, ScoredLink) for sl in result)

    def test_empty_input_returns_empty(self, prioritizer):
        result = prioritizer.score_links([], page_text="")
        assert result == []

    # ------------------------------------------------------------------
    # CPE-Score-Grenzen
    # ------------------------------------------------------------------

    def test_cpe_score_bounded(self, prioritizer):
        links = [
            ("https://muster.de/vergabe", "Vergabe Ausschreibung", "Neubau Kanal"),
            ("https://muster.de/impressum", "Impressum", ""),
            ("https://muster.de/ausschreibung.pdf", "PDF", ""),
        ]
        for sl in prioritizer.score_links(links, page_text="Straßenbau"):
            assert 0.0 <= sl.cpe_score <= 1.5, f"CPE-Score außerhalb Erwartung: {sl.cpe_score}"

    # ------------------------------------------------------------------
    # Priorisierung
    # ------------------------------------------------------------------

    def test_relevant_link_higher_than_irrelevant(self, prioritizer):
        links = [
            ("https://muster.de/ausschreibung", "Öffentliche Ausschreibung Vergabe", "Sanierung"),
            ("https://muster.de/impressum", "Impressum", ""),
        ]
        scored = prioritizer.score_links(links, page_text="Straßenbau Vergabe")
        scores = {sl.url: sl.cpe_score for sl in scored}
        assert scores["https://muster.de/ausschreibung"] > scores["https://muster.de/impressum"]

    def test_pdf_link_gets_priority_flag(self, prioritizer):
        links = [("https://muster.de/bekanntmachung.pdf", "Bekanntmachung PDF", "")]
        result = prioritizer.score_links(links, page_text="")
        assert result[0].is_pdf

    def test_priority_flag_set_correctly(self, prioritizer):
        links = [
            ("https://muster.de/ausschreibung", "Ausschreibung Vergabe Straßenbau", "Neubau Sanierung"),
        ]
        result = prioritizer.score_links(links, page_text="Ausschreibung Vergabe")
        # Muss entweder priority oder pdf sein
        sl = result[0]
        if sl.cpe_score >= 0.10:
            assert sl.is_priority or sl.is_pdf

    # ------------------------------------------------------------------
    # Gewichtungsformel
    # ------------------------------------------------------------------

    def test_cpe_formula_weights(self, prioritizer):
        """
        CPE = 0.20*page + 0.40*anchor + 0.25*context + 0.15*url
        Überprüft, ob alle Teilscores vorhanden sind.
        """
        links = [("https://muster.de/vergabe", "Vergabe", "Straßenbau")]
        result = prioritizer.score_links(links, page_text="Vergabe")
        sl = result[0]
        assert hasattr(sl, "anchor_score")
        assert hasattr(sl, "context_score")
        assert hasattr(sl, "url_score")
        assert hasattr(sl, "page_score")

    def test_sorted_by_cpe_descending(self, prioritizer):
        """Ergebnisse müssen nach CPE-Score absteigend sortiert sein."""
        links = [
            ("https://muster.de/impressum", "Impressum", ""),
            ("https://muster.de/ausschreibung", "Ausschreibung Vergabe", "Sanierung"),
            ("https://muster.de/kontakt", "Kontakt", ""),
        ]
        result = prioritizer.score_links(links, page_text="Vergabe")
        scores = [sl.cpe_score for sl in result]
        assert scores == sorted(scores, reverse=True), "Links nicht nach CPE absteigend sortiert"
