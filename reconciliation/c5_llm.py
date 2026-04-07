"""
Layer C5 - LLM & Generative AI (Confidence variable, validated)
Uses Claude/GPT for complex, ambiguous, or cryptic payment labels.
Includes prompt library, anti-hallucination validation, cost optimization.

Components:
  C5.1 - LLM architecture (6 components)
  C5.2 - Prompt library (generic, cryptic, ambiguous)
  C5.3 - Response validation (anti-hallucination)
  C5.4 - Cost optimization (8 techniques)
  C5.5 - LLM metrics and monitoring
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .config import C5Config
from .models import Invoice, MatchMethod, MatchResult, Payment

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C5.2 — Prompt Library
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert payment reconciliation assistant for a factoring company.
Your task is to analyze incoming payment information and match it to open invoices.

RULES:
1. Only suggest matches you are confident about based on the evidence provided.
2. Never fabricate invoice references or amounts.
3. If you cannot determine a match, say so explicitly.
4. Always explain your reasoning step by step.
5. Return structured JSON output as specified.

DOMAIN CONTEXT:
- Factoring: a company purchases receivables (invoices) from sellers and collects from debtors.
- Payment labels are often truncated, abbreviated, or in multiple languages (FR, EN, DE, NL).
- Common abbreviations: FAC=facture, REGLT=règlement, VIR=virement, AVO=avoir.
- Debtors may reference PO numbers, BL numbers, or period descriptions instead of invoice numbers.
"""

PROMPT_GENERIC = """Analyze this payment and determine which invoice(s) it corresponds to.

PAYMENT:
- ID: {payment_id}
- Amount: {amount} {currency}
- Date: {date}
- Label: "{label_raw}"
- Normalized label: "{label_normalized}"
- Debtor: {debtor_name} (ID: {debtor_id})
- IBAN source: {iban}
- Extracted references: {refs}
- Detected keywords: {keywords}

OPEN INVOICES FOR THIS DEBTOR:
{invoices_table}

PREVIOUS LAYER RESULTS:
{previous_results}

Respond in this exact JSON format:
{{
  "match_found": true/false,
  "matched_invoices": ["REF1", "REF2"],
  "confidence": 0.0 to 1.0,
  "reasoning": "Step-by-step explanation",
  "allocation": {{"REF1": amount1, "REF2": amount2}},
  "flags": ["FLAG1", "FLAG2"],
  "alternative_matches": [{{"refs": ["REF3"], "confidence": 0.5, "reason": "..."}}]
}}"""

PROMPT_CRYPTIC = """This payment has a CRYPTIC label that previous matching layers could not resolve.
Analyze the limited information available and try to determine the most likely invoice match.

PAYMENT:
- Amount: {amount} {currency}
- Date: {date}
- Raw label: "{label_raw}"
- Debtor: {debtor_name}

OPEN INVOICES:
{invoices_table}

DEBTOR PAYMENT HISTORY PATTERNS:
{debtor_patterns}

Think step by step:
1. Is there any hidden structure in the label?
2. Does the amount match any invoice exactly or with known tolerance?
3. Does the payment timing align with any invoice due date?
4. Is this consistent with the debtor's payment patterns?

Respond in JSON format as specified above."""

PROMPT_AMBIGUOUS = """This payment could match MULTIPLE invoices. Determine the most likely allocation.

PAYMENT:
- Amount: {amount} {currency}
- Label: "{label_raw}"
- Debtor: {debtor_name}

CANDIDATE MATCHES (from previous layers):
{candidates_table}

For each candidate, evaluate:
1. Strength of reference match
2. Amount compatibility
3. Temporal plausibility
4. Consistency with debtor behavior

Choose the best match or explain why it's a multi-invoice payment.
Respond in JSON format as specified above."""


# ---------------------------------------------------------------------------
# C5.1 — LLM Client Abstraction
# ---------------------------------------------------------------------------

