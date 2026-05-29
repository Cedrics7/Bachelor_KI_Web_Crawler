"""
rate_limiter.py
===============
TokenManager: Rate-Limit-Kontrolle (RPM / TPM / RPD) für die Telekom LLM API.
"""

import time
import threading
from collections import deque
from datetime import date

from config import CONFIG
from logger import log_event


class TokenManager:
    def __init__(self):
        self.rpm_limit      = CONFIG["rpm_limit"]
        self.tpm_limit      = CONFIG["tpm_limit"]
        self.rpd_limit      = CONFIG["rpd_limit"]
        self.window         = deque()
        self.requests_today = 0
        self.day_start      = date.today()
        self._lock          = threading.Lock()

    def _evict_old(self):
        cutoff = time.monotonic() - 60.0
        while self.window and self.window[0][0] < cutoff:
            self.window.popleft()

    def check_and_wait(self, estimated_tokens: int) -> bool:
        with self._lock:
            if estimated_tokens >= self.tpm_limit:
                log_event("!!!", f"Prompt zu groß ({estimated_tokens} Tokens) – übersprungen!")
                return False
            if date.today() > self.day_start:
                self.requests_today = 0
                self.day_start = date.today()
            if self.requests_today >= self.rpd_limit:
                log_event("!!!", "Tageslimit (RPD) erreicht.")
                return False
        while True:
            with self._lock:
                self._evict_old()
                rpm_ok = len(self.window) < self.rpm_limit
                tpm_ok = sum(t for _, t in self.window) + estimated_tokens < self.tpm_limit
                if rpm_ok and tpm_ok:
                    return True
                oldest = self.window[0][0] if self.window else time.monotonic()
                wait   = max((oldest + 61.0) - time.monotonic(), 1.0)
            reason = "RPM" if not rpm_ok else "TPM"
            log_event("⏳", f"Rate-Limit ({reason}) – warte {wait:.1f}s ...")
            time.sleep(wait)

    def update_usage(self, token_count: int):
        with self._lock:
            self.window.append((time.monotonic(), token_count))
            self.requests_today += 1


# Singleton – wird von llm_client.py importiert
api_guard = TokenManager()
