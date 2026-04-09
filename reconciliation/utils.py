"""
Shared utility functions used across all reconciliation layers.

Centralizes hot-path operations to avoid redundant regex compilation
and inconsistent normalization between layers.
"""
from __future__ import annotations

import re
from functools import lru_cache

# Pre-compiled regex for reference normalization (hot path)
_NON_ALNUM = re.compile(r"[^A-Z0-9]")
_MULTI_SPACE = re.compile(r"\s{2,}")
_LEADING_ZEROS = re.compile(r"^0+")


@lru_cache(maxsize=8192)
def normalize_ref(ref: str | None) -> str:
    """Normalize an invoice/PO/BL reference for matching.

    Strips all non-alphanumeric characters, uppercases, and caches
    results for hot-path efficiency. ``None`` returns empty string.

    >>> normalize_ref("FAC-2024-001")
    'FAC2024001'
    >>> normalize_ref("fac/2024/001")
    'FAC2024001'
    """
    if not ref:
        return ""
    return _NON_ALNUM.sub("", ref.upper())


def strip_leading_zeros(text: str) -> str:
    """Remove leading zeros from a numeric string (keeps at least one digit)."""
    if not text:
        return ""
    result = _LEADING_ZEROS.sub("", text)
    return result or "0"


def collapse_spaces(text: str) -> str:
    """Collapse multiple whitespaces into a single space."""
    if not text:
        return ""
    return _MULTI_SPACE.sub(" ", text).strip()


def safe_float(value, default: float = 0.0) -> float:
    """Convert value to float, returning default on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_div(num: float, denom: float, default: float = 0.0) -> float:
    """Division with zero-guard."""
    return num / denom if denom else default
