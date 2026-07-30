"""
tests/test_relevance_classifier.py
===================================
Unit-Tests für RelevanceClassifier (BCW + TF-IDF Ensemble).

Alle Tests laufen offline.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from Alt.focused_crawler.domain_model import DomainModel
from Alt.focused_crawler import RelevanceClassifier, RelevanceResult


@pytest.fixture
def classifier():
    return RelevanceClassifier(
        domain_model=DomainModel(),
        relevance_threshold=0.15,
    )


@pytest.fixture
def strict_classifier():
    """Strenger Klassifikator mit hohem Schwellwert."""
    return RelevanceClassifier(
        domain_model=DomainModel(),
        relevance_threshold=0.50,
    )


@pytest.mark.unit
class TestRelevanceClassifier:

    # ------------------------------------------------------------------
    # Rückgabetyp
    # ------------------------------------------------------------------

    def test_classify_returns_relevance_result(self, classifier):
        result = classifier.classify("Ausschreibung Straßenbau")
        assert isinstance(result, RelevanceResult)

    def test_result_has_all_fields(self, classifier):
        r = classifier.classify("Ausschreibung")
        assert hasattr(r, "score")
        assert hasattr(r, "tfidf_score")
        assert hasattr(r, "bayes_score")
        assert hasattr(r, "is_relevant")
        assert hasattr(r, "top_category")
        assert hasattr(r, "confidence")
        assert hasattr(r, "matched_keywords")
        assert hasattr(r, "url")

    # ------------------------------------------------------------------
    # Score-Grenzen
    # ------------------------------------------------------------------

    def test_score_bounded(self, classifier):
        for text in ["", "a", "Ausschreibung " * 50]:
            r = classifier.classify(text)
            assert 0.0 <= r.score <= 1.0
            assert 0.0 <= r.tfidf_score <= 1.0
            assert 0.0 <= r.bayes_score <= 1.0

    def test_empty_text_not_relevant(self, classifier):
        r = classifier.classify("")
        assert not r.is_relevant

    # ------------------------------------------------------------------
    # Relevanzentscheidung
    # ------------------------------------------------------------------

    def test_relevant_krs_text(self, classifier):
        text = (
            "Öffentliche Ausschreibung: Erneuerung der Kanalisation. "
            "Vergabe nach VOB/A. Bieter reichen Angebote ein. "
            "Baubeginn Q3. Brückenneubau Hauptstraße 12."
        )
        r = classifier.classify(text)
        assert r.is_relevant, f"KRS-Text wurde als nicht relevant klassifiziert. Score={r.score:.4f}"

    def test_irrelevant_text(self, classifier):
        text = "Willkommen auf unserer Seite! Heute ist schönes Wetter."
        r = classifier.classify(text)
        assert not r.is_relevant, f"Irrelevanter Text als relevant klassifiziert. Score={r.score:.4f}"

    def test_strict_threshold_rejects_marginal(self, strict_classifier):
        """Ein leicht relevanter Text soll beim Schwellwert 0.50 abgelehnt werden."""
        text = "Baustelle gesperrt"
        r = strict_classifier.classify(text)
        assert not r.is_relevant

    # ------------------------------------------------------------------
    # Ensemble-Gewichtung
    # ------------------------------------------------------------------

    def test_ensemble_formula(self, classifier):
        """Score muss 0.4*TF-IDF + 0.6*BCW entsprechen (±0.001 Toleranz)."""
        r = classifier.classify("Ausschreibung Sanierung Vergabe")
        expected = 0.4 * r.tfidf_score + 0.6 * r.bayes_score
        assert abs(r.score - expected) < 0.001, (
            f"Ensemble-Formel verletzt: {r.score:.4f} != 0.4*{r.tfidf_score:.4f} + 0.6*{r.bayes_score:.4f}"
        )

    # ------------------------------------------------------------------
    # Keywords
    # ------------------------------------------------------------------

    def test_matched_keywords_non_empty_for_relevant(self, classifier):
        text = "Ausschreibung Sanierung Vergabe Straßenbau"
        r = classifier.classify(text)
        if r.is_relevant:
            assert len(r.matched_keywords) > 0

    def test_matched_keywords_list_type(self, classifier):
        r = classifier.classify("Ausschreibung")
        assert isinstance(r.matched_keywords, list)

    # ------------------------------------------------------------------
    # URL-Bonus
    # ------------------------------------------------------------------

    def test_pdf_url_gets_bonus(self, classifier):
        text = "Bekanntmachung Vergabe"
        r_normal = classifier.classify(text, url="https://muster.de/seite")
        r_pdf    = classifier.classify(text, url="https://muster.de/ausschreibung.pdf")
        assert r_pdf.score >= r_normal.score, "PDF-URL-Bonus nicht angewendet"

    # ------------------------------------------------------------------
    # Determinismus
    # ------------------------------------------------------------------

    def test_classify_deterministic(self, classifier):
        text = "Straßenbau Vergabe öffentlich"
        r1 = classifier.classify(text)
        r2 = classifier.classify(text)
        assert r1.score == r2.score, "Klassifikator ist nicht deterministisch"
        assert r1.top_category == r2.top_category
