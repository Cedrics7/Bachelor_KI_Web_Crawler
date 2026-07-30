"""
baseline_runner.py
==================
Automatisierter BFS-vs-Focused Vergleichs-Runner fuer die Thesis-Evaluation (Kap. 6.1).

Funktionsweise:
  1. Szenarien werden aus einer JSON-Datei geladen (seed_url, max_pages,
     reference_corpus_size, label).
  2. Pro Szenario wird zuerst ein BFS-Lauf (Link-Priorisierung deaktiviert,
     FIFO-Queue) und danach ein Focused-Lauf mit CPE-Priorisierung ausgefuehrt.
  3. Metriken beider Laeufe (Harvest Rate, Precision, Recall, F1, Laufzeit)
     werden in einer JSON-Datei gespeichert UND als Tabelle ausgegeben.

Verwendung (beide Varianten funktionieren):
    # Als Modul (empfohlen):
    cd D:\PycharmProjects\Bachelor_KI_Web_Crawler
    python -m Bachelor_Crawler_erweitert.baseline_runner

    # Direkt als Script (PyCharm / python baseline_runner.py):
    python Bachelor_Crawler_erweitert/baseline_runner.py

    # Eigene Szenariendatei:
    python -m Bachelor_Crawler_erweitert.baseline_runner --scenarios my_scenarios.json

    # Ausgabepfad anpassen:
    python -m Bachelor_Crawler_erweitert.baseline_runner --output results/eval_2026.json

Szenario-Format (JSON-Array):
    [
      {
        "label": "Musterstadt",
        "seed_url": "https://www.musterstadt.de",
        "max_pages": 50,
        "reference_corpus_size": 12
      }
    ]

BFS-Modus:
    Die BFS-Baseline verwendet denselben FocusedCrawler, jedoch mit:
      - priority_threshold = 999.0  (kein Link wird als prioritaet eingestuft)
      - FIFO-Queue (alle Links ans Ende, keine Umordnung)
    Damit crawlt der BFS-Modus in Breitensuche-Reihenfolge ohne
    inhaltliche Priorisierung - exakt die Baseline aus der Literatur.

Exportformat (JSON):
    Jedes Szenario enthaelt 'bfs' und 'focused' als EvaluationReport-Dicts
    sowie 'comparison'-Schluessel mit Delta-Werten fuer den direkten Vergleich.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Direkt-Aufruf Bootstrap
# Ermoeglicht 'python baseline_runner.py' OHNE -m Flag (z.B. in PyCharm).
# Wird nur aktiv wenn __package__ nicht gesetzt ist (= direkter Script-Aufruf).
# ---------------------------------------------------------------------------
import sys
if __package__ is None or __package__ == '':
    from pathlib import Path as _Path
    _pkg_root = str(_Path(__file__).resolve().parent.parent)
    if _pkg_root not in sys.path:
        sys.path.insert(0, _pkg_root)
    __package__ = 'Bachelor_Crawler_erweitert'

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .focused_crawler import FocusedCrawler
from .evaluation import EvaluationReport
from .config import DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# BFS-Patch: FocusedCrawler im BFS-Modus
# ---------------------------------------------------------------------------

class _BFSCrawler(FocusedCrawler):
    """
    Subklasse, die den FocusedCrawler in eine BFS-Baseline verwandelt.

    Aenderungen gegenueber dem Focused-Modus:
      - priority_threshold = 999.0  ->  kein Link gilt als prioritaer
      - _enqueue_scored_links() haengt alle Links ans Ende der Queue (FIFO)

    Alle anderen Komponenten (DSGVO, robots.txt, Relevanzklassifikation)
    bleiben unveraendert aktiv, damit der Vergleich methodisch sauber ist.
    """

    def __init__(self, config: Optional[Dict] = None, run_id: Optional[str] = None) -> None:
        bfs_config = {**(config or {}), 'priority_threshold': 999.0}
        super().__init__(config=bfs_config, run_id=run_id or 'bfs_baseline')

    def _enqueue_scored_links(self, queue: list, scored_links: list, visited_urls: set) -> int:
        """
        Ueberschreibt die Link-Einreihungs-Logik: Alle Links werden
        ohne Umordnung am Ende der Queue angehaengt (FIFO = BFS).
        Gibt die Anzahl tatsaechlich eingereihter Links zurueck.
        """
        n = 0
        for sl in scored_links:
            if len(queue) >= self._config['max_queue']:
                break
            from urllib.parse import urlparse, urlunparse
            from .focused_crawler import _is_skip_url
            p = urlparse(sl.url)
            target_base = urlunparse((p.scheme, p.netloc, p.path.rstrip('/'), '', '', ''))
            if target_base in visited_urls or _is_skip_url(sl.url):
                continue
            queue.append((sl.url, sl.anchor_text, ''))
            n += 1
        return n


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _load_scenarios(path: Path) -> List[Dict[str, Any]]:
    """Laedt Szenarienliste aus einer JSON-Datei."""
    with open(path, encoding='utf-8') as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f'Szenariendatei muss ein JSON-Array sein: {path}')
    required = {'label', 'seed_url', 'max_pages'}
    for i, s in enumerate(data):
        missing = required - set(s.keys())
        if missing:
            raise ValueError(f'Szenario #{i} fehlt Felder: {missing}')
    return data


def _run_mode(
    seed_url: str,
    max_pages: int,
    reference_corpus_size: Optional[int],
    mode: str,
    run_id: str,
) -> Tuple[EvaluationReport, float]:
    """
    Fuehrt einen einzelnen Crawl-Lauf durch (BFS oder Focused).

    Returns:
        (EvaluationReport, laufzeit_sekunden)
    """
    crawler_config = {
        **DEFAULT_CONFIG,
        'max_pages': max_pages,
        'db_enabled': False,
        'llm_enabled': False,
        'js_rendering': False,
    }

    if mode == 'bfs':
        crawler = _BFSCrawler(config=crawler_config, run_id=run_id)
    else:
        crawler = FocusedCrawler(config=crawler_config, run_id=run_id)

    t0 = time.time()
    _, report = crawler.crawl(
        start_url=seed_url,
        max_pages=max_pages,
        reference_corpus_size=reference_corpus_size,
    )
    elapsed = round(time.time() - t0, 2)
    return report, elapsed


def _compare(focused: EvaluationReport, bfs: EvaluationReport) -> Dict[str, Any]:
    """Berechnet Deltas zwischen Focused und BFS."""
    def delta(a: float, b: float) -> float:
        return round(a - b, 4)

    improvement_pct = 0.0
    if bfs.harvest_rate > 0:
        improvement_pct = round(
            (focused.harvest_rate - bfs.harvest_rate) / bfs.harvest_rate * 100, 2
        )

    return {
        'harvest_rate_delta':            delta(focused.harvest_rate, bfs.harvest_rate),
        'harvest_rate_improvement_pct':  improvement_pct,
        'recall_delta':                  delta(focused.recall, bfs.recall),
        'f1_delta':                      delta(focused.f1_score, bfs.f1_score),
        'avg_relevance_score_delta':     delta(focused.avg_relevance_score, bfs.avg_relevance_score),
        'focused_wins':                  focused.harvest_rate > bfs.harvest_rate,
    }


def _print_table(results: List[Dict[str, Any]]) -> None:
    """Gibt eine formatierte Vergleichstabelle fuer alle Szenarien aus."""
    header = (
        f"{'Szenario':<25} "
        f"{'Modus':<10} "
        f"{'Gecrawlt':>9} "
        f"{'Relevant':>9} "
        f"{'HR':>7} "
        f"{'Recall':>7} "
        f"{'F1':>7} "
        f"{'Zeit(s)':>8}"
    )
    sep = '-' * len(header)
    print()
    print('=' * len(header))
    print(' BASELINE-RUNNER - EVALUATIONSERGEBNISSE (Kap. 6.1)')
    print('=' * len(header))
    print(header)
    print(sep)

    for entry in results:
        label = entry['scenario_label']
        for mode in ('bfs', 'focused'):
            r = entry[mode]['report']
            elapsed = entry[mode]['elapsed_seconds']
            tag = 'BFS' if mode == 'bfs' else 'Focused'
            print(
                f"{label:<25} "
                f"{tag:<10} "
                f"{r['total_crawled']:>9} "
                f"{r['total_relevant']:>9} "
                f"{r['harvest_rate']:>7.4f} "
                f"{r['recall']:>7.4f} "
                f"{r['f1_score']:>7.4f} "
                f"{elapsed:>8.1f}"
            )
        cmp = entry['comparison']
        sign = '+' if cmp['harvest_rate_improvement_pct'] >= 0 else ''
        print(
            f"{'  -> Verbesserung HR':<35} "
            f"{sign}{cmp['harvest_rate_improvement_pct']:.1f}%"
        )
        print(sep)

    print()


# ---------------------------------------------------------------------------
# Haupt-Runner
# ---------------------------------------------------------------------------

def run_baseline(
    scenarios_path: Path,
    output_path: Path,
) -> List[Dict[str, Any]]:
    """
    Fuehrt alle Szenarien aus und schreibt die Ergebnisse in eine JSON-Datei.

    Args:
        scenarios_path: Pfad zur JSON-Szenariendatei
        output_path:    Pfad fuer die JSON-Ausgabedatei

    Returns:
        Liste aller Szenario-Ergebnisse (dict)
    """
    scenarios = _load_scenarios(scenarios_path)
    all_results: List[Dict[str, Any]] = []

    print(f'\nBaseline-Runner gestartet: {len(scenarios)} Szenario(en)')
    print(f'Szenarien:  {scenarios_path}')
    print(f'Ausgabe:    {output_path}')
    print()

    for i, scenario in enumerate(scenarios, 1):
        label = scenario['label']
        seed = scenario['seed_url']
        max_pages = int(scenario['max_pages'])
        ref_size = scenario.get('reference_corpus_size')

        print(f'[{i}/{len(scenarios)}] Szenario: {label}')
        print(f'  Seed-URL:            {seed}')
        print(f'  Max Seiten:          {max_pages}')
        print(f'  Referenzkorpus:      {ref_size if ref_size else "nicht gesetzt"}')

        print('  Modus BFS  ... ', end='', flush=True)
        bfs_report, bfs_time = _run_mode(
            seed_url=seed,
            max_pages=max_pages,
            reference_corpus_size=ref_size,
            mode='bfs',
            run_id=f'baseline_bfs_{i}_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        )
        print(f'fertig ({bfs_time}s, HR={bfs_report.harvest_rate:.4f})')

        print('  Modus Focused ... ', end='', flush=True)
        focused_report, focused_time = _run_mode(
            seed_url=seed,
            max_pages=max_pages,
            reference_corpus_size=ref_size,
            mode='focused',
            run_id=f'baseline_focused_{i}_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        )
        print(f'fertig ({focused_time}s, HR={focused_report.harvest_rate:.4f})')

        comparison = _compare(focused_report, bfs_report)

        scenario_result = {
            'scenario_label':        label,
            'seed_url':              seed,
            'max_pages':             max_pages,
            'reference_corpus_size': ref_size,
            'run_timestamp':         datetime.now().isoformat(),
            'bfs': {
                'report':          bfs_report.to_dict(),
                'elapsed_seconds': bfs_time,
            },
            'focused': {
                'report':          focused_report.to_dict(),
                'elapsed_seconds': focused_time,
            },
            'comparison': comparison,
        }
        all_results.append(scenario_result)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as fh:
        json.dump(all_results, fh, indent=2, ensure_ascii=False)

    _print_table(all_results)
    print(f'Ergebnisse gespeichert: {output_path}')
    return all_results


# ---------------------------------------------------------------------------
# CLI-Einstiegspunkt
# ---------------------------------------------------------------------------

def _default_scenarios_path() -> Path:
    return Path(__file__).resolve().parent / 'scenarios' / 'baseline_scenarios.json'


def _default_output_path() -> Path:
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    return Path(__file__).resolve().parent.parent / 'results' / f'baseline_{ts}.json'


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description='Automatisierter BFS-vs-Focused Baseline-Runner (Kap. 6.1)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        '--scenarios',
        type=Path,
        default=_default_scenarios_path(),
        help='Pfad zur JSON-Szenariendatei (default: scenarios/baseline_scenarios.json)',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=None,
        help='Pfad fuer JSON-Ausgabe (default: results/baseline_TIMESTAMP.json)',
    )
    args = parser.parse_args(argv)

    output = args.output or _default_output_path()

    if not args.scenarios.exists():
        print(f'FEHLER: Szenariendatei nicht gefunden: {args.scenarios}', file=sys.stderr)
        sys.exit(1)

    run_baseline(scenarios_path=args.scenarios, output_path=output)


if __name__ == '__main__':
    main()
