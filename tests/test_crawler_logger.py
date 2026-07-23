"""
tests/test_crawler_logger.py
=============================
Unit-Tests für CrawlerLogger – alle 4 Log-Kanäle.

Fix v1.1:
  - CSV-Header-Test liest Datei erst NACH dem logger.close() (damit Flush garantiert)
  - Alternativ: eigene Logger-Instanz pro Test, die vor dem Read geschlossen wird
"""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from focused_crawler.crawler_logger import CrawlerLogger


def make_logger(tmp_path, run_id="test_run"):
    """Hilfsfunktion: Erstellt Logger mit tmp_path und stillem Console-Level."""
    return CrawlerLogger(
        run_id=run_id,
        log_dir=str(tmp_path),
        console_level="ERROR",
        use_color=False,
    )


@pytest.fixture
def tmp_logger(tmp_path):
    """Logger mit temporärem Log-Verzeichnis."""
    logger = make_logger(tmp_path)
    yield logger, tmp_path
    logger.close()


@pytest.mark.unit
class TestCrawlerLogger:

    # ------------------------------------------------------------------
    # Dateierstellung
    # ------------------------------------------------------------------

    def test_log_files_created(self, tmp_logger):
        _, tmp_path = tmp_logger
        log_files = list(tmp_path.iterdir())
        assert len(log_files) == 4, f"Erwartet 4 Log-Dateien, erhalten: {len(log_files)}"

    def test_main_log_exists(self, tmp_logger):
        _, tmp_path = tmp_logger
        main_logs = [f for f in tmp_path.iterdir() if "focused_crawler" in f.name]
        assert len(main_logs) == 1

    def test_relevance_csv_exists(self, tmp_logger):
        _, tmp_path = tmp_logger
        rel_logs = [f for f in tmp_path.iterdir() if "relevance" in f.name]
        assert len(rel_logs) == 1

    def test_privacy_log_exists(self, tmp_logger):
        _, tmp_path = tmp_logger
        priv_logs = [f for f in tmp_path.iterdir() if "privacy" in f.name]
        assert len(priv_logs) == 1

    def test_evaluation_log_exists(self, tmp_logger):
        _, tmp_path = tmp_logger
        eval_logs = [f for f in tmp_path.iterdir() if "evaluation" in f.name]
        assert len(eval_logs) == 1

    # ------------------------------------------------------------------
    # Relevanz-Log (CSV)
    # ------------------------------------------------------------------

    def test_relevance_csv_has_header(self, tmp_path):
        """
        CSV-Header-Test: Logger wird explizit geschlossen (flush garantiert),
        dann wird die Datei gelesen.
        """
        logger = make_logger(tmp_path, run_id="header_test")
        logger.close()  # flush + close VOR dem Lesen

        rel_files = [f for f in tmp_path.iterdir() if "relevance" in f.name]
        assert len(rel_files) == 1, f"Keine relevance-Datei gefunden in {list(tmp_path.iterdir())}"
        lines = rel_files[0].read_text(encoding="utf-8").splitlines()
        assert len(lines) >= 1, "CSV-Datei ist leer"
        header = lines[0]
        assert "score" in header
        assert "url" in header
        assert "is_relevant" in header

    def test_relevance_log_writes_row(self, tmp_logger):
        logger, tmp_path = tmp_logger
        logger.relevance(
            url="https://muster.de/test",
            score=0.75,
            tfidf_score=0.60,
            bayes_score=0.85,
            is_relevant=True,
            top_category="Ausschreibung",
            confidence=0.90,
            matched_keywords=["ausschreibung", "vergabe"],
        )
        logger.close()  # Sicherstellen, dass alles geflusht ist
        rel_file = next(f for f in tmp_path.iterdir() if "relevance" in f.name)
        lines = rel_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2, f"Erwartet 2 Zeilen (Header + 1 Daten), erhalten {len(lines)}"
        assert "0.75" in lines[1]
        assert "Ausschreibung" in lines[1]

    # ------------------------------------------------------------------
    # Privacy-Log (AUDIT-Level)
    # ------------------------------------------------------------------

    def test_privacy_log_writes_json(self, tmp_logger):
        logger, tmp_path = tmp_logger
        logger.privacy(
            url="https://muster.de/kontakt",
            event="PII_REMOVED",
            details="2x E-Mail",
            counts={"email": 2, "phone": 0, "iban": 0},
        )
        logger.close()
        priv_file = next(f for f in tmp_path.iterdir() if "privacy" in f.name)
        content = priv_file.read_text(encoding="utf-8").strip()
        assert content
        entry = json.loads(content.splitlines()[0])
        assert entry["event"] == "PII_REMOVED"
        assert entry["url"] == "https://muster.de/kontakt"

    def test_privacy_audit_always_written(self, tmp_path):
        """AUDIT-Events müssen auch bei console_level=ERROR in privacy.log erscheinen."""
        logger = make_logger(tmp_path, run_id="audit_test")
        logger.privacy("https://muster.de", "ROBOTS_DISALLOWED", "Disallow: /")
        logger.close()
        priv_file = next(f for f in tmp_path.iterdir() if "privacy" in f.name)
        assert priv_file.read_text(encoding="utf-8").strip()

    # ------------------------------------------------------------------
    # Evaluation-Log
    # ------------------------------------------------------------------

    def test_evaluation_log_writes_json(self, tmp_path):
        logger = make_logger(tmp_path, run_id="eval_test")
        report = {
            "harvest_rate": 0.65,
            "recall": 0.54,
            "f1_score": 0.59,
            "total_crawled": 100,
            "total_relevant": 65,
            "improvement_vs_baseline": 103.1,
        }
        logger.evaluation(report, label="FOCUSED")
        logger.close()
        eval_file = next(f for f in tmp_path.iterdir() if "evaluation" in f.name)
        content = eval_file.read_text(encoding="utf-8").strip()
        data = json.loads(content)
        assert data["label"] == "FOCUSED"
        assert data["report"]["harvest_rate"] == 0.65

    # ------------------------------------------------------------------
    # Vollprotokoll (JSON-Lines)
    # ------------------------------------------------------------------

    def test_main_log_valid_jsonlines(self, tmp_path):
        logger = make_logger(tmp_path, run_id="jsonlines_test")
        logger.info("CRAWL", "Testmeldung", url="https://muster.de", status=200)
        logger.close()
        main_file = next(f for f in tmp_path.iterdir() if "focused_crawler" in f.name)
        for line in main_file.read_text(encoding="utf-8").strip().splitlines():
            entry = json.loads(line)
            assert "ts" in entry
            assert "level" in entry
            assert "component" in entry

    def test_close_no_exception(self, tmp_path):
        """close() darf nicht crashen."""
        logger = make_logger(tmp_path, run_id="close_test")
        try:
            logger.close()
        except Exception as e:
            pytest.fail(f"close() crasht: {e}")
