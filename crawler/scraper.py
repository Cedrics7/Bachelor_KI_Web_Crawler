"""
scraper.py
==========
Web-Scraping, PDF-Extraktion und Textzusammenstellung.

Neu (v1.7):  get_subpages() gibt zusätzlich page_hashes zurück.
Neu (v1.8):  Regex-Scan für PDF-Links im Rohtext (JS-gerenderte Seiten).
             assemble_text() fügt Kontext-URL-Hinweis vor jedem PDF-Block ein,
             damit das LLM die korrekte quelle_url zurückgibt.
Neu (v1.9):  requests durch httpx ersetzt – echter DNS-Timeout verhindert
             Prozess-Kills bei nicht auflösbaren Domains.
Neu (v1.10): max_redirects=5 verhindert Redirect-Loops bei defekten Domains.
Neu (v1.11): httpx.Client statt httpx.get() – max_redirects wird erst vom
             Client-Objekt unterstützt, nicht von der Top-Level-Funktion.
Neu (v1.12): DNS-Blocking-Fix – httpx-Calls laufen in separatem Thread via
             ThreadPoolExecutor. Der Haupt-Thread wartet maximal timeout+2s,
             danach wird DNS_TIMEOUT geloggt und das Target übersprungen.
             Verhindert Prozess-Kills durch blockierende OS-DNS-Lookups.
Neu (v1.13): HTTP→HTTPS-Redirect-Crash-Fix:
             1. extract_pdf_text erstellt den httpx.Client vollständig im
                Worker-Thread – verhindert SSL-Blocking im Main-Thread.
             2. _safe_get fängt alle Exceptions ab (inkl. SSLError,
                RemoteProtocolError), nicht nur TimeoutError.
             3. get_url_base normalisiert das Schema auf 'https', damit
                http://x.de und https://x.de als dieselbe URL erkannt
                werden und kein doppeltes Crawlen entsteht.
Neu (v1.14): Outer-try/except um den gesamten httpx.Client-Block in
             get_subpages() – verhindert Crawler-Absturz wenn der Client-
             Kontext selbst fehlschlägt (z.B. 502 + DNS-Fehler gleichzeitig,
             notresolvable, Network unreachable). Gibt immer leere Listen
             zurück statt eine unkontrollierte Exception zu werfen.
Neu (v1.15): _safe_get verwendet executor.shutdown(wait=False) statt
             with-Block – verhindert dass der Haupt-Prozess beim Warten
             auf einen hängenden Thread vom OS gekillt wird (SIGKILL).
             Bei Timeout/Fehler wird der Thread losgelassen und None
             zurückgegeben.
"""

import re
import hashlib
import httpx
import fitz
import warnings
import concurrent.futures
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin, urlparse, parse_qs, urlencode

from config import CONFIG, IGNORIERE_PARAMS, PDF_PRIO_KEYWORDS
from logger import log_event, _write_console_log, get_german_time

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

# Regex für absolute PDF-URLs im Rohtext (JS-gerenderte Links, data-Attribute, etc.)
_PDF_URL_RE = re.compile(r'https?://[^\s"\'<>]+\.pdf', re.IGNORECASE)

# Maximale Anzahl an Redirects pro Request
_MAX_REDIRECTS = 5


def _safe_get(client: httpx.Client, url: str, timeout: float):
    """
    Führt client.get() in einem separaten Thread aus.
    Gibt None zurück wenn der OS-DNS-Resolver den Thread blockiert
    oder die Verbindung hängt (z.B. 502, notresolvable, Network unreachable).

    Verwendet shutdown(wait=False) statt with-Block, damit der Haupt-Thread
    den Worker-Thread bei Timeout loslässt und nicht vom OS gekillt wird.
    """
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
    future = executor.submit(client.get, url, timeout=timeout)
    try:
        return future.result(timeout=timeout + 2)
    except Exception:
        future.cancel()
        return None
    finally:
        executor.shutdown(wait=False)


def get_pdf_year(url: str) -> int:
    match = re.search(r'(20\d{2})', url.split("/")[-1])
    return int(match.group(1)) if match else 9999


def is_prio_pdf(url: str) -> bool:
    filename = url.split("/")[-1].lower()
    return any(kw in filename for kw in PDF_PRIO_KEYWORDS)


def get_content_hash(text: str) -> str:
    """SHA-256 Hash eines Textes (für Gesamt-Hash der gesammelten Inhalte)."""
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
    """
    Normalisiert eine URL für Dedup-Zwecke.
    Schema wird auf 'https' vereinheitlicht, damit http://x.de und
    https://x.de als dieselbe Basis-URL erkannt werden und kein
    doppeltes Crawlen nach einem HTTP→HTTPS-Redirect entsteht.
    """
    parsed = urlparse(url)
    parsed = parsed._replace(scheme="https")
    if not parsed.query:
        return parsed._replace(fragment="").geturl()
    params    = parse_qs(parsed.query, keep_blank_values=True)
    gefiltert = {k: v for k, v in params.items() if k.lower() not in IGNORIERE_PARAMS}
    return parsed._replace(query=urlencode(gefiltert, doseq=True), fragment="").geturl()


