"""
baseline_eval.py
================
BFS-Baseline-Evaluationsskript für den Focused Crawler.

Führt zwei parallele Crawl-Läufe durch:
    1. FocusedCrawler  – CPE-Priorisierung + BCW-Relevanzklassifikation
    2. BFS-Baseline    – Breadth-First-Search ohne Priorisierung

Vergleicht anschließend:
    Harvest Rate, Precision, Recall, F1-Score, Irrelevance Ratio

Der Vergleich ist der Literatur-Mindeststandard für den Nachweis
er Wirksamkeit eines Focused Crawlers:
    Liu et al. (2025), Joe Dhanith et al. (2024), Kaur et al. (2023)

Ausgabe:
    - Konsole: Vergleichstabelle
    - logs/evaluation_*.json: Maschinenlesbarer Bericht
    - logs/baseline_comparison_*.csv: CSV für Thesis-Tabellen

Verwendung:
    python baseline_eval.py --url https://www.musterstadt.de --pages 100
    python baseline_eval.py --url https://www.musterstadt.de --pages 50 --threshold 0.2
    python baseline_eval.py --url https://www.musterstadt.de --pages 100 --reference 500
"""

import argparse
import csv
import hashlib
import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
import warnings

try:
    import httpx
except ImportError:
    raise ImportError("httpx nicht installiert: pip install httpx")

try:
    from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
    warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
except ImportError:
    raise ImportError("beautifulsoup4 nicht installiert: pip install beautifulsoup4")

from .focused_crawler import FocusedCrawler, DEFAULT_CONFIG
from .relevance_classifier import RelevanceClassifier, RelevanceResult
from .domain_model import DomainModel
from .evaluation import CrawlEvaluator, EvaluationReport
from .crawler_logger import CrawlerLogger


# ---------------------------------------------------------------------------
# BFS-Baseline-Crawler (einfache Breadth-First-Suche ohne Priorisierung)
# ---------------------------------------------------------------------------

