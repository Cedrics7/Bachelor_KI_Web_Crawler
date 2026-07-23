"""
crawler_logger.py
=================
Zentrales Logging-Modul für den focused_crawler.

Loggt alle relevanten Schritte strukturiert in drei Kanäle:
    1. Konsole          – farbige Echtzeit-Ausgabe
    2. focused_crawler.log  – maschinenlesbares Vollprotokoll (JSON-Lines)
    3. relevance.log    – nur Relevanzberechnungen (CSV-kompatibel)
    4. privacy.log      – nur Datenschutz-Events (DSGVO-Nachweis)
    5. evaluation.log   – Evaluationsmetriken nach jedem Crawl-Lauf

Log-Level:
    DEBUG   – detaillierte Schritte (CPE-Scores, BCW-Wahrscheinlichkeiten)
    INFO    – reguläre Ereignisse (Seite gecrawlt, Relevanz berechnet)
    WARN    – Auffälligkeiten (robots.txt blockiert, PII entfernt)
    ERROR   – Fehler (Timeout, Verbindungsfehler)
    AUDIT   – Datenschutz-relevante Events (immer gespeichert, nie gefiltert)

Verwendung:
    logger = CrawlerLogger(run_id="musterstadt_001")
    logger.info("CRAWL", "Seite gecrawlt", url="https://...")
    logger.relevance(url, score, category, matched_kw)
    logger.privacy(url, event="PII_REMOVED", details="3x E-Mail")
    logger.evaluation(report_dict)
    logger.close()
"""

import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# ANSI-Farben für Konsolen-Ausgabe
# ---------------------------------------------------------------------------
class _C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    RED    = "\033[91m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"
    BLUE   = "\033[94m"
    MAGENTA= "\033[95m"

_LEVEL_COLORS = {
    "DEBUG" : _C.GRAY,
    "INFO"  : _C.CYAN,
    "WARN"  : _C.YELLOW,
    "ERROR" : _C.RED,
    "AUDIT" : _C.MAGENTA,
    "OK"    : _C.GREEN,
}

_COMPONENT_ICONS = {
    "CRAWL"      : "🌐",
    "RELEVANCE"  : "📊",
    "PRIVACY"    : "🔒",
    "EVALUATION" : "📈",
    "ROBOTS"     : "🤖",
    "QUEUE"      : "📋",
    "CPE"        : "🔗",
    "BCW"        : "🧠",
    "DOMAIN"     : "🗂️",
    "HTTP"       : "📡",
    "HASH"       : "#️⃣",
    "PDF"        : "📄",
    "BASELINE"   : "📉",
    "SYSTEM"     : "⚙️",
    "ERROR"      : "❌",
    "WARN"       : "⚠️",
}


