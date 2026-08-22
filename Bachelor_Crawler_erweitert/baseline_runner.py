r"""
baseline_runner.py
==================
Automatisierter BFS-vs-Focused Vergleichs-Runner fuer die Thesis-Evaluation (Kap. 6.1).

Verwendung (beide Varianten funktionieren):
    # Als Modul (empfohlen):
    cd D:\PycharmProjects\Bachelor_KI_Web_Crawler
    python -m Bachelor_Crawler_erweitert.baseline_runner

    # Direkt als Script (PyCharm):
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
        "reference_corpus_size": 12,
        "goldstandard_path": "Bachelor_Crawler_erweitert/goldstandard/musterstadt.json"
      }
    ]

Goldstandard (optional):
    Wenn 'goldstandard_path' gesetzt ist und die Datei existiert, wird
    Recall und F1 automatisch gegen den annotierten Referenzkorpus berechnet.
    Ansonsten wird 'reference_corpus_size' als Fallback verwendet (nur Zahl).
    Goldstandard-Dateien liegen unter Bachelor_Crawler_erweitert/goldstandard/.

BFS-Modus:
    Die BFS-Baseline verwendet denselben FocusedCrawler, jedoch mit:
      - priority_threshold = 999.0  (kein Link wird als prioritaet eingestuft)
      - FIFO-Queue (alle Links ans Ende, keine Umordnung, ueber
        _enqueue_scored_links() erzwungen)
    Damit crawlt der BFS-Modus in Breitensuche-Reihenfolge ohne
    inhaltliche Priorisierung - exakt die Baseline aus der Literatur.

Exportformat (JSON):
    Jedes Szenario enthaelt 'bfs' und 'focused' als EvaluationReport-Dicts
    sowie 'comparison'-Schluessel mit Delta-Werten fuer den direkten Vergleich.
    Wenn ein Goldstandard vorhanden ist, enthaelt 'goldstandard_stats' die
    Recall-Werte beider Modi gegen den annotierten Referenzkorpus, UND die
    'comparison'-Deltas (recall_delta/f1_delta) werden dann aus diesen
    goldstandard-basierten Werten berechnet statt aus der reinen
    reference_corpus_size-Naeherung in EvaluationReport.recall (siehe FIX
    unten).

FIX (2026-08-13):
    1) _BFSCrawler._enqueue_scored_links() ueberschrieb bisher eine Methode,
       die es in FocusedCrawler gar nicht gab (dort lag die Enqueue-Logik
       inline im crawl()-Loop) -> der Override war toter Code. Seit dem
       Refactoring von focused_crawler.py (Methode _enqueue_scored_links()
       existiert jetzt dort) greift dieser Override tatsaechlich.
    2) _compare() nutzte fuer recall_delta/f1_delta bisher ausschliesslich
       EvaluationReport.recall, das bei kleinen reference_corpus_size-Werten
       fast immer bei 1.0 saettigt und damit keine Trennschaerfe zwischen
       BFS und Focused liefert. Ist ein Goldstandard vorhanden, werden die
       Deltas jetzt aus recall_vs_goldstandard/f1_vs_goldstandard berechnet.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Direkt-Aufruf Bootstrap
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
from .reference_corpus import ReferenceCorpus


# ---------------------------------------------------------------------------
# Patched FocusedCrawler: Seed-URL ignoriert robots.txt
# ---------------------------------------------------------------------------

class _SeedIgnoreRobotsCrawler(FocusedCrawler):
    """
    Erweiterung von FocusedCrawler: Die allererste Seed-URL wird
    nie durch robots.txt geblockt. Das entspricht dem Standard-Vorgehen
    in der Focused-Crawler-Literatur (Seed wird immer gefetcht).
    Alle Folgeseiten unterliegen weiterhin der robots.txt-Pruefung.
    """

    def __init__(self, config: Optional[Dict] = None, run_id: Optional[str] = None) -> None:
        super().__init__(config=config, run_id=run_id)
        self._seed_fetched = False
        self._visited_urls_log: List[str] = []  # fuer Goldstandard-Recall-Berechnung

    def _is_robots_allowed(self, url: str) -> bool:
        if not self._seed_fetched:
            return True
        if self._robots is None:
            return True
        return self._robots.is_allowed(url)

    def crawl(self, start_url, max_pages=None, reference_corpus_size=None, ags=None):
        self._seed_fetched = False
        self._visited_urls_log = []
        _original_is_allowed = None
        if self._robots is not None:
            _original_is_allowed = self._robots.is_allowed
            crawler_self = self

            def _patched_is_allowed(url: str) -> bool:
                if not crawler_self._seed_fetched:
                    crawler_self._seed_fetched = True
                    return True
                return _original_is_allowed(url)

            self._robots.is_allowed = _patched_is_allowed

        try:
            pages, report = super().crawl(
                start_url=start_url,
                max_pages=max_pages,
                reference_corpus_size=reference_corpus_size,
                ags=ags,
            )
            # Besuchte URLs fuer spaetere Goldstandard-Auswertung sammeln
            if pages:
                self._visited_urls_log = [p.url for p in pages if hasattr(p, 'url')]
            return pages, report
        finally:
            if _original_is_allowed is not None:
                self._robots.is_allowed = _original_is_allowed


# ---------------------------------------------------------------------------
# BFS-Patch: FocusedCrawler im BFS-Modus
# ---------------------------------------------------------------------------

class _BFSCrawler(_SeedIgnoreRobotsCrawler):
    """
    BFS-Baseline: kein Link gilt als prioritaer, FIFO-Queue.
    Erbt den Seed-robots.txt-Bypass von _SeedIgnoreRobotsCrawler.

    _enqueue_scored_links() ist jetzt eine echte Ueberschreibung der in
    FocusedCrawler ausgelagerten Methode und wird tatsaechlich aus crawl()
    heraus aufgerufen (siehe Fix-Hinweis im Moduldocstring). Zusammen mit
    priority_threshold=999.0 ist das eine doppelte Absicherung fuer reines
    FIFO-Verhalten ohne inhaltliche Priorisierung.
    """

    def __init__(self, config: Optional[Dict] = None, run_id: Optional[str] = None) -> None:
        bfs_config = {**(config or {}), 'priority_threshold': 999.0}
        super().__init__(config=bfs_config, run_id=run_id or 'bfs_baseline')

    def _enqueue_scored_links(self, queue: list, scored_links: list, visited_urls: set) -> int:
        from .focused_crawler import _is_skip_url
        n = 0
        for sl in scored_links:
            if len(queue) >= self._config['max_queue']:
                break
            target_base = self._get_url_base(sl.url)
            if target_base in visited_urls or _is_skip_url(sl.url):
                continue
            queue.append((sl.url, sl.anchor_text, ''))
            n += 1
        return n


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def _load_scenarios(path: Path) -> List[Dict[str, Any]]:
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


def _load_corpus(goldstandard_path: Optional[str]) -> Optional[ReferenceCorpus]:
    """
    Laedt den Referenzkorpus aus einer JSON-Datei, wenn der Pfad gesetzt
    und die Datei vorhanden ist. Gibt None zurueck wenn kein Goldstandard
    verfuegbar ist (kein Fehler, nur Warnung).
    """
    if not goldstandard_path:
        return None
    p = Path(goldstandard_path)
    if not p.exists():
        print(f'  [GOLDSTANDARD] Datei nicht gefunden: {p} (Recall bleibt 0.0)')
        return None
    try:
        corpus = ReferenceCorpus.from_json(str(p))
        print(f'  [GOLDSTANDARD] Geladen: {corpus.domain} '
              f'({corpus.total_relevant} relevante / {corpus.total_entries} gesamt)')
        return corpus
    except Exception as exc:
        print(f'  [GOLDSTANDARD] Fehler beim Laden: {exc} (Recall bleibt 0.0)')
        return None


def _run_mode(
    seed_url: str,
    max_pages: int,
    reference_corpus_size: Optional[int],
    mode: str,
    run_id: str,
) -> Tuple[EvaluationReport, float, List[str]]:
    """
    Fuehrt einen Crawl-Lauf (BFS oder Focused) durch.

    Returns:
        (EvaluationReport, elapsed_seconds, visited_urls)
    """
    crawler_config = {
        **DEFAULT_CONFIG,
        'max_pages': max_pages,
        'db_enabled': False,
        'llm_enabled': False,
        'js_rendering': False,
        'robots_respect': True,
    }

    if mode == 'bfs':
        crawler = _BFSCrawler(config=crawler_config, run_id=run_id)
    else:
        crawler = _SeedIgnoreRobotsCrawler(config=crawler_config, run_id=run_id)

    t0 = time.time()
    _, report = crawler.crawl(
        start_url=seed_url,
        max_pages=max_pages,
        reference_corpus_size=reference_corpus_size,
    )
    elapsed = round(time.time() - t0, 2)
    visited_urls = getattr(crawler, '_visited_urls_log', [])
    return report, elapsed, visited_urls


def _apply_goldstandard(
    report: EvaluationReport,
    visited_urls: List[str],
    corpus: Optional[ReferenceCorpus],
) -> Dict[str, Any]:
    """
    Berechnet Recall und F1 gegen den Goldstandard und gibt
    ein Dict mit den Ergebnissen zurueck.

    Wenn kein Korpus vorhanden ist, werden Nullwerte zurueckgegeben.
    """
    if corpus is None or corpus.total_relevant == 0:
        return {
            'goldstandard_available': False,
            'recall_vs_goldstandard': 0.0,
            'f1_vs_goldstandard': 0.0,
            'goldstandard_total_relevant': 0,
        }

    recall = corpus.compute_recall(visited_urls)
    f1 = corpus.compute_f1(precision=report.harvest_rate, crawled_urls=visited_urls)
    return {
        'goldstandard_available': True,
        'recall_vs_goldstandard': recall,
        'f1_vs_goldstandard': f1,
        'goldstandard_total_relevant': corpus.total_relevant,
        'goldstandard_domain': corpus.domain,
        'goldstandard_category_distribution': corpus.category_distribution(),
    }


def _compare(
    focused: EvaluationReport,
    bfs: EvaluationReport,
    focused_gs: Optional[Dict[str, Any]] = None,
    bfs_gs: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Vergleicht Focused- und BFS-Ergebnisse.

    FIX: recall_delta/f1_delta werden jetzt aus den goldstandard-basierten
    Werten berechnet, sofern ein Goldstandard vorhanden ist. Die alte
    EvaluationReport.recall-Naeherung saettigt sonst fast immer bei 1.0
    und liefert dann konstant recall_delta=0.0 - unabhaengig davon, ob
    Focused oder BFS tatsaechlich besser abschneidet.
    """
    def delta(a: float, b: float) -> float:
        return round(a - b, 4)

    improvement_pct = 0.0
    if bfs.harvest_rate > 0:
        improvement_pct = round(
            (focused.harvest_rate - bfs.harvest_rate) / bfs.harvest_rate * 100, 2
        )

    use_goldstandard = (
        focused_gs is not None
        and bfs_gs is not None
        and focused_gs.get('goldstandard_available')
        and bfs_gs.get('goldstandard_available')
    )

    if use_goldstandard:
        recall_delta = delta(
            focused_gs['recall_vs_goldstandard'], bfs_gs['recall_vs_goldstandard']
        )
        f1_delta = delta(
            focused_gs['f1_vs_goldstandard'], bfs_gs['f1_vs_goldstandard']
        )
        recall_source = 'goldstandard'
    else:
        recall_delta = delta(focused.recall, bfs.recall)
        f1_delta = delta(focused.f1_score, bfs.f1_score)
        recall_source = 'reference_corpus_size_approx'

    return {
        'harvest_rate_delta':            delta(focused.harvest_rate, bfs.harvest_rate),
        'harvest_rate_improvement_pct':  improvement_pct,
        'recall_delta':                  recall_delta,
        'f1_delta':                      f1_delta,
        'recall_delta_source':           recall_source,
        'avg_relevance_score_delta':     delta(focused.avg_relevance_score, bfs.avg_relevance_score),
        'focused_wins':                  focused.harvest_rate > bfs.harvest_rate,
    }


