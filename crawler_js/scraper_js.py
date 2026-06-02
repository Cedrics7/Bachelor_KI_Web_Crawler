"""
scraper_js.py
=============
Erweiterung von scraper.py mit optionalem JavaScript-Rendering via Playwright.

Nur die geänderten/neuen Teile gegenüber scraper.py (v1.21) sind hier enthalten.
Alle anderen Funktionen (get_pdf_year, is_prio_pdf, get_content_hash,
is_relevant_url, get_url_base, extract_pdf_text, assemble_text, etc.)
werden aus dem originalen scraper.py im gleichen Ordner importiert.

Neu (v2.0 – JS-Support):
    - _is_js_rendered(): erkennt ob eine Seite JS-Rendering benötigt
    - _fetch_with_playwright(): lädt eine Seite via Chromium (headless)
    - get_subpages() überschreibt die Original-Funktion mit JS-Fallback:
      Wenn httpx einen leeren/minimalen Body liefert, wird Playwright
      als Fallback gestartet (nur für HTML-Seiten, nicht für PDFs).

Neu (v2.1 – VG-Redirect-Fix):
    - _is_vg_redirect(): erkennt Verwaltungsgemeinschaft-Redirects.
      Wenn munningen.de → vg-oettingen.de/mitgliedsgemeinden/munningen,
      prüft die Funktion ob der Gemeindenamen (aus der ursprünglichen
      Domain extrahiert) im Pfad der Ziel-URL vorkommt.
      Falls ja: Guard wird übersprungen, Crawler folgt dem Redirect.
      Die neue base_domain wird auf die Ziel-Domain aktualisiert, damit
      alle weiteren Links auf der VG-Seite korrekt gefiltert werden.
      Zusätzlich: der Queue-Guard (_MAX_QUEUE) wird auf
      CONFIG["vg_max_queue"] reduziert, um Link-Explosionen auf VG-Seiten
      (die viele Gemeinden aggregieren) zu verhindern.

Konfiguration:
    CONFIG["js_rendering"]  = True/False     – JS-Rendering Schalter
    CONFIG["js_min_chars"]  = 500            – Schwellwert JS-Erkennung
    CONFIG["js_timeout"]    = 20             – Playwright-Timeout (s)
    CONFIG["js_wait_until"] = "networkidle"  – Playwright wait_until
    CONFIG["vg_max_queue"]  = 80             – Queue-Limit bei VG-Redirects
"""

import re
import hashlib
import httpx
import warnings
import concurrent.futures
try:
    import psutil
    _PSUTIL_AVAILABLE = True
except ImportError:
    _PSUTIL_AVAILABLE = False

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from urllib.parse import urljoin, urlparse

# Alle unveränderten Hilfsfunktionen aus scraper.py importieren
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
from config_js import CONFIG, IGNORIERE_PARAMS
from logger import log_event, _write_console_log, get_german_time

warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)


# ---------------------------------------------------------------------------
# VG-Redirect-Erkennung (v2.1)
# ---------------------------------------------------------------------------

def _extract_gemeinde_slug(netloc: str) -> str:
    """
    Extrahiert den Gemeindenamen aus einer Domain für den Subpath-Vergleich.

    Beispiele:
        www.munningen.de      → "munningen"
        munningen.de          → "munningen"
        www.bad-windsheim.de  → "bad-windsheim"
        stadt-ansbach.de      → "stadt-ansbach"  ("stadt-" bleibt erhalten –
                                                   im VG-Pfad steht er meistens
                                                   auch, oder der Fallback
                                                   auf "ansbach" greift über
                                                   _slug_variants)
    """
    # www. entfernen, TLD (.de / .com / ...) entfernen
    name = _strip_www(netloc)          # "munningen.de"
    name = re.sub(r'\.[a-z]{2,}$', '', name)  # "munningen"
    return name.lower()


def _slug_variants(slug: str) -> list[str]:
    """
    Gibt Varianten des Slugs zurück, die im VG-Pfad vorkommen könnten.

    Beispiel für "stadt-ansbach":
        ["stadt-ansbach", "ansbach"]
    Für "bad-windsheim":
        ["bad-windsheim", "windsheim"]
    """
    variants = [slug]
    # Wenn Slug mit bekanntem Präfix beginnt, auch ohne Präfix probieren
    for prefix in ("stadt-", "markt-", "gemeinde-", "bad-"):
        if slug.startswith(prefix):
            variants.append(slug[len(prefix):])
            break
    return variants


