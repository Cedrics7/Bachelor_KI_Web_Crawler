"""
scraper.py
==========
Web-Scraping, PDF-Extraktion und Textzusammenstellung.
"""

import re
import hashlib
import requests
import fitz
import warnings
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin, urlparse, parse_qs, urlencode

from config import CONFIG, IGNORIERE_PARAMS, PDF_PRIO_KEYWORDS
from logger import log_event, _write_console_log, get_german_time

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


def get_pdf_year(url: str) -> int:
    match = re.search(r'(20\d{2})', url.split("/")[-1])
    return int(match.group(1)) if match else 9999


def is_prio_pdf(url: str) -> bool:
    filename = url.split("/")[-1].lower()
    return any(kw in filename for kw in PDF_PRIO_KEYWORDS)


def get_content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def extract_main_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
        tag.decompose()
    return soup.get_text(separator=" ", strip=True)


def is_relevant_url(url: str) -> bool:
    ignore = ["impressum", "datenschutz", "kontakt", "sitemap", "login",
              ".jpg", ".png", ".gif", ".svg", ".webp"]
    return not any(kw in url.lower() for kw in ignore)


def get_url_base(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return parsed._replace(fragment="").geturl()
    params    = parse_qs(parsed.query, keep_blank_values=True)
    gefiltert = {k: v for k, v in params.items() if k.lower() not in IGNORIERE_PARAMS}
    return parsed._replace(query=urlencode(gefiltert, doseq=True), fragment="").geturl()


def extract_pdf_text(url: str, max_pages: int) -> str:
    try:
        response = requests.get(url, timeout=10)
        with fitz.open(stream=response.content, filetype="pdf") as doc:
            meta   = doc.metadata
            c_date = meta.get("creationDate", "")
            if c_date.startswith("D:"):
                year = int(c_date[2:6])
                if year < CONFIG["min_pdf_year"]:
                    return ""
            return "".join(page.get_text() for page in doc[:max_pages])
    except Exception as e:
        _write_console_log(f"[{get_german_time()}] ❌ PDF-Fehler ({url[:60]}): {e}")
        return ""


def get_subpages(start_url: str, max_pages: int):
    visited_base   = set()
    visited_full   = set()
    to_visit       = [start_url]
    html_collected = []
    pdf_collected  = []
    skipped_urls   = []
    status_log     = {}
    base_domain    = urlparse(start_url).netloc
    prio_keywords  = ["aktuell", "news", "nachricht", "bauen", "projekt", "bebauungsplan"]

    while to_visit and (len(html_collected) + len(pdf_collected)) < max_pages:
        curr      = to_visit.pop(0)
        curr_base = get_url_base(curr)
        if curr_base in visited_base:
            skipped_urls.append(curr)
            continue
        visited_base.add(curr_base)
        visited_full.add(curr)
        try:
            resp = requests.get(curr, timeout=CONFIG["timeout_seconds"],
                                headers={"User-Agent": "BachelorCrawler/1.0"})
            status_log[curr] = resp.status_code
            if resp.url != curr:
                final_base = get_url_base(resp.url)
                if final_base in visited_base and final_base != curr_base:
                    skipped_urls.append(curr)
                    visited_base.discard(curr_base)
                    continue
                visited_base.add(final_base)
                visited_full.add(resp.url)
            if resp.status_code == 200:
                if curr.lower().endswith(".pdf"):
                    text = extract_pdf_text(curr, CONFIG["max_pdf_pages"])
                    if text:
                        pdf_collected.append((curr, text))
                else:
                    html_collected.append((curr, extract_main_text(resp.text)))
                    soup = BeautifulSoup(resp.text, "html.parser")
                    for link in soup.find_all("a", href=True):
                        nxt      = urljoin(start_url, link["href"])
                        nxt_base = get_url_base(nxt)
                        if (urlparse(nxt).netloc == base_domain
                                and is_relevant_url(nxt)
                                and nxt_base not in visited_base
                                and nxt not in visited_full):
                            visited_full.add(nxt)
                            if any(p in nxt.lower() for p in prio_keywords):
                                to_visit.insert(0, nxt)
                            else:
                                to_visit.append(nxt)
        except requests.exceptions.Timeout:
            status_log[curr] = "TIMEOUT"
        except requests.exceptions.ConnectionError:
            status_log[curr] = "CONNECTION_ERROR"
        except Exception as ex:
            status_log[curr] = f"ERROR: {str(ex)[:60]}"

    return html_collected, pdf_collected, skipped_urls, status_log


def assemble_text(ort: str, html_pages: list, pdf_pages: list, limit: int):
    text_bulk = ""
    for url, content in html_pages:
        if content:
            text_bulk += f"\n--- URL: {url} ---\n{content}"

    prio_pdfs      = [(u, t) for u, t in pdf_pages if is_prio_pdf(u)]
    normale_pdfs   = sorted([(u, t) for u, t in pdf_pages if not is_prio_pdf(u)],
                            key=lambda x: get_pdf_year(x[0]), reverse=True)
    sortierte_pdfs = prio_pdfs + normale_pdfs
    verbleibend    = limit - len(text_bulk)

    if sum(len(t) for _, t in sortierte_pdfs) <= verbleibend:
        for url, content in sortierte_pdfs:
            text_bulk += f"\n--- URL: {url} ---\n{content}"
        return text_bulk, False, False

    for reduzierte_seiten in [3, 2, 1]:
        neu_pdf = [(u, extract_pdf_text(u, reduzierte_seiten)) for u, _ in sortierte_pdfs]
        if sum(len(t) for _, t in neu_pdf) <= verbleibend:
            log_event("⚠️", f"PDFs auf {reduzierte_seiten} Seite(n) gekürzt für {ort}")
            for url, content in neu_pdf:
                if content:
                    text_bulk += f"\n--- URL: {url} ---\n{content}"
            return text_bulk, True, False

    return text_bulk[:limit], True, True