class BFSCrawler:
    """
    Einfacher BFS-Crawler ohne Relevanzpriorisierung.
    Dient als Baseline zum Vergleich mit dem FocusedCrawler.

    Der BFS-Crawler verwendet dieselbe RelevanceClassifier-Instanz,
    sodass die Relevanzbeurteilung identisch ist – nur die Reihenfolge
    der gecrawlten Seiten unterscheidet sich (FIFO statt CPE).
    """

    USER_AGENT = "BachelorCrawler-BFS-Baseline/1.0"
    TIMEOUT    = 10

    def __init__(
        self,
        classifier: RelevanceClassifier,
        logger: CrawlerLogger,
        crawl_delay: float = 1.0,
        max_queue: int = 300,
        robots_respect: bool = True,
    ) -> None:
        self._clf     = classifier
        self._logger  = logger
        self._delay   = crawl_delay
        self._max_q   = max_queue
        self._robots  = self._init_robots(robots_respect)

    def crawl(
        self,
        start_url: str,
        max_pages: int = 100,
    ) -> Tuple[List[RelevanceResult], EvaluationReport]:
        """
        Führt einen BFS-Crawl durch und gibt alle Relevanz-Ergebnisse zurück.
        """
        self._logger.section(f"BFS-BASELINE CRAWL: {start_url[:60]}")
        evaluator  = CrawlEvaluator(start_url=start_url)
        queue      = [start_url]  # FIFO – keine Priorisierung!
        visited    = set()
        hashes     = set()
        results    = []
        base_domain = urlparse(start_url).netloc

        try:
            with httpx.Client(
                follow_redirects=True,
                max_redirects=5,
                headers={"User-Agent": self.USER_AGENT},
                timeout=self.TIMEOUT,
            ) as client:
                while queue and len(results) < max_pages:
                    url = queue.pop(0)  # BFS: immer von vorne

                    if url in visited:
                        continue
                    visited.add(url)

                    # robots.txt-Check
                    if self._robots and not self._robots.is_allowed(url):
                        self._logger.privacy(url, "ROBOTS_DISALLOWED", "BFS-Baseline")
                        evaluator.add_robots_blocked()
                        continue

                    time.sleep(self._delay)

                    try:
                        resp = client.get(url)
                    except Exception as e:
                        self._logger.error("CRAWL", f"BFS-Fehler: {e}", url=url)
                        continue

                    # Domain-Guard
                    if self._strip_www(urlparse(str(resp.url)).netloc) != self._strip_www(base_domain):
                        continue

                    if resp.status_code != 200:
                        continue

                    if url.lower().endswith(".pdf"):
                        evaluator.add_result(
                            self._clf.classify("", url=url), is_pdf=True
                        )
                        continue

                    # Duplikat-Check
                    h = hashlib.sha256(resp.content).hexdigest()
                    if h in hashes:
                        evaluator.add_skipped()
                        continue
                    hashes.add(h)

                    raw_html = resp.text
                    soup = BeautifulSoup(raw_html, "html.parser")
                    for tag in soup.find_all(["script", "style"]):
                        tag.decompose()
                    text = soup.get_text(separator=" ", strip=True)

                    # Links extrahieren – BFS: einfach anhängen, keine Priorisierung
                    for a in soup.find_all("a", href=True):
                        nxt = urljoin(url, a["href"])
                        if (self._strip_www(urlparse(nxt).netloc) == self._strip_www(base_domain)
                                and nxt not in visited
                                and len(queue) < self._max_q):
                            queue.append(nxt)  # BFS: hinten anhängen
                    soup.decompose()

                    relevance = self._clf.classify(text, url=url)
                    results.append(relevance)
                    evaluator.add_result(relevance)

                    marker = "✅" if relevance.is_relevant else "⬜"
                    self._logger.info(
                        "BASELINE",
                        f"{marker} BFS [{len(results):>3}/{max_pages}] "
                        f"Score={relevance.score:.3f} Cat={relevance.top_category:<12} {url[:55]}"
                    )

        except Exception as e:
            self._logger.error("BASELINE", f"BFS-Absturz: {e}")

        report = evaluator.get_report()
        self._logger.evaluation(report.to_dict(), label="BFS_BASELINE")
        return results, report

    @staticmethod
    def _strip_www(netloc: str) -> str:
        return netloc.removeprefix("www.")

    def _init_robots(self, respect: bool):
        if not respect:
            return None
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../..", "Bachelor_Crawler"))
            from robots_checker import RobotsChecker
            return RobotsChecker(user_agent=self.USER_AGENT)
        except ImportError:
            return None


# ---------------------------------------------------------------------------
# Vergleichs-Evaluator
# ---------------------------------------------------------------------------

