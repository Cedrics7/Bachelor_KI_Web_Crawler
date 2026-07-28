"""
evaluation.py
=============
Evaluationsmodul fuer den Focused Crawler.

Berechnet die Standardmetriken aus der Focused-Crawler-Literatur:

    Harvest Rate (HR):     Anteil relevanter Seiten an allen gecrawlten Seiten
                           HR = |relevant| / |gesamt|  ∈ [0.0, 1.0]
                           Quelle: Liu et al. (2025), Joe Dhanith et al. (2024)

    Precision:             HR = Harvest Rate (bei Focused Crawling identisch)

    Recall:                Anteil relevanter Seiten der Zieldomaene, die gefunden wurden
                           Recall = |relevant_gefunden| / |relevant_gesamt|
                           (Setzt einen bekannten Referenzkorpus voraus)

    F1-Score:              Harmonisches Mittel aus Precision und Recall

    Irrelevance Ratio:     Anteil irrelevanter Seiten
                           IR = 1 - HR

    Baseline-Vergleich:    Harvest Rate einer BFS-Baseline (zufaellige Reihenfolge)
                           im Vergleich zum Focused Crawler

Wissenschaftliche Basis:
    Liu, J., Wu, Y., Liu, Z. (2025) – Harvest Rate, Precision, Recall
    Joe Dhanith, P.R. et al. (2024) – Harvest Rate als Kernevaluationsmetrik
    Kaur, S. et al. (2023) – Precision/Recall-Vergleich zwischen Crawler-Varianten
"""

import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from datetime import datetime

from .relevance_classifier import RelevanceResult


@dataclass
class EvaluationReport:
    """
    Vollstaendiger Evaluationsbericht eines Crawl-Laufs.

    Alle Metriken sind ∈ [0.0, 1.0], ausser total_crawled und total_relevant.
    """
    total_crawled:         int = 0
    total_relevant:        int = 0
    total_irrelevant:      int = 0
    total_skipped:         int = 0
    total_robots_blocked:  int = 0
    total_pdfs:            int = 0

    harvest_rate:          float = 0.0
    irrelevance_ratio:     float = 0.0
    recall:                float = 0.0
    f1_score:              float = 0.0
    avg_relevance_score:   float = 0.0

    baseline_harvest_rate: float = 0.0
    improvement_vs_baseline: float = 0.0

    category_distribution: Dict[str, int] = field(default_factory=dict)

    start_url:      str = ""
    crawl_start:    str = ""
    crawl_end:      str = ""
    crawler_version: str = "focused_crawler_v1.0"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def print_summary(self) -> None:
        """Gibt einen lesbaren Evaluationsbericht aus."""
        print("\n" + "=" * 60)
        print(" FOCUSED CRAWLER – EVALUATIONSBERICHT")
        print("=" * 60)
        print(f"  Start-URL:           {self.start_url}")
        print(f"  Gecrawlt:            {self.total_crawled}")
        print(f"  Relevant:            {self.total_relevant}")
        print(f"  Irrelevant:          {self.total_irrelevant}")
        print(f"  robots.txt gesperrt: {self.total_robots_blocked}")
        print(f"  PDFs:                {self.total_pdfs}")
        print("-" * 60)
        print(f"  Harvest Rate:        {self.harvest_rate:.4f}  ({self.harvest_rate*100:.1f}%)")
        print(f"  Irrelevance Ratio:   {self.irrelevance_ratio:.4f}  ({self.irrelevance_ratio*100:.1f}%)")
        if self.recall > 0:
            print(f"  Recall:              {self.recall:.4f}  ({self.recall*100:.1f}%)")
            print(f"  F1-Score:            {self.f1_score:.4f}")
        print(f"  Ø Relevanz-Score:    {self.avg_relevance_score:.4f}")
        if self.baseline_harvest_rate > 0:
            print("-" * 60)
            print(f"  Baseline HR (BFS):   {self.baseline_harvest_rate:.4f}  ({self.baseline_harvest_rate*100:.1f}%)")
            print(f"  Verbesserung:        +{self.improvement_vs_baseline:.1f}%")
        if self.category_distribution:
            print("-" * 60)
            print("  Kategorie-Verteilung:")
            for cat, count in sorted(self.category_distribution.items(), key=lambda x: -x[1]):
                print(f"    {cat:<20} {count}")
        print("=" * 60 + "\n")


