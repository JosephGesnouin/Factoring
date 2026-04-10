"""
Layer C3 - NLP, Fuzzy Matching (Confidence 75-92%)
Uses 8 fuzzy algorithms with composite scoring, custom NER, and
TF-IDF character n-grams.

Components:
  C3.1 - Fuzzy matching (8 algorithms + composite score)
  C3.2 - Custom NER (10 entity types)
  C3.3 - (disabled) Semantic embeddings via sentence-transformers
  C3.4 - Combined multi-signal NLP rules
  C3.5 - TF-IDF character n-grams
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .config import C3Config
from .models import Invoice, MatchMethod, MatchResult, Payment
from .utils import normalize_ref

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# C3.1 — Fuzzy matching algorithms
# ---------------------------------------------------------------------------

def _levenshtein_ratio(s1: str, s2: str) -> float:
    """Normalized Levenshtein distance."""
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0
    max_len = max(len(s1), len(s2))
    try:
        from rapidfuzz.distance import Levenshtein
        dist = Levenshtein.distance(s1, s2)
    except ImportError:
        dist = _simple_levenshtein(s1, s2)
    return 1.0 - dist / max_len


def _simple_levenshtein(s1: str, s2: str) -> int:
    """Pure-Python Levenshtein distance fallback."""
    if len(s1) < len(s2):
        return _simple_levenshtein(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            curr.append(min(
                prev[j + 1] + 1,
                curr[j] + 1,
                prev[j] + (0 if c1 == c2 else 1),
            ))
        prev = curr
    return prev[-1]


def _jaro_winkler(s1: str, s2: str) -> float:
    """Jaro-Winkler similarity - good for short strings and typos."""
    try:
        from rapidfuzz.distance import JaroWinkler
        return JaroWinkler.similarity(s1, s2)
    except ImportError:
        return _levenshtein_ratio(s1, s2)  # fallback


def _token_sort_ratio(s1: str, s2: str) -> float:
    """Sort tokens alphabetically then compare - handles word reordering."""
    sorted1 = " ".join(sorted(s1.split()))
    sorted2 = " ".join(sorted(s2.split()))
    return _levenshtein_ratio(sorted1, sorted2)


def _token_set_ratio(s1: str, s2: str) -> float:
    """Set-based comparison - handles extra/missing words."""
    set1 = set(s1.split())
    set2 = set(s2.split())
    if not set1 and not set2:
        return 1.0
    if not set1 or not set2:
        return 0.0
    intersection = set1 & set2
    union = set1 | set2
    return len(intersection) / len(union)


def _partial_ratio(s1: str, s2: str) -> float:
    """Best partial substring match."""
    try:
        from rapidfuzz import fuzz
        return fuzz.partial_ratio(s1, s2) / 100.0
    except ImportError:
        shorter, longer = (s1, s2) if len(s1) <= len(s2) else (s2, s1)
        if not shorter:
            return 0.0
        best = 0.0
        for i in range(len(longer) - len(shorter) + 1):
            chunk = longer[i:i + len(shorter)]
            score = _levenshtein_ratio(shorter, chunk)
            best = max(best, score)
        return best


def _ngram_similarity(s1: str, s2: str, n: int = 3) -> float:
    """Character n-gram overlap (Jaccard)."""
    if len(s1) < n or len(s2) < n:
        return _levenshtein_ratio(s1, s2)
    ng1 = {s1[i:i + n] for i in range(len(s1) - n + 1)}
    ng2 = {s2[i:i + n] for i in range(len(s2) - n + 1)}
    if not ng1 or not ng2:
        return 0.0
    return len(ng1 & ng2) / len(ng1 | ng2)


def _longest_common_subsequence_ratio(s1: str, s2: str) -> float:
    """LCS-based similarity."""
    if not s1 or not s2:
        return 0.0
    m, n = len(s1), len(s2)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    lcs_len = dp[m][n]
    return 2.0 * lcs_len / (m + n)


def _numeric_ref_similarity(s1: str, s2: str) -> float:
    """Extract numeric parts and compare - handles prefix changes."""
    nums1 = re.findall(r"\d+", s1)
    nums2 = re.findall(r"\d+", s2)
    if not nums1 or not nums2:
        return 0.0
    # Compare longest numeric sequences
    n1 = max(nums1, key=len)
    n2 = max(nums2, key=len)
    # Strip leading zeros for comparison
    n1s = n1.lstrip("0") or "0"
    n2s = n2.lstrip("0") or "0"
    if n1s == n2s:
        return 1.0
    return _levenshtein_ratio(n1s, n2s)


FUZZY_ALGORITHMS = {
    "levenshtein": (_levenshtein_ratio, 0.15),
    "jaro_winkler": (_jaro_winkler, 0.15),
    "token_sort": (_token_sort_ratio, 0.10),
    "token_set": (_token_set_ratio, 0.10),
    "partial": (_partial_ratio, 0.15),
    "ngram": (_ngram_similarity, 0.10),
    "lcs": (_longest_common_subsequence_ratio, 0.10),
    "numeric_ref": (_numeric_ref_similarity, 0.15),
}


def compute_composite_fuzzy_score(s1: str, s2: str) -> float:
    """Weighted composite of all 8 fuzzy algorithms."""
    total = 0.0
    for name, (func, weight) in FUZZY_ALGORITHMS.items():
        score = func(s1, s2)
        total += score * weight
    return total


# ---------------------------------------------------------------------------
# C3.2 — Custom NER (Named Entity Recognition)
# ---------------------------------------------------------------------------

@dataclass
class NEREntity:
    entity_type: str
    value: str
    start: int
    end: int
    confidence: float


NER_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    ("INVOICE_REF", re.compile(r"\b(FAC(?:T(?:URE)?)?[\s\-/]*\d{4,10})\b", re.I), "invoice"),
    ("PO_REF", re.compile(r"\b((?:PO|CMD|BC|COMMANDE)[\s\-/]*\d{3,10})\b", re.I), "po"),
    ("BL_REF", re.compile(r"\b(BL[\s\-/]*\d{3,10})\b", re.I), "bl"),
    ("AMOUNT", re.compile(r"\b(\d{1,3}(?:[.\s]\d{3})*[,]\d{2})\s*(?:EUR|€)?\b"), "amount"),
    ("DATE", re.compile(r"\b(\d{2}[/\-]\d{2}[/\-]\d{2,4})\b"), "date"),
    ("PERIOD", re.compile(r"\b((?:JANV|FEV|MARS|AVR|MAI|JUIN|JUIL|AOUT|SEPT|OCT|NOV|DEC)\w*\s*\d{2,4})\b", re.I), "period"),
    ("DEBTOR_CODE", re.compile(r"\b(CLT[\s\-/]*\d{4,8})\b", re.I), "debtor"),
    ("IBAN", re.compile(r"\b([A-Z]{2}\d{2}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4}[\s]?\d{4})\b"), "iban"),
    ("CREDIT_NOTE", re.compile(r"\b(AV(?:OIR)?[\s\-/]*\d{3,10})\b", re.I), "credit"),
    ("CONTRACT", re.compile(r"\b(CTR[\s\-/]*\d{3,10})\b", re.I), "contract"),
]


def extract_ner_entities(text: str) -> list[NEREntity]:
    """Rule-based NER for payment label entities."""
    entities = []
    for entity_type, pattern, _ in NER_PATTERNS:
        for m in pattern.finditer(text):
            entities.append(NEREntity(
                entity_type=entity_type,
                value=m.group(1),
                start=m.start(1),
                end=m.end(1),
                confidence=0.85,
            ))
    return entities


# ---------------------------------------------------------------------------
# C3.5 — TF-IDF Character N-Grams
# ---------------------------------------------------------------------------

class TFIDFMatcher:
    """TF-IDF based matching using character n-grams."""

    def __init__(self, ngram_range: tuple[int, int] = (2, 4)):
        self.ngram_range = ngram_range
        self._vectorizer = None
        self._matrix = None
        self._invoice_ids: list[str] = []

    def fit(self, invoices: list[Invoice]) -> None:
        """Build TF-IDF matrix from invoice references and metadata."""
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
        except ImportError:
            logger.warning("scikit-learn not available, TF-IDF disabled")
            return

        if not invoices:
            return

        docs = []
        self._invoice_ids = []
        for inv in invoices:
            text = f"{inv.reference} {inv.debtor_id} {inv.amount}"
            docs.append(text)
            self._invoice_ids.append(inv.id)

        try:
            self._vectorizer = TfidfVectorizer(
                analyzer="char",
                ngram_range=self.ngram_range,
            )
            self._matrix = self._vectorizer.fit_transform(docs)
        except ValueError:
            # Empty vocabulary (e.g. single very short doc)
            self._vectorizer = None
            self._matrix = None

    def find_similar(self, query: str, top_k: int = 5) -> list[tuple[str, float]]:
        """Find top-k similar invoices by TF-IDF cosine similarity."""
        if self._vectorizer is None or self._matrix is None:
            return []

        try:
            from sklearn.metrics.pairwise import cosine_similarity
        except ImportError:
            return []

        query_vec = self._vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self._matrix).flatten()
        top_indices = scores.argsort()[::-1][:top_k]

        results = []
        for idx in top_indices:
            if scores[idx] > 0.1:
                results.append((self._invoice_ids[idx], float(scores[idx])))
        return results


# C3.3 Semantic embedding layer removed. Re-enable by reintroducing an
# EmbeddingMatcher class that wraps sentence-transformers.


# ---------------------------------------------------------------------------
# Main C3 Matcher
# ---------------------------------------------------------------------------

class NLPFuzzyMatcher:
    """
    Layer C3: Combines fuzzy matching, NER, and TF-IDF.
    Multi-signal scoring for cases not caught by C1/C2.
    """

    def __init__(self, config: C3Config | None = None):
        self.config = config or C3Config()
        self._tfidf = TFIDFMatcher(ngram_range=self.config.tfidf_ngram_range)
        self._invoice_lookup: dict[str, Invoice] = {}

    def build_index(self, invoices: list[Invoice]) -> None:
        """Build all NLP indexes."""
        self._invoice_lookup = {inv.id: inv for inv in invoices}
        self._tfidf.fit(invoices)
        self._invoices = invoices

    def match(self, payment: Payment, open_invoices: list[Invoice]) -> MatchResult | None:
        """Run C3 multi-signal matching."""
        if not self._invoice_lookup:
            self.build_index(open_invoices)

        # Pre-filter to debtor's invoices for performance
        if payment.debtor_id:
            debtor_invoices = [i for i in open_invoices if i.debtor_id == payment.debtor_id]
        else:
            debtor_invoices = open_invoices[:100]  # Cap to avoid O(n²) on large portfolios

        # C3.1: Fuzzy reference matching
        result = self._fuzzy_ref_match(payment, debtor_invoices)
        if result:
            return result

        # C3.4: Combined NER + fuzzy + amount
        result = self._combined_nlp_match(payment, debtor_invoices)
        if result:
            return result

        # C3.5: TF-IDF similarity
        result = self._tfidf_match(payment, debtor_invoices)
        if result:
            return result

        return None

    def _fuzzy_ref_match(self, payment: Payment, invoices: list[Invoice]) -> MatchResult | None:
        """C3.1: Fuzzy match payment refs against invoice refs.

        Includes OCR-correction (O→0, l→1) for common misreads.
        """
        payment_refs = payment.signals.raw_refs
        if not payment_refs:
            return None

        best_score = 0.0
        best_invoice: Invoice | None = None
        best_ref = ""

        def _ocr_fix(s: str) -> str:
            """Fix common OCR/typo confusions: O→0, l→1."""
            return s.replace("O", "0").replace("o", "0").replace("l", "1").replace("I", "1")

        for pref in payment_refs[:5]:
            pref_norm = normalize_ref(pref)
            pref_ocr = _ocr_fix(pref_norm)  # also try OCR-corrected version

            candidates: list[tuple[Invoice, str, float]] = []
            for inv in invoices:
                if payment.debtor_id and inv.debtor_id != payment.debtor_id:
                    continue
                inv_ref_norm = normalize_ref(inv.reference)
                # Check both raw and OCR-corrected
                quick = max(
                    _numeric_ref_similarity(pref_norm, inv_ref_norm),
                    _numeric_ref_similarity(pref_ocr, inv_ref_norm),
                )
                if quick > 0.3:
                    candidates.append((inv, inv_ref_norm, quick))

            candidates.sort(key=lambda x: x[2], reverse=True)
            for inv, inv_ref_norm, _ in candidates[:10]:
                # Score both raw and OCR-corrected, take the best
                score = max(
                    compute_composite_fuzzy_score(pref_norm, inv_ref_norm),
                    compute_composite_fuzzy_score(pref_ocr, inv_ref_norm),
                )
                if score > best_score:
                    best_score = score
                    best_invoice = inv
                    best_ref = pref

        if best_invoice and best_score >= self.config.fuzzy_min_score:
            # Boost confidence if amount also matches
            amount_factor = 1.0
            if abs(payment.amount - best_invoice.amount) < 0.01:
                amount_factor = 1.10
            elif abs(payment.amount - best_invoice.amount) / max(best_invoice.amount, 1) < 0.05:
                amount_factor = 1.05

            confidence = min(best_score * amount_factor, 0.95)

            return MatchResult(
                payment_id=payment.id,
                invoices=[best_invoice],
                method=MatchMethod.C3_FUZZY,
                confidence=confidence,
                allocated={best_invoice.reference: min(payment.amount, best_invoice.amount)},
                flags=["FUZZY_REF_MATCH"],
                rule_id="R-FUZZY",
                metadata={"fuzzy_score": best_score, "matched_ref": best_ref},
            )

        return None

    def _combined_nlp_match(self, payment: Payment, invoices: list[Invoice]) -> MatchResult | None:
        """C3.4: Combine NER entities + fuzzy + amount signals."""
        entities = extract_ner_entities(payment.label_normalized)
        if not entities:
            return None

        # Extract invoice refs from NER
        invoice_refs = [e.value for e in entities if e.entity_type == "INVOICE_REF"]
        amounts = [e.value for e in entities if e.entity_type == "AMOUNT"]
        periods = [e.value for e in entities if e.entity_type == "PERIOD"]

        if not invoice_refs and not amounts:
            return None

        best_invoice: Invoice | None = None
        best_confidence = 0.0

        for inv in invoices:
            if payment.debtor_id and inv.debtor_id != payment.debtor_id:
                continue

            score = 0.0
            signals_used = []

            # NER reference match
            inv_ref_norm = normalize_ref(inv.reference)
            for ref in invoice_refs:
                ref_norm = normalize_ref(ref)
                ref_score = compute_composite_fuzzy_score(ref_norm, inv_ref_norm)
                if ref_score > 0.6:
                    score += ref_score * 0.5
                    signals_used.append("NER_REF")

            # Amount match from NER
            if abs(payment.amount - inv.amount) < 0.01:
                score += 0.3
                signals_used.append("AMOUNT_EXACT")
            elif abs(payment.amount - inv.amount) / max(inv.amount, 1) < 0.05:
                score += 0.15
                signals_used.append("AMOUNT_CLOSE")

            # Debtor match
            if payment.debtor_id and inv.debtor_id == payment.debtor_id:
                score += 0.2
                signals_used.append("DEBTOR_MATCH")

            if score > best_confidence:
                best_confidence = score
                best_invoice = inv

        if best_invoice and best_confidence >= 0.60:
            return MatchResult(
                payment_id=payment.id,
                invoices=[best_invoice],
                method=MatchMethod.C3_NLP_COMBINED,
                confidence=min(best_confidence, 0.92),
                allocated={best_invoice.reference: min(payment.amount, best_invoice.amount)},
                flags=["NLP_COMBINED"],
                rule_id="R-NLP",
                metadata={"ner_entities": len(entities)},
            )

        return None

    def _tfidf_match(self, payment: Payment, invoices: list[Invoice]) -> MatchResult | None:
        """C3.5: TF-IDF character n-gram matching."""
        query = f"{payment.label_normalized} {payment.amount}"
        results = self._tfidf.find_similar(query, top_k=3)

        for inv_id, score in results:
            inv = self._invoice_lookup.get(inv_id)
            if not inv:
                continue
            if payment.debtor_id and inv.debtor_id != payment.debtor_id:
                continue

            # Require decent TF-IDF score + amount proximity
            amount_diff_pct = abs(payment.amount - inv.amount) / max(inv.amount, 1)
            if score >= 0.5 and amount_diff_pct < 0.05:
                confidence = min(score * 0.9, 0.88)
                return MatchResult(
                    payment_id=payment.id,
                    invoices=[inv],
                    method=MatchMethod.C3_TFIDF,
                    confidence=confidence,
                    allocated={inv.reference: min(payment.amount, inv.amount)},
                    flags=["TFIDF_MATCH"],
                    rule_id="R-TFIDF",
                    metadata={"tfidf_score": score},
                )

        return None
