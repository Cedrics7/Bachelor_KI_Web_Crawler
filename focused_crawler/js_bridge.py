# focused_crawler/js_bridge.py
"""
Brückenmodul: ruft crawler_js als Subprocess auf und liest das gerenderte HTML
zurück. crawler_js muss das fertige HTML sauber über stdout ausgeben (kein
gemischtes Logging auf stdout).

Verwendung:
    from focused_crawler.js_bridge import fetch_via_crawler_js, looks_like_js_shell

Erwartetes Interface von crawler_js:
    Aufruf:  node crawler_js/index.js <url>
    Ausgabe: reines HTML auf stdout  (exit 0 = OK, exit !=0 = Fehler)

    ODER (JSON-Modus, wenn USE_JSON_OUTPUT=True):
    Ausgabe: {"url": "...", "html": "..."}  auf stdout
"""
import subprocess
import json
import re
from typing import Optional

# Pfad zum Node-Einstiegspunkt relativ zum Projektroot
DEFAULT_CRAWLER_JS_PATH = "crawler_js/index.js"

# Auf True setzen, wenn crawler_js JSON statt reinem HTML ausgibt
USE_JSON_OUTPUT: bool = False


def fetch_via_crawler_js(
    url: str,
    crawler_js_path: str = DEFAULT_CRAWLER_JS_PATH,
    timeout: int = 30,
) -> str:
    """
    Übergibt `url` an crawler_js und gibt das gerenderte HTML zurück.

    Args:
        url:              Ziel-URL
        crawler_js_path:  Pfad zu crawler_js/index.js (relativ zum Projektroot)
        timeout:          Timeout in Sekunden

    Returns:
        Gerendertes HTML als String

    Raises:
        RuntimeError: wenn crawler_js einen Fehler zurückgibt oder der
                      Prozess den Timeout überschreitet
    """
    try:
        result = subprocess.run(
            ["node", crawler_js_path, url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"crawler_js Timeout ({timeout}s) für {url}"
        ) from exc
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"Node.js nicht gefunden oder Pfad falsch: {crawler_js_path}"
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            f"crawler_js fehlgeschlagen für {url}:\n"
            f"  stderr: {result.stderr.strip()[:500]}"
        )

    if USE_JSON_OUTPUT:
        try:
            data = json.loads(result.stdout)
            return data["html"]
        except (json.JSONDecodeError, KeyError) as exc:
            raise RuntimeError(
                f"Ungültiger JSON-Output von crawler_js für {url}: {exc}"
            ) from exc

    return result.stdout


# ---------------------------------------------------------------------------
# Heuristik: Ist die Seite eine JS-Shell (SPA/dynamische App)?
# ---------------------------------------------------------------------------

_JS_SHELL_PATTERNS = [
    re.compile(r'<div[^>]+id=["\']app["\']\s*/?>', re.IGNORECASE),
    re.compile(r'<div[^>]+id=["\']root["\']\s*/?>', re.IGNORECASE),
    re.compile(r'<noscript>[^<]{0,200}</noscript>', re.IGNORECASE),
]

_MIN_CONTENT_LENGTH = 500  # Byte-Schwelle für "zu wenig Inhalt"


def looks_like_js_shell(html: str) -> bool:
    """
    Einfache Heuristik: Gibt True zurück, wenn das HTML wahrscheinlich eine
    SPA-Shell ist, die serverseitig kaum Content liefert.

    Kriterien (alle müssen zutreffen):
        1. Mindestens eines der SPA-Muster ist vorhanden (app/root div, noscript)
        2. Sichtbarer Textinhalt ist sehr kurz (< _MIN_CONTENT_LENGTH Zeichen)
    """
    pattern_match = any(p.search(html) for p in _JS_SHELL_PATTERNS)
    if not pattern_match:
        return False

    # Grober Text-Extrakt: alle Tags entfernen
    plain_text = re.sub(r"<[^>]+>", "", html)
    plain_text = re.sub(r"\s+", " ", plain_text).strip()
    return len(plain_text) < _MIN_CONTENT_LENGTH
