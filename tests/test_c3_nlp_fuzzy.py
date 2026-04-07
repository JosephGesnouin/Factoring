"""Tests for Layer C3 - NLP, Fuzzy Matching & Embeddings."""

import pytest
from datetime import date

from reconciliation.c3_nlp_fuzzy import (
    NLPFuzzyMatcher,
    compute_composite_fuzzy_score,
    extract_ner_entities,
    _levenshtein_ratio,
    _jaro_winkler,
    _token_set_ratio,
    _ngram_similarity,
    _numeric_ref_similarity,
)
from reconciliation.models import Invoice, Payment, PaymentSignals


def make_invoice(ref="FAC-2024-001", amount=10000.0, debtor_id="D1"):
    return Invoice(
        id=f"INV-{ref}", reference=ref, debtor_id=debtor_id,
        amount=amount, amount_ht=amount / 1.20,
        issue_date=date(2024, 9, 1), due_date=date(2024, 10, 1),
    )


class TestFuzzyAlgorithms:
    def test_levenshtein_identical(self):
        assert _levenshtein_ratio("FAC001", "FAC001") == 1.0

    def test_levenshtein_similar(self):
        score = _levenshtein_ratio("FAC001", "FAC002")
        assert score > 0.8

    def test_levenshtein_different(self):
        score = _levenshtein_ratio("FAC001", "XYZ999")
        assert score < 0.5

    def test_jaro_winkler_similar(self):
        score = _jaro_winkler("FAC2024001", "FAC2024002")
        assert score > 0.85

    def test_token_set_overlap(self):
        score = _token_set_ratio("FAC 2024 001 OCTOBRE", "FAC 2024 001")
        assert score > 0.5

    def test_ngram_similarity(self):
        score = _ngram_similarity("FAC2024001", "FAC2024002")
        assert score > 0.5

    def test_numeric_ref_identical(self):
        assert _numeric_ref_similarity("FAC001234", "INV001234") == 1.0

    def test_numeric_ref_leading_zeros(self):
        assert _numeric_ref_similarity("FAC001234", "FAC1234") == 1.0

    def test_composite_score(self):
        score = compute_composite_fuzzy_score("FAC2024001", "FAC2024001")
        assert score > 0.95

        score_diff = compute_composite_fuzzy_score("FAC001", "XYZ999")
        assert score_diff < 0.5


class TestNER:
    def test_invoice_ref_extraction(self):
        entities = extract_ner_entities("REGLEMENT FAC-2024-001234 DU 01/10/2024")
        types = [e.entity_type for e in entities]
        assert "INVOICE_REF" in types

    def test_amount_extraction(self):
        entities = extract_ner_entities("MONTANT 15.000,50 EUR")
        types = [e.entity_type for e in entities]
        assert "AMOUNT" in types

    def test_date_extraction(self):
        entities = extract_ner_entities("PAIEMENT DU 15/10/2024")
        types = [e.entity_type for e in entities]
        assert "DATE" in types

    def test_credit_note_extraction(self):
        entities = extract_ner_entities("DEDUCTION AVOIR AV-001234")
        types = [e.entity_type for e in entities]
        assert "CREDIT_NOTE" in types

    def test_empty_text(self):
        entities = extract_ner_entities("")
        assert len(entities) == 0


class TestNLPFuzzyMatcher:
    def test_fuzzy_ref_match(self):
        matcher = NLPFuzzyMatcher()
        inv = make_invoice("FAC2024001234", 10000.0)
        payment = Payment(
            id="P1", amount=10000.0, debtor_id="D1",
            date=date(2024, 10, 15),
            label_raw="FAC2024001235",  # Off by one digit
            label_normalized="FAC2024001235",
            signals=PaymentSignals(raw_refs=["FAC2024001235"]),
        )
        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        # Should find a fuzzy match since refs are very similar
        assert result is not None
        assert result.confidence > 0.75

    def test_no_match_completely_different(self):
        matcher = NLPFuzzyMatcher()
        inv = make_invoice("FAC2024001234", 10000.0)
        payment = Payment(
            id="P1", amount=5000.0, debtor_id="D2",
            label_raw="XYZ", label_normalized="XYZ",
            signals=PaymentSignals(raw_refs=["XYZ"]),
        )
        matcher.build_index([inv])
        result = matcher.match(payment, [inv])
        assert result is None  # Different debtor + different ref
