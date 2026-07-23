"""
scraper_bachelor.py
===================
Hauptmodul des Bachelor_Crawlers.

Baut vollständig auf scraper_js.py (crawler_js v2.2) auf und erweitert ihn um:

    NEU (v3.0 – robots.txt-Compliance):
        - Alle URLs werden vor dem Crawlen gegen robots.txt geprüft
        - Crawl-Delay aus robots.txt wird automatisch eingehalten
        - RobotsChecker-Klasse (robots_checker.py) übernimmt Caching + Logging
        - Ablehnungen werden in status_log als "ROBOTS_DISALLOWED" eingetragen

    NEU (v3.0 – DSGVO-Datenschutz):
        - PII (E-Mails, Telefonnummern, IBAN) wird aus extrahiertem Text entfernt
        - Sensitive URLs (Login, Formulare, Bewerbungsportale) werden übersprungen
        - PrivacyGuard-Klasse (privacy_guard.py) übernimmt alle Filterungen
        - Datenschutz-Summary wird nach Crawl-Ende geloggt

    BEIBEHALTEN aus crawler_js:
        - JS-Rendering via Playwright (v2.0)
        - VG-Redirect-Unterstützung (v2.1)
        - Browser-User-Agent für httpx (v2.2)
        - Alle Hilfsfunktionen aus scraper.py (Import-Kette bleibt erhalten)
        - Rate-Limiter (rate_limiter.py)
        - Logger (logger.py)

Konfiguration (config_bachelor.py):
    CONFIG["robots_respect"]           – robots.txt einhalten (Standard: True)
    CONFIG["privacy_filter_pii"]       – PII filtern (Standard: True)
    CONFIG["privacy_skip_sensitive_urls"] – Sensitive URLs überspringen
    CONFIG["crawl_delay_default"]      – Fallback-Delay ohne robots.txt-Angabe
"""

import sys
import os
import re
import hashlib
import httpx
import time
import warnings
import concurrent.futures

try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin, urlparse

# --- Pfad zu crawler_js setzen (Import-Kette erhalten) ---
_CRAWLER_JS_PATH = os.path.join(os.path.dirname(__file__), "..", "crawler_js")
sys.path.insert(0, _CRAWLER_JS_PATH)

# --- Alle unveränderten Hilfsfunktionen aus crawler_js importieren ---
from scraper import (
    _safe_get,
    _strip_www,
    _get_rss_mb,
    extract_main_text,
    extract_pdf_text,
    is_relevant_url,
    get_url_base,
    get_content_hash,
    get_pdf_year,
    is_prio_pdf,
    assemble_text,
    _PDF_URL_RE,
    _MAX_REDIRECTS,
    _MAX_QUEUE,
    _RAM_WARN_MB,
)

# VG-Hilfsfunktionen aus scraper_js importieren (nicht duplizieren)
from scraper_js import (
    _extract_gemeinde_slug,
    _slug_variants,
    _is_vg_redirect,
    _is_js_rendered,
    _fetch_with_playwright,
)

# Bachelor_Crawler-spezifische Module
from config_bachelor import CONFIG, IGNORIERE_PARAMS
from robots_checker import RobotsChecker
from privacy_guard import PrivacyGuard

try:
    from logger import log_event, _write_console_log, get_german_time
except ImportError:
    def log_event(emoji, msg): print(f"{emoji} {msg}")
    def _write_console_log(msg): print(msg)
    def get_german_time(): return "00:00:00"

try:
    from rate_limiter import RateLimiter
