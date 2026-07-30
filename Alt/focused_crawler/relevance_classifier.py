"""
relevance_classifier.py
=======================
Relevanzberechnung und Klassifikator für den Focused Crawler.

Implementiert zwei Bewertungsebenen:

1. TF-IDF/Kosinus-Score (schnell, ohne externe Abhängigkeiten)
   Entspricht dem IDF-basierten Ansatz von Hernandez et al. (2020) / DomainModel.

2. Bayesscher Naiver Klassifikator mit Kategorie-Gewichtung (BCW)
   Angelehnt an Liu et al. (2025): "Biased Category Weighted Naive Bayes"
   Jede Seite erhält eine Zielkategorie + Relevanz-Score ∈ [0.0, 1.0].
   Ein konfigurierbarer Schwellwert (relevance_threshold) entscheidet,
   ob eine Seite als relevant gilt.

3. Kombinierter Score (Ensemble)
   Kombiniert TF-IDF-Kosinus und BCW zu einem Gesamtscore.
   Dieser Score bestimmt die Relevanz einer Seite.

Wissenschaftliche Basis:
    Liu, J., Wu, Y., Liu, Z. (2025): BCW – Biased Category Weighted Naive Bayes
    Hernandez, J. et al. (2020): IDF-gewichtetes KRS-Domänenmodell
    Joe Dhanith, P.R. et al. (2024): Relevance Computation Module
"""

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .domain_model import DomainModel


@dataclass
class RelevanceResult:
    """
    Ergebnis der Relevanzbewertung einer Seite.

    Attribute:
        url:                URL der Seite
        score:              Gesamtscore ∈ [0.0, 1.0]
        tfidf_score:        TF-IDF/Kosinus-Score
        bayes_score:        BCW-Score
        is_relevant:        True wenn score >= relevance_threshold
        top_category:       Beste Zielkategorie (z.B. "Neubau")
        matched_categories: Alle Kategorien mit Score > 0
        matched_keywords:   Treffer-Keywords aus der Domäne
        confidence:         Konfidenz der Klassifikation ∈ [0.0, 1.0]
    """
    url: str
    score: float
    tfidf_score: float
    bayes_score: float
    is_relevant: bool
    top_category: str
    matched_categories: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "score": self.score,
            "tfidf_score": self.tfidf_score,
            "bayes_score": self.bayes_score,
            "is_relevant": self.is_relevant,
            "top_category": self.top_category,
            "matched_categories": self.matched_categories,
            "matched_keywords": self.matched_keywords,
            "confidence": self.confidence,
        }


