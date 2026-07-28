"""
DSGVO-konforme Datenschutzfilterung.
"""
import re
from typing import Any

_RE_EMAIL = re.compile(r'[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}', re.IGNORECASE)
_RE_PHONE = re.compile(r'(?:(?:\+49|0049|0)[\s\-.]?)?(?:\(?\d{2,5}\)?[\s\-.]?)?\d{3,}[\s\-.]?\d{3,}(?:[\s\-.]?\d{1,4})?', re.IGNORECASE)
_RE_IBAN = re.compile(r'\b[A-Z]{2}\d{2}(?:\s?[0-9A-Z]{4}){3,7}\b')
_RE_SVN = re.compile(r'\b\d{2}[0-3]\d{6}[A-Z]\d{3}\b')
_RE_SENSITIVE = re.compile(r'/login|/auth|/signin|/signup|/register|/account|/profil|/admin|/datenschutz|/privacy|/cookie|/tracking|/bewerbung|/formular|/antrag', re.IGNORECASE)
_RE_IMPRESSUM = re.compile(r'/impressum|/legal|/kontakt|/imprint|/ueber-uns|/about', re.IGNORECASE)

class PrivacyGuard:
    def __init__(self, log_removals: bool = True) -> None:
        self._log_removals = log_removals
        self._removal_counts = {"email": 0, "phone": 0, "iban": 0, "svn": 0}

    def filter_text(self, text: str, source_url: str = "") -> str:
        email_count = len(_RE_EMAIL.findall(text)); text = _RE_EMAIL.sub('[E-MAIL ENTFERNT]', text)
        phone_count = len(_RE_PHONE.findall(text)); text = _RE_PHONE.sub('[TEL ENTFERNT]', text)
        iban_count = len(_RE_IBAN.findall(text)); text = _RE_IBAN.sub('[IBAN ENTFERNT]', text)
        svn_count = len(_RE_SVN.findall(text)); text = _RE_SVN.sub('[SVN ENTFERNT]', text)
        self._removal_counts['email'] += email_count
        self._removal_counts['phone'] += phone_count
        self._removal_counts['iban'] += iban_count
        self._removal_counts['svn'] += svn_count
        return text

    def is_sensitive_url(self, url: str) -> bool:
        return bool(_RE_SENSITIVE.search(url))

    def check_legal_notice(self, url: str) -> bool:
        return bool(_RE_IMPRESSUM.search(url))

    def sanitize_metadata(self, data: dict[str, Any]) -> dict[str, Any]:
        sensitive_keys = {"author","creator","producer","email","phone","user","username","ip","geolocation","location"}
        return {k: ('[ENTFERNT – DSGVO Art. 5]' if k.lower() in sensitive_keys else v) for k, v in data.items()}

    def get_removal_summary(self) -> dict[str, int]:
        return dict(self._removal_counts)
