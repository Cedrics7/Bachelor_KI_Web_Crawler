"""
domain_model.py
===============
Leichtgewichtiges Domänenrepräsentationsmodell nach dem KRS-Ansatz
(Knowledge Representation Schema) von Hernandez et al. (2020).

Konzept:
    Anstelle einer vollständigen Ontologie wird ein einfaches Keyword-basiertes
    Domänenmodell verwendet, das Entitäten und deren IDF-Gewichte speichert.
    Dieses Modell wird von RelevanceClassifier und LinkPrioritizer verwendet,
    um Seiten und Links gegen die Zieldomäne zu bewerten.

Wissenschaftliche Basis:
    Hernandez, J., Marin-Castro, H.M., Morales-Sandoval, M. (2020):
    "Knowledge Representation Schema (KRS) as a lightweight alternative
    to full ontologies for focused crawling."
    IDF-Gewichtung: Terme, die selten über alle Dokumente vorkommen,
    erhalten höheres Gewicht (informativer für die Domäne).
"""

import math
import re
from collections import Counter
from typing import Dict, List, Tuple


# ---------------------------------------------------------------------------
# Kommunale Domänendefinition (Zieldomäne der Bachelorthesis)
# Quelle: CONFIG["ziel_kategorien"] aus config_js.py + thesisrelevante Erweiterung
# ---------------------------------------------------------------------------

DOMAIN_KEYWORDS: Dict[str, List[str]] = {
    "Sanierung": [
        "sanierung", "sanierungsgebiet", "stadtsanierung", "fördergebiet",
        "fördermaßnahme", "instandsetzung", "revitalisierung", "erneuerung",
    ],
    "Neubau": [
        "neubau", "neubaugebiet", "bebauungsplan", "b-plan", "bplan",
        "erschließung", "erschliessung", "baugebiet", "wohngebiet",
        "gewerbegebiet", "aufstellungsbeschluss", "satzung",
    ],
    "Privatisierung": [
        "grundstücksverkauf", "veräußerung", "liegenschaften", "entwidmung",
        "eigentumsübertragung", "verkauf", "versteigerung",
    ],
    "Straßenbau": [
        "straßenbau", "straßensanierung", "fahrbahnerneuerung", "kreisverkehr",
        "gehweg", "radweg", "straßenausbau", "fahrbahndecke", "asphaltierung",
        "deckenerneuerung", "verkehrsplanung",
    ],
    "Brückenbau": [
        "brückenbau", "brückensanierung", "brückenneubau", "brückeninstandsetzung",
        "unterführung", "düker", "überführung", "brücke",
    ],
    "Ausschreibung": [
        "ausschreibung", "vergabe", "öffentliche auftragsvergabe", "submission",
        "vob", "dtvp", "bieterverfahren", "bekanntmachung", "ausschreibungstext",
        "leistungsverzeichnis", "los", "zuschlag",
    ],
    "Bekanntmachung": [
        "bekanntmachung", "amtsblatt", "gemeindeblatt", "öffentliche bekanntmachung",
        "amtliche bekanntmachung", "ratsbeschluss", "sitzungsergebnis",
        "bürgerinformation", "öffentlichkeitsbeteiligung",
    ],
}

# Alle Terme flach (für IDF-Berechnung)
_ALL_TERMS: List[str] = [
    term for terms in DOMAIN_KEYWORDS.values() for term in terms
]