class RelevanceClassifier:
    """
    Zweistufiger Relevanzklassifikator für kommunale Webseiten.

    Stufe 1: TF-IDF/Kosinus-Ähnlichkeit mit dem DomainModel (schnell)
    Stufe 2: BCW – Biased Category Weighted Naive Bayes (genauer)

    Verwendung:
        clf = RelevanceClassifier(relevance_threshold=0.15)
        result = clf.classify(url="https://...", text="Bebauungsplan...")
        print(result.score, result.top_category, result.is_relevant)
    """

    def __init__(
        self,
        domain_model: Optional[DomainModel] = None,
        relevance_threshold: float = 0.15,
        tfidf_weight: float = 0.4,
        bayes_weight: float = 0.6,
    ) -> None:
        """
        Args:
            domain_model:         DomainModel-Instanz (wird neu erstellt wenn None)
            relevance_threshold:  Mindest-Score für "relevant" ∈ [0.0, 1.0]
            tfidf_weight:         Gewicht des TF-IDF-Scores im Ensemble
            bayes_weight:         Gewicht des BCW-Scores im Ensemble
        """
        self._model = domain_model or DomainModel()
        self._threshold = relevance_threshold
        self._w_tfidf = tfidf_weight
        self._w_bayes = bayes_weight

        # BCW: Trainingskorpus (wird durch .train() befüllt oder mit Seed initialisiert)
        self._bcw_class_priors: Dict[str, float] = {}
        self._bcw_term_probs: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._bcw_trained = False

        # Seed-Training: Domänen-Keywords als Trainingsbeispiele
        self._seed_train()

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def classify(self, text: str, url: str = "") -> RelevanceResult:
        """
        Klassifiziert eine Seite und gibt einen RelevanceResult zurück.

        Der Score ist ein Ensemble aus TF-IDF/Kosinus (40%) und BCW (60%).
        Entspricht dem "Relevance Computation Module" von Joe Dhanith et al. (2024).
        """
        # Stufe 1: TF-IDF/Kosinus
        tfidf_score, matched_cats = self._model.score_text(text)

        # Stufe 2: BCW-Klassifikation
        bayes_score, top_cat, confidence = self._bcw_classify(text)

        # Ensemble-Score
        ensemble_score = round(
            self._w_tfidf * tfidf_score + self._w_bayes * bayes_score, 4
        )

        # Alle relevanten Keyword-Treffer extrahieren
        matched_kw = self._find_matched_keywords(text)

        return RelevanceResult(
            url=url,
            score=ensemble_score,
            tfidf_score=round(tfidf_score, 4),
            bayes_score=round(bayes_score, 4),
            is_relevant=ensemble_score >= self._threshold,
            top_category=top_cat,
            matched_categories=matched_cats,
            matched_keywords=matched_kw[:20],  # max. 20 für Übersichtlichkeit
            confidence=round(confidence, 4),
        )

    def train(self, texts: List[Tuple[str, str]]) -> None:
        """
        Trainiert den BCW-Klassifikator auf einem beschrifteten Korpus.

        Args:
            texts: Liste von (text, category)-Paaren.
                   Kategoriename muss in DomainModel.get_categories() vorhanden sein.

        Beispiel:
            clf.train([
                ("Neuer Bebauungsplan für Wohngebiet", "Neubau"),
                ("Brückensanierung Hauptstraße", "Brückenbau"),
            ])
        """
        class_counts: Counter = Counter()
        term_counts: Dict[str, Counter] = defaultdict(Counter)
        vocab: set = set()

        for text, cat in texts:
            tokens = self._tokenize(text)
            class_counts[cat] += 1
            term_counts[cat].update(tokens)
            vocab.update(tokens)

        total_docs = sum(class_counts.values())
        vocab_size = len(vocab)

        # Klassenwahrscheinlichkeiten P(c)
        self._bcw_class_priors = {
            cat: count / total_docs for cat, count in class_counts.items()
        }

        # P(t|c) mit Laplace-Glättung
        self._bcw_term_probs = {}
        for cat, tc in term_counts.items():
            total_terms = sum(tc.values()) + vocab_size
            self._bcw_term_probs[cat] = {
                term: (tc[term] + 1) / total_terms for term in vocab
            }
        self._bcw_trained = True

    # ------------------------------------------------------------------
    # Interne Methoden
    # ------------------------------------------------------------------

    def _seed_train(self) -> None:
        """
        Seed-Training: Erstellt Trainingsbeispiele aus den Domänen-Keywords.
        Jedes Keyword wird als ein-Wort-Dokument seiner Kategorie behandelt.
        Dadurch ist der BCW sofort ohne externen Trainingskorpus einsatzbereit.
        """
        from .domain_model import DOMAIN_KEYWORDS
        training_data: List[Tuple[str, str]] = []
        for cat, keywords in DOMAIN_KEYWORDS.items():
            for kw in keywords:
                # Mehrfach hinzufügen für bessere Prior-Schätzung
                training_data.extend([(kw, cat)] * 3)
            # Auch Phrasen als einzelne Trainingsdokumente
            training_data.append((" ".join(keywords), cat))
        self.train(training_data)

    def _bcw_classify(self, text: str) -> Tuple[float, str, float]:
        """
        BCW-Klassifikation nach Liu et al. (2025).
        Gibt (score, top_category, confidence) zurück.
        Score ∈ [0.0, 1.0] ist die normalisierte Wahrscheinlichkeit der Top-Klasse.
        """
        if not self._bcw_trained or not self._bcw_class_priors:
            return 0.0, "Unbekannt", 0.0

        tokens = self._tokenize(text)
        if not tokens:
            return 0.0, "Unbekannt", 0.0

        log_probs: Dict[str, float] = {}
        for cat, prior in self._bcw_class_priors.items():
            log_prob = math.log(prior + 1e-10)
            term_probs = self._bcw_term_probs.get(cat, {})
            for token in tokens:
                tp = term_probs.get(token, 1e-6)
                log_prob += math.log(tp)
            log_probs[cat] = log_prob

        # Softmax-ähnliche Normalisierung für Score ∈ [0, 1]
        max_log = max(log_probs.values())
        exp_probs = {cat: math.exp(lp - max_log) for cat, lp in log_probs.items()}
        total = sum(exp_probs.values())
        norm_probs = {cat: p / total for cat, p in exp_probs.items()}

        top_cat = max(norm_probs, key=norm_probs.get)
        top_score = norm_probs[top_cat]

        # Zweithöchste Wahrscheinlichkeit für Konfidenzberechnung
        sorted_probs = sorted(norm_probs.values(), reverse=True)
        confidence = (sorted_probs[0] - sorted_probs[1]) if len(sorted_probs) > 1 else sorted_probs[0]

        return round(top_score, 4), top_cat, round(confidence, 4)

    def _find_matched_keywords(self, text: str) -> List[str]:
        """Findet alle Domänen-Keywords, die im Text vorkommen."""
        text_lower = text.lower()
        found = []
        for term in self._model.get_all_keywords():
            if term in text_lower:
                found.append(term)
        return sorted(set(found))

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        return re.findall(r'[a-züöäß][a-züöäß\-]{2,}', text.lower())
