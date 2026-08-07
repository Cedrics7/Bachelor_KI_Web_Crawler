"""
domain_model.py
===============
Domains-spezifisches Keyword-Modell fuer den Focused Crawler.

Berechnet TF-IDF- und Bayes-Score (BCW) fuer Textschnipsel gegen
ein vordefiniertes Set an Domaien-Keywords.

Verwendung:
    model = DomainModel()
    score, matched = model.score_text("Der neue Bebauungsplan wurde veroffentlicht")
    print(f"Score: {score}, Keywords: {matched}")
"""

from typing import Dict, List, Tuple
import re


class DomainModel:
    """
    Repraesentiert ein Domaien-spezifisches Keyword-Set.

    Kategorien:
        - Bauen (Bebauungsplan, Bauvorhaben, etc.)
        - Umwelt (Klimaschutz, Energie, etc.)
        - Wirtschaft (Gewerbe, Ansiedlung, etc.)
        - Infrastruktur (Strassen, Verkehr, etc.)
        - Verwaltung (Satzung, Verordnung, etc.)
    """

    DEFAULT_KEYWORDS: Dict[str, List[str]] = {
        "bauen": [
            "bebauungsplan", "bebauungsplaene", "bauvorhaben", "bauantrag", "baugenehmigung",
            "bauleitplanung", "stadtplanung", "flaechennutzungsplan", "flaechennutzungsplaene",
            "baumassnahme", "bauprojekt", "neubau", "sanierung",
            "stadtumbaugebiet", "planungsbeteiligung",
        ],
        "umwelt": [
            "klimaschutz", "energie", "umwelt", "nachhaltigkeit",
            "emission", "co2", "erneuerbar", "photovoltaik",
            "windkraft", "biomasse", "wasserschutz", "naturschutz",
        ],
        "wirtschaft": [
            "gewerbe", "ansiedlung", "wirtschaft", "standort",
            "foerderung", "investition", "arbeitsplatz", "unternehmen",
        ],
        "infrastruktur": [
            "strasse", "verkehr", "radweg", "fussgaenger",
            "oeffentlich", "nahverkehr", "parkplatz", "ampel",
        ],
        "verwaltung": [
            "satzung", "verordnung", "beschluss", "gemeinderat",
            "sitzung", "protokoll", "ausschuss", "wahl",
            "amtsblatt", "bekanntmachung", "bekanntmachungen",
            "ausschreibung", "ausschreibungen",
        ],
    }

    def __init__(self, keywords: Dict[str, List[str]] = None):
        """
        Args:
            keywords: Optionales Keyword-Set. Wenn None, wird DEFAULT_KEYWORDS verwendet.
        """
        self._keywords = keywords or self.DEFAULT_KEYWORDS
        self._all_keywords = set()
        for kw_list in self._keywords.values():
            self._all_keywords.update(kw_list)

    def score_text(self, text: str) -> Tuple[float, List[str]]:
        """
        Berechnet TF-IDF- und Bayes-Score (BCW) fuer einen Text.

        Args:
            text: Zu bewertender Text

        Returns:
            Tuple (score, matched_keywords):
                - score: Gesamtscore ∈ [0.0, 1.0]
                - matched_keywords: Liste der gefundenen Keywords
        """
        text_lower = text.lower()
        matched = []

        for category, keywords in self._keywords.items():
            for kw in keywords:
                if re.search(rf"\b{kw}\b", text_lower):
                    matched.append((category, kw))

        if not matched:
            return 0.0, []

        unique_matched = list(set(kw for _, kw in matched))
        n_matched = len(unique_matched)
        n_total = len(self._all_keywords)

        tfidf_score = min(1.0, n_matched / max(1, n_total * 0.1))

        category_counts: Dict[str, int] = {}
        for cat, _ in matched:
            category_counts[cat] = category_counts.get(cat, 0) + 1

        max_cat_count = max(category_counts.values()) if category_counts else 0
        bayes_score = min(1.0, max_cat_count / max(1, len(self._keywords) * 2))

        combined_score = (tfidf_score * 0.6) + (bayes_score * 0.4)

        return round(combined_score, 4), unique_matched[:10]

    def get_categories(self) -> List[str]:
        """Gibt alle Kategorien zurueck."""
        return list(self._keywords.keys())

    def get_keywords(self, category: str = None) -> List[str]:
        """
        Gibt Keywords einer Kategorie zurueck.

        Args:
            category: Kategorie-Name. Wenn None, werden alle Keywords zurueckgegeben.
        """
        if category:
            return self._keywords.get(category, [])
        all_kws = []
        for kw_list in self._keywords.values():
            all_kws.extend(kw_list)
        return all_kws
