"""
Vollständig kombinierter Crawler: Focused + DSGVO + robots + JS/VG-Fallback.
Konfiguration via config.py / .env (python-dotenv).
"""
from __future__ import annotations
import hashlib
import io
import re
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
from bs4 import BeautifulSoup

from .config import DEFAULT_CONFIG, OPENAI_API_KEY, OPENAI_BASE_URL
from .domain_model import DomainModel
from .relevance_classifier import RelevanceClassifier, RelevanceResult
from .link_prioritizer import LinkPrioritizer
from .evaluation import CrawlEvaluator, EvaluationReport
from .crawler_logger import CrawlerLogger
from .privacy_guard import PrivacyGuard
from .robots_checker import RobotsChecker
from .llm_client import LLMClient
from .db_client import DBClient

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_PDF_URL_RE = re.compile(r'https?://[^\s"'<>]+\.pdf', re.IGNORECASE)


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
    llm_result: Optional[dict] = None


class FocusedCrawler:
    def __init__(
        self,
        config: Optional[Dict] = None,
        run_id: Optional[str] = None,
        logger: Optional[CrawlerLogger] = None,
    ) -> None:
        self._config = {**DEFAULT_CONFIG, **(config or {})}
        self._domain_model = DomainModel()
        self._classifier = RelevanceClassifier(
            self._domain_model, self._config['relevance_threshold']
        )
        self._prioritizer = LinkPrioritizer(
            self._domain_model, self._config['priority_threshold']
        )
        self._privacy = PrivacyGuard()
        self._robots = (
            RobotsChecker(
                self._config['user_agent'], self._config['robots_timeout']
            )
            if self._config.get('robots_respect', True)
            else None
        )
        self._http_headers = {'User-Agent': self._config['user_agent']}
        self._logger = logger or CrawlerLogger(
            run_id=run_id or 'vollstaendig_run',
            log_dir=self._config['log_dir'],
        )
        self._owns_logger = logger is None
        self._run_id = run_id or 'vollstaendig_run'

        # LLM-Client (optional)
        self._llm: Optional[LLMClient] = None
        if self._config.get('llm_enabled'):
            self._llm = LLMClient(
                api_key=self._config.get('llm_api_key') or OPENAI_API_KEY,
                base_url=self._config.get('llm_base_url') or OPENAI_BASE_URL,
                model=self._config.get('llm_model', 'gpt-4o-mini'),
                max_tokens=self._config.get('llm_max_tokens', 512),
                temperature=self._config.get('llm_temperature', 0.0),
            )

        # DB-Client (optional)
        self._db: Optional[DBClient] = None
        if self._config.get('db_enabled'):
            self._db = DBClient(db_url=self._config.get('db_url', 'sqlite:///./bachelor_crawler.db'))

    def crawl(
        self,
        start_url: str,
        max_pages: Optional[int] = None,
        reference_corpus_size: Optional[int] = None,
    ) -> Tuple[List[CrawlResult], EvaluationReport]:
        limit = max_pages or self._config['max_pages']
        evaluator = CrawlEvaluator(
            start_url=start_url, reference_corpus_size=reference_corpus_size
        )
        visited_hashes, visited_urls = set(), set()
        queue: List[Tuple[str, str, str]] = [(start_url, '', '')]
        results: List[CrawlResult] = []
        base_domain = urlparse(start_url).netloc
        effective_domain, effective_start_path = base_domain, ''
        first_request = True

        with httpx.Client(
            follow_redirects=True,
            max_redirects=self._config['max_redirects'],
            headers=self._http_headers,
            timeout=self._config['timeout_seconds'],
        ) as client:
            while queue and len(results) < limit:
                curr_url, anchor, ctx = queue.pop(0)
                curr_base = self._get_url_base(curr_url)
                if curr_base in visited_urls or self._privacy.is_sensitive_url(curr_url):
                    evaluator.add_skipped()
                    continue
                visited_urls.add(curr_base)

                mem_mb = self._get_rss_mb()
                if mem_mb > self._config['ram_warn_mb']:
                    self._logger.info(
                        'SYSTEM', 'RAM-Warnung',
                        rss_mb=round(mem_mb, 1), queue_size=len(queue)
                    )

                if self._robots and not self._robots.is_allowed(curr_url):
                    evaluator.add_robots_blocked()
                    self._logger.privacy(curr_url, 'ROBOTS_DISALLOWED', 'robots.txt blockiert')
                    continue

                delay = max(
                    self._config['crawl_delay_default'],
                    self._robots.get_crawl_delay(curr_url) if self._robots else 0.0,
                )
                if self._robots:
                    self._robots.wait_for_crawl_delay(curr_url)
                elif delay:
                    time.sleep(delay)

                t0 = time.time()
                try:
                    resp = client.get(curr_url)
                except Exception as e:
                    self._logger.error(
                        'HTTP', f'Request-Fehler: {str(e)[:80]}', url=curr_url
                    )
                    continue

                if self._robots:
                    self._robots.record_access(curr_url)
                fetch_ms = (time.time() - t0) * 1000
                final_url = str(resp.url)
                final_domain = urlparse(final_url).netloc

                if first_request:
                    first_request = False
                    if (
                        self._strip_www(final_domain) != self._strip_www(base_domain)
                        and self._is_vg_redirect(base_domain, final_url)
                    ):
                        effective_domain = final_domain
                        effective_start_path = urlparse(final_url).path.rstrip('/')

                if self._strip_www(final_domain) != self._strip_www(effective_domain):
                    self._logger.privacy(
                        curr_url, 'DOMAIN_GUARD', f'Externe Domain: {final_domain}'
                    )
                    continue

                if resp.status_code != 200:
                    continue

                is_pdf = curr_url.lower().endswith('.pdf')
                content_hash = hashlib.sha256(resp.content).hexdigest()
                if content_hash in visited_hashes:
                    evaluator.add_skipped()
                    continue
                visited_hashes.add(content_hash)

                if is_pdf:
                    text = self._extract_pdf_text_bytes(resp.content)
                    blocks, new_links = [], []
                else:
                    raw_html = resp.text
                    if self._config.get('js_rendering') and self._is_js_rendered(raw_html):
                        js_html = self._fetch_with_playwright(curr_url)
                        if js_html and len(js_html) > len(raw_html):
                            raw_html = js_html
                    text, blocks, new_links = self._extract_html(
                        raw_html, curr_url, effective_domain, effective_start_path
                    )
                    scored_links = self._prioritizer.score_links(
                        new_links, page_text=text
                    )
                    for sl in scored_links:
                        if len(queue) >= self._config['max_queue']:
                            break
                        target_base = self._get_url_base(sl.url)
                        if target_base in visited_urls:
                            continue
                        entry = (sl.url, sl.anchor_text, '')
                        if sl.is_priority or sl.is_pdf:
                            queue.insert(0, entry)
                        else:
                            queue.append(entry)

                if self._config['privacy_filter_pii']:
                    text = self._privacy.filter_text(text, source_url=curr_url)

                relevance = self._classifier.classify(text=text, url=curr_url)

                # --- LLM-Analyse (optional) ---
                llm_result = None
                if self._llm and self._llm.available:
                    llm_result = self._llm.analyse(text, url=curr_url)
                    if llm_result:
                        self._logger.info(
                            'LLM', 'Analyse',
                            url=curr_url,
                            relevant=llm_result.get('relevant'),
                            confidence=llm_result.get('confidence'),
                        )

                result = CrawlResult(
                    curr_url, text, relevance, content_hash,
                    is_pdf, resp.status_code, blocks,
                    round(fetch_ms, 1), llm_result
                )
                results.append(result)
                evaluator.add_result(relevance, is_pdf=is_pdf)

                # --- DB-Persistierung (optional) ---
                if self._db:
                    self._db.save_result(self._run_id, result)

        report = evaluator.get_report()
        self._logger.evaluation(report.to_dict(), label='FOCUSED')
        if self._owns_logger:
            self._logger.close()
        if self._db:
            self._db.close()
        return results, report

    def _extract_html(
        self,
        html: str,
        base_url: str,
        effective_domain: str,
        effective_start_path: str,
    ) -> Tuple[str, List[str], List[Tuple[str, str, str]]]:
        soup = BeautifulSoup(html, 'html.parser')
        for tag in soup.find_all(['script', 'style', 'nav', 'footer', 'header']):
            tag.decompose()
        full_text = soup.get_text(separator=' ', strip=True)
        blocks = []
        for block_tag in soup.find_all(['div', 'section', 'article', 'main']):
            block_text = block_tag.get_text(separator=' ', strip=True)
            if len(block_text) > 100:
                score, _ = self._domain_model.score_text(block_text)
                if score > 0.05:
                    blocks.append(block_text[:500])
        bs_links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag.get('href', '')
            full_url = urljoin(base_url, href)
            parsed = urlparse(full_url)
            if self._strip_www(parsed.netloc) != self._strip_www(effective_domain):
                continue
            if effective_start_path and not parsed.path.startswith(effective_start_path):
                continue
            if not parsed.scheme.startswith('http'):
                continue
            anchor_text = a_tag.get_text(strip=True)[:200]
            parent = a_tag.find_parent(['p', 'li', 'div', 'td'])
            context = (
                parent.get_text(separator=' ', strip=True)[:300] if parent else ''
            )
            bs_links.append((full_url, anchor_text, context))
        regex_links = []
        for raw_url in _PDF_URL_RE.findall(html):
            if urlparse(raw_url).netloc == effective_domain:
                regex_links.append((raw_url, 'PDF', 'regex_pdf_scan'))
        seen: set = set()
        links = []
        for item in bs_links + regex_links:
            if item[0] not in seen:
                seen.add(item[0])
                links.append(item)
        soup.decompose()
        return full_text, blocks[:10], links

    def _extract_pdf_text_bytes(self, data: bytes) -> str:
        try:
            from pdfminer.high_level import extract_text
            return extract_text(io.BytesIO(data))[:50000]
        except Exception:
            return '[PDF-Extraktion nicht verfügbar]'

    def _is_js_rendered(self, html: str) -> bool:
        if len(html.strip()) < self._config.get('js_min_chars', 500):
            return True
        html_lower = html.lower()
        return any(
            m in html_lower
            for m in [
                '<noscript>', 'id="root"', "id='root'",
                'id="app"', "id='app'",
                'data-reactroot', 'ng-version', 'data-v-app',
            ]
        )

    def _fetch_with_playwright(self, url: str) -> Optional[str]:
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            timeout_ms = int(self._config.get('js_timeout', 20) * 1000)
            wait_until = self._config.get('js_wait_until', 'networkidle')
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page(user_agent=self._config['user_agent'])
                    page.goto(url, timeout=timeout_ms, wait_until=wait_until)
                    return page.content()
                except PWTimeout:
                    return None
                finally:
                    browser.close()
        except Exception:
            return None

    def _is_vg_redirect(self, base_domain: str, final_url: str) -> bool:
        slug = re.sub(
            r'\.[a-z]{2,}$', '', self._strip_www(base_domain)
        ).lower()
        variants = [slug]
        for prefix in ('stadt-', 'markt-', 'gemeinde-', 'bad-'):
            if slug.startswith(prefix):
                variants.append(slug[len(prefix):])
        path_segments = [
            s.lower() for s in urlparse(final_url).path.split('/') if s
        ]
        return any(v in path_segments for v in variants)

    def _get_rss_mb(self) -> float:
        if not _PSUTIL:
            return 0.0
        try:
            return psutil.Process().memory_info().rss / 1024 / 1024
        except Exception:
            return 0.0

    @staticmethod
    def _strip_www(netloc: str) -> str:
        return netloc.removeprefix('www.')

    @staticmethod
    def _get_url_base(url: str) -> str:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path.rstrip('/'), '', '', ''))
