"""
LLM-Client für Bachelor_Crawler_erweitert.
Nutzt die OpenAI-kompatible API (OpenAI, Azure OpenAI, Ollama, etc.).
Wird über config.py / .env konfiguriert und im FocusedCrawler optional aktiviert.

Prompt-Logik übernommen aus crawler_js/llm_client.py (_build_prompt):
Extrahiert konkrete Bau- und Infrastrukturmaßnahmen als JSON-Liste,
statt nur einen relevant=true/false-Boolean zu liefern.
"""
from __future__ import annotations
import json
import logging
import re
from datetime import date
from typing import Optional
from urllib.parse import urlparse
from config import ZIEL_KATEGORIEN as _CONFIG_ZIEL_KATEGORIEN

logger = logging.getLogger(__name__)


def _build_prompt(text: str, url: str, kategorien: dict | None = None) -> str:
    """
    Baut den LLM-Prompt analog zu crawler_js/llm_client.py::_build_prompt().
    Extrahiert konkrete Massnahmen als JSON-Liste.

    kategorien: optionales Override-Dict {Kategoriename: [Synonyme, ...]}
                (Standard: aus config.ZIEL_KATEGORIEN).
    """
    aktive_kategorien = kategorien if kategorien is not None else _CONFIG_ZIEL_KATEGORIEN

    base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
    kategorien_namen = list(aktive_kategorien.keys())
    kategorien_str = "\n".join(
        f"- {name}: {', '.join(synonyme)}" for name, synonyme in aktive_kategorien.items()
    )
    today_str  = date.today().strftime("%Y-%m-%d")
    cutoff_str = date.today().replace(year=date.today().year - 3).strftime("%Y-%m-%d")
    snippet = text[:12_000].strip()

    return f"""Du bist ein Experte für die Analyse kommunaler Ausschreibungen und Bauprojekte.

AUFGABE: Extrahiere AUSSCHLIESSLICH echte Bau-, Infrastruktur- oder Sanierungsvorhaben.

STRIKTE AUSSCHLUSSKRITERIEN – ignoriere komplett:
- Fahrzeugbeschaffung (LKW, Feuerwehrfahrzeuge, Busse)
- Kursangebote, Wellness, Thermalbad, medizinische Pläne
- Stellenausschreibungen, reine Dienstleistungen (z.B. Winterdienst)
- Kulturelle Veranstaltungen, Feste, Sitzungstermine
- Navigationsmenüs, Kategorielisten, Ortsplan-Übersichtsseiten ohne konkreten Projektinhalt
- Reine Ver- und Entsorgungsübersichtsseiten ohne beschriebenes Projekt oder Baumaßnahme

KATEGORIEN (Kategoriename: typische Begriffe/Synonyme zur Einordnung):
{kategorien_str}

WICHTIG ZUR KATEGORIE-ZUORDNUNG:
- Das Feld "kategorie" MUSS exakt einem dieser Namen entsprechen: {", ".join(kategorien_namen)}
- Nutze die aufgelisteten Begriffe/Synonyme nur als inhaltliche Orientierung,
  nicht als exakten Textabgleich – ordne nach Bedeutung zu.

ZEITRAUM-FILTER (Stichtag heute: {today_str}):
- Erfasse NUR Maßnahmen die NOCH LAUFEN oder IN DER ZUKUNFT liegen.
- "massnahme_ende" vorhanden UND liegt VOR {today_str} → Maßnahme WEGLASSEN.
- Nur Startdatum vorhanden, älter als 3 Jahre (vor {cutoff_str}) → WEGLASSEN.

WICHTIG:
- Wenn der Text KEINE konkrete Baumaßnahme beschreibt, gib zurück: {{"massnahmen": []}}
- Eine Maßnahme ist NUR relevant wenn der SEITENINHALT (nicht das Navigationsmenü)
  ein konkretes Projekt, eine Baumaßnahme, Ausschreibung oder einen Gemeinderatsbeschluss
  zu einem Infrastrukturvorhaben beschreibt.
- Jede Maßnahme MUSS ein Start- oder Enddatum haben.
- "quelle_url": Gib IMMER eine vollständige absolute URL an (Basis: {base_url}).
- Bei Dopplungen (gleiche Maßnahme, verschiedene URLs): nur einmal ausgeben.

Antworte ausschließlich als JSON:
{{
    "massnahmen": [
        {{
            "kategorie": "...",
            "massnahme": "...",
            "adresse": "...",
            "massnahme_start": "YYYY-MM-DD oder null",
            "massnahme_ende": "YYYY-MM-DD oder null",
            "quelle_url": "..."
        }}
    ]
}}

Seitentext (URL: {url}):
{snippet}
"""


