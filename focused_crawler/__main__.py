# focused_crawler/__main__.py
"""
CLI-Einstiegspunkt für den focused_crawler.
Aufruf:
    python -m focused_crawler --seed https://musterstadt.de --depth 2 --threshold 0.5
    focused-crawler --seed https://musterstadt.de --use-js --output output/lauf1
"""
import argparse
import sys
from Alt.focused_crawler.focused_crawler import FocusedCrawler
from Alt.focused_crawler.crawler_logger import CrawlerLogger
from Alt.focused_crawler.evaluation import CrawlEvaluator


def main():
    parser = argparse.ArgumentParser(
        prog="focused_crawler",
        description="Eigenständiger Focused Crawler für Infrastruktur-Ausbauprojekte"
    )
    parser.add_argument(
        "--seed",
        required=True,
        help="Start-URL oder Pfad zu einer Seed-CSV-Datei"
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=3,
        help="Maximale Crawl-Tiefe (Standard: 3)"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.5,
        help="Relevanzschwelle 0.0–1.0 (Standard: 0.5)"
    )
    parser.add_argument(
        "--use-js",
        action="store_true",
        help="crawler_js-Fallback für dynamisch gerenderte Seiten aktivieren"
    )
    parser.add_argument(
        "--output",
        default="output/",
        help="Ausgabeverzeichnis (Standard: output/)"
    )
    args = parser.parse_args()

    logger = CrawlerLogger(run_id="cli_run", log_dir=args.output)
    evaluator = CrawlEvaluator(start_url=args.seed)
    crawler = FocusedCrawler(
        relevance_threshold=args.threshold,
        max_depth=args.depth,
        use_js_fallback=args.use_js,
        logger=logger,
        evaluator=evaluator,
    )

    try:
        results = crawler.crawl(args.seed)
        report = evaluator.get_report()
        report.print_summary()
    except KeyboardInterrupt:
        print("\n[CLI] Crawl durch Benutzer abgebrochen.", file=sys.stderr)
    finally:
        logger.close()

    sys.exit(0)


if __name__ == "__main__":
    main()
