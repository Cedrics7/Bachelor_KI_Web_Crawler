"""
relevance_classifier.py
=======================
Relevanzklassifikation fuer den Focused Crawler.

Implementiert einen Ensemble-Klassifikator aus:
    1. TF-IDF-Kosinus-Score gegen DomainModel (40% Gewichtung)
    2. Bayesscher Naive-Bayes-Klassifikator mit Kategorie-Gewichtung (BCW, 60% Gewichtung)

Angelehnt an Liu et al. (2025): Focused Crawling mit Comprehensive Priority Evaluation.

Verwendung:
    classifier = RelevanceClassifier()
    result = classifier.classify(text="Der neue Bebauungsplan wurde veroffentlicht", url="https://...")
    print(f"Score: {result.score}, Relevant: {result.is_relevant}, Kategorie: {result.top_category}")
"""

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from .domain_model import DomainModel


@dataclass
class RelevanceResult:
    """
    Ergebnis einer Relevanzklassifikation.

    Attribute:
        url: URL der klassifizierten Seite
        text: Text der Seite (gekuerzt)
        score: Gesamtscore ∈ [0.0, 1.0]
        tfidf_score: TF-IDF-Kosinus-Score (40% Gewichtung)
        bayes_score: Bayes-Score (BCW, 60% Gewichtung)
        is_relevant: True wenn score >= relevance_threshold
        top_category: Kategorie mit hoechstem Score
        confidence: Confidence ∈ [0.0, 1.0]
        matched_keywords: Liste der gefundenen Keywords
    """
    url: str
    text: str
    score: float
    tfidf_score: float
    bayes_score: float
    is_relevant: bool
    top_category: str
    confidence: float
    matched_keywords: List[str]


class RelevanceClassifier:
    """
    Ensemble-Klassifikator fuer Relevanzbewertung.

    Verwendung:
        classifier = RelevanceClassifier(domain_model=DomainModel(), relevance_threshold=0.15)
        result = classifier.classify(text="...", url="https://...")
    """

    def __init__(
        self,
        domain_model: Optional[DomainModel] = None,
        relevance_threshold: float = 0.15,
    ):
        """
        Args:
            domain_model: DomainModel fuer Keyword-Matching
            relevance_threshold: Ab wann gilt eine Seite als relevant?
        """
        self._model = domain_model or DomainModel()
        self._threshold = relevance_threshold

    def classify(self, text: str, url: str = "") -> RelevanceResult:
        """
        Klassifiziert einen Text auf Relevanz.

        Args:
            text: Zu klassifizierender Text
            url: URL der Seite (fuer Logging)

        Returns:
            RelevanceResult mit Score, Kategorie, Keywords, etc.
        """
        tfidf_score, matched = self._model.score_text(text)

        category_scores: Dict[str, float] = {}
        for category in self._model.get_categories():
            cat_keywords = self._model.get_keywords(category)
            cat_count = sum(1 for kw in cat_keywords if kw.lower() in text.lower())
            category_scores[category] = cat_count / max(1, len(cat_keywords))

        top_category = max(category_scores, key=category_scores.get) if category_scores else ""
        bayes_score = category_scores.get(top_category, 0.0)

        combined_score = (tfidf_score * 0.4) + (bayes_score * 0.6)

        is_relevant = combined_score >= self._threshold

        confidence = min(1.0, (combined_score / self._threshold) * 0.5) if self._threshold > 0 else 0.0

        return RelevanceResult(
            url=url,
            text=text[:500],
            score=round(combined_score, 4),
            tfidf_score=round(tfidf_score, 4),
            bayes_score=round(bayes_score, 4),
            is_relevant=is_relevant,
            top_category=top_category,
            confidence=round(confidence, 4),
            matched_keywords=matched,
        )

    def set_threshold(self, threshold: float) -> None:
        """Setzt den Relevanz-Threshold neu."""
        self._threshold = threshold