class DomainModel:
    """
    KRS-inspiriertes Domänenmodell für kommunale Bau- und Bekanntmachungsdaten.

    Speichert TF-IDF-gewichtete Terme pro Kategorie und ermöglicht
    die Berechnung einer Kosinus-Ähnlichkeit zwischen einem Text und
    der Zieldomäne.

    Verwendung:
        model = DomainModel()
        score, matched_cats = model.score_text("Neuer Bebauungsplan für Wohngebiet")
        # score ∈ [0.0, 1.0], matched_cats = ["Neubau"]
    """

    def __init__(self, custom_keywords: Dict[str, List[str]] = None) -> None:
        self._keywords = custom_keywords if custom_keywords else DOMAIN_KEYWORDS
        # IDF-Gewichte: seltenere Terme erhalten höheres Gewicht
        self._idf: Dict[str, float] = self._compute_idf()
        # Normalisierte Termvektoren pro Kategorie
        self._category_vectors: Dict[str, Dict[str, float]] = self._build_vectors()

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def score_text(self, text: str) -> Tuple[float, List[str]]:
        """
        Bewertet einen Text gegen alle Kategorien der Zieldomäne.

        Returns:
            (relevance_score, matched_categories)
            relevance_score: float ∈ [0.0, 1.0]
                0.0 = kein Bezug zur Zieldomäne
                1.0 = maximale Übereinstimmung
            matched_categories: Liste der Kategorien, in denen der Score > 0
        """
        text_vec = self._text_to_vector(text.lower())
        if not text_vec:
            return 0.0, []

        scores: Dict[str, float] = {}
        for cat, cat_vec in self._category_vectors.items():
            scores[cat] = self._cosine_similarity(text_vec, cat_vec)

        matched = [cat for cat, s in scores.items() if s > 0.0]
        max_score = max(scores.values()) if scores else 0.0
        return round(max_score, 4), matched

    def get_all_keywords(self) -> List[str]:
        """Gibt alle Domänen-Terme als flache Liste zurück."""
        return list(set(_ALL_TERMS))

    def get_categories(self) -> List[str]:
        """Gibt alle Kategorienamen zurück."""
        return list(self._keywords.keys())

    # ------------------------------------------------------------------
    # Interne Berechnungen
    # ------------------------------------------------------------------

    def _compute_idf(self) -> Dict[str, float]:
        """IDF = log(N / df) wobei N = Anzahl Kategorien, df = in wie vielen Kategorien Term vorkommt."""
        N = len(self._keywords)
        df: Counter = Counter()
        for terms in self._keywords.values():
            for term in set(terms):
                df[term] += 1
        return {term: math.log(N / df[term]) for term in df}

    def _build_vectors(self) -> Dict[str, Dict[str, float]]:
        """Erstellt normalisierte TF-IDF-Vektoren pro Kategorie."""
        vectors: Dict[str, Dict[str, float]] = {}
        for cat, terms in self._keywords.items():
            tf: Counter = Counter(terms)
            vec = {term: tf[term] * self._idf.get(term, 1.0) for term in tf}
            vec = self._normalize(vec)
            vectors[cat] = vec
        return vectors

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Einfacher Tokenizer: Lowercase-Wörter, Bindestriche erlaubt."""
        return re.findall(r'[a-züöäß][a-züöäß\-]{2,}', text.lower())

    def _text_to_vector(self, text: str) -> Dict[str, float]:
        """Erstellt einen TF-IDF-Vektor für den gegebenen Text."""
        tokens = self._tokenize(text)
        if not tokens:
            return {}
        tf: Counter = Counter(tokens)
        vec: Dict[str, float] = {}
        # Nur Terme berücksichtigen, die in der Domäne vorkommen
        for term, count in tf.items():
            if term in self._idf:
                vec[term] = (count / len(tokens)) * self._idf[term]
        return self._normalize(vec)

    @staticmethod
    def _normalize(vec: Dict[str, float]) -> Dict[str, float]:
        """L2-Normalisierung des Vektors."""
        norm = math.sqrt(sum(v ** 2 for v in vec.values()))
        if norm == 0:
            return vec
        return {k: v / norm for k, v in vec.items()}

    @staticmethod
    def _cosine_similarity(a: Dict[str, float], b: Dict[str, float]) -> float:
        """Kosinus-Ähnlichkeit zweier vorher L2-normalisierter Vektoren."""
        common = set(a) & set(b)
        return sum(a[k] * b[k] for k in common)
