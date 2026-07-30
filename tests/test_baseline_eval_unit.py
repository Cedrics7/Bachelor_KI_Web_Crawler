"""
tests/test_baseline_eval_unit.py
=================================
Unit-Tests für baseline_eval.py – BFS-Baseline und Vergleichslogik.

Nur Offline-Tests: BaselineComparison-Klasse und Metrik-Berechnung.
Kein echter BFS-Crawl (das würde echtes Netzwerk brauchen).
"""

import json
import sys
import os
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from Alt.focused_crawler.baseline_eval import BaselineComparison
from Alt.focused_crawler.evaluation import EvaluationReport
from Alt.focused_crawler.crawler_logger import CrawlerLogger


def make_report(
    total_crawled: int,
    total_relevant: int,
    start_url: str = "https://muster.de",
) -> EvaluationReport:
    """Erstellt einen synthetischen EvaluationReport für Tests."""
    class FakeReport:
        pass
    r = FakeReport()
    r.start_url          = start_url
    r.total_crawled      = total_crawled
    r.total_relevant     = total_relevant
    r.total_skipped      = 0
    r.total_robots_blocked = 0
    r.harvest_rate       = total_relevant / total_crawled if total_crawled > 0 else 0.0
    r.irrelevance_ratio  = 1.0 - r.harvest_rate
    r.avg_relevance_score = 0.4 if total_relevant > 0 else 0.1
    r.recall             = 0.0
    r.f1_score           = 0.0
    r.baseline_harvest_rate = 0.0
    r.improvement_vs_baseline = 0.0
    def to_dict(self):
        return {k: v for k, v in vars(self).items() if not callable(v)}
    import types
    r.to_dict = types.MethodType(to_dict, r)
    return r


@pytest.fixture
def comparison_logger(tmp_path):
    logger = CrawlerLogger(
        run_id="test_comparison",
        log_dir=str(tmp_path),
        console_level="ERROR",
        use_color=False,
    )
    yield logger, tmp_path
    logger.close()


@pytest.mark.unit
class TestBaselineComparison:

    # ------------------------------------------------------------------
    # Vergleichsberechnung
    # ------------------------------------------------------------------

    def test_compare_returns_dict(self, comparison_logger, tmp_path):
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        focused = make_report(100, 65)
        baseline = make_report(100, 30)
        result = comp.compare(focused, baseline, output_dir=str(log_dir))
        assert isinstance(result, dict)

    def test_improvement_positive_when_focused_better(self, comparison_logger, tmp_path):
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        focused  = make_report(100, 65)  # HR = 0.65
        baseline = make_report(100, 30)  # HR = 0.30
        result = comp.compare(focused, baseline, output_dir=str(log_dir))
        assert result["improvement_pct"] > 0, "Verbesserung muss positiv sein"

    def test_improvement_formula(self, comparison_logger, tmp_path):
        """(HR_focused - HR_bfs) / HR_bfs * 100"""
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        focused  = make_report(100, 60)  # HR = 0.60
        baseline = make_report(100, 30)  # HR = 0.30
        result = comp.compare(focused, baseline, output_dir=str(log_dir))
        expected = (0.60 - 0.30) / 0.30 * 100  # = 100%
        assert abs(result["improvement_pct"] - expected) < 0.1

    def test_harvest_rates_in_result(self, comparison_logger, tmp_path):
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        result = comp.compare(
            make_report(100, 65), make_report(100, 32),
            output_dir=str(log_dir)
        )
        metrics = result["metric"]
        focused_vals = result["focused_crawler"]
        idx = metrics.index("Harvest Rate")
        assert abs(focused_vals[idx] - 0.65) < 0.001

    # ------------------------------------------------------------------
    # Ausgabedateien
    # ------------------------------------------------------------------

    def test_csv_file_created(self, comparison_logger, tmp_path):
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        comp.compare(make_report(100, 65), make_report(100, 30), output_dir=str(log_dir))
        csv_files = list(Path(log_dir).glob("baseline_comparison_*.csv"))
        assert len(csv_files) == 1

    def test_json_file_created(self, comparison_logger, tmp_path):
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        comp.compare(make_report(100, 65), make_report(100, 30), output_dir=str(log_dir))
        json_files = list(Path(log_dir).glob("baseline_comparison_*.json"))
        assert len(json_files) == 1

    def test_csv_has_correct_columns(self, comparison_logger, tmp_path):
        import csv
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        comp.compare(make_report(100, 65), make_report(100, 30), output_dir=str(log_dir))
        csv_file = list(Path(log_dir).glob("baseline_comparison_*.csv"))[0]
        with open(csv_file, encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
        assert "Metrik" in header
        assert "FocusedCrawler" in header
        assert "BFS-Baseline" in header

    def test_json_contains_improvement_pct(self, comparison_logger, tmp_path):
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        comp.compare(make_report(100, 65), make_report(100, 30), output_dir=str(log_dir))
        json_file = list(Path(log_dir).glob("baseline_comparison_*.json"))[0]
        data = json.loads(json_file.read_text(encoding="utf-8"))
        assert "improvement_pct" in data
        assert data["improvement_pct"] > 0

    # ------------------------------------------------------------------
    # Edge Cases
    # ------------------------------------------------------------------

    def test_zero_baseline_hr_no_division_error(self, comparison_logger, tmp_path):
        """HR_baseline = 0 darf keinen ZeroDivisionError auslösen."""
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        focused  = make_report(100, 50)
        baseline = make_report(100, 0)  # HR = 0
        try:
            result = comp.compare(focused, baseline, output_dir=str(log_dir))
        except ZeroDivisionError:
            pytest.fail("ZeroDivisionError bei HR_baseline = 0")

    def test_equal_performance_zero_improvement(self, comparison_logger, tmp_path):
        logger, log_dir = comparison_logger
        comp = BaselineComparison(logger=logger)
        result = comp.compare(
            make_report(100, 50), make_report(100, 50),
            output_dir=str(log_dir)
        )
        assert result["improvement_pct"] == 0.0
