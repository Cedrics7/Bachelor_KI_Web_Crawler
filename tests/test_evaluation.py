"""
tests/test_evaluation.py
=========================
Unit-Tests für CrawlEvaluator und EvaluationReport.

Alle Tests laufen offline.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from focused_crawler.domain_model import DomainModel
from focused_crawler.relevance_classifier import RelevanceClassifier, RelevanceResult
from focused_crawler.evaluation import CrawlEvaluator, EvaluationReport


def make_result(score: float, threshold: float = 0.15) -> RelevanceResult:
    """Erstellt ein synthetisches RelevanceResult für Tests."""
    clf = RelevanceClassifier(domain_model=DomainModel(), relevance_threshold=threshold)
    r = clf.classify("test")
    # Felder direkt überschreiben für deterministische Tests
    object.__setattr__(r, "score", score) if hasattr(r, "__dataclass_fields__") else None
    # Fallback: manuelles Objekt
    class FakeResult:
        pass
    obj = FakeResult()
    obj.score       = score
    obj.is_relevant = score >= threshold
    obj.tfidf_score = score * 0.5
    obj.bayes_score = score * 0.5
    obj.top_category = "AUSSCHREIBUNG"
    obj.confidence   = 0.8
    obj.matched_keywords = ["ausschreibung"]
    obj.url = "https://muster.de/test"
    return obj


@pytest.mark.unit
class TestCrawlEvaluator:

    def setup_method(self):
        self.ev = CrawlEvaluator(start_url="https://muster.de")

    # ------------------------------------------------------------------
    # Grundfunktionen
    # ------------------------------------------------------------------

    def test_initial_state_zero(self):
        r = self.ev.get_report()
        assert r.total_crawled == 0
        assert r.total_relevant == 0
        assert r.harvest_rate == 0.0

    def test_add_relevant_result(self):
        self.ev.add_result(make_result(0.8))
        r = self.ev.get_report()
        assert r.total_crawled == 1
        assert r.total_relevant == 1

    def test_add_irrelevant_result(self):
        self.ev.add_result(make_result(0.05))
        r = self.ev.get_report()
        assert r.total_crawled == 1
        assert r.total_relevant == 0

    def test_add_robots_blocked(self):
        self.ev.add_robots_blocked()
        r = self.ev.get_report()
        assert r.total_robots_blocked == 1

    # ------------------------------------------------------------------
    # Harvest Rate
    # ------------------------------------------------------------------

    def test_harvest_rate_calculation(self):
        """6 relevant von 10 → HR = 0.6"""
        for i in range(10):
            score = 0.8 if i < 6 else 0.05
            self.ev.add_result(make_result(score))
        r = self.ev.get_report()
        assert abs(r.harvest_rate - 0.6) < 0.001, f"HR: {r.harvest_rate}"

    def test_harvest_rate_all_relevant(self):
        for _ in range(5):
            self.ev.add_result(make_result(0.9))
        assert abs(self.ev.get_report().harvest_rate - 1.0) < 0.001

    def test_harvest_rate_none_relevant(self):
        for _ in range(5):
            self.ev.add_result(make_result(0.01))
        assert self.ev.get_report().harvest_rate == 0.0

    # ------------------------------------------------------------------
    # Irrelevance Ratio
    # ------------------------------------------------------------------

    def test_irrelevance_ratio_complement(self):
        """irrelevance_ratio muss = 1 - harvest_rate sein."""
        for i in range(10):
            self.ev.add_result(make_result(0.8 if i < 4 else 0.02))
        r = self.ev.get_report()
        assert abs(r.irrelevance_ratio - (1.0 - r.harvest_rate)) < 0.001

    # ------------------------------------------------------------------
    # Recall & F1
    # ------------------------------------------------------------------

    def test_recall_with_reference_corpus(self):
        ev = CrawlEvaluator(
            start_url="https://muster.de",
            reference_corpus_size=10,
        )
        for _ in range(4):
            ev.add_result(make_result(0.8))
        r = ev.get_report()
        assert abs(r.recall - 0.4) < 0.001, f"Recall: {r.recall}"

    def test_f1_score_formula(self):
        ev = CrawlEvaluator(
            start_url="https://muster.de",
            reference_corpus_size=10,
        )
        for i in range(10):
            ev.add_result(make_result(0.8 if i < 5 else 0.02))
        r = ev.get_report()
        if r.recall > 0 and r.harvest_rate > 0:
            expected_f1 = 2 * r.harvest_rate * r.recall / (r.harvest_rate + r.recall)
            assert abs(r.f1_score - expected_f1) < 0.001

    # ------------------------------------------------------------------
    # Report-Serialisierung
    # ------------------------------------------------------------------

    def test_report_to_dict(self):
        self.ev.add_result(make_result(0.7))
        d = self.ev.get_report().to_dict()
        assert isinstance(d, dict)
        assert "harvest_rate" in d
        assert "total_crawled" in d
        assert "total_relevant" in d

    def test_report_print_summary_no_crash(self):
        """print_summary() darf nicht crashen."""
        self.ev.add_result(make_result(0.7))
        try:
            self.ev.get_report().print_summary()
        except Exception as e:
            pytest.fail(f"print_summary() crasht: {e}")