class LLMClient:
    """Abstraction over LLM providers (Claude, GPT, etc.)."""

    def __init__(self, config: C5Config):
        self.config = config
        self._client = None
        self._cache: dict[str, Any] = {}
        self._total_tokens = 0
        self._total_cost = 0.0
        self._call_count = 0

    def _init_client(self):
        """Lazy-initialize the LLM client."""
        if self._client is not None:
            return

        if "claude" in self.config.model:
            try:
                import anthropic
                self._client = anthropic.Anthropic()
                self._provider = "anthropic"
                return
            except ImportError:
                pass

        try:
            import openai
            self._client = openai.OpenAI()
            self._provider = "openai"
        except ImportError:
            logger.error("No LLM client available (anthropic or openai)")
            self._provider = None

    def query(self, prompt: str, system: str = SYSTEM_PROMPT) -> dict[str, Any] | None:
        """Send prompt to LLM and return parsed JSON response."""
        # C5.4: Cache check
        cache_key = hashlib.md5(prompt.encode()).hexdigest()
        if cache_key in self._cache:
            logger.debug("LLM cache hit")
            return self._cache[cache_key]

        self._init_client()
        if self._client is None:
            return None

        start = time.time()
        response_text = ""

        try:
            if self._provider == "anthropic":
                response = self._client.messages.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    system=system,
                    messages=[{"role": "user", "content": prompt}],
                )
                response_text = response.content[0].text
                self._total_tokens += response.usage.input_tokens + response.usage.output_tokens

            elif self._provider == "openai":
                response = self._client.chat.completions.create(
                    model=self.config.model,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                )
                response_text = response.choices[0].message.content or ""
                if response.usage:
                    self._total_tokens += response.usage.total_tokens

        except Exception as e:
            logger.error("LLM call failed: %s", e)
            return None

        elapsed = time.time() - start
        self._call_count += 1

        # Parse JSON from response
        result = self._parse_json_response(response_text)

        if result:
            self._cache[cache_key] = result

        logger.info("LLM call: %.2fs, tokens=%d", elapsed, self._total_tokens)
        return result

    def _parse_json_response(self, text: str) -> dict[str, Any] | None:
        """Extract and parse JSON from LLM response."""
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try extracting JSON block
        import re
        json_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try finding first { ... }
        brace_match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group())
            except json.JSONDecodeError:
                pass

        logger.warning("Failed to parse LLM JSON response")
        return None

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "total_tokens": self._total_tokens,
            "total_cost_usd": self._total_cost,
            "call_count": self._call_count,
            "cache_size": len(self._cache),
        }


# ---------------------------------------------------------------------------
# C5.3 — Response Validation (Anti-Hallucination)
# ---------------------------------------------------------------------------

class ResponseValidator:
    """Validates LLM responses against known facts to prevent hallucinations."""

    def validate(
        self,
        response: dict[str, Any],
        payment: Payment,
        invoices: list[Invoice],
    ) -> tuple[bool, list[str]]:
        """
        Validate LLM response. Returns (is_valid, list_of_issues).
        """
        issues: list[str] = []
        invoice_refs = {inv.reference for inv in invoices}
        invoice_by_ref = {inv.reference: inv for inv in invoices}

        matched_refs = response.get("matched_invoices", [])
        allocation = response.get("allocation", {})
        confidence = response.get("confidence", 0)

        # Check 1: All referenced invoices must exist
        for ref in matched_refs:
            if ref not in invoice_refs:
                issues.append(f"HALLUCINATED_REF: {ref} not in open invoices")

        # Check 2: Allocation amounts must be positive and reasonable
        for ref, amount in allocation.items():
            if amount <= 0:
                issues.append(f"NEGATIVE_ALLOCATION: {ref}={amount}")
            if ref in invoice_by_ref:
                inv = invoice_by_ref[ref]
                if amount > inv.amount * 1.1:
                    issues.append(f"OVER_ALLOCATED: {ref} allocated {amount} > invoice {inv.amount}")

        # Check 3: Total allocation should not exceed payment amount (with small tolerance)
        total_allocated = sum(allocation.values())
        if total_allocated > payment.amount * 1.05:
            issues.append(f"OVER_TOTAL: allocated {total_allocated} > payment {payment.amount}")

        # Check 4: Confidence must be reasonable
        if confidence > 0.99:
            issues.append("OVERCONFIDENT: LLM confidence > 0.99 is suspicious")

        # Check 5: Must have reasoning
        if not response.get("reasoning"):
            issues.append("NO_REASONING: LLM did not explain its decision")

        is_valid = len(issues) == 0
        return is_valid, issues


# ---------------------------------------------------------------------------
# Main C5 Matcher
# ---------------------------------------------------------------------------