class CrawlerLogger:
    """
    Strukturiertes Logging für alle Schritte des focused_crawler.

    Jede Log-Zeile wird als JSON-Lines-Eintrag gespeichert und
    gleichzeitig formatiert auf der Konsole ausgegeben.

    Log-Dateien:
        {log_dir}/focused_crawler_{run_id}.log   – Vollprotokoll (JSON-Lines)
        {log_dir}/relevance_{run_id}.log          – Nur Relevanz-Events (CSV)
        {log_dir}/privacy_{run_id}.log            – Nur DSGVO-Events
        {log_dir}/evaluation_{run_id}.log         – Evaluationsergebnisse (JSON)
    """

    def __init__(
        self,
        run_id: str = "run",
        log_dir: str = "logs",
        console_level: str = "INFO",
        file_level: str = "DEBUG",
        use_color: bool = True,
    ) -> None:
        self.run_id = run_id
        self._use_color = use_color and sys.stdout.isatty()
        self._console_level = console_level
        self._file_level = file_level
        self._start_time = time.time()

        # Log-Verzeichnis erstellen
        self._log_dir = Path(log_dir)
        self._log_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '_', run_id)

        # Datei-Handler
        self._main_log  = open(self._log_dir / f"focused_crawler_{safe_id}_{ts}.log", "w", encoding="utf-8")
        self._rel_log   = open(self._log_dir / f"relevance_{safe_id}_{ts}.csv", "w", encoding="utf-8")
        self._priv_log  = open(self._log_dir / f"privacy_{safe_id}_{ts}.log", "w", encoding="utf-8")
        self._eval_log  = open(self._log_dir / f"evaluation_{safe_id}_{ts}.json", "w", encoding="utf-8")

        # CSV-Header für Relevanz-Log
        self._rel_log.write(
            "timestamp,url,score,tfidf_score,bayes_score,is_relevant,"
            "top_category,confidence,matched_keywords\n"
        )

        # Startmeldung
        self._log_to_main("SYSTEM", "INFO", "Logger gestartet", {
            "run_id": run_id,
            "log_dir": str(self._log_dir.resolve()),
            "console_level": console_level,
            "file_level": file_level,
        })
        self._console_print("SYSTEM", "INFO", f"Logger gestartet – Run-ID: {run_id} | Logs: {self._log_dir}/")

    # ------------------------------------------------------------------
    # Öffentliche Logging-Methoden
    # ------------------------------------------------------------------

    def debug(self, component: str, msg: str, **kwargs) -> None:
        self._emit(component, "DEBUG", msg, kwargs)

    def info(self, component: str, msg: str, **kwargs) -> None:
        self._emit(component, "INFO", msg, kwargs)

    def warn(self, component: str, msg: str, **kwargs) -> None:
        self._emit(component, "WARN", msg, kwargs)

    def error(self, component: str, msg: str, **kwargs) -> None:
        self._emit(component, "ERROR", msg, kwargs)

    def ok(self, component: str, msg: str, **kwargs) -> None:
        """Erfolgreiche Abschluss-Events (grün)."""
        self._emit(component, "OK", msg, kwargs)

    def relevance(
        self,
        url: str,
        score: float,
        tfidf_score: float,
        bayes_score: float,
        is_relevant: bool,
        top_category: str,
        confidence: float,
        matched_keywords: List[str],
    ) -> None:
        """
        Loggt eine Relevanzberechnung.
        Wird in das Vollprotokoll UND in die CSV-Datei (relevance_*.csv) geschrieben.
        """
        ts = self._ts()
        level = "OK" if is_relevant else "INFO"
        marker = "✅ RELEVANT" if is_relevant else "⬜ irrelev."

        self._emit("RELEVANCE", level,
            f"{marker} Score={score:.4f} (TF-IDF={tfidf_score:.3f}, BCW={bayes_score:.3f}) "
            f"Cat={top_category} Conf={confidence:.3f} | {url[:70]}",
            {"url": url, "score": score, "tfidf": tfidf_score, "bayes": bayes_score,
             "is_relevant": is_relevant, "category": top_category,
             "confidence": confidence, "matched_kw": matched_keywords}
        )

        # CSV-Zeile
        kw_str = "|".join(matched_keywords[:10]).replace(",", ";")
        self._rel_log.write(
            f"{ts},{url},{score},{tfidf_score},{bayes_score},"
            f"{is_relevant},{top_category},{confidence},\"{kw_str}\"\n"
        )
        self._rel_log.flush()

    def privacy(
        self,
        url: str,
        event: str,
        details: str = "",
        counts: Optional[Dict[str, int]] = None,
    ) -> None:
        """
        Loggt ein Datenschutz-Event (AUDIT-Level – immer gespeichert).
        Events: PII_REMOVED, SENSITIVE_URL_SKIPPED, ROBOTS_DISALLOWED,
                DOMAIN_GUARD, HASH_DUPLICATE
        """
        payload = {"url": url, "event": event, "details": details}
        if counts:
            payload["pii_counts"] = counts

        self._emit("PRIVACY", "AUDIT", f"{event} | {details} | {url[:70]}", payload)

        # Privacy-Log (immer schreiben, unabhängig vom Level-Filter)
        entry = {"ts": self._ts(), "event": event, "url": url,
                 "details": details, **(counts or {})}
        self._priv_log.write(json.dumps(entry, ensure_ascii=False) + "\n")
        self._priv_log.flush()

    def crawl_step(
        self,
        url: str,
        step: str,
        status: int = 0,
        page_num: int = 0,
        total: int = 0,
        queue_size: int = 0,
        elapsed_s: float = 0.0,
        extra: Optional[Dict] = None,
    ) -> None:
        """
        Loggt einen einzelnen Crawl-Schritt mit allen relevanten Metriken.

        Steps: FETCH, PARSE, CLASSIFY, QUEUE_UPDATE, SKIP, DUPLICATE,
               ROBOTS_CHECK, DELAY, PDF_EXTRACT, BLOCK_SEGMENT
        """
        msg = (
            f"[{page_num:>3}/{total}] {step:<15} "
            f"HTTP={status} Q={queue_size} t={elapsed_s:.1f}s | {url[:60]}"
        )
        payload = {
            "url": url, "step": step, "http_status": status,
            "page_num": page_num, "total": total,
            "queue_size": queue_size, "elapsed_s": elapsed_s,
            **(extra or {})
        }
        self._emit("CRAWL", "DEBUG", msg, payload)

    def cpe_score(
        self,
        url: str,
        cpe: float,
        anchor: float,
        context: float,
        url_score: float,
        page: float,
        is_priority: bool,
    ) -> None:
        """Loggt den CPE-Score eines Links (DEBUG-Level)."""
        msg = (
            f"CPE={cpe:.3f} "
            f"[A={anchor:.2f} C={context:.2f} U={url_score:.2f} P={page:.2f}] "
            f"{'⭐PRIO' if is_priority else '     '} {url[:55]}"
        )
        self._emit("CPE", "DEBUG", msg, {
            "url": url, "cpe": cpe, "anchor": anchor,
            "context": context, "url_score": url_score,
            "page": page, "is_priority": is_priority,
        })

    def evaluation(
        self,
        report_dict: Dict[str, Any],
        label: str = "FOCUSED",
    ) -> None:
        """
        Loggt den vollständigen Evaluationsbericht.
        Wird in evaluation_*.json geschrieben.
        """
        hr  = report_dict.get("harvest_rate", 0)
        rec = report_dict.get("recall", 0)
        f1  = report_dict.get("f1_score", 0)
        imp = report_dict.get("improvement_vs_baseline", 0)
        total = report_dict.get("total_crawled", 0)
        rel   = report_dict.get("total_relevant", 0)

        self._emit("EVALUATION", "OK",
            f"[{label}] HR={hr:.4f} ({hr*100:.1f}%) "
            f"Recall={rec:.4f} F1={f1:.4f} "
            f"Relevant={rel}/{total} "
            f"Δ_BFS={imp:+.1f}%",
            {"label": label, **report_dict}
        )

        # Separater Eval-Log mit vollem Bericht
        entry = {"ts": self._ts(), "label": label, "report": report_dict}
        self._eval_log.write(json.dumps(entry, indent=2, ensure_ascii=False) + "\n")
        self._eval_log.flush()

    def section(self, title: str) -> None:
        """Gibt eine visuelle Trennlinie mit Titel aus (nur Konsole)."""
        line = "─" * 70
        if self._use_color:
            print(f"\n{_C.BOLD}{_C.BLUE}{line}{_C.RESET}")
            print(f"{_C.BOLD}{_C.BLUE}  {title}{_C.RESET}")
            print(f"{_C.BOLD}{_C.BLUE}{line}{_C.RESET}\n")
        else:
            print(f"\n{line}\n  {title}\n{line}\n")

    def close(self) -> None:
        """Schließt alle Log-Dateien sauber."""
        elapsed = time.time() - self._start_time
        self._log_to_main("SYSTEM", "INFO", "Logger beendet", {"elapsed_s": round(elapsed, 2)})
        self._console_print("SYSTEM", "INFO", f"Logger beendet – Laufzeit: {elapsed:.1f}s")
        for fh in [self._main_log, self._rel_log, self._priv_log, self._eval_log]:
            try:
                fh.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Interne Methoden
    # ------------------------------------------------------------------

    def _emit(self, component: str, level: str, msg: str, payload: Dict) -> None:
        """Schreibt in alle relevanten Kanäle."""
        self._log_to_main(component, level, msg, payload)
        if self._should_console(level):
            self._console_print(component, level, msg)

    def _log_to_main(self, component: str, level: str, msg: str, payload: Dict) -> None:
        if not self._should_file(level):
            return
        entry = {
            "ts":        self._ts(),
            "run_id":    self.run_id,
            "level":     level,
            "component": component,
            "msg":       msg,
            **payload,
        }
        try:
            self._main_log.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
            self._main_log.flush()
        except Exception:
            pass

    def _console_print(self, component: str, level: str, msg: str) -> None:
        icon  = _COMPONENT_ICONS.get(component, "•")
        color = _LEVEL_COLORS.get(level, "")
        ts    = datetime.now().strftime("%H:%M:%S")
        if self._use_color:
            line = (
                f"{_C.GRAY}[{ts}]{_C.RESET} "
                f"{icon} "
                f"{color}{level:<5}{_C.RESET} "
                f"{_C.BOLD}{component:<10}{_C.RESET} "
                f"{msg}"
            )
        else:
            line = f"[{ts}] {level:<5} {component:<10} {icon} {msg}"
        print(line)

    def _should_console(self, level: str) -> bool:
        order = ["DEBUG", "INFO", "OK", "WARN", "ERROR", "AUDIT"]
        try:
            return order.index(level) >= order.index(self._console_level)
        except ValueError:
            return True

    def _should_file(self, level: str) -> bool:
        order = ["DEBUG", "INFO", "OK", "WARN", "ERROR", "AUDIT"]
        try:
            return order.index(level) >= order.index(self._file_level)
        except ValueError:
            return True

    @staticmethod
    def _ts() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
