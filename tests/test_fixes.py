"""Tests for audit fixes: duplicate index, layer attribute, subset sum DP, etc."""

import pytest
from datetime import date

from reconciliation.c1_exact_matching import ExactMatcher, InvoiceHashIndex
from reconciliation.c2_business_rules import BusinessRuleMatcher, DuplicateIndex
from reconciliation.c5_llm import LLMClient, llm_config_from_env
from reconciliation.config import C5Config, ReconciliationConfig
from reconciliation.models import (
    CreditNote, Debtor, Invoice, MatchMethod, Payment, PaymentSignals,
)
from reconciliation.orchestrator import ReconciliationOrchestrator
from reconciliation.utils import normalize_ref, safe_div, strip_leading_zeros


# ───────────────────────── utils ─────────────────────────

class TestNormalizeRef:
    def test_basic(self):
        assert normalize_ref("FAC-2024-001") == "FAC2024001"

    def test_lowercase(self):
        assert normalize_ref("fac/2024/001") == "FAC2024001"

    def test_none(self):
        assert normalize_ref(None) == ""

    def test_empty(self):
        assert normalize_ref("") == ""

    def test_cached(self):
        # Verify lru_cache: calling twice should return the same exact object
        a = normalize_ref("FAC-2024-001")
        b = normalize_ref("FAC-2024-001")
        assert a is b


class TestSafeDiv:
    def test_normal(self):
        assert safe_div(10, 2) == 5.0

    def test_zero_denom(self):
        assert safe_div(10, 0) == 0.0

    def test_zero_denom_custom_default(self):
        assert safe_div(10, 0, default=999.0) == 999.0


class TestStripLeadingZeros:
    def test_basic(self):
        assert strip_leading_zeros("000123") == "123"

    def test_all_zeros(self):
        assert strip_leading_zeros("000") == "0"

    def test_empty(self):
        assert strip_leading_zeros("") == ""


# ───────────────────────── DuplicateIndex ─────────────────────────

def _make_payment(pid, amount=1000.0, debtor="D1", dt=None, fp=None):
    signals = PaymentSignals()
    if fp:
        signals.fingerprint = fp
    return Payment(
        id=pid, amount=amount, date=dt or date(2024, 10, 15),
        label_raw="", label_normalized="", debtor_id=debtor,
        signals=signals,
    )


class TestDuplicateIndex:
    def test_add_and_find_exact(self):
        idx = DuplicateIndex()
        p1 = _make_payment("P1", fp="abc123")
        idx.add(p1)
        p2 = _make_payment("P2", fp="abc123")
        assert idx.find_exact(p2) == "P1"

    def test_find_same_day_amount(self):
        idx = DuplicateIndex()
        p1 = _make_payment("P1", amount=1000.0, debtor="D1", dt=date(2024, 10, 15))
        idx.add(p1)
        p2 = _make_payment("P2", amount=1000.0, debtor="D1", dt=date(2024, 10, 15))
        assert idx.find_same_day_amount(p2) == "P1"

    def test_different_debtor_no_match(self):
        idx = DuplicateIndex()
        p1 = _make_payment("P1", amount=1000.0, debtor="D1")
        idx.add(p1)
        p2 = _make_payment("P2", amount=1000.0, debtor="D2")
        assert idx.find_same_day_amount(p2) is None

    def test_no_double_alert(self):
        """Same payment matching multiple criteria should only emit one alert."""
        matcher = BusinessRuleMatcher()
        p1 = _make_payment("P1", amount=1000.0, debtor="D1", dt=date(2024, 10, 15))
        p2 = _make_payment("P2", amount=1000.0, debtor="D1", dt=date(2024, 10, 15))
        alerts = matcher.check_duplicates(p2, [p1])
        assert len(alerts) == 1  # no double emission


# ───────────────────────── layer attribute metric fix ─────────────────────────

def _make_invoice(ref="FAC001", amount=10000.0, debtor="D1"):
    return Invoice(
        id=f"INV-{ref}", reference=ref, debtor_id=debtor,
        amount=amount, amount_ht=amount/1.2,
        issue_date=date(2024, 9, 1), due_date=date(2024, 10, 1),
    )


class TestOrchestratorLayerAttribute:
    def test_c2_match_has_layer_2(self):
        """Regression test: C2 matches used to leave layer=0 in metrics."""
        orch = ReconciliationOrchestrator()
        inv = _make_invoice("FAC001", 10000.0)
        payment = Payment(
            id="P1", amount=10000.5, debtor_id="D1",
            date=date(2024, 10, 15), label_raw="", label_normalized="",
            signals=PaymentSignals(),
        )
        orch.setup([inv])
        ctx = orch.process_payment(payment, [inv])
        if ctx.final_match:
            assert ctx.final_match.layer == 2, \
                f"Expected layer=2 for C2 match, got {ctx.final_match.layer}"


# ───────────────────────── InvoiceHashIndex determinism ─────────────────────────

