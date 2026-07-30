#!/usr/bin/env python3
"""
crawler_js/render_url.py – Schlanke HTML-Renderer-CLI

Rendert eine einzelne URL via Playwright (Chromium, headless) und gibt
das vollständig gerenderte HTML auf stdout aus oder speichert es in eine Datei.

Verwendung:
    python -m crawler_js.render_url --url https://example.com
    python -m crawler_js.render_url --url https://example.com --out seite.html
    python -m crawler_js.render_url --url https://example.com --timeout 15000

Voraussetzung:
    pip install playwright
    playwright install chromium
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def render(url: str, timeout_ms: int = 10_000) -> str:
    """Rendert *url* mit Playwright/Chromium und gibt das HTML zurück."""
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "Playwright ist nicht installiert.\n"
            "Bitte ausführen: pip install playwright && playwright install chromium"
        ) from exc

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=timeout_ms, wait_until="networkidle")
        html = page.content()
        browser.close()

    return html


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m crawler_js.render_url",
        description="Rendert eine URL mit Playwright und gibt das HTML aus",
    )
    parser.add_argument("--url", required=True, metavar="URL", help="Zu rendernde URL")
    parser.add_argument(
        "--out",
        metavar="DATEI",
        default=None,
        help="Ausgabedatei (Standard: stdout)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=10_000,
        metavar="MS",
        help="Timeout in Millisekunden (Standard: 10000)",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    html = render(args.url, timeout_ms=args.timeout)

    if args.out:
        Path(args.out).write_text(html, encoding="utf-8")
        print(f"HTML gespeichert in: {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(html)


if __name__ == "__main__":
    main()
