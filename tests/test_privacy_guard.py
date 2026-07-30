"""
Unit-Tests fuer Bachelor_Crawler_erweitert.privacy_guard.PrivacyGuard.
DSGVO-Filterlogik: E-Mail, Telefon, IBAN, SVN, sensible URLs, Metadaten.
"""
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'Bachelor_Crawler_erweitert'))
from Bachelor_Crawler_erweitert.privacy_guard import PrivacyGuard


class TestPrivacyGuardFilterText:
    def setup_method(self):
        self.guard = PrivacyGuard(log_removals=True)

    # --- E-Mail -----------------------------------------------------------
    def test_email_is_removed(self):
        result = self.guard.filter_text('Kontakt: max.mustermann@example.de')
        assert '[E-MAIL ENTFERNT]' in result
        assert 'max.mustermann@example.de' not in result

    def test_multiple_emails_removed(self):
        text = 'A: a@foo.de  B: b@bar.org'
        result = self.guard.filter_text(text)
        assert result.count('[E-MAIL ENTFERNT]') == 2

    def test_no_false_positive_plain_text(self):
        result = self.guard.filter_text('Kein personenbezogenes Datum hier.')
        assert result == 'Kein personenbezogenes Datum hier.'

    # --- Telefon ----------------------------------------------------------
    def test_german_phone_removed(self):
        result = self.guard.filter_text('Rufnummer: 040 123456789')
        assert '[TEL ENTFERNT]' in result

    def test_international_phone_removed(self):
        result = self.guard.filter_text('Tel: +49 30 12345678')
        assert '[TEL ENTFERNT]' in result

    # --- IBAN -------------------------------------------------------------
    def test_iban_removed(self):
        result = self.guard.filter_text('IBAN: DE89 3704 0044 0532 0130 00')
        assert '[IBAN ENTFERNT]' in result
        assert 'DE89' not in result

    # --- SVN --------------------------------------------------------------
    def test_svn_removed(self):
        # Format: 2 Ziffern + DDMMYYYY (6 Ziffern) + Grossbuchstabe + 3 Ziffern
        result = self.guard.filter_text('SVN: 12010180A123')
        assert '[SVN ENTFERNT]' in result

    # --- Kombiniertes Vorkommen -------------------------------------------
    def test_combined_pii_removed(self):
        text = 'E-Mail: info@test.de, Tel: 030 999888, IBAN: DE02200400600266345400'
        cleaned, count = self.guard.filter_text_counted(text)
        assert count >= 2
        assert 'info@test.de' not in cleaned

    # --- Zähler -----------------------------------------------------------
    def test_removal_counts_accumulate(self):
        g = PrivacyGuard()
        g.filter_text('a@b.de c@d.de')
        summary = g.get_removal_summary()
        assert summary['email'] == 2

    def test_removal_counts_zero_initially(self):
        g = PrivacyGuard()
        assert g.get_removal_summary() == {'email': 0, 'phone': 0, 'iban': 0, 'svn': 0}


class TestPrivacyGuardURLChecks:
    def setup_method(self):
        self.guard = PrivacyGuard()

    # --- Sensible URLs ----------------------------------------------------
    def test_login_url_is_sensitive(self):
        assert self.guard.is_sensitive_url('https://example.com/login') is True

    def test_admin_url_is_sensitive(self):
        assert self.guard.is_sensitive_url('https://example.com/admin/users') is True

    def test_datenschutz_url_is_sensitive(self):
        assert self.guard.is_sensitive_url('https://example.com/datenschutz') is True

    def test_bewerbung_url_is_sensitive(self):
        assert self.guard.is_sensitive_url('https://example.com/bewerbung') is True

    def test_normal_url_not_sensitive(self):
        assert self.guard.is_sensitive_url('https://example.com/news/artikel') is False

    def test_tracking_url_is_sensitive(self):
        assert self.guard.is_sensitive_url('https://example.com/tracking/pixel') is True

    # --- Impressum / Legal Notice -----------------------------------------
    def test_impressum_url_detected(self):
        assert self.guard.check_legal_notice('https://example.com/impressum') is True

    def test_legal_url_detected(self):
        assert self.guard.check_legal_notice('https://example.com/legal/notice') is True

    def test_kontakt_url_detected(self):
        assert self.guard.check_legal_notice('https://example.com/kontakt') is True

    def test_about_url_detected(self):
        assert self.guard.check_legal_notice('https://example.com/about-us') is True

    def test_news_url_not_legal(self):
        assert self.guard.check_legal_notice('https://example.com/news') is False


class TestPrivacyGuardSanitizeMetadata:
    def setup_method(self):
        self.guard = PrivacyGuard()

    def test_author_key_is_sanitized(self):
        result = self.guard.sanitize_metadata({'author': 'Max Mustermann', 'title': 'Doc'})
        assert result['author'] == '[ENTFERNT – DSGVO Art. 5]'
        assert result['title'] == 'Doc'

    def test_email_key_is_sanitized(self):
        result = self.guard.sanitize_metadata({'email': 'x@y.de'})
        assert result['email'] == '[ENTFERNT – DSGVO Art. 5]'

    def test_ip_key_is_sanitized(self):
        result = self.guard.sanitize_metadata({'ip': '192.168.1.1'})
        assert result['ip'] == '[ENTFERNT – DSGVO Art. 5]'

    def test_non_sensitive_key_unchanged(self):
        result = self.guard.sanitize_metadata({'language': 'de', 'pages': 10})
        assert result['language'] == 'de'
        assert result['pages'] == 10

    def test_empty_dict_returns_empty(self):
        assert self.guard.sanitize_metadata({}) == {}

    def test_case_insensitive_key_match(self):
        result = self.guard.sanitize_metadata({'Author': 'Test'})
        assert result['Author'] == '[ENTFERNT – DSGVO Art. 5]'