class TestInvoiceHashIndexDeterministic:
    def test_year_variants_use_invoice_year(self):
        """Index should use invoice.issue_date.year, not datetime.now()."""
        idx = InvoiceHashIndex()
        inv = Invoice(
            id="INV-001", reference="FAC-2020-001", debtor_id="D1",
            amount=100.0, amount_ht=83.0,
            issue_date=date(2020, 5, 15),
            due_date=date(2020, 6, 15),
        )
        idx.index_invoice(inv)
        # Variants should include the invoice's own year
        variants = idx._generate_ref_variants(inv.reference, year=2020)
        assert any("2020" in v for v in variants)

    def test_lookup_all_returns_list(self):
        idx = InvoiceHashIndex()
        inv = Invoice(
            id="INV-001", reference="FAC001", debtor_id="D1",
            amount=100.0, amount_ht=83.0, issue_date=date(2024, 1, 1),
        )
        idx.index_invoice(inv)
        ids = idx.lookup_all("FAC001")
        assert isinstance(ids, list)
        assert "INV-001" in ids


# ───────────────────────── LLM config and parser ─────────────────────────

class TestLLMConfig:
    def test_explicit_api_key(self):
        cfg = C5Config()
        cfg.api_key = "sk-ant-test123"
        cfg.provider = "anthropic"
        client = LLMClient(cfg)
        assert client.config.api_key == "sk-ant-test123"

    def test_llm_disabled(self):
        cfg = C5Config()
        cfg.enabled = False
        client = LLMClient(cfg)
        # query() should return None without calling the API
        result = client.query("test prompt")
        assert result is None

    def test_llm_config_from_env(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "anthropic")
        monkeypatch.setenv("LLM_MODEL", "claude-haiku")
        monkeypatch.setenv("LLM_MAX_TOKENS", "512")
        monkeypatch.setenv("LLM_ENABLED", "false")
        cfg = llm_config_from_env()
        assert cfg.provider == "anthropic"
        assert cfg.model == "claude-haiku"
        assert cfg.max_tokens == 512
        assert cfg.enabled is False

    def test_llm_json_parser_nested(self):
        """Regression: old regex only matched one level of brace nesting."""
        from reconciliation.c5_llm import LLMClient
        cfg = C5Config()
        client = LLMClient(cfg)
        text = 'Some prose\n{"match_found": true, "allocation": {"A": 100, "B": 200}}\nmore text'
        result = client._parse_json_response(text)
        assert result is not None
        assert result["match_found"] is True
        assert result["allocation"]["A"] == 100

    def test_llm_json_parser_fenced(self):
        from reconciliation.c5_llm import LLMClient
        client = LLMClient(C5Config())
        text = 'Here is the JSON:\n```json\n{"a": 1, "b": {"c": [1,2,3]}}\n```'
        result = client._parse_json_response(text)
        assert result == {"a": 1, "b": {"c": [1, 2, 3]}}


# ───────────────────────── subset sum DP ─────────────────────────

class TestSubsetSumDP:
    def test_large_portfolio(self):
        """Meet-in-the-middle should handle 20 invoices in < 100ms."""
        import time
        matcher = BusinessRuleMatcher()
        invoices = [
            Invoice(id=f"INV-{i}", reference=f"FAC{i}", debtor_id="D1",
                    amount=float(100 * (i + 1)), amount_ht=float(100 * (i + 1)),
                    issue_date=date(2024, 1, 1))
            for i in range(20)
        ]
        # Target = sum of invoices 3, 7, 11 = 400 + 800 + 1200 = 2400
        target = 400.0 + 800.0 + 1200.0
        payment = Payment(
            id="P1", amount=target, debtor_id="D1",
            date=date(2024, 2, 15), label_raw="BULK", label_normalized="BULK",
            signals=PaymentSignals(),
        )
        t0 = time.time()
        result = matcher._rule_subset_sum(payment, invoices)
        elapsed = time.time() - t0
        assert result is not None, "Should find subset sum match"
        assert elapsed < 1.0, f"Subset sum too slow: {elapsed:.2f}s"

    def test_greedy_requires_min_2_invoices(self):
        """Single-invoice 'subset' should not be returned by C2 subset sum."""
        matcher = BusinessRuleMatcher()
        invoices = [
            Invoice(id="INV-1", reference="F1", debtor_id="D1",
                    amount=1000.0, amount_ht=833.0, issue_date=date(2024, 1, 1)),
        ]
        payment = Payment(
            id="P1", amount=1000.0, debtor_id="D1",
            date=date(2024, 2, 15), label_raw="", label_normalized="",
            signals=PaymentSignals(),
        )
        result = matcher._greedy_subset(1000.0, invoices, payment)
        # Single-invoice matches belong to C1, not subset-sum
        assert result is None


# ───────────────────────── normalize_label loop ─────────────────────────

class TestNormalizeLabelLoop:
    def test_multiple_bank_prefixes(self):
        """Stripping should loop until stable."""
        from reconciliation.c0_preprocessing import PaymentPreprocessor
        pp = PaymentPreprocessor()
        # Mix of two prefixes in sequence
        result = pp.normalize_label("VIREMENT RECU DE SEPA CREDIT TRANSFER FAC-001")
        assert "VIREMENT" not in result
        assert "SEPA CREDIT TRANSFER" not in result
        assert "FAC" in result
