"""
privacy_guard.py
================
DSGVO-konforme Datenschutzfilterung für den Bachelor_Crawler.

Dieses Modul implementiert die datenschutzrechtlichen Anforderungen, die im
Kontext der Bachelorthesis für einen ethisch und legal konformen Web-Crawler
notwendig sind. Es operiert nach dem Grundsatz der Datensparsamkeit (Art. 5
Abs. 1 lit. c DSGVO) und der Zweckbindung (Art. 5 Abs. 1 lit. b DSGVO).

Funktionen:
    PrivacyGuard.filter_text(text)       – Entfernt PII aus extrahiertem Text
    PrivacyGuard.is_sensitive_url(url)   – Erkennt datenschutzsensible URLs
    PrivacyGuard.check_legal_notice(url) – Prüft auf Impressum/Datenschutzerklärung
    PrivacyGuard.sanitize_metadata(data) – Bereinigt gespeicherte Metadaten

DSGVO-Artikel-Referenzen:
    Art. 5  – Grundsätze der Verarbeitung (Zweckbindung, Datensparsamkeit)
    Art. 6  – Rechtmäßigkeit (berechtigtes Interesse bei öffentlichen Behörden)
    Art. 17 – Recht auf Löschung (sensitiver Daten)
    Art. 25 – Datenschutz durch Technikgestaltung (Privacy by Design)
"""

import re
from typing import Any

try:
    from logger import log_event
except ImportError:
    def log_event(emoji: str, msg: str) -> None:
        print(f"[PrivacyGuard] {emoji} {msg}")


# ---------------------------------------------------------------------------
# Reguläre Ausdrücke für personenbezogene Daten (PII)
# ---------------------------------------------------------------------------

# E-Mail-Adressen
_RE_EMAIL = re.compile(
    r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}',
    re.IGNORECASE
)

# Deutsche Telefonnummern (mobil und fest)
_RE_PHONE = re.compile(
    r'(?:(?:\+49|0049|0)[\s\-.]?)?'
    r'(?:\(?\d{2,5}\)?[\s\-.]?)?'
    r'\d{3,}[\s\-.]?\d{3,}(?:[\s\-.]?\d{1,4})?',
    re.IGNORECASE
)

# IBAN-Nummern
_RE_IBAN = re.compile(
    r'\b[A-Z]{2}\d{2}(?:\s?\d{4}){4,7}\b'
)

# Sozialversicherungsnummern (DE-Format)
_RE_SVN = re.compile(
    r'\b\d{2}[0-3]\d{6}[A-Z]\d{3}\b'
)

# URLs die Login/Auth/Profil-Seiten anzeigen
_SENSITIVE_PATH_PATTERNS = [
    r'/login', r'/auth', r'/signin', r'/signup', r'/register',
    r'/account', r'/profil', r'/mein-', r'/passwort', r'/password',
    r'/nutzer', r'/user', r'/admin',
    r'/datenschutz', r'/privacy', r'/dsgvo',  # Datenschutzseiten nicht crawlen
    r'/cookie', r'/tracking',
    r'/bewerbung', r'/application',
    r'/formular', r'/antrag',  # Formulare mit PII-Risiko
]
_RE_SENSITIVE_PATHS = re.compile(
    '|'.join(_SENSITIVE_PATH_PATTERNS),
    re.IGNORECASE
)

# Legal-Notice Indikatoren
_IMPRESSUM_PATTERNS = [
    r'/impressum', r'/legal', r'/kontakt', r'/imprint',
    r'/ueber-uns', r'/about',
]
_RE_IMPRESSUM = re.compile(
    '|'.join(_IMPRESSUM_PATTERNS),
    re.IGNORECASE
)


class PrivacyGuard:
    """
    DSGVO-konforme Datenschutzfilterung für gecrawlte Inhalte.

    Verwendung:
        guard = PrivacyGuard()
        clean_text = guard.filter_text(raw_text)
        if not guard.is_sensitive_url(url):
            # URL crawlen
    """

    def __init__(self, log_removals: bool = True) -> None:
        """
        Args:
            log_removals: Wenn True, werden PII-Entfernungen geloggt (ohne den
                          eigentlichen Inhalt, nur Zähler + URL).
        """
        self._log_removals = log_removals
        self._removal_counts: dict[str, int] = {"email": 0, "phone": 0, "iban": 0, "svn": 0}

    # ------------------------------------------------------------------
    # Öffentliche API
    # ------------------------------------------------------------------

    def filter_text(self, text: str, source_url: str = "") -> str:
        """
        Entfernt erkannte personenbezogene Daten aus dem Text.
        Ersetzt Treffer durch Platzhalter – der Satzkontext bleibt erhalten.

        Entspricht Art. 25 DSGVO: Privacy by Design / Datensparsamkeit.
        """
        original_len = len(text)

        email_count = len(_RE_EMAIL.findall(text))
        text = _RE_EMAIL.sub("[E-MAIL ENTFERNT]", text)

        phone_count = len(_RE_PHONE.findall(text))
        text = _RE_PHONE.sub("[TEL ENTFERNT]", text)

        iban_count = len(_RE_IBAN.findall(text))
        text = _RE_IBAN.sub("[IBAN ENTFERNT]", text)

        svn_count = len(_RE_SVN.findall(text))
        text = _RE_SVN.sub("[SVN ENTFERNT]", text)

        total = email_count + phone_count + iban_count + svn_count
        if total > 0 and self._log_removals:
            log_event(
                "🔒",
                f"PII entfernt aus {source_url[:60]}: "
                f"{email_count}x E-Mail, {phone_count}x Tel, "
                f"{iban_count}x IBAN, {svn_count}x SVN "
                f"(Text: {original_len} → {len(text)} Zeichen)"
            )
        self._removal_counts["email"] += email_count
        self._removal_counts["phone"] += phone_count
        self._removal_counts["iban"]  += iban_count
        self._removal_counts["svn"]   += svn_count

        return text

    def is_sensitive_url(self, url: str) -> bool:
        """
        Gibt True zurück wenn die URL auf einen datenschutzsensiblen Bereich zeigt.
        Solche URLs werden nicht gecrawlt (Login, Formulare, etc.).

        Entspricht Art. 5 Abs. 1 lit. b DSGVO: Zweckbindung.
        """
        match = _RE_SENSITIVE_PATHS.search(url)
        if match:
            log_event(
                "🔒",
                f"Sensitive URL übersprungen (DSGVO): {url[:80]} "
                f"(Muster: {match.group()!r})"
            )
            return True
        return False

    def check_legal_notice(self, url: str) -> bool:
        """
        Gibt True zurück wenn die URL ein Impressum oder eine
        Datenschutzerklärung ist. Diese werden gecrawlt aber nicht
        als inhaltliche Daten an die KI weitergegeben.
        """
        return bool(_RE_IMPRESSUM.search(url))

    def sanitize_metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Entfernt oder pseudonymisiert personenbezogene Felder aus
        gecrawlten Metadaten-Dicts.

        Felder die entfernt werden: author, creator, producer, email,
        phone, user, username, ip, geolocation.
        """
        sensitive_keys = {
            "author", "creator", "producer", "email", "phone",
            "user", "username", "ip", "geolocation", "location",
        }
        cleaned = {}
        for k, v in data.items():
            if k.lower() in sensitive_keys:
                cleaned[k] = "[ENTFERNT – DSGVO Art. 5]"
            else:
                cleaned[k] = v
        return cleaned

    def get_removal_summary(self) -> dict[str, int]:
        """Gibt eine Zusammenfassung aller bisherigen PII-Entfernungen zurück."""
        return dict(self._removal_counts)
