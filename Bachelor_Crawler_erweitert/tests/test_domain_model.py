"""
tests/test_domain_model.py
==========================
Unit-Tests für DomainModel (KRS-Domänenmodell, TF-IDF-Gewichtung).

Alle Tests laufen offline – kein Netzwerk nötig.

Fix v1.1:
  - Kategorienamen sind lowercase (z.B. 'Ausschreibung', nicht 'AUSSCHREIBUNG')
  - score_text() gibt (float, List[str]) zurück, nicht (float, str)
  - get_keywords() → _keywords[cat] (kein öffentliches get_keywords)
  - get_domain_vector() → get_all_keywords()
  - cosine_similarity_to_domain() → score_text()[0]
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))
from Alt.focused_crawler.domain_model import DomainModel


@pytest.mark.unit
class TestDomainModel:

    def setup_method(self):
        self.model = DomainModel()

    # ------------------------------------------------------------------
    # Grundstruktur
    # ------------------------------------------------------------------

    def test_has_seven_categories(self):
        """Das KRS-Domänenmodell muss genau 7 Kategorien enthalten."""
        cats = self.model.get_categories()
        assert len(cats) == 7, f"Erwartet 7, erhalten: {len(cats)}"

    def test_expected_categories_present(self):
        """Kategorien heißen 'Ausschreibung' (nicht 'AUSSCHREIBUNG')."""
        cats = self.model.get_categories()
        for expected in ["Ausschreibung", "Neubau", "Sanierung", "Bekanntmachung"]:
            assert expected in cats, f"Kategorie '{expected}' fehlt in {cats}"

    def test_all_categories_have_keywords(self):
        """Jede Kategorie muss mindestens 3 Keywords besitzen."""
        for cat in self.model.get_categories():
            # _keywords ist das interne Dict {cat: [kw, ...]}
            kws = self.model._keywords[cat]
            assert len(kws) >= 3, f"{cat} hat zu wenige Keywords: {kws}"

    # ------------------------------------------------------------------
    # score_text
    # ------------------------------------------------------------------

    def test_score_relevant_text_high(self):
        """Typischer KRS-Text muss Score > 0.1 erhalten."""
        text = (
            "Öffentliche Ausschreibung für Straßensanierung. "
            "Vergabe nach VOB/A. Angebotsfrist 30 Tage. "
            "Baumaßnahme Brückenneubau Hauptstraße."
        )
        score, matched_cats = self.model.score_text(text)
        assert score > 0.1, f"Score zu niedrig: {score}"
        # matched_cats ist eine Liste von Kategorienamen
        assert isinstance(matched_cats, list)
        assert len(matched_cats) >= 1, "Mindestens eine Kategorie muss matchen"

    def test_score_irrelevant_text_low(self):
        """Vollständig irrelevanter Text muss Score <= 0.05 erhalten."""
        text = "Herzlich willkommen auf unserer Webseite. Kontakt: info@beispiel.de"
        score, _ = self.model.score_text(text)
        assert score <= 0.05, f"Score zu hoch für irrelevanten Text: {score}"

    def test_score_returns_tuple(self):
        """score_text() gibt (float, list) zurück."""
        score, cats = self.model.score_text("Sanierungsmaßnahme")
        assert isinstance(score, float)
        assert isinstance(cats, list)  # Liste, nicht str!

    def test_score_bounded_zero_to_one(self):
        """Score muss immer in [0.0, 1.0] liegen."""
        texts = [
            "",
            "a",
            "Ausschreibung " * 100,
            "xyz abc def ghi jkl",
        ]
        for t in texts:
            score, _ = self.model.score_text(t)
            assert 0.0 <= score <= 1.0, f"Score außerhalb [0,1]: {score}"

    def test_empty_text_returns_zero(self):
        score, _ = self.model.score_text("")
        assert score == 0.0

    def test_ausschreibung_text_matches_category(self):
        """KRS-typischer Ausschreibungstext muss 'Ausschreibung' in matched_cats enthalten."""
        text = "Öffentliche Ausschreibung VOB Vergabe Bauleistung Angebot einreichen"
        score, matched_cats = self.model.score_text(text)
        assert "Ausschreibung" in matched_cats, (
            f"'Ausschreibung' nicht in matched_cats: {matched_cats}"
        )

    # ------------------------------------------------------------------
    # Vektoroperationen
    # ------------------------------------------------------------------

    def test_get_all_keywords_not_empty(self):
        """get_all_keywords() gibt eine nicht-leere Liste zurück."""
        kws = self.model.get_all_keywords()
        assert len(kws) > 0

    def test_score_higher_for_relevant_than_irrelevant(self):
        """Relevanter Text muss höheren Score haben als irrelevanter."""
        relevant   = "Ausschreibung Straßenbau Vergabe VOB Sanierung Brücke"
        irrelevant = "Wetter heute sonnig Urlaub Rezept kochen"
        score_rel, _ = self.model.score_text(relevant)
        score_irr, _ = self.model.score_text(irrelevant)
        assert score_rel > score_irr, (
            f"Relevanter Text hat kleineren Score: {score_rel} < {score_irr}"
        )

    def test_score_deterministic(self):
        """score_text() muss deterministisch sein."""
        text = "Straßenbau Sanierung Ausschreibung"
        score1, cats1 = self.model.score_text(text)
        score2, cats2 = self.model.score_text(text)
        assert score1 == score2
        assert cats1 == cats2