except ImportError:
    RateLimiter = None

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# User-Agent aus CONFIG
_HTTP_USER_AGENT = CONFIG.get(
    "http_user_agent",
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


# ===========================================================================
# Haupt-Crawler-Funktion
# ===========================================================================

def get_subpages(start_url: str, max_pages: int):
    """
    Erweiterung von scraper_js.get_subpages() mit robots.txt-Compliance
    und DSGVO-konformer PII-Filterung.

    Args:
        start_url:  Einstiegs-URL der Gemeinde/Behörde
        max_pages:  Maximale Anzahl gecrawlter Seiten

    Returns:
        Identisches Format zu scraper.get_subpages():
        (html_collected, pdf_collected, skipped_urls, status_log, page_hashes)

        html_collected: list[(url, filtered_text)]  – PII bereits entfernt
        pdf_collected:  list[(url, filtered_text)]  – PII bereits entfernt
        skipped_urls:   list[str]                   – übersprungene URLs
        status_log:     dict[url, status]            – inkl. ROBOTS_DISALLOWED
        page_hashes:    dict[url_base, sha256]       – Duplikat-Erkennung
    """

    # --- Initialisierung ---
    robots_respect = CONFIG.get("robots_respect", True)
    privacy_filter = CONFIG.get("privacy_filter_pii", True)
    privacy_skip   = CONFIG.get("privacy_skip_sensitive_urls", True)
    delay_default  = CONFIG.get("crawl_delay_default", 1.0)
    delay_max      = CONFIG.get("crawl_delay_max", 10.0)
    js_rendering   = CONFIG.get("js_rendering", False)
    vg_max_queue   = CONFIG.get("vg_max_queue", 80)

    # robots.txt-Checker und DSGVO-Guard
    robots_ua = CONFIG.get("robots_user_agent", "BachelorCrawler")
    checker   = RobotsChecker(
        user_agent=robots_ua,
        timeout=CONFIG.get("robots_timeout", 10)
    ) if robots_respect else None
    guard     = PrivacyGuard(
        log_removals=CONFIG.get("privacy_log_removals", True)
    ) if privacy_filter else None

    log_event("🎓", f"Bachelor_Crawler v1.0 startet: {start_url[:60]}")
    log_event("📋", f"Rechtsgrundlage: {CONFIG.get('privacy_legal_basis', 'unbekannt')}")
    if robots_respect:
        log_event("🤖", f"robots.txt-Compliance: AKTIV (UA: {robots_ua})")
    if privacy_filter:
        log_event("🔒", "DSGVO-PII-Filter: AKTIV")

    visited_base         = set()
    visited_full         = set()
    to_visit             = [start_url]
    html_collected       = []
    pdf_collected        = []
    skipped_urls         = []
    status_log           = {}
    page_hashes          = {}
    base_domain          = urlparse(start_url).netloc
    effective_domain     = base_domain
    effective_start_path = ""
    prio_keywords        = ["aktuell", "news", "nachricht", "bauen", "projekt", "bebauungsplan"]
    first_request        = True
    js_fallback_count    = 0
    active_max_queue     = _MAX_QUEUE
    robots_blocked       = 0
    privacy_skipped      = 0

    try:
        with httpx.Client(
            follow_redirects=True,
            max_redirects=_MAX_REDIRECTS,
            headers={"User-Agent": _HTTP_USER_AGENT},
        ) as client:
            while to_visit and (len(html_collected) + len(pdf_collected)) < max_pages:
                curr      = to_visit.pop(0)
                curr_base = get_url_base(curr)

                if curr_base in visited_base:
                    skipped_urls.append(curr)
                    continue

                # ----------------------------------------------------------
                # DSGVO-Check: Sensitive URL überspringen
                # ----------------------------------------------------------
                if guard and privacy_skip and guard.is_sensitive_url(curr):
                    status_log[curr] = "PRIVACY_SENSITIVE_URL"
                    skipped_urls.append(curr)
                    privacy_skipped += 1
                    continue

                # ----------------------------------------------------------
                # robots.txt-Check
                # ----------------------------------------------------------
                if checker and not checker.is_allowed(curr):
                    status_log[curr] = "ROBOTS_DISALLOWED"
                    skipped_urls.append(curr)
                    robots_blocked += 1
                    continue

                visited_base.add(curr_base)
                visited_full.add(curr)

                # ----------------------------------------------------------
                # Crawl-Delay einhalten (robots.txt oder Standard)
                # ----------------------------------------------------------
                if checker:
                    checker.wait_for_crawl_delay(curr)
                else:
                    # Minimaler Standard-Delay auch ohne robots.txt-Checker
                    time.sleep(max(0, min(delay_default, delay_max)))

                mem_mb = _get_rss_mb()
                if mem_mb > _RAM_WARN_MB:
                    log_event("⚠️", f"RAM-Warnung: {mem_mb:.0f} MB | "
                                    f"queue={len(to_visit)} | visited={len(visited_full)} | "
                                    f"url={curr[:60]}")

                if len(visited_full) > 2000:
                    visited_full = set(visited_base)

                try:
                    resp = _safe_get(client, curr, CONFIG["timeout_seconds"])
                    if resp is None:
                        status_log[curr] = "DNS_TIMEOUT"
                        continue

                    # Zugriffszeit für Crawl-Delay aktualisieren
                    if checker:
                        checker.record_access(curr)

                    # ----------------------------------------------------------
                    # Domain-Redirect-Guard mit VG-Ausnahme (aus scraper_js v2.1)
                    # ----------------------------------------------------------
                    if first_request:
                        first_request = False
                        final_url     = str(resp.url)
                        final_domain  = urlparse(final_url).netloc

                        if _strip_www(final_domain) != _strip_www(base_domain):
                            if _is_vg_redirect(base_domain, final_url):
                                effective_domain     = final_domain
                                effective_start_path = urlparse(final_url).path.rstrip("/")
                                active_max_queue     = vg_max_queue
                                log_event("🏘️", f"VG-Redirect akzeptiert: "
                                               f"{base_domain} → {final_domain}"
                                               f"{effective_start_path}")
                            else:
                                log_event("🔀", f"EXTERNAL_REDIRECT: {base_domain} → "
                                               f"{final_domain} – übersprungen.")
                                status_log[curr] = f"EXTERNAL_REDIRECT:{final_domain}"
                                del resp
                                break

                    status_log[curr] = resp.status_code
                    if str(resp.url) != curr:
                        final_base = get_url_base(str(resp.url))
                        if final_base in visited_base and final_base != curr_base:
                            skipped_urls.append(curr)
                            visited_base.discard(curr_base)
                            del resp
                            continue
                        visited_base.add(final_base)
                        visited_full.add(str(resp.url))

                    if resp.status_code == 200:
                        raw_hash = hashlib.sha256(resp.content).hexdigest()
                        page_hashes[curr_base] = raw_hash

                        if curr.lower().endswith(".pdf"):
                            del resp
                            text = extract_pdf_text(curr, CONFIG["max_pdf_pages"])
                            if text:
                                # DSGVO: PII aus PDF-Text entfernen
                                if guard:
                                    text = guard.filter_text(text, source_url=curr)
                                pdf_collected.append((curr, text))
                            del text
                        else:
                            raw_html = resp.text
                            del resp

                            # JS-Fallback (aus scraper_js v2.0)
                            if js_rendering and _is_js_rendered(raw_html):
                                js_html = _fetch_with_playwright(curr)
                                if js_html and len(js_html) > len(raw_html):
                                    raw_html = js_html
                                    js_fallback_count += 1
                                    log_event("🌐", f"JS-Rendering: {curr[:60]}")

                            page_text = extract_main_text(raw_html)

                            # DSGVO: PII aus HTML-Text entfernen
                            if guard:
                                page_text = guard.filter_text(page_text, source_url=curr)

                            html_collected.append((curr, page_text))
                            del page_text

                            soup = BeautifulSoup(raw_html, "html.parser")
                            bs_links = set()
                            for link in soup.find_all("a", href=True):
                                nxt = urljoin(curr, link["href"])
                                bs_links.add(nxt)
                            soup.decompose()
                            del soup

                            regex_pdf_links = set()
                            for raw_url in _PDF_URL_RE.findall(raw_html):
                                if urlparse(raw_url).netloc == effective_domain:
                                    regex_pdf_links.add(raw_url)
                            del raw_html

                            neu_via_regex = regex_pdf_links - bs_links
                            if neu_via_regex:
                                log_event(
                                    "🔎",
                                    f"Regex-Scan: {len(neu_via_regex)} zus. PDF(s) auf "
                                    + curr[:60] + ": "
                                    + ", ".join(u.split('/')[-1] for u in neu_via_regex)
                                )

                            alle_links = bs_links | regex_pdf_links
                            del bs_links, regex_pdf_links, neu_via_regex

                            for nxt in alle_links:
                                nxt_parsed = urlparse(nxt)
                                nxt_base   = get_url_base(nxt)

                                if nxt_parsed.netloc != effective_domain:
                                    continue
                                if effective_start_path:
                                    if not nxt_parsed.path.startswith(effective_start_path):
                                        continue
                                if (is_relevant_url(nxt)
                                        and nxt_base not in visited_base
                                        and nxt not in visited_full
                                        and len(to_visit) < active_max_queue):
                                    visited_full.add(nxt)
                                    if nxt.lower().endswith(".pdf") or any(
                                            p in nxt.lower() for p in prio_keywords):
                                        to_visit.insert(0, nxt)
                                    else:
                                        to_visit.append(nxt)
                    else:
                        del resp

                except PermissionError as e:
                    status_log[curr] = f"PERMISSION_ERROR: {str(e)[:60]}"
                except httpx.TooManyRedirects:
                    status_log[curr] = "TOO_MANY_REDIRECTS"
                except httpx.TimeoutException:
                    status_log[curr] = "TIMEOUT"
                except httpx.ConnectError:
                    status_log[curr] = "CONNECTION_ERROR"
                except Exception as ex:
                    status_log[curr] = f"ERROR: {str(ex)[:60]}"

    except Exception as outer_ex:
        log_event("⚠️", f"Bachelor_Crawler-Absturz bei {start_url}: {str(outer_ex)[:80]}")

    # --- Abschluss-Logging ---
    if js_fallback_count:
        log_event("🌐", f"JS-Rendering {js_fallback_count}x aktiviert für {start_url[:50]}")
    if robots_blocked:
        log_event("🤖", f"robots.txt: {robots_blocked} URL(s) gesperrt für {start_url[:50]}")
    if guard:
        summary = guard.get_removal_summary()
        log_event(
            "🔒",
            f"DSGVO-Zusammenfassung {start_url[:50]}: "
            f"E-Mails: {summary['email']}, Tel: {summary['phone']}, "
            f"IBAN: {summary['iban']}, SVN: {summary['svn']}"
        )
    if privacy_skipped:
        log_event("🔒", f"DSGVO: {privacy_skipped} sensitive URL(s) übersprungen")

    return html_collected, pdf_collected, skipped_urls, status_log, page_hashes