class CrawlEvaluator:
    """
    Sammelt RelevanceResults waehrend des Crawlens und berechnet
    am Ende den vollstaendigen Evaluationsbericht.

    Verwendung:
        evaluator = CrawlEvaluator(start_url="https://...")
        evaluator.add_result(relevance_result)
        report = evaluator.get_report()
        report.print_summary()
    """

    def __init__(
        self,
        start_url: str = "",
        reference_corpus_size: Optional[int] = None,
    ):
        """
        Args:
            start_url:              Einstiegs-URL des Crawls
            reference_corpus_size:  Bekannte Gesamtgroesse des relevanten Korpus
        """
        self._results: List[RelevanceResult] = []
        self._baseline_results: List[RelevanceResult] = []
        self._skipped: int = 0
        self._robots_blocked: int = 0
        self._pdfs: int = 0
        self._start_url = start_url
        self._reference_size = reference_corpus_size
        self._start_time = datetime.now().isoformat()

    def add_result(self, result: RelevanceResult, is_pdf: bool = False) -> None:
        """Fuegt ein RelevanceResult hinzu."""
        self._results.append(result)
        if is_pdf:
            self._pdfs += 1

    def add_skipped(self, count: int = 1) -> None:
        """Zaehlt uebersprungene URLs."""
        self._skipped += count

    def add_robots_blocked(self, count: int = 1) -> None:
        """Zaehlt durch robots.txt gesperrte URLs."""
        self._robots_blocked += count

    def add_baseline_crawl(self, baseline_results: List[RelevanceResult]) -> None:
        """
        Fuegt die Ergebnisse einer BFS-Baseline hinzu.
        """
        self._baseline_results = baseline_results

    def get_report(self) -> EvaluationReport:
        """Berechnet und gibt den vollstaendigen Evaluationsbericht zurueck."""
        total = len(self._results)
        if total == 0:
            return EvaluationReport(
                total_crawled=0,
                total_relevant=0,
                total_irrelevant=0,
                total_skipped=self._skipped,
                total_robots_blocked=self._robots_blocked,
                total_pdfs=self._pdfs,
                harvest_rate=0.0,
                irrelevance_ratio=0.0,
                recall=0.0,
                f1_score=0.0,
                avg_relevance_score=0.0,
                baseline_harvest_rate=0.0,
                improvement_vs_baseline=0.0,
                category_distribution={},
                start_url=self._start_url,
                crawl_start=self._start_time,
                crawl_end=datetime.now().isoformat(),
            )

        relevant_results = [r for r in self._results if r.is_relevant]
        n_relevant = len(relevant_results)
        n_irrelevant = total - n_relevant

        harvest_rate = n_relevant / total
        irrelevance_ratio = n_irrelevant / total
        avg_score = sum(r.score for r in self._results) / total

        recall = 0.0
        f1 = 0.0
        if self._reference_size and self._reference_size > 0:
            recall = min(1.0, n_relevant / self._reference_size)
            if harvest_rate + recall > 0:
                f1 = 2 * (harvest_rate * recall) / (harvest_rate + recall)

        cat_dist: Dict[str, int] = {}
        for r in relevant_results:
            cat = r.top_category
            cat_dist[cat] = cat_dist.get(cat, 0) + 1

        baseline_hr = 0.0
        improvement = 0.0
        if self._baseline_results:
            n_base = len(self._baseline_results)
            n_base_rel = sum(1 for r in self._baseline_results if r.is_relevant)
            baseline_hr = n_base_rel / n_base if n_base > 0 else 0.0
            if baseline_hr > 0:
                improvement = ((harvest_rate - baseline_hr) / baseline_hr) * 100

        return EvaluationReport(
            total_crawled=total,
            total_relevant=n_relevant,
            total_irrelevant=n_irrelevant,
            total_skipped=self._skipped,
            total_robots_blocked=self._robots_blocked,
            total_pdfs=self._pdfs,
            harvest_rate=round(harvest_rate, 4),
            irrelevance_ratio=round(irrelevance_ratio, 4),
            recall=round(recall, 4),
            f1_score=round(f1, 4),
            avg_relevance_score=round(avg_score, 4),
            baseline_harvest_rate=round(baseline_hr, 4),
            improvement_vs_baseline=round(improvement, 2),
            category_distribution=cat_dist,
            start_url=self._start_url,
            crawl_start=self._start_time,
            crawl_end=datetime.now().isoformat(),
        )

    def get_relevant_pages(self) -> List[RelevanceResult]:
        """Gibt alle als relevant klassifizierten Seiten zurueck."""
        return [r for r in self._results if r.is_relevant]
