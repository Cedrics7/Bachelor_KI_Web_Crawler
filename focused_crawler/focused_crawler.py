"""
focused_crawler.py
==================
Hauptmodul des Focused Crawlers für die Bachelorthesis.

Eigenständiger, vollständig neuer Crawler – kein Code aus crawler_js oder
Bachelor_Crawler wird übernommen oder ersetzt.

Versionsverlauf:
    v1.0 – Grundimplementierung (BCW, CPE, Evaluation)
    v1.1 – Vollständiges Step-Logging via CrawlerLogger
           Folgende Änderungen werden jetzt geloggt:
             - CRAWL.FETCH        : HTTP-Request + Statuscode + Ladezeit
             - CRAWL.PARSE        : HTML-Parsing + Anzahl Links/Blöcke
             - RELEVANCE          : Score, TF-IDF, BCW, Kategorie, Keywords
             - CPE                : Teilscores aller Links (DEBUG-Level)
             - CRAWL.QUEUE_UPDATE : Queue-Größe nach jedem Update
             - PRIVACY.PII_REMOVED: Anzahl entfernter PII-Felder
             - PRIVACY.SENSITIVE_URL_SKIPPED: URL + Muster
             - ROBOTS.DISALLOWED  : URL + User-Agent
             - ROBOTS.ALLOWED     : URL (DEBUG)
             - CRAWL.DUPLICATE    : Hash-Duplikate
             - CRAWL.DOMAIN_GUARD : Externe Domain-Redirects
             - CRAWL.PDF_EXTRACT  : PDF-URL + Textlänge
             - EVALUATION.*       : Harvest Rate, Precision, Recall, F1
             - SYSTEM             : Start, Stop, Konfiguration
"""

import hashlib
import re
import time
import warnings
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .domain_model import DomainModel
from .relevance_classifier import RelevanceClassifier, RelevanceResult
from .link_prioritizer import LinkPrioritizer
from .evaluation import CrawlEvaluator, EvaluationReport
from .crawler_logger import CrawlerLogger

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: Dict = {
    "user_agent":           "BachelorCrawler/1.0 (Focused Crawler – Bachelorthesis)",
    "timeout_seconds":      10,
    "max_redirects":        5,
    "crawl_delay_default":  1.0,
    "relevance_threshold":  0.15,
    "priority_threshold":   0.10,
    "robots_respect":       True,
    "robots_timeout":       8,
    "privacy_filter_pii":   True,
    "max_pages":            100,
    "max_queue":            300,
    "ram_warn_mb":          1500,
    "log_dir":              "logs",
    "log_console_level":    "INFO",   # DEBUG = alle CPE-Scores sichtbar
    "log_file_level":       "DEBUG",  # DEBUG = vollständiges Protokoll
}

_RE_EMAIL = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
_RE_PHONE = re.compile(r'(?:(?:\+49|0049|0)[\s\-.]?)(?:\(?\d{2,5}\)?[\s\-.]?)?\d{3,}[\s\-.]?\d{3,}(?:[\s\-.]?\d{1,4})?')
_RE_IBAN = re.compile(r'\b[A-Z]{2}\d{2}[0-9A-Z]{11,30}\b')


@dataclass
class CrawlResult:
    url: str
    text: str
    relevance: RelevanceResult
    content_hash: str
    is_pdf: bool = False
    http_status: int = 200
    blocks: List[str] = field(default_factory=list)
    fetch_time_ms: float = 0.0


