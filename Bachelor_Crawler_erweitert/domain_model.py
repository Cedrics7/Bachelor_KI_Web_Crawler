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

Normalisierung (Umlaute, Plural, URL-Encoding) erfolgt zentral ueber
text_utils.normalize_text() / text_utils.build_keyword_pattern(), damit
Keywords und Text IMMER konsistent abgeglichen werden.
"""

import re
from typing import Dict, List, Tuple
from .text_utils import normalize_text, build_keyword_pattern


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

    DEFAULT_KEYWORDS = {
        "bauen": [
            "bebauungsplan", "bebauungsplaene", "flaechennutzungsplan", "flaechennutzungsplaene",
            "bauleitplanung", "baugenehmigung", "bauvorhaben", "neubau", "sanierung",
            "sanierungsgebiet", "stadtumbaugebiet", "stadtentwicklung", "dorfentwicklung", "entwicklung",
            "planungsbeteiligung", "buergerbeteiligung", "oeffentlichkeitsbeteiligung", "oeffentliche-auslegung",
            "planfeststellung", "satzungsbeschluss",
        ],
        "verwaltung": [
            "amtliche-bekanntmachung", "oeffentliche-bekanntmachung",
            "ausschreibung", "vergabe", "vergabeverfahren",
            "gemeinderatsbeschluss", "satzung", "verordnung",
            "amtsblatt", "bekanntmachungsblatt",
        ],
        "wirtschaft": [
            "gewerbegebiet", "gewerbeflaeche", "wirtschaftsfoerderung",
            "foerderprogramm", "foerderbescheid", "investitionsprogramm",
            "breitbandausbau", "glasfaserausbau",
        ],
        "infrastruktur": [
            "radverkehrskonzept", "verkehrskonzept", "mobilitaetskonzept",
            "nahverkehrsplan", "strassenausbau", "radwegebau", "radweg",
        ],
        "aktuelles": [
            "pressemitteilung", "bekanntmachung", "mitteilung",
            "neuigkeit", "meldung", "ankuendigung", "allgemein"
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

        # Vorkompilierte, normalisierte Regex-Patterns pro Keyword (Umlaute,
        # Plural-Endungen und Bindestrich/Leerzeichen-Varianten werden dabei
        # automatisch beruecksichtigt, siehe text_utils.build_keyword_pattern).
        self._patterns: Dict[str, List[Tuple[str, re.Pattern]]] = {}
        for category, kw_list in self._keywords.items():
            self._patterns[category] = [(kw, build_keyword_pattern(kw)) for kw in kw_list]

    def score_text(self, text: str) -> Tuple[float, List[str]]:
        """
        Berechnet TF-IDF- und Bayes-Score (BCW) fuer einen Text.

        Args:
            text: Zu bewertender Text

        Returns:
            Tuple (score, matched_keywords):
                - score: Gesamtscore in [0.0, 1.0]
                - matched_keywords: Liste der gefundenen Keywords
        """
        text_norm = normalize_text(text)
        matched = []

        for category, patterns in self._patterns.items():
            for kw, pattern in patterns:
                if pattern.search(text_norm):
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

    def get_patterns(self, category: str) -> List[Tuple[str, re.Pattern]]:
        """Gibt die vorkompilierten (Keyword, Pattern)-Paare einer Kategorie zurueck."""
        return self._patterns.get(category, [])