def _is_vg_redirect(base_domain: str, final_url: str) -> bool:
    """
    Gibt True zurück wenn der Redirect ein zulässiger VG-/Sammelseiten-Redirect ist.

    Bedingung: Der Gemeindename (aus base_domain extrahiert) oder eine seiner
    Varianten muss im Pfad der final_url als Pfadsegment vorkommen.

    Beispiel:
        base_domain = "www.munningen.de"
        final_url   = "https://www.vg-oettingen.de/mitgliedsgemeinden/munningen"
        slug        = "munningen"
        → "munningen" ist Pfadsegment → True ✓

    Gegenbeispiel (echter Fremd-Redirect):
        base_domain = "www.musterdorf.de"
        final_url   = "https://www.kreis-ansbach.de/"
        slug        = "musterdorf"
        → "musterdorf" nicht im Pfad → False ✓
    """
    slug     = _extract_gemeinde_slug(base_domain)
    variants = _slug_variants(slug)
    # Pfadsegmente aus final_url extrahieren (lowercase)
    path_segments = [s.lower() for s in urlparse(final_url).path.split("/") if s]
    return any(v in path_segments for v in variants)


# ---------------------------------------------------------------------------
# JS-Rendering – Hilfsfunktionen
# ---------------------------------------------------------------------------

def _is_js_rendered(html: str) -> bool:
    """
    Erkennt ob eine Seite wahrscheinlich JS-Rendering benötigt.

    Kriterien (mindestens eines muss zutreffen):
      1. Zu wenig sichtbarer Text (< js_min_chars Zeichen nach strip)
      2. Typische SPA-Marker im HTML (<noscript>, id="root", id="app",
         data-reactroot, ng-version, data-v-app)
    """
    min_chars = CONFIG.get("js_min_chars", 500)
    if len(html.strip()) < min_chars:
        return True
    spa_markers = [
        '<noscript>',
        'id="root"',
        "id='root'",
        'id="app"',
        "id='app'",
        'data-reactroot',
        'ng-version',
        'data-v-app',
    ]
    html_lower = html.lower()
    return any(m.lower() in html_lower for m in spa_markers)


def _fetch_with_playwright(url: str) -> str | None:
    """
    Lädt eine Seite mit Playwright (Chromium, headless) und gibt das
    vollständig gerenderte HTML zurück.

    Gibt None zurück bei Fehler oder Timeout.
    Playwright wird lazy importiert – der Rest des Crawlers funktioniert
    auch ohne installiertes Playwright (js_rendering = False).
    """
    timeout_ms = int(CONFIG.get("js_timeout", 20) * 1000)
    wait_until = CONFIG.get("js_wait_until", "networkidle")
    user_agent = CONFIG.get("js_user_agent",
                            "Mozilla/5.0 (X11; Linux x86_64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/124.0.0.0 Safari/537.36")
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=user_agent)
                page    = context.new_page()
                # Ressourcen-Blocking: Bilder/Fonts/Media sparen RAM & Zeit
                page.route(
                    "**/*",
                    lambda route: route.abort()
                    if route.request.resource_type in ("image", "media", "font")
                    else route.continue_()
                )
                page.goto(url, timeout=timeout_ms, wait_until=wait_until)
                html = page.content()
                return html
            except PWTimeout:
                _write_console_log(
                    f"[{get_german_time()}] ⏱️  Playwright-Timeout ({url[:60]})"
                )
                return None
            except Exception as e:
                _write_console_log(
                    f"[{get_german_time()}] ❌ Playwright-Fehler ({url[:60]}): {e}"
                )
                return None
            finally:
                browser.close()
    except ImportError:
        _write_console_log(
            f"[{get_german_time()}] ⚠️  Playwright nicht installiert – "
            "JS-Rendering deaktiviert. Bitte: pip install playwright && "
            "playwright install chromium"
        )
        return None


# ---------------------------------------------------------------------------
# Überschriebene get_subpages() mit JS-Fallback + VG-Redirect-Fix
# ---------------------------------------------------------------------------