def extract_pdf_text(url: str, max_pages: int) -> str:
    """
    Lädt eine PDF-Datei und extrahiert den Text.
    Der httpx.Client wird vollständig im Worker-Thread erstellt,
    damit ein HTTP→HTTPS-Redirect keinen SSL-Blocking im Main-Thread auslöst.
    """
    try:
        def _fetch():
            with httpx.Client(
                follow_redirects=True,
                max_redirects=_MAX_REDIRECTS
            ) as client:
                return client.get(url, timeout=10)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_fetch)
        try:
            response = future.result(timeout=12)
        except Exception:
            future.cancel()
            return ""
        finally:
            executor.shutdown(wait=False)

        if response is None:
            return ""
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
    """
    Crawlt Unterseiten und PDFs.

    Rückgabe:
        html_collected  – list[(url, text)]
        pdf_collected   – list[(url, text)]
        skipped_urls    – list[url]
        status_log      – dict{url: status_code/error}
        page_hashes     – dict{url: sha256}  (Unterseiten-Hashing)
    """
    visited_base   = set()
    visited_full   = set()
    to_visit       = [start_url]
    html_collected = []
    pdf_collected  = []
    skipped_urls   = []
    status_log     = {}
    page_hashes    = {}
    base_domain    = urlparse(start_url).netloc
    prio_keywords  = ["aktuell", "news", "nachricht", "bauen", "projekt", "bebauungsplan"]

    try:
        with httpx.Client(
            follow_redirects=True,
            max_redirects=_MAX_REDIRECTS,
            headers={"User-Agent": "BachelorCrawler/1.0"}
        ) as client:
            while to_visit and (len(html_collected) + len(pdf_collected)) < max_pages:
                curr      = to_visit.pop(0)
                curr_base = get_url_base(curr)
                if curr_base in visited_base:
                    skipped_urls.append(curr)
                    continue
                visited_base.add(curr_base)
                visited_full.add(curr)
                try:
                    resp = _safe_get(client, curr, CONFIG["timeout_seconds"])
                    if resp is None:
                        status_log[curr] = "DNS_TIMEOUT"
                        continue

                    status_log[curr] = resp.status_code
                    if str(resp.url) != curr:
                        final_base = get_url_base(str(resp.url))
                        if final_base in visited_base and final_base != curr_base:
                            skipped_urls.append(curr)
                            visited_base.discard(curr_base)
                            continue
                        visited_base.add(final_base)
                        visited_full.add(str(resp.url))

                    if resp.status_code == 200:
                        raw_hash = hashlib.sha256(resp.content).hexdigest()
                        page_hashes[curr_base] = raw_hash

                        if curr.lower().endswith(".pdf"):
                            text = extract_pdf_text(curr, CONFIG["max_pdf_pages"])
                            if text:
                                pdf_collected.append((curr, text))
                        else:
                            html_collected.append((curr, extract_main_text(resp.text)))
                            soup = BeautifulSoup(resp.text, "html.parser")

                            bs_links = set()
                            for link in soup.find_all("a", href=True):
                                nxt = urljoin(start_url, link["href"])
                                bs_links.add(nxt)

                            regex_pdf_links = set()
                            for raw_url in _PDF_URL_RE.findall(resp.text):
                                if urlparse(raw_url).netloc == base_domain:
                                    regex_pdf_links.add(raw_url)

                            neu_via_regex = regex_pdf_links - bs_links
                            if neu_via_regex:
                                log_event("🔎", f"Regex-Scan fand {len(neu_via_regex)} zus. PDF(s) "
                                                   f"auf {curr[:60]}: "
                                                   + ", ".join(u.split('/')[-1] for u in neu_via_regex))

                            alle_links = bs_links | regex_pdf_links

                            for nxt in alle_links:
                                nxt_base = get_url_base(nxt)
                                if (urlparse(nxt).netloc == base_domain
                                        and is_relevant_url(nxt)
                                        and nxt_base not in visited_base
                                        and nxt not in visited_full):
                                    visited_full.add(nxt)
                                    if nxt.lower().endswith(".pdf") or any(
                                            p in nxt.lower() for p in prio_keywords):
                                        to_visit.insert(0, nxt)
                                    else:
                                        to_visit.append(nxt)

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
        log_event("⚠️", f"Scraper-Absturz abgefangen bei {start_url}: {str(outer_ex)[:80]}")

    return html_collected, pdf_collected, skipped_urls, status_log, page_hashes


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

    def _pdf_block(url: str, content: str) -> str:
        return (
            f"\n--- URL: {url} ---"
            f"\n[QUELLE: Direkte PDF-URL ist {url} – diese URL als quelle_url verwenden]\n"
            f"{content}"
        )

    if sum(len(t) for _, t in sortierte_pdfs) <= verbleibend:
        for url, content in sortierte_pdfs:
            text_bulk += _pdf_block(url, content)
        return text_bulk, False, False

    for reduzierte_seiten in [3, 2, 1]:
        neu_pdf = [(u, extract_pdf_text(u, reduzierte_seiten)) for u, _ in sortierte_pdfs]
        if sum(len(t) for _, t in neu_pdf) <= verbleibend:
            log_event("⚠️", f"PDFs auf {reduzierte_seiten} Seite(n) gekürzt für {ort}")
            for url, content in neu_pdf:
                if content:
                    text_bulk += _pdf_block(url, content)
            return text_bulk, True, False

    return text_bulk[:limit], True, True