class BaselineComparison:
    """
    Vergleicht FocusedCrawler vs. BFS-Baseline und erstellt einen
    vollständigen Bericht für die Bachelorthesis.
    """

    def __init__(self, logger: CrawlerLogger) -> None:
        self._logger = logger

    def compare(
        self,
        focused_report: EvaluationReport,
        baseline_report: EvaluationReport,
        output_dir: str = "logs",
    ) -> Dict:
        """
        Berechnet den Vergleich und schreibt CSV + JSON.

        Returns:
            dict mit allen Vergleichswerten (für Thesis-Tabellen)
        """
        fhr  = focused_report.harvest_rate
        bhr  = baseline_report.harvest_rate
        delta_hr = fhr - bhr
        improvement = (delta_hr / bhr * 100) if bhr > 0 else 0.0

        comparison = {
            "metric":                    ["Harvest Rate", "Irrelevance Ratio", "Avg Score",
                                          "Total Crawled", "Total Relevant", "F1-Score"],
            "focused_crawler":           [fhr,
                                          focused_report.irrelevance_ratio,
                                          focused_report.avg_relevance_score,
                                          focused_report.total_crawled,
                                          focused_report.total_relevant,
                                          focused_report.f1_score],
            "bfs_baseline":              [bhr,
                                          baseline_report.irrelevance_ratio,
                                          baseline_report.avg_relevance_score,
                                          baseline_report.total_crawled,
                                          baseline_report.total_relevant,
                                          baseline_report.f1_score],
            "delta":                     [delta_hr, -(delta_hr),
                                          focused_report.avg_relevance_score - baseline_report.avg_relevance_score,
                                          0, 0, 0],
            "improvement_pct":           improvement,
            "focused_start_url":         focused_report.start_url,
            "timestamp":                 datetime.now().isoformat(),
        }

        # Bericht auf Konsole
        self._print_comparison_table(
            focused_report, baseline_report, delta_hr, improvement
        )

        # CSV für Thesis
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_path  = out_dir / f"baseline_comparison_{ts}.csv"
        json_path = out_dir / f"baseline_comparison_{ts}.json"

        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["Metrik", "FocusedCrawler", "BFS-Baseline", "Delta"])
            for i, metric in enumerate(comparison["metric"]):
                writer.writerow([
                    metric,
                    comparison["focused_crawler"][i],
                    comparison["bfs_baseline"][i],
                    comparison["delta"][i],
                ])

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(comparison, f, indent=2, ensure_ascii=False, default=str)

        self._logger.ok(
            "EVALUATION",
            f"Vergleich abgeschlossen – "
            f"HR Focused={fhr:.4f} vs BFS={bhr:.4f} "
            f"Δ={delta_hr:+.4f} ({improvement:+.1f}%)",
            csv=str(csv_path), json=str(json_path)
        )
        return comparison

    @staticmethod
    def _print_comparison_table(
        focused: EvaluationReport,
        baseline: EvaluationReport,
        delta_hr: float,
        improvement: float,
    ) -> None:
        sep = "═" * 72
        print(f"\n{sep}")
        print("  EVALUATIONSVERGLEICH: FocusedCrawler vs. BFS-Baseline")
        print(f"  Quelle: Liu et al. (2025), Joe Dhanith et al. (2024), Kaur et al. (2023)")
        print(sep)
        print(f"  {'Metrik':<25} {'FocusedCrawler':>15} {'BFS-Baseline':>15} {'Δ':>10}")
        print("─" * 72)

        rows = [
            ("Harvest Rate (Precision)", focused.harvest_rate,   baseline.harvest_rate,   "↑ besser"),
            ("Irrelevance Ratio",         focused.irrelevance_ratio, baseline.irrelevance_ratio, "↓ besser"),
            ("Ø Relevanz-Score",          focused.avg_relevance_score, baseline.avg_relevance_score, ""),
            ("Recall",                    focused.recall,          baseline.recall,          ""),
            ("F1-Score",                  focused.f1_score,        baseline.f1_score,        ""),
            ("Gecrawlt gesamt",           focused.total_crawled,   baseline.total_crawled,   ""),
            ("Davon relevant",            focused.total_relevant,  baseline.total_relevant,  ""),
            ("robots.txt gesperrt",       focused.total_robots_blocked, baseline.total_robots_blocked, ""),
        ]
        for metric, fv, bv, note in rows:
            try:
                delta = fv - bv
                delta_str = f"{delta:+.4f}" if isinstance(delta, float) else f"{delta:+d}"
            except TypeError:
                delta_str = "n/a"
            fv_str = f"{fv:.4f}" if isinstance(fv, float) else str(fv)
            bv_str = f"{bv:.4f}" if isinstance(bv, float) else str(bv)
            print(f"  {metric:<25} {fv_str:>15} {bv_str:>15} {delta_str:>10}  {note}")

        print("─" * 72)
        print(f"  Verbesserung HR:          {improvement:+.2f}%  gegenüber BFS-Baseline")
        print(f"{sep}\n")


# ---------------------------------------------------------------------------
# Hauptfunktion (CLI)
# ---------------------------------------------------------------------------

