"""
LLM-Client für Bachelor_Crawler_erweitert.
Nutzt die OpenAI-kompatible API (OpenAI, Azure OpenAI, Ollama, etc.).
Wird über config.py / .env konfiguriert und im FocusedCrawler optional aktiviert.
"""
from __future__ import annotations
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# System-Prompt für Infrastruktur-Relevanzprüfung
_SYSTEM_PROMPT = """Du bist ein KI-Assistent zur Analyse von Webseiteninhalten.
Deine Aufgabe: Bestimme, ob der folgende Text einen konkreten Hinweis auf
Infrastrukturprojekte (Glasfaser, Breitband, 5G, Stromnetz, Wasser, Verkehr)
enthält.
Antworte ausschließlich mit einem JSON-Objekt:
{"relevant": true/false, "confidence": 0.0-1.0, "reason": "<kurze Begründung>"}
"""


class LLMClient:
    """
    Wrapper um den openai-Client.
    Fällt bei fehlendem API-Key oder Netzwerkfehler sicher zurück (None).
    """

    def __init__(
        self,
        api_key: Optional[str],
        base_url: str = 'https://api.openai.com/v1',
        model: str = 'gpt-4o-mini',
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> None:
        self._model = model
        # FIX #2: max_tokens auf das API-Maximum von 128000 clampen.
        # Verhindert den Fehler 'max_tokens is too large: 400000'.
        self._max_tokens = max(1, min(int(max_tokens), 128_000))
        self._temperature = temperature
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
        Sendet einen Textausschnitt an das LLM und gibt das geparste JSON zurück.
        Gibt None zurück bei Fehler oder deaktiviertem Client.
        """
        if not self.available:
            return None

        # Nur die ersten 3000 Zeichen senden (Token-Limit schonen)
        snippet = text[:3000].strip()
        if not snippet:
            return None

        # FIX #3: Modellabhängige temperature-Behandlung.
        # GPT-5 / GPT-5-mini akzeptieren kein temperature-Parameter.
        # GPT-5.1 benötigt reasoning_effort='none', damit temperature gesetzt werden darf.
        payload: dict = {
            'model': self._model,
            'max_tokens': self._max_tokens,
            'messages': [
                {'role': 'system', 'content': _SYSTEM_PROMPT},
                {'role': 'user', 'content': f'URL: {url}\n\nText:\n{snippet}'},
            ],
        }
        if self._model.startswith('gpt-5.1'):
            payload['reasoning_effort'] = 'none'
            payload['temperature'] = self._temperature
        elif not self._model.startswith('gpt-5'):
            # Alle anderen Modelle (gpt-4o, gpt-4o-mini, Ollama, etc.)
            payload['temperature'] = self._temperature
        # reines gpt-5 / gpt-5-mini: temperature weglassen

        try:
            import json
            response = self._client.chat.completions.create(**payload)
            raw = response.choices[0].message.content.strip()
            # JSON aus Antwort extrahieren (robust gegen Markdown-Code-Blöcke)
            if raw.startswith('```'):
                raw = raw.split('```')[1]
                if raw.startswith('json'):
                    raw = raw[4:]
            return json.loads(raw)
        except Exception as exc:
            logger.warning('LLM: Analyse-Fehler für %s: %s', url, exc)
            return None

    def batch_analyse(self, items: list[tuple[str, str]]) -> list[Optional[dict]]:
        """Analysiert eine Liste von (text, url)-Tupeln."""
        return [self.analyse(text, url) for text, url in items]
