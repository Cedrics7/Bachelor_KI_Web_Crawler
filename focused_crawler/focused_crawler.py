"""
focused_crawler.py
==================
Hauptmodul des Focused Crawlers für die Bachelorthesis.

Eigenständiger, vollständig neuer Crawler – kein Code aus crawler_js oder
Bachelor_Crawler wird übernommen oder ersetzt. Dieser Crawler implementiert
die wissenschaftlich geforderten Bausteine eines Focused Crawlers:

    ✅ Domänenmodell (KRS nach Hernandez et al. 2020)
    ✅ Relevanzberechnung + BCW-Klassifikator (Liu et al. 2025 / Joe Dhanith et al. 2024)
    ✅ CPE-Linkpriorisierung (Liu et al. 2025)
    ✅ robots.txt-Compliance (RFC 9309)
    ✅ DSGVO-PII-Filter (Art. 5, 6, 25 DSGVO)
    ✅ Evaluationsmetriken: Harvest Rate, Precision, Recall, F1 (Literaturstandard)
    ✅ Content-Block-Segmentierung für Tunneling (Liu et al. 2025)

Architektur:
    FocusedCrawler
    ├── DomainModel          – KRS-Domänenrepräsentation
    ├── RelevanceClassifier  – BCW + TF-IDF Ensemble
    ├── LinkPrioritizer      – CPE-basierte Queue-Priorisierung
    ├── CrawlEvaluator       – Harvest Rate, Precision, Recall, F1
    └── (RobotsChecker)      – aus Bachelor_Crawler importiert
"""

import hashlib
import re
import time
import warnings
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from .domain_model import DomainModel
from .relevance_classifier import RelevanceClassifier, RelevanceResult
from .link_prioritizer import LinkPrioritizer
from .evaluation import CrawlEvaluator, EvaluationReport

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
}

# PII-Regex-Pattern
_RE_EMAIL = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}')
_RE_PHONE = re.compile(r'(?:(?:\+49|0049|0)[\s\-.]?)(?:\(?\d{2,5}\)?[\s\-.]?)?\d{3,}[\s\-.]?\d{3,}(?:[\s\-.]?\d{1,4})?')
_RE_IBAN  = re.compile(r'\b[A-Z]{2}\d{2}(?:\s?\d{4}){4,7}\b')


# ---------------------------------------------------------------------------
# Crawl-Ergebnis Datenklasse
# ---------------------------------------------------------------------------

@dataclass
class CrawlResult:
    """
    Ergebnis eines einzelnen gecrawlten Dokuments.

    Attribute:
        url:             URL der Seite/PDF
        text:            Extrahierter, PII-gefilterter Text
        relevance:       Vollständiges RelevanceResult (Score, Klasse, Confidence)
        content_hash:    SHA256 des Rohinhalts (Duplikat-Erkennung)
        is_pdf:          True wenn Dokument ein PDF ist
        http_status:     HTTP-Status-Code
        blocks:          Content-Blöcke (Tunneling nach Liu et al. 2025)
    """
    url: str
    text: str
    relevance: RelevanceResult
    content_hash: str
    is_pdf: bool = False
    http_status: int = 200
    blocks: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Hauptklasse
# ---------------------------------------------------------------------------