def run_baseline_evaluation(
    start_url: str,
    max_pages: int = 100,
    relevance_threshold: float = 0.15,
    reference_corpus_size: Optional[int] = None,
    log_dir: str = "logs",
    crawl_delay: float = 1.0,
    robots_respect: bool = True,
) -> Dict:
    """
    Führt den vollständigen Evaluationsvergleich durch.

    Args:
        start_url:              Einstiegs-URL
        max_pages:              Seiten pro Crawler-Lauf
        relevance_threshold:    Mindest-Score für "relevant"
        reference_corpus_size:  Für Recall-Berechnung (optional)
        log_dir:                Log-Verzeichnis
        crawl_delay:            Pause zwischen Requests (Sekunden)
        robots_respect:         robots.txt einhalten

    Returns:
        dict mit allen Vergleichswerten
    """
    domain = urlparse(start_url).netloc.replace("www.", "")
    ts     = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_id = f"{domain}_{ts}"

    logger = CrawlerLogger(run_id=run_id, log_dir=log_dir)
    logger.section("BASELINE-EVALUATION GESTARTET")
    logger.info("SYSTEM", "Evaluation gestartet",
                url=start_url, max_pages=max_pages,
                threshold=relevance_threshold,
                reference_corpus=reference_corpus_size)

    # --- Geteilte Komponenten (identisch für beide Crawler) ---
    domain_model = DomainModel()
    classifier   = RelevanceClassifier(
        domain_model=domain_model,
        relevance_threshold=relevance_threshold,
    )

    # =========================================================
    # LAUF 1: Focused Crawler
    # =========================================================
    logger.section("LAUF 1 – FOCUSED CRAWLER (CPE-Priorisierung + BCW)")
    focused = FocusedCrawler(config={
        **DEFAULT_CONFIG,
        "relevance_threshold": relevance_threshold,
        "max_pages":           max_pages,
        "crawl_delay_default": crawl_delay,
        "robots_respect":      robots_respect,
    })
    # Logger in FocusedCrawler injizieren
    focused._external_logger = logger

    focused_results, focused_report = focused.crawl(
        start_url=start_url,
        max_pages=max_pages,
        reference_corpus_size=reference_corpus_size,
    )
    logger.evaluation(focused_report.to_dict(), label="FOCUSED")

    # =========================================================
    # LAUF 2: BFS-Baseline
    # =========================================================
    logger.section("LAUF 2 – BFS-BASELINE (FIFO, keine Priorisierung)")
    bfs = BFSCrawler(
        classifier=classifier,
        logger=logger,
        crawl_delay=crawl_delay,
        robots_respect=robots_respect,
    )
    bfs_results, bfs_report = bfs.crawl(start_url=start_url, max_pages=max_pages)

    # BFS-Report in Focused-Report eintragen (für Baseline-Delta)
    focused_report.baseline_harvest_rate = bfs_report.harvest_rate
    if bfs_report.harvest_rate > 0:
        focused_report.improvement_vs_baseline = round(
            (focused_report.harvest_rate - bfs_report.harvest_rate)
            / bfs_report.harvest_rate * 100, 2
        )

    # =========================================================
    # VERGLEICH
    # =========================================================
    logger.section("ERGEBNISVERGLEICH")
    comparison_obj = BaselineComparison(logger=logger)
    comparison = comparison_obj.compare(
        focused_report=focused_report,
        baseline_report=bfs_report,
        output_dir=log_dir,
    )

    logger.close()
    return comparison


# ---------------------------------------------------------------------------
# CLI-Einstiegspunkt
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Focused Crawler vs. BFS-Baseline Evaluation"
    )
    parser.add_argument("--url",       required=True,  help="Start-URL")
    parser.add_argument("--pages",     type=int, default=100, help="Max. Seiten pro Lauf")
    parser.add_argument("--threshold", type=float, default=0.15, help="Relevanz-Schwellwert")
    parser.add_argument("--reference", type=int, default=None,  help="Referenzkorpusgröße für Recall")
    parser.add_argument("--log-dir",   default="logs",  help="Log-Verzeichnis")
    parser.add_argument("--delay",     type=float, default=1.0, help="Crawl-Delay in Sekunden")
    parser.add_argument("--no-robots", action="store_true",     help="robots.txt ignorieren")
    args = parser.parse_args()

    result = run_baseline_evaluation(
        start_url=args.url,
        max_pages=args.pages,
        relevance_threshold=args.threshold,
        reference_corpus_size=args.reference,
        log_dir=args.log_dir,
        crawl_delay=args.delay,
        robots_respect=not args.no_robots,
    )
    print("\nFertig. Logs unter:", args.log_dir)
