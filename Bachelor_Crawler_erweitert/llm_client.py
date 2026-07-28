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
        self._max_tokens = max_tokens
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

        try:
            import json
            response = self._client.chat.completions.create(
                model=self._model,
                max_tokens=self._max_tokens,
                temperature=self._temperature,
                messages=[
                    {'role': 'system', 'content': _SYSTEM_PROMPT},
                    {'role': 'user', 'content': f'URL: {url}\n\nText:\n{snippet}'},
                ],
            )
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