class FocusedCrawler:
    """
    Eigenständiger Focused Crawler für die Bachelorthesis.

    Vollständiges Logging aller Schritte via CrawlerLogger:
        - Jeder HTTP-Request (URL, Status, Ladezeit)
        - Jede Relevanzberechnung (Score, TF-IDF, BCW, Kategorie)
        - Jede PII-Entfernung (Typ, Anzahl, URL)
        - Jede robots.txt-Entscheidung
        - CPE-Teilscores aller Links (DEBUG)
        - Evaluationsmetriken nach Crawl-Ende
    """

    def __init__(
        self,
        config: Optional[Dict] = None,
        run_id: Optional[str] = None,
        logger: Optional[CrawlerLogger] = None,
    ) -> None:
        self._config = {**DEFAULT_CONFIG, **(config or {})}
        self._domain_model = DomainModel()
        self._classifier = RelevanceClassifier(
            domain_model=self._domain_model,
            relevance_threshold=self._config["relevance_threshold"],
        )
        self._prioritizer = LinkPrioritizer(
            domain_model=self._domain_model,
            priority_threshold=self._config["priority_threshold"],
        )
        self._robots = self._init_robots_checker()
        self._http_headers = {"User-Agent": self._config["user_agent"]}
        self._external_logger: Optional[CrawlerLogger] = None

        # Logger: extern injiziert (Baseline-Eval) oder neu erstellen
        if logger:
            self._logger = logger
            self._owns_logger = False
        else:
            from urllib.parse import urlparse as _up
            _rid = run_id or "focused_run"
            self._logger = CrawlerLogger(
                run_id=_rid,
                log_dir=self._config.get("log_dir", "logs"),
                console_level=self._config.get("log_console_level", "INFO"),
                file_level=self._config.get("log_file_level", "DEBUG"),
            )
            self._owns_logger = True

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def crawl(
        self,
        start_url: str,
        max_pages: Optional[int] = None,
        reference_corpus_size: Optional[int] = None,
    ) -> Tuple[List[CrawlResult], EvaluationReport]:
        limit     = max_pages or self._config["max_pages"]
        evaluator = CrawlEvaluator(
            start_url=start_url,
            reference_corpus_size=reference_corpus_size,
        )

        self._logger.section(f"FOCUSED CRAWLER STARTET: {start_url[:60]}")
        self._logger.info("SYSTEM", "Crawl gestartet",
            url=start_url, max_pages=limit,
            relevance_threshold=self._config["relevance_threshold"],
            priority_threshold=self._config["priority_threshold"],
            robots_respect=self._config["robots_respect"],
            privacy_filter=self._config["privacy_filter_pii"],
        )

        visited_hashes : set = set()
        visited_urls   : set = set()
        queue: List[Tuple[str, str, str]] = [(start_url, "", "")]
        results        : List[CrawlResult] = []
        base_domain    = urlparse(start_url).netloc
        status_log     : Dict[str, str] = {}
        robots_blocked = 0
        crawl_start    = time.time()

        try:
            with httpx.Client(
                follow_redirects=True,
                max_redirects=self._config["max_redirects"],
                headers=self._http_headers,
                timeout=self._config["timeout_seconds"],
            ) as client:
                while queue and len(results) < limit:
                    curr_url, anchor, ctx = queue.pop(0)

                    if curr_url in visited_urls:
                        continue
                    visited_urls.add(curr_url)

                    page_num = len(results) + 1

                    # --------------------------------------------------
                    # robots.txt-Check
                    # --------------------------------------------------
                    if self._robots and not self._robots.is_allowed(curr_url):
                        self._logger.privacy(
                            curr_url, "ROBOTS_DISALLOWED",
                            f"UA: {self._config['user_agent'][:40]}"
                        )
                        status_log[curr_url] = "ROBOTS_DISALLOWED"
                        evaluator.add_robots_blocked()
                        robots_blocked += 1
                        continue
                    else:
                        self._logger.debug("ROBOTS", f"Erlaubt: {curr_url[:70]}")

                    # --------------------------------------------------
                    # Crawl-Delay
                    # --------------------------------------------------
                    delay = self._config["crawl_delay_default"]
                    if self._robots:
                        delay = max(delay, self._robots.get_crawl_delay(curr_url))
                        self._robots.wait_for_crawl_delay(curr_url)
                    else:
                        time.sleep(delay)
                    self._logger.crawl_step(
                        curr_url, "DELAY",
                        page_num=page_num, total=limit,
                        queue_size=len(queue),
                        extra={"delay_s": delay}
                    )

                    # --------------------------------------------------
                    # HTTP-Request
                    # --------------------------------------------------
                    t0 = time.time()
                    try:
                        resp = client.get(curr_url)
                    except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as e:
                        self._logger.error("HTTP", f"Request-Fehler: {str(e)[:60]}", url=curr_url)
                        status_log[curr_url] = f"ERROR:{str(e)[:40]}"
                        continue
                    fetch_ms = (time.time() - t0) * 1000

                    if self._robots:
                        self._robots.record_access(curr_url)

                    # --------------------------------------------------
                    # Domain-Guard
                    # --------------------------------------------------
                    final_domain = urlparse(str(resp.url)).netloc
                    if self._strip_www(final_domain) != self._strip_www(base_domain):
                        self._logger.privacy(
                            curr_url, "DOMAIN_GUARD",
                            f"Externe Domain: {final_domain}"
                        )
                        status_log[curr_url] = f"EXTERNAL:{final_domain}"
                        continue

                    self._logger.crawl_step(
                        curr_url, "FETCH",
                        status=resp.status_code,
                        page_num=page_num, total=limit,
                        queue_size=len(queue),
                        elapsed_s=fetch_ms / 1000,
                        extra={"content_length": len(resp.content), "final_url": str(resp.url)}
                    )

                    if resp.status_code != 200:
                        status_log[curr_url] = str(resp.status_code)
                        continue

                    is_pdf = curr_url.lower().endswith(".pdf")
                    raw_bytes = resp.content

                    # --------------------------------------------------
                    # Duplikat-Check
                    # --------------------------------------------------
                    content_hash = hashlib.sha256(raw_bytes).hexdigest()
                    if content_hash in visited_hashes:
                        self._logger.privacy(
                            curr_url, "HASH_DUPLICATE",
                            f"Hash: {content_hash[:16]}…"
                        )
                        evaluator.add_skipped()
                        continue
                    visited_hashes.add(content_hash)

                    # --------------------------------------------------
                    # Text extrahieren
                    # --------------------------------------------------
                    if is_pdf:
                        text = self._extract_pdf_text(curr_url)
                        blocks = []
                        self._logger.crawl_step(
                            curr_url, "PDF_EXTRACT",
                            page_num=page_num, total=limit,
                            queue_size=len(queue),
                            extra={"text_len": len(text)}
                        )
                    else:
                        raw_html = resp.text
                        text, blocks, new_links = self._extract_html(
                            html=raw_html,
                            base_url=curr_url,
                            base_domain=base_domain,
                        )

                        self._logger.crawl_step(
                            curr_url, "PARSE",
                            status=resp.status_code,
                            page_num=page_num, total=limit,
                            queue_size=len(queue),
                            extra={
                                "links_found": len(new_links),
                                "blocks_found": len(blocks),
                                "text_len": len(text),
                            }
                        )

                        # CPE-Linkpriorisierung
                        scored_links = self._prioritizer.score_links(
                            links=new_links, page_text=text
                        )

                        prio_count = 0
                        for sl in scored_links:
                            # CPE-Score jedes Links loggen (DEBUG)
                            self._logger.cpe_score(
                                sl.url, sl.cpe_score,
                                sl.anchor_score, sl.context_score,
                                sl.url_score, sl.page_score,
                                sl.is_priority,
                            )
                            if sl.url not in visited_urls and len(queue) < self._config["max_queue"]:
                                entry = (sl.url, sl.anchor_text, "")
                                if sl.is_priority or sl.is_pdf:
                                    queue.insert(0, entry)
                                    prio_count += 1
                                else:
                                    queue.append(entry)

                        self._logger.debug(
                            "QUEUE",
                            f"Queue nach Update: {len(queue)} URLs "
                            f"({prio_count} priorisiert)",
                            queue_size=len(queue), prio_added=prio_count
                        )

                    # --------------------------------------------------
                    # DSGVO: PII-Filter
                    # --------------------------------------------------
                    if self._config["privacy_filter_pii"]:
                        text, pii_counts = self._filter_pii_with_counts(text)
                        total_pii = sum(pii_counts.values())
                        if total_pii > 0:
                            self._logger.privacy(
                                curr_url, "PII_REMOVED",
                                f"Gesamt: {total_pii} Einträge entfernt",
                                counts=pii_counts
                            )

                    # --------------------------------------------------
                    # Relevanzklassifikation
                    # --------------------------------------------------
                    relevance = self._classifier.classify(text=text, url=curr_url)
                    self._logger.relevance(
                        url=curr_url,
                        score=relevance.score,
                        tfidf_score=relevance.tfidf_score,
                        bayes_score=relevance.bayes_score,
                        is_relevant=relevance.is_relevant,
                        top_category=relevance.top_category,
                        confidence=relevance.confidence,
                        matched_keywords=relevance.matched_keywords,
                    )

                    result = CrawlResult(
                        url=curr_url,
                        text=text,
                        relevance=relevance,
                        content_hash=content_hash,
                        is_pdf=is_pdf,
                        http_status=resp.status_code,
                        blocks=blocks,
                        fetch_time_ms=round(fetch_ms, 1),
                    )
                    results.append(result)
                    evaluator.add_result(relevance, is_pdf=is_pdf)

        except Exception as e:
            self._logger.error("SYSTEM", f"Crawler-Fehler: {e}")

        # ------------------------------------------------------------------
        # Abschluss
        # ------------------------------------------------------------------
        elapsed = time.time() - crawl_start
        self._logger.info(
            "SYSTEM", "Crawl beendet",
            total_crawled=len(results),
            elapsed_s=round(elapsed, 2),
            robots_blocked=robots_blocked,
        )

        report = evaluator.get_report()
        self._logger.evaluation(report.to_dict(), label="FOCUSED")

        if self._owns_logger:
            self._logger.close()

        return results, report

    def set_relevance_threshold(self, threshold: float) -> None:
        self._config["relevance_threshold"] = threshold
        self._classifier = RelevanceClassifier(
            domain_model=self._domain_model,
            relevance_threshold=threshold,
        )

    def get_domain_model(self) -> DomainModel:
        return self._domain_model

    # ------------------------------------------------------------------
    # HTML-Verarbeitung mit Content-Block-Segmentierung
    # ------------------------------------------------------------------

    def _extract_html(
        self, html: str, base_url: str, base_domain: str
    ) -> Tuple[str, List[str], List[Tuple[str, str, str]]]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        full_text = soup.get_text(separator=" ", strip=True)

        blocks: List[str] = []
        for block_tag in soup.find_all(["div", "section", "article", "main"]):
            block_text = block_tag.get_text(separator=" ", strip=True)
            if len(block_text) > 100:
                score, _ = self._domain_model.score_text(block_text)
                if score > 0.05:
                    blocks.append(block_text[:500])

        links: List[Tuple[str, str, str]] = []
        for a_tag in soup.find_all("a", href=True):
            href = a_tag.get("href", "")
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if self._strip_www(parsed.netloc) != self._strip_www(base_domain):
                continue
            if not parsed.scheme.startswith("http"):
                continue
            anchor_text = a_tag.get_text(strip=True)[:200]
            context = ""
            parent = a_tag.find_parent(["p", "li", "div", "td"])
            if parent:
                context = parent.get_text(separator=" ", strip=True)[:300]
            links.append((full_url, anchor_text, context))

        soup.decompose()
        return full_text, blocks[:10], links

    # ------------------------------------------------------------------
    # Hilfsmethoden
    # ------------------------------------------------------------------

    def _extract_pdf_text(self, url: str) -> str:
        try:
            import io, urllib.request
            with urllib.request.urlopen(url, timeout=self._config["timeout_seconds"]) as r:
                data = r.read()
            try:
                from pdfminer.high_level import extract_text
                return extract_text(io.BytesIO(data))[:50_000]
            except ImportError:
                return f"[PDF – pdfminer nicht installiert: {url}]"
        except Exception as e:
            return f"[PDF-Fehler: {str(e)[:60]}]"

    @staticmethod
    def _filter_pii_with_counts(text: str) -> Tuple[str, Dict[str, int]]:
        email_count = len(_RE_EMAIL.findall(text))
        text = _RE_EMAIL.sub("[E-MAIL ENTFERNT]", text)

        iban_count = len(_RE_IBAN.findall(text))
        text = _RE_IBAN.sub("[IBAN ENTFERNT]", text)

        phone_count = len(_RE_PHONE.findall(text))
        text = _RE_PHONE.sub("[TEL ENTFERNT]", text)

        return text, {"email": email_count, "phone": phone_count, "iban": iban_count}

    @staticmethod
    def _strip_www(netloc: str) -> str:
        return netloc.removeprefix("www.")

    def _init_robots_checker(self):
        if not self._config.get("robots_respect", True):
            return None
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Bachelor_Crawler"))
            from robots_checker import RobotsChecker
            return RobotsChecker(
                user_agent=self._config["user_agent"],
                timeout=self._config.get("robots_timeout", 8),
            )
        except ImportError:
            return None