class LLMMatcher:
    """
    Layer C5: LLM-based matching for complex/ambiguous cases.
    """

    def __init__(self, config: C5Config | None = None):
        self.config = config or C5Config()
        self._client = LLMClient(self.config)
        self._validator = ResponseValidator()

    def match(
        self,
        payment: Payment,
        open_invoices: list[Invoice],
        previous_candidates: list[MatchResult] | None = None,
    ) -> MatchResult | None:
        """Use LLM to resolve complex matching cases."""
        debtor_invoices = [
            inv for inv in open_invoices
            if not payment.debtor_id or inv.debtor_id == payment.debtor_id
        ]

        if not debtor_invoices:
            return None

        # Select appropriate prompt
        prompt = self._build_prompt(payment, debtor_invoices, previous_candidates)

        # Query LLM
        response = self._client.query(prompt)
        if not response:
            return None

        # Validate response
        is_valid, issues = self._validator.validate(response, payment, debtor_invoices)
        if not is_valid:
            logger.warning("LLM response validation failed: %s", issues)
            # Retry once with explicit correction
            if self.config.max_retries > 0:
                correction_prompt = (
                    f"Your previous response had issues: {issues}. "
                    f"Please correct and respond again.\n\n{prompt}"
                )
                response = self._client.query(correction_prompt)
                if response:
                    is_valid, issues = self._validator.validate(response, payment, debtor_invoices)

            if not is_valid:
                return None

        # Convert to MatchResult
        return self._response_to_result(response, payment, debtor_invoices)

    def _build_prompt(
        self,
        payment: Payment,
        invoices: list[Invoice],
        candidates: list[MatchResult] | None,
    ) -> str:
        """Build the appropriate prompt based on the payment characteristics."""
        # Build invoices table
        invoices_table = self._format_invoices(invoices)

        # Select prompt template
        if payment.signals.label_class.value in ("EMPTY", "CRYPTIC"):
            template = PROMPT_CRYPTIC
            return template.format(
                amount=payment.amount,
                currency=payment.currency.value,
                date=payment.date,
                label_raw=payment.label_raw,
                debtor_name=payment.debtor.name if payment.debtor else "Unknown",
                invoices_table=invoices_table,
                debtor_patterns=self._format_debtor_patterns(payment.debtor),
            )

        if candidates and len(candidates) > 1:
            template = PROMPT_AMBIGUOUS
            return template.format(
                amount=payment.amount,
                currency=payment.currency.value,
                label_raw=payment.label_raw,
                debtor_name=payment.debtor.name if payment.debtor else "Unknown",
                candidates_table=self._format_candidates(candidates),
            )

        # Generic prompt
        return PROMPT_GENERIC.format(
            payment_id=payment.id,
            amount=payment.amount,
            currency=payment.currency.value,
            date=payment.date,
            label_raw=payment.label_raw,
            label_normalized=payment.label_normalized,
            debtor_name=payment.debtor.name if payment.debtor else "Unknown",
            debtor_id=payment.debtor_id or "Unknown",
            iban=payment.iban_source,
            refs=payment.signals.raw_refs,
            keywords=payment.signals.keywords,
            invoices_table=invoices_table,
            previous_results=self._format_candidates(candidates) if candidates else "None",
        )

    def _format_invoices(self, invoices: list[Invoice]) -> str:
        lines = ["| Ref | Amount | HT | Issue Date | Due Date | PO |"]
        lines.append("|-----|--------|-----|------------|----------|-----|")
        for inv in invoices[:20]:  # Limit to 20 to control token usage
            lines.append(
                f"| {inv.reference} | {inv.amount:.2f} | {inv.amount_ht:.2f} "
                f"| {inv.issue_date} | {inv.due_date} | {inv.po_number or '-'} |"
            )
        if len(invoices) > 20:
            lines.append(f"| ... and {len(invoices) - 20} more invoices |")
        return "\n".join(lines)

    def _format_candidates(self, candidates: list[MatchResult] | None) -> str:
        if not candidates:
            return "None"
        lines = []
        for c in candidates:
            refs = [inv.reference for inv in c.invoices]
            lines.append(
                f"- Method: {c.method.value}, Confidence: {c.confidence:.2f}, "
                f"Invoices: {refs}, Flags: {c.flags}"
            )
        return "\n".join(lines)

    def _format_debtor_patterns(self, debtor) -> str:
        if not debtor:
            return "No debtor history available"
        return (
            f"- Avg payment delay: {debtor.avg_payment_delay} days\n"
            f"- Regularity score: {debtor.payment_regularity_score}\n"
            f"- Known patterns: {debtor.known_payment_patterns}\n"
            f"- Usual invoices per payment: {debtor.usual_invoice_counts_per_payment}"
        )

    def _response_to_result(
        self,
        response: dict[str, Any],
        payment: Payment,
        invoices: list[Invoice],
    ) -> MatchResult | None:
        if not response.get("match_found"):
            return None

        matched_refs = response.get("matched_invoices", [])
        allocation = response.get("allocation", {})
        confidence = min(response.get("confidence", 0), 0.95)  # Cap LLM confidence

        inv_by_ref = {inv.reference: inv for inv in invoices}
        matched_invs = [inv_by_ref[ref] for ref in matched_refs if ref in inv_by_ref]

        if not matched_invs:
            return None

        return MatchResult(
            payment_id=payment.id,
            invoices=matched_invs,
            method=MatchMethod.C5_LLM,
            confidence=confidence,
            allocated=allocation,
            flags=response.get("flags", ["LLM_MATCH"]),
            explanation=response.get("reasoning", ""),
            rule_id="R-LLM",
            metadata={
                "llm_model": self.config.model,
                "alternative_matches": response.get("alternative_matches", []),
            },
        )

    @property
    def metrics(self) -> dict[str, Any]:
        return self._client.metrics