def _print_table(results: List[Dict[str, Any]]) -> None:
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
        has_gs = entry.get('bfs', {}).get('goldstandard', {}).get('goldstandard_available', False)

        for mode in ('bfs', 'focused'):
            r = entry[mode]['report']
            elapsed = entry[mode]['elapsed_seconds']
            gs = entry[mode].get('goldstandard', {})
            tag = 'BFS' if mode == 'bfs' else 'Focused'

            # Wenn Goldstandard vorhanden: echten Recall/F1 anzeigen
            recall_display = gs.get('recall_vs_goldstandard', r['recall']) if has_gs else r['recall']
            f1_display = gs.get('f1_vs_goldstandard', r['f1_score']) if has_gs else r['f1_score']

            print(
                f"{label:<25} "
                f"{tag:<10} "
                f"{r['total_crawled']:>9} "
                f"{r['total_relevant']:>9} "
                f"{r['harvest_rate']:>7.4f} "
                f"{recall_display:>7.4f} "
                f"{f1_display:>7.4f} "
                f"{elapsed:>8.1f}"
            )

        gs_note = f" [Goldstandard: {entry['bfs']['goldstandard'].get('goldstandard_total_relevant', '?')} relevante Seiten]" if has_gs else " [kein Goldstandard]"
        cmp = entry['comparison']
        sign = '+' if cmp['harvest_rate_improvement_pct'] >= 0 else ''
        print(
            f"{'  -> Verbesserung HR':<35} "
            f"{sign}{cmp['harvest_rate_improvement_pct']:.1f}%{gs_note}"
        )
        print(
            f"{'  -> Recall-Delta-Quelle':<35} {cmp.get('recall_delta_source', '?')}"
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
        gs_path = scenario.get('goldstandard_path')

        print(f'[{i}/{len(scenarios)}] Szenario: {label}')
        print(f'  Seed-URL:            {seed}')
        print(f'  Max Seiten:          {max_pages}')
        print(f'  Referenzkorpus:      {ref_size if ref_size else "nicht gesetzt"}')
        print(f'  Goldstandard:        {gs_path if gs_path else "nicht gesetzt"}')

        # Goldstandard laden (optional)
        corpus = _load_corpus(gs_path)

        # Plausibilitaetscheck: Domain im Goldstandard vs. Seed-URL.
        # Faengt Faelle wie "gemeindesinn.de" (Seed) vs. "gemeinde-sinn.de"
        # (Goldstandard-Domain) ab, bevor stillschweigend Recall=0.0 entsteht.
        if corpus is not None and corpus.domain:
            from urllib.parse import urlparse as _urlparse
            seed_netloc = _urlparse(seed).netloc.lower().replace('www.', '')
            gs_domain = corpus.domain.lower().replace('www.', '')
            if gs_domain not in seed_netloc and seed_netloc not in gs_domain:
                print(
                    f'  [WARNUNG] Goldstandard-Domain "{gs_domain}" passt nicht offensichtlich '
                    f'zur Seed-URL-Domain "{seed_netloc}". Bitte Szenario/Goldstandard-Zuordnung '
                    f'pruefen, sonst ist der Recall fuer dieses Szenario nicht aussagekraeftig.'
                )

        print('  Modus BFS  ... ', end='', flush=True)
        bfs_report, bfs_time, bfs_urls = _run_mode(
            seed_url=seed,
            max_pages=max_pages,
            reference_corpus_size=ref_size,
            mode='bfs',
            run_id=f'baseline_bfs_{i}_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        )
        print(f'fertig ({bfs_time}s, HR={bfs_report.harvest_rate:.4f})')

        print('  Modus Focused ... ', end='', flush=True)
        focused_report, focused_time, focused_urls = _run_mode(
            seed_url=seed,
            max_pages=max_pages,
            reference_corpus_size=ref_size,
            mode='focused',
            run_id=f'baseline_focused_{i}_{datetime.now().strftime("%Y%m%d_%H%M%S")}',
        )
        print(f'fertig ({focused_time}s, HR={focused_report.harvest_rate:.4f})')

        # Goldstandard-Recall berechnen (falls vorhanden)
        bfs_gs = _apply_goldstandard(bfs_report, bfs_urls, corpus)
        focused_gs = _apply_goldstandard(focused_report, focused_urls, corpus)

        if corpus and corpus.total_relevant > 0:
            print(f'  Recall BFS:          {bfs_gs["recall_vs_goldstandard"]:.4f}  '
                  f'F1: {bfs_gs["f1_vs_goldstandard"]:.4f}')
            print(f'  Recall Focused:      {focused_gs["recall_vs_goldstandard"]:.4f}  '
                  f'F1: {focused_gs["f1_vs_goldstandard"]:.4f}')

        comparison = _compare(focused_report, bfs_report, focused_gs, bfs_gs)

        scenario_result = {
            'scenario_label':        label,
            'seed_url':              seed,
            'max_pages':             max_pages,
            'reference_corpus_size': ref_size,
            'goldstandard_path':     gs_path,
            'run_timestamp':         datetime.now().isoformat(),
            'bfs': {
                'report':          bfs_report.to_dict(),
                'elapsed_seconds': bfs_time,
                'goldstandard':    bfs_gs,
            },
            'focused': {
                'report':          focused_report.to_dict(),
                'elapsed_seconds': focused_time,
                'goldstandard':    focused_gs,
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
        description='Automatisierter BFS-vs-Focused Baseline-Runner mit Goldstandard-Recall (Kap. 6.1)',
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