class FocusedCrawler:
    """
    Eigenständiger Focused Crawler für die Bachelorthesis.

    Implementiert die wissenschaftlich geforderten Kernbausteine:
    Domänenmodell, Relevanzklassifikator, CPE-Linkpriorisierung und Evaluation.

    Verwendung:
        crawler = FocusedCrawler()
        results, report = crawler.crawl(
            start_url="https://www.musterstadt.de",
            max_pages=100,
        )
        report.print_summary()
        print(report.to_json())  # für Thesis-Dokumentation
    """

    def __init__(self, config: Optional[Dict] = None) -> None:
        self._config = {**DEFAULT_CONFIG, **(config or {})}

        # Geteilte Domänenmodell-Instanz (alle Module nutzen dasselbe Modell)
        self._domain_model = DomainModel()

        # Klassifikator und Priorisierer
        self._classifier = RelevanceClassifier(
            domain_model=self._domain_model,
            relevance_threshold=self._config["relevance_threshold"],
        )
        self._prioritizer = LinkPrioritizer(
            domain_model=self._domain_model,
            priority_threshold=self._config["priority_threshold"],
        )

        # robots.txt-Checker (aus Bachelor_Crawler – falls verfügbar)
        self._robots = self._init_robots_checker()

        self._http_headers = {"User-Agent": self._config["user_agent"]}

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def crawl(
        self,
        start_url: str,
        max_pages: Optional[int] = None,
        reference_corpus_size: Optional[int] = None,
    ) -> Tuple[List[CrawlResult], EvaluationReport]:
        """
        Startet den Focused Crawler ab start_url.

        Args:
            start_url:              Einstiegs-URL
            max_pages:              Max. Seitenanzahl (überschreibt Config)
            reference_corpus_size:  Bekannte Gesamtzahl relevanter Seiten (für Recall)

        Returns:
            (results, report)
            results: Liste aller CrawlResults (inkl. Relevanz-Score)
            report:  EvaluationReport mit Harvest Rate, Precision, Recall, F1
        """
        limit = max_pages or self._config["max_pages"]
        evaluator = CrawlEvaluator(
            start_url=start_url,
            reference_corpus_size=reference_corpus_size,
        )

        visited_hashes: set = set()
        visited_urls: set = set()
        # Queue: Liste von (url, anchor_text, context_text)
        queue: List[Tuple[str, str, str]] = [(start_url, "", "")]
        results: List[CrawlResult] = []
        base_domain = urlparse(start_url).netloc
        status_log: Dict[str, str] = {}
        robots_blocked = 0

        self._log(f"🎓 Focused Crawler startet: {start_url[:60]}")
        self._log(f"📊 Relevanz-Schwellwert: {self._config['relevance_threshold']}")
        self._log(f"🔗 CPE-Priorität-Schwellwert: {self._config['priority_threshold']}")

        try:
            with httpx.Client(
                follow_redirects=True,
                max_redirects=self._config["max_redirects"],
                headers=self._http_headers,
                timeout=self._config["timeout_seconds"],
            ) as client:
                while queue and len(results) < limit:
                    curr_url, _, _ = queue.pop(0)

                    if curr_url in visited_urls:
                        continue
                    visited_urls.add(curr_url)

                    # robots.txt-Check
                    if self._robots and not self._robots.is_allowed(curr_url):
                        status_log[curr_url] = "ROBOTS_DISALLOWED"
                        evaluator.add_robots_blocked()
                        robots_blocked += 1
                        continue

                    # Crawl-Delay
                    if self._robots:
                        self._robots.wait_for_crawl_delay(curr_url)
                    else:
                        time.sleep(self._config["crawl_delay_default"])

                    try:
                        resp = client.get(curr_url)
                    except (httpx.TimeoutException, httpx.ConnectError, httpx.RequestError) as e:
                        status_log[curr_url] = f"ERROR:{str(e)[:40]}"
                        continue

                    if self._robots:
                        self._robots.record_access(curr_url)

                    # Domain-Guard: kein Verlassen der Startdomain
                    final_domain = urlparse(str(resp.url)).netloc
                    if self._strip_www(final_domain) != self._strip_www(base_domain):
                        status_log[curr_url] = f"EXTERNAL:{final_domain}"
                        continue

                    if resp.status_code != 200:
                        status_log[curr_url] = str(resp.status_code)
                        continue

                    is_pdf = curr_url.lower().endswith(".pdf")
                    raw_bytes = resp.content

                    # Duplikat-Check via Content-Hash
                    content_hash = hashlib.sha256(raw_bytes).hexdigest()
                    if content_hash in visited_hashes:
                        evaluator.add_skipped()
                        continue
                    visited_hashes.add(content_hash)

                    # Text extrahieren
                    if is_pdf:
                        text, blocks = self._extract_pdf_text(curr_url), []
                    else:
                        raw_html = resp.text
                        text, blocks, new_links = self._extract_html(
                            html=raw_html,
                            base_url=curr_url,
                            base_domain=base_domain,
                        )

                        # CPE-Linkpriorisierung
                        scored_links = self._prioritizer.score_links(
                            links=new_links,
                            page_text=text,
                        )

                        # In Queue einreihen: Priority-Links vorne, Rest hinten
                        for sl in scored_links:
                            if sl.url not in visited_urls and len(queue) < self._config["max_queue"]:
                                entry = (sl.url, sl.anchor_text, "")
                                if sl.is_priority or sl.is_pdf:
                                    queue.insert(0, entry)  # vorne
                                else:
                                    queue.append(entry)  # hinten

                    # DSGVO: PII-Filter
                    if self._config["privacy_filter_pii"]:
                        text = self._filter_pii(text)

                    # Relevanzklassifikation
                    relevance = self._classifier.classify(text=text, url=curr_url)

                    result = CrawlResult(
                        url=curr_url,
                        text=text,
                        relevance=relevance,
                        content_hash=content_hash,
                        is_pdf=is_pdf,
                        http_status=resp.status_code,
                        blocks=blocks,
                    )
                    results.append(result)
                    evaluator.add_result(relevance, is_pdf=is_pdf)

                    rel_marker = "✅" if relevance.is_relevant else "⬜"
                    self._log(
                        f"{rel_marker} [{len(results):>3}/{limit}] "
                        f"Score={relevance.score:.3f} "
                        f"Cat={relevance.top_category:<15} "
                        f"{curr_url[:55]}"
                    )

        except Exception as e:
            self._log(f"❌ Crawler-Fehler: {e}")

        if robots_blocked:
            self._log(f"🤖 robots.txt: {robots_blocked} URL(s) gesperrt")

        report = evaluator.get_report()
        report.print_summary()
        return results, report

    def set_relevance_threshold(self, threshold: float) -> None:
        """Ändert den Relevanz-Schwellwert (nützlich für Evaluation verschiedener Schwellwerte)."""
        self._config["relevance_threshold"] = threshold
        self._classifier = RelevanceClassifier(
            domain_model=self._domain_model,
            relevance_threshold=threshold,
        )

    def get_domain_model(self) -> DomainModel:
        """Gibt das interne DomainModel zurück (für externe Anpassung)."""
        return self._domain_model

    # ------------------------------------------------------------------
    # HTML-Verarbeitung mit Content-Block-Segmentierung (Tunneling)
    # ------------------------------------------------------------------

    def _extract_html(
        self,
        html: str,
        base_url: str,
        base_domain: str,
    ) -> Tuple[str, List[str], List[Tuple[str, str, str]]]:
        """
        Extrahiert Text, Content-Blöcke und Links aus HTML.

        Content-Block-Segmentierung nach Liu et al. (2025):
        Jedes <div> und <section> wird als eigener Block behandelt.
        Blöcke mit Relevanz-Score > 0 werden für Tunneling genutzt,
        d.h. auch auf irrelevanten Seiten werden relevante Bereiche gefunden.

        Returns:
            (full_text, relevant_blocks, links)
            links: Liste von (url, anchor_text, context_text)
        """
        soup = BeautifulSoup(html, "html.parser")

        # Störende Elemente entfernen
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Volltext
        full_text = soup.get_text(separator=" ", strip=True)

        # Content-Block-Segmentierung (Tunneling)
        blocks: List[str] = []
        for block_tag in soup.find_all(["div", "section", "article", "main"]):
            block_text = block_tag.get_text(separator=" ", strip=True)
            if len(block_text) > 100:
                score, _ = self._domain_model.score_text(block_text)
                if score > 0.05:  # Nur relevante Blöcke speichern
                    blocks.append(block_text[:500])

        # Links mit Ankertext und Kontext extrahieren
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
            # Kontext: umgebender Paragraf oder übergeordnetes Div
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
        """Extrahiert Text aus einer PDF-URL via pdfminer (falls installiert)."""
        try:
            import io
            import urllib.request
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
    def _filter_pii(text: str) -> str:
        """DSGVO: Entfernt PII aus Text (Art. 25 – Privacy by Design)."""
        text = _RE_EMAIL.sub("[E-MAIL ENTFERNT]", text)
        text = _RE_PHONE.sub("[TEL ENTFERNT]", text)
        text = _RE_IBAN.sub("[IBAN ENTFERNT]", text)
        return text

    @staticmethod
    def _strip_www(netloc: str) -> str:
        return netloc.removeprefix("www.")

    def _init_robots_checker(self):
        """Versucht RobotsChecker aus Bachelor_Crawler zu importieren."""
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "Bachelor_Crawler"))
            from robots_checker import RobotsChecker
            return RobotsChecker(
                user_agent=self._config["user_agent"],
                timeout=self._config["robots_timeout"],
            )
        except ImportError:
            self._log("⚠️  RobotsChecker nicht gefunden – robots.txt wird nicht geprüft")
            return None

    @staticmethod
    def _log(msg: str) -> None:
        try:
            from Bachelor_Crawler.robots_checker import log_event
            log_event("", msg)
        except Exception:
            print(f"[FocusedCrawler] {msg}")