def _parse_llm_response(raw: str, fallback_url: str, gueltige_kategorien: list | None = None) -> dict:
    """
    Parst die LLM-Antwort robust.
    Gibt immer ein Dict mit dem Key 'massnahmen' (Liste) zurück.

    gueltige_kategorien: optionale Liste bekannter Kategorienamen zur
                          Plausibilitätsprüfung (nur Warnung, kein Verwerfen).
    """
    if not raw:
        return {"massnahmen": []}

    # Markdown-Code-Blöcke entfernen
    clean = re.sub(r'```(?:json)?\s*', '', raw).replace('```', '').strip()
    clean = re.sub(r'<think>.*?</think>', '', clean, flags=re.DOTALL | re.IGNORECASE).strip()

    # JSON extrahieren
    match = re.search(r'(\{.*\})', clean, re.DOTALL)
    if match:
        clean = match.group(1)

    try:
        data = json.loads(clean)
    except json.JSONDecodeError:
        # Trailing-Komma-Repair
        clean = re.sub(r',\s*([\}\]])', r'\1', clean)
        try:
            data = json.loads(clean)
        except json.JSONDecodeError:
            logger.warning('LLM: JSON-Parsing fehlgeschlagen, Antwort: %s', raw[:200])
            return {"massnahmen": []}

    massnahmen = data.get('massnahmen', [])
    if not isinstance(massnahmen, list):
        massnahmen = []

    # quelle_url normalisieren + optionale Kategorie-Plausibilitätsprüfung
    base = f"{urlparse(fallback_url).scheme}://{urlparse(fallback_url).netloc}"
    for item in massnahmen:
        url_val = item.get('quelle_url', '')
        if url_val and not url_val.startswith('http'):
            item['quelle_url'] = base.rstrip('/') + '/' + url_val.lstrip('/')
        if not item.get('quelle_url'):
            item['quelle_url'] = fallback_url

        if gueltige_kategorien and item.get('kategorie') not in gueltige_kategorien:
            logger.warning(
                "LLM: Unbekannte Kategorie '%s' für %s (erwartet: %s) - wird trotzdem übernommen.",
                item.get('kategorie'), item.get('quelle_url'), gueltige_kategorien
            )

    return {"massnahmen": massnahmen}


class LLMClient:
    """
    Wrapper um den openai-Client.
    Fällt bei fehlendem API-Key oder Netzwerkfehler sicher zurück (None).

    analyse() gibt jetzt {"massnahmen": [...]} zurück statt {"relevant": bool}.
    Dies ist kompatibel mit dem crawler_js-Format und erlaubt save_llm_result()
    in db_client.py konkrete Maßnahmen-Objekte zu speichern.
    """

    def __init__(
        self,
        api_key: Optional[str],
        base_url: str = 'https://api.openai.com/v1',
        model: str = 'gpt-4o-mini',
        max_tokens: int = 4096,
        temperature: float = 0.0,
        kategorien: Optional[dict] = None,
    ) -> None:
        self._model = model
        self._max_tokens = max(1, min(int(max_tokens), 128_000))
        self._temperature = temperature
        self._kategorien = kategorien if kategorien is not None else _CONFIG_ZIEL_KATEGORIEN
        self._client = None

        if not api_key:
            logger.warning('LLM: Kein API-Key gesetzt – LLM-Analyse deaktiviert.')
            return

        try:
            from openai import OpenAI
            self._client = OpenAI(api_key=api_key, base_url=base_url)
            logger.info('LLM: Client initialisiert (Modell: %s, Endpunkt: %s)', model, base_url)
        except ImportError:
            logger.error('LLM: openai-Paket nicht installiert – pip install openai')

    @property
    def available(self) -> bool:
        return self._client is not None

    @property
    def model(self) -> str:
        return self._model

    def analyse(self, text: str, url: str = '') -> Optional[dict]:
        """
        Sendet den Seitentext an das LLM und gibt ein Dict zurück:
          {"massnahmen": [{"kategorie": ..., "massnahme": ..., ...}, ...]}

        Leere Liste in 'massnahmen' bedeutet: kein relevanter Fund.
        Gibt None zurück bei Fehler oder deaktiviertem Client.

        Kompatibilität mit focused_crawler.py:
          llm_result.get('relevant') → True wenn len(massnahmen) > 0
          llm_result.get('confidence') → 1.0 (wird nicht mehr verwendet)
        """
        if not self.available:
            return None

        prompt = _build_prompt(text, url, kategorien=self._kategorien)
        if not prompt:
            return None

        payload: dict = {
            'model':      self._model,
            'max_tokens': self._max_tokens,
            'messages':   [{'role': 'user', 'content': prompt}],
        }
        if self._model.startswith('gpt-5.1'):
            payload['reasoning_effort'] = 'none'
            payload['temperature'] = self._temperature
        elif not self._model.startswith('gpt-5'):
            payload['temperature'] = self._temperature

        try:
            response = self._client.chat.completions.create(**payload)
            raw = response.choices[0].message.content.strip()
            result = _parse_llm_response(
                raw, fallback_url=url, gueltige_kategorien=list(self._kategorien.keys())
            )
            # Kompatibilitäts-Keys für focused_crawler.py (Gate-Logik)
            result['relevant']   = len(result.get('massnahmen', [])) > 0
            result['confidence'] = 1.0 if result['relevant'] else 0.0
            return result
        except Exception as exc:
            logger.warning('LLM: Analyse-Fehler für %s: %s', url, exc)
            return None

    def batch_analyse(self, items: list[tuple[str, str]]) -> list[Optional[dict]]:
        """Analysiert eine Liste von (text, url)-Tupeln."""
        return [self.analyse(text, url) for text, url in items]