def get_subpages(start_url: str, max_pages: int):
    """
    Wie scraper.get_subpages(), aber mit:
      - optionalem Playwright-Fallback für JS-gerenderte Seiten (v2.0)
      - VG-Redirect-Support: Gemeinden die auf VG-Sammelseiten zeigen
        werden korrekt gecrawlt statt übersprungen (v2.1)

    Rückgabe: identisch zu scraper.get_subpages()
        html_collected, pdf_collected, skipped_urls, status_log, page_hashes
    """
    js_rendering      = CONFIG.get("js_rendering", False)
    vg_max_queue      = CONFIG.get("vg_max_queue", 80)
    visited_base      = set()
    visited_full      = set()
    to_visit          = [start_url]
    html_collected    = []
    pdf_collected     = []
    skipped_urls      = []
    status_log        = {}
    page_hashes       = {}
    base_domain       = urlparse(start_url).netloc
    # effective_domain kann bei VG-Redirect auf die VG-Domain wechseln
    effective_domain  = base_domain
    # effective_start_path: bei VG-Redirect nur Links unterhalb dieses Pfades crawlen
    effective_start_path = ""
    prio_keywords     = ["aktuell", "news", "nachricht", "bauen", "projekt", "bebauungsplan"]
    first_request     = True
    js_fallback_count = 0
    active_max_queue  = _MAX_QUEUE   # kann bei VG-Redirect reduziert werden

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

                # RAM-Warn-Logger
                mem_mb = _get_rss_mb()
                if mem_mb > _RAM_WARN_MB:
                    log_event("⚠️", f"RAM-Warnung: {mem_mb:.0f} MB | "
                                    f"queue={len(to_visit)} | "
                                    f"visited={len(visited_full)} | "
                                    f"url={curr[:60]}")

                if len(visited_full) > 2000:
                    visited_full = set(visited_base)

                try:
                    resp = _safe_get(client, curr, CONFIG["timeout_seconds"])
                    if resp is None:
                        status_log[curr] = "DNS_TIMEOUT"
                        continue

                    # ----------------------------------------------------------
                    # Domain-Redirect-Guard mit VG-Redirect-Ausnahme (v2.1)
                    # ----------------------------------------------------------
                    if first_request:
                        first_request = False
                        final_url    = str(resp.url)
                        final_domain = urlparse(final_url).netloc

                        if _strip_www(final_domain) != _strip_www(base_domain):
                            # Prüfen: ist es ein zulässiger VG-/Subpath-Redirect?
                            if _is_vg_redirect(base_domain, final_url):
                                # VG-Redirect: Crawler folgt, aber mit eingeschränkter Domain
                                # und reduziertem Queue-Limit
                                effective_domain     = final_domain
                                effective_start_path = urlparse(final_url).path.rstrip("/")
                                active_max_queue     = vg_max_queue
                                log_event("🏘️", f"VG-Redirect akzeptiert: "
                                               f"{base_domain} → {final_domain}"
                                               f"{effective_start_path} "
                                               f"(Queue-Limit: {active_max_queue})")
                            else:
                                # Echter Fremd-Redirect → wie bisher blocken
                                log_event("🔀", f"EXTERNAL_REDIRECT: {base_domain} → "
                                               f"{final_domain} – Target wird übersprungen.")
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
                                pdf_collected.append((curr, text))
                            del text
                        else:
                            raw_html = resp.text
                            del resp

                            # --- JS-Fallback (v2.0) ---
                            if js_rendering and _is_js_rendered(raw_html):
                                js_html = _fetch_with_playwright(curr)
                                if js_html and len(js_html) > len(raw_html):
                                    raw_html = js_html
                                    js_fallback_count += 1
                                    log_event("🌐", f"JS-Rendering: {curr[:60]}")

                            page_text = extract_main_text(raw_html)
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
                                log_event("🔎", f"Regex-Scan fand {len(neu_via_regex)} zus. "
                                               f"PDF(s) auf {curr[:60]}: "
                                               + ", ".join(
                                                   u.split('/')[-1] for u in neu_via_regex
                                               ))

                            alle_links = bs_links | regex_pdf_links
                            del bs_links, regex_pdf_links, neu_via_regex

                            for nxt in alle_links:
                                nxt_parsed = urlparse(nxt)
                                nxt_base   = get_url_base(nxt)

                                # Domain-Filter: bei VG-Redirect nur effective_domain
                                if nxt_parsed.netloc != effective_domain:
                                    continue

                                # Subpath-Filter: bei VG-Redirect nur Links unterhalb
                                # des Gemeinde-Pfades zulassen (verhindert komplettes
                                # VG-Crawlen aller anderen Mitgliedsgemeinden)
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
        log_event("⚠️", f"Scraper-Absturz abgefangen bei {start_url}: {str(outer_ex)[:80]}")

    if js_fallback_count:
        log_event("🌐", f"JS-Rendering insgesamt {js_fallback_count}x aktiviert für {start_url[:50]}")

    return html_collected, pdf_collected, skipped_urls, status_log, page_hashes
