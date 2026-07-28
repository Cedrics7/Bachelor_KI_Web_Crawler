"""
link_prioritizer.py
===================
CPE-basierte Link-Priorisierung fuer den Focused Crawler.

Implementiert die "Comprehensive Priority Evaluation" (CPE) nach Liu et al. (2025):

    CPE(link) = w1 * score_page_content
              + w2 * score_anchor_text
              + w3 * score_link_context
              + w4 * score_url_pattern

Jeder der vier Teilscores wird gegen das DomainModel berechnet.
Links mit hoeherem CPE-Score werden priorisiert in die Queue eingereiht.

Wissenschaftliche Basis:
    Liu, J., Wu, Y., Liu, Z. (2025): CPE – Comprehensive Priority Evaluation
"""

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

from .domain_model import DomainModel


@dataclass
class ScoredLink:
    """
    Ein Link mit CPE-Score und Teilscores.

    Attribute:
        url:           Ziel-URL
        cpe_score:     Gesamtscore ∈ [0.0, 1.0] (Comprehensive Priority Evaluation)
        anchor_score:  Teilscore Ankertext
        context_score: Teilscore Linkkontext
        url_score:     Teilscore URL-Muster
        page_score:    Teilscore Seiteninhalts-Relevanz
        anchor_text:   Ankertext des Links
        is_pdf:        True wenn Link auf PDF zeigt
        is_priority:   True wenn CPE-Score > priority_threshold
    """
    url: str
    cpe_score: float
    anchor_score: float
    context_score: float
    url_score: float
    page_score: float
    anchor_text: str = ""
    is_pdf: bool = False
    is_priority: bool = False


class LinkPrioritizer:
    """
    CPE-basierte Link-Priorisierung nach Liu et al. (2025).

    Bewertet jeden extrahierten Link mit einem CPE-Score und gibt
    die sortierten Links zurueck (hoechster Score zuerst).
    """

    # CPE-Gewichte (w1..w4): Summe = 1.0
    _W_PAGE = 0.20      # w1: Seiteninhalt-Relevanz
    _W_ANCHOR = 0.40    # w2: Ankertext-Relevanz
    _W_CONTEXT = 0.25   # w3: Linkkontext-Relevanz
    _W_URL = 0.15       # w4: URL-Pattern-Relevanz

    def __init__(
        self,
        domain_model: Optional[DomainModel] = None,
        priority_threshold: float = 0.10,
    ):
        """
        Args:
            domain_model: DomainModel fuer Keyword-Matching
            priority_threshold: Ab wann wird ein Link priorisiert?
        """
        self._model = domain_model or DomainModel()
        self._threshold = priority_threshold

    def score_links(
        self,
        links: List[Tuple[str, str, str]],
        page_text: str = "",
    ) -> List[ScoredLink]:
        """
        Bewertet eine Liste von Links und gibt sie sortiert nach CPE-Score zurueck.

        Args:
            links:      Liste von (url, anchor_text, context_text)
            page_text:  Gesamttext der Quellseite

        Returns:
            Sortierte Liste von ScoredLink (hoechster Score zuerst)
        """
        page_score, _ = self._model.score_text(page_text) if page_text else (0.0, [])
        scored: List[ScoredLink] = []

        for url, anchor_text, context_text in links:
            sl = self._score_single(
                url=url,
                anchor_text=anchor_text,
                context_text=context_text,
                page_score=page_score,
            )
            scored.append(sl)

        scored.sort(key=lambda x: (x.is_pdf, x.cpe_score), reverse=True)
        return scored

    def score_url_only(self, url: str) -> float:
        """Schneller URL-Score ohne Ankertext/Kontext (fuer Queue-Vorsortierung)."""
        return self._score_url(url)

    def _score_single(
        self,
        url: str,
        anchor_text: str,
        context_text: str,
        page_score: float,
    ) -> ScoredLink:
        anchor_s = self._score_text_snippet(anchor_text)
        context_s = self._score_text_snippet(context_text)
        url_s = self._score_url(url)
        is_pdf = url.lower().endswith(".pdf")

        if is_pdf:
            url_s = min(1.0, url_s + 0.3)

        cpe = round(
            self._W_PAGE * page_score
            + self._W_ANCHOR * anchor_s
            + self._W_CONTEXT * context_s
            + self._W_URL * url_s,
            4
        )

        return ScoredLink(
            url=url,
            cpe_score=cpe,
            anchor_score=round(anchor_s, 4),
            context_score=round(context_s, 4),
            url_score=round(url_s, 4),
            page_score=round(page_score, 4),
            anchor_text=anchor_text[:100],
            is_pdf=is_pdf,
            is_priority=cpe >= self._threshold,
        )

    def _score_text_snippet(self, text: str) -> float:
        """TF-IDF/Kosinus-Score eines kurzen Textschnipsels."""
        if not text or not text.strip():
            return 0.0
        score, _ = self._model.score_text(text)
        return score

    def _score_url(self, url: str) -> float:
        """
        Bewertet eine URL anhand ihrer Pfadsegmente und Query-Parameter
        gegen die Domaien-Keywords.
        """
        parsed = urlparse(url)
        path_text = re.sub(r"[/_\-]", " ", parsed.path)
        query_text = re.sub(r"[=&+_\-]", " ", parsed.query)
        combined = f"{path_text} {query_text}"
        score, _ = self._model.score_text(combined)
        return score
