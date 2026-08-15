"""
text_utils.py
=============
Zentrale Text-Normalisierung fuer Keyword-Matching im Focused Crawler.

Wird von domain_model.py, relevance_classifier.py und link_prioritizer.py
gemeinsam genutzt, damit Text und Keywords IMMER identisch normalisiert
werden (Umlaute, Sonderzeichen, Pluralformen, URL-Encoding).
"""
from __future__ import annotations
import re
from urllib.parse import unquote

_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

# Deutsche Plural-/Flexionsendungen, die beim Wort-Match toleriert werden sollen.
_PLURAL_SUFFIX = r"(?:e|en|es|n|s)?"


def normalize_text(text: str, *, is_url: bool = False) -> str:
    """
    Normalisiert Text fuer den Keyword-Abgleich.

    Args:
        text: Roh-Text oder URL-Pfad/Query
        is_url: Wenn True, wird zusaetzlich URL-Dekodierung (%C3%A4 -> ae)
                und die Umwandlung von '/','_','-','=','&','+' in
                Leerzeichen durchgefuehrt, bevor normalisiert wird.
    """
    if text is None:
        return ""

    if is_url:
        text = unquote(text, encoding="utf-8", errors="replace")
        text = re.sub(r"[/_\-=&+]+", " ", text)

    text = text.lower().translate(_UMLAUT_MAP)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_keyword_pattern(keyword: str) -> re.Pattern:
    """
    Baut ein pluralfaehiges, umlaut-normalisiertes Regex-Pattern fuer ein
    einzelnes Keyword. Bindestrich-Komposita werden zusaetzlich als
    Leerzeichen-Variante zugelassen (z.B. 'oeffentliche-auslegung' matcht
    auch 'oeffentliche auslegung' im normalisierten Fliesstext).
    """
    normalized = normalize_text(keyword)
    escaped = re.escape(normalized)
    flexible = escaped.replace(r"\-", r"[\s-]").replace(r"\ ", r"[\s-]")
    return re.compile(rf"\b{flexible}{_PLURAL_SUFFIX}\b")
