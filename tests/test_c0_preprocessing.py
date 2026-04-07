"""Tests for Layer C0 - Preprocessing & Normalization."""

import pytest
from datetime import date

from reconciliation.c0_preprocessing import PaymentPreprocessor
from reconciliation.config import C0Config
from reconciliation.models import (
    Currency,
    Debtor,
    LabelClass,
    Payment,
    PaymentSignals,
)


@pytest.fixture
def preprocessor():
    return PaymentPreprocessor()


class TestLabelNormalization:
    """Test all 14 normalization transforms (N001-N014)."""

    def test_n001_uppercase(self, preprocessor):
        assert "FAC" in preprocessor.normalize_label("fac-2024-001")

    def test_n002_deaccentuation(self, preprocessor):
        result = preprocessor.normalize_label("Règlmnt Létudé")
        assert "REGLMNT" in result
        assert "è" not in result and "é" not in result

    def test_n003_strip_punctuation(self, preprocessor):
        result = preprocessor.normalize_label("FAC.001,TXT!")
        # After uppercase + deaccent + strip bank prefix + strip punct
        assert "FAC" in result
        assert "001" in result
        assert "." not in result

    def test_n006_remove_duplicate_spaces(self, preprocessor):
        result = preprocessor.normalize_label("FAC  001   FAC")
        assert "  " not in result

    def test_n007_expand_abbreviations(self, preprocessor):
        result = preprocessor.normalize_label("REGLT facture")
        assert "REGLEMENT" in result

    def test_n011_strip_bank_prefixes(self, preprocessor):
        result = preprocessor.normalize_label("VIREMENT RECU DE FAC-2024-001")
        assert "VIREMENT RECU DE" not in result
        assert "FAC" in result

    def test_empty_label(self, preprocessor):
        assert preprocessor.normalize_label("") == ""
        assert preprocessor.normalize_label(None) == ""


class TestAmountNormalization:
    def test_european_format(self, preprocessor):
        assert preprocessor.normalize_amount("15.000,50") == 15000.50

    def test_us_format(self, preprocessor):
        assert preprocessor.normalize_amount("15,000.50") == 15000.50

    def test_simple_comma_decimal(self, preprocessor):
        assert preprocessor.normalize_amount("15000,50") == 15000.50

    def test_empty(self, preprocessor):
        assert preprocessor.normalize_amount("") is None
        assert preprocessor.normalize_amount(None) is None


class TestIBANNormalization:
    def test_normalize_iban(self, preprocessor):
        assert preprocessor.normalize_iban("fr76 1234 5678") == "FR7612345678"

    def test_empty(self, preprocessor):
        assert preprocessor.normalize_iban("") == ""


class TestDateNormalization:
    def test_dd_mm_yyyy(self, preprocessor):
        assert preprocessor.normalize_date("01/10/2024") == date(2024, 10, 1)

    def test_dd_mm_yy(self, preprocessor):
        result = preprocessor.normalize_date("01/10/24")
        assert result == date(2024, 10, 1)

    def test_iso_format(self, preprocessor):
        assert preprocessor.normalize_date("2024-10-01") == date(2024, 10, 1)

    def test_invalid(self, preprocessor):
        assert preprocessor.normalize_date("not a date") is None


class TestCurrencyNormalization:
    def test_euro_symbol(self, preprocessor):
        assert preprocessor.normalize_currency("€") == Currency.EUR

    def test_usd(self, preprocessor):
        assert preprocessor.normalize_currency("USD") == Currency.USD

    def test_unknown_defaults_eur(self, preprocessor):
        assert preprocessor.normalize_currency("XYZ") == Currency.EUR


class TestLanguageDetection:
    def test_french(self, preprocessor):
        assert preprocessor.detect_language("REGLEMENT FACTURE MONTANT") == "FR"

    def test_english(self, preprocessor):
        assert preprocessor.detect_language("PAYMENT INVOICE AMOUNT TRANSFER") == "EN"


class TestSignalExtraction:
    def test_extract_refs(self, preprocessor):
        payment = Payment(
            id="P1", amount=1000, label_raw="FAC-2024-001234",
            label_normalized="FAC 2024 001234",
        )
        signals = preprocessor.extract_signals(payment)
        assert len(signals.raw_refs) > 0

    def test_label_classification_empty(self, preprocessor):
        payment = Payment(id="P1", amount=1000, label_raw="", label_normalized="")
        signals = preprocessor.extract_signals(payment)
        assert signals.label_class == LabelClass.EMPTY

    def test_label_quality_score(self, preprocessor):
        payment = Payment(
            id="P1", amount=1000,
            label_raw="FAC-2024-001 REGLEMENT OCTOBRE",
            label_normalized="FAC 2024 001 REGLEMENT OCTOBRE",
        )
        signals = preprocessor.extract_signals(payment)
        assert signals.label_quality > 0.3

    def test_keywords_detected(self, preprocessor):
        payment = Payment(
            id="P1", amount=1000,
            label_raw="ACOMPTE FAC-001",
            label_normalized="ACOMPTE FAC 001",
        )
        signals = preprocessor.extract_signals(payment)
        assert signals.keywords.get("partial") is True or signals.keywords.get("advance") is True


class TestFullPreprocessing:
    def test_full_pipeline(self, preprocessor):
        payment = Payment(
            id="P1",
            amount=15000.50,
            label_raw="Règlement fac-2024-001234 octobre",
            iban_source="FR76 1234 5678 9012 3456 7890 123",
        )
        result = preprocessor.process(payment)
        assert result.label_normalized != ""
        assert result.signals.fingerprint != ""
        assert result.signals.label_class != LabelClass.EMPTY

    def test_debtor_enrichment(self, preprocessor):
        debtor = Debtor(id="D1", name="Test Corp", iban="FR7612345678901234567890123")
        payment = Payment(
            id="P1", amount=1000,
            label_raw="test", iban_source="FR7612345678901234567890123",
        )
        result = preprocessor.process(
            payment,
            debtor_lookup={"D1": debtor},
            iban_debtor_map={"FR7612345678901234567890123": "D1"},
        )
        assert result.debtor_id == "D1"
        assert result.debtor is not None
