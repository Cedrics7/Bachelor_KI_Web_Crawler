#!/usr/bin/env python3
"""
run_crawler.py – Zentraler Startpunkt des Bachelor-Crawlers

Verwendung:
    python run_crawler.py --mode focused --seed https://musterstadt.de --depth 2
    python run_crawler.py --mode focused --seed https://musterstadt.de --depth 2 --use-js
    python run_crawler.py --mode telekom

Modes:
    focused   – Eigenständiger Focused Crawler (focused_crawler-Paket)
    telekom   – JS-basierter Telekom-Crawler   (crawler_js/crawler_telekom.py)
"""

import argparse
import sys


def run_focused(args: argparse.Namespace) -> None:
    """Startet den focused_crawler über seinen __main__-Einstieg."""
    from focused_crawler.__main__ import main as focused_main  # type: ignore

    # Argumente für focused_crawler in sys.argv schreiben, damit argparse
    # im Untermodul korrekt parst.
    argv = ["focused-crawler", "--seed", args.seed, "--depth", str(args.depth)]
    if args.use_js:
        argv.append("--use-js")
    sys.argv = argv
    focused_main()


def run_telekom() -> None:
    """Startet den crawler_js/crawler_telekom.py als eigenständiges Programm."""
    import subprocess

    result = subprocess.run(
        [sys.executable, "-m", "crawler_js.crawler_telekom"],
        check=False,
    )
    sys.exit(result.returncode)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_crawler",
        description="Zentraler Starter für den Bachelor KI Web Crawler",
    )
    sub = parser.add_subparsers(dest="mode", required=True, metavar="MODE")

    # --- focused sub-command ---
    p_focused = sub.add_parser("focused", help="Focused Crawler starten")
    p_focused.add_argument(
        "--seed",
        required=True,
        metavar="URL",
        help="Start-URL für den Focused Crawler",
    )
    p_focused.add_argument(
        "--depth",
        type=int,
        default=2,
        metavar="N",
        help="Crawl-Tiefe (Standard: 2)",
    )
    p_focused.add_argument(
        "--use-js",
        action="store_true",
        help="JS-Rendering via render_url aktivieren",
    )

    # --- telekom sub-command ---
    sub.add_parser("telekom", help="Telekom JS-Crawler starten")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.mode == "focused":
        run_focused(args)
    elif args.mode == "telekom":
        run_telekom()


if __name__ == "__main__":
    main()
