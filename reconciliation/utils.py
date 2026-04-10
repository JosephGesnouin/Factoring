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


# =====================================================================
# Typo / mutation engine for realistic fuzzy-match simulation
# =====================================================================

def introduce_typo(ref: str, rng, severity: str = "light") -> str:
    """Introduce realistic typos/mutations in a reference.

    Shared across all simulation scripts for consistent behavior.

    Args:
        ref: The original reference string (e.g. "FAC-2024-01200345").
        rng: A ``random.Random`` instance for reproducibility.
        severity:
            ``"light"``  — 1 mutation (swap, digit, 0→O).
            ``"medium"`` — 2 mutations (prefix swap, truncate, sep change...).
            ``"heavy"``  — 3-5 mutations, severely mangled.

    Returns:
        The mutated reference string.
    """
    c = list(ref)
    if len(c) < 5:
        return ref

    _MUTATIONS = {
        "swap":            lambda: _mut_swap(c, rng),
        "drop":            lambda: _mut_drop(c, rng),
        "0_to_O":          lambda: _mut_0O(c),
        "1_to_l":          lambda: _mut_1l(c),
        "wrong_digit":     lambda: _mut_digit(c, rng),
        "double_char":     lambda: _mut_double(c, rng),
        "extra_space":     lambda: _mut_space(c, rng),
        "wrong_sep":       lambda: _mut_sep(c, rng),
        "truncate_end":    lambda: _mut_truncate_end(c, rng),
        "truncate_start":  lambda: _mut_truncate_start(c, rng),
        "prefix_swap":     lambda: _mut_prefix_swap(c, rng),
        "strip_prefix":    lambda: _mut_strip_prefix(c),
        "strip_zeros":     lambda: _mut_strip_zeros(c),
        "add_zeros":       lambda: _mut_add_zeros(c, rng),
        "case_change":     lambda: _mut_case(c, rng),
        "reverse_segment": lambda: _mut_reverse(c, rng),
    }

    if severity == "light":
        n_mut = 1
        pool = ["swap", "drop", "0_to_O", "1_to_l", "wrong_digit", "double_char"]
    elif severity == "medium":
        n_mut = 2
        pool = list(_MUTATIONS.keys())
    else:
        n_mut = rng.randint(3, 5)
        pool = list(_MUTATIONS.keys())

    used: set[str] = set()
    for _ in range(n_mut):
        available = [m for m in pool if m not in used]
        if not available:
            break
        op = rng.choice(available)
        used.add(op)
        _MUTATIONS[op]()

    return "".join(c)


# ── Individual mutation operators ──

def _mut_swap(c, rng):
    if len(c) > 5:
        i = rng.randint(2, len(c) - 2)
        c[i], c[i + 1] = c[i + 1], c[i]

def _mut_drop(c, rng):
    if len(c) > 4:
        c.pop(rng.randint(2, len(c) - 1))

def _mut_0O(c):
    for i, ch in enumerate(c):
        if ch == "0":
            c[i] = "O"
            break

def _mut_1l(c):
    for i, ch in enumerate(c):
        if ch == "1":
            c[i] = "l"
            break

def _mut_digit(c, rng):
    ds = [i for i, ch in enumerate(c) if ch.isdigit()]
    if ds:
        i = rng.choice(ds)
        c[i] = str((int(c[i]) + rng.randint(1, 3)) % 10)

def _mut_double(c, rng):
    if len(c) > 4:
        i = rng.randint(2, len(c) - 1)
        c.insert(i, c[i])

def _mut_space(c, rng):
    i = rng.randint(3, len(c) - 2)
    c.insert(i, " ")

def _mut_sep(c, rng):
    seps = {"-": "/", "/": "-", ".": "-"}
    for i, ch in enumerate(c):
        if ch in seps:
            c[i] = seps[ch]
            break

def _mut_truncate_end(c, rng):
    n = rng.randint(1, min(3, len(c) - 4))
    del c[-n:]

def _mut_truncate_start(c, rng):
    n = rng.randint(1, min(3, len(c) - 4))
    del c[:n]

def _mut_prefix_swap(c, rng):
    prefixes = ["FAC", "FACT", "INV", "F", "FC", "FT"]
    alpha_end = 0
    for i, ch in enumerate(c):
        if ch.isdigit() or ch in "-/":
            break
        alpha_end = i + 1
    if alpha_end > 0:
        c[:alpha_end] = list(rng.choice(prefixes))

def _mut_strip_prefix(c):
    first_digit = next((i for i, ch in enumerate(c) if ch.isdigit()), None)
    if first_digit and first_digit > 0:
        del c[:first_digit]

def _mut_strip_zeros(c):
    first_digit = next((i for i, ch in enumerate(c) if ch.isdigit()), None)
    if first_digit is not None:
        while first_digit < len(c) - 1 and c[first_digit] == "0":
            c.pop(first_digit)

def _mut_add_zeros(c, rng):
    first_digit = next((i for i, ch in enumerate(c) if ch.isdigit()), None)
    if first_digit is not None:
        for _ in range(rng.randint(1, 3)):
            c.insert(first_digit, "0")

def _mut_case(c, rng):
    for _ in range(rng.randint(1, 3)):
        i = rng.randint(0, len(c) - 1)
        c[i] = c[i].lower() if c[i].isupper() else c[i].upper()

def _mut_reverse(c, rng):
    if len(c) > 6:
        i = rng.randint(2, len(c) - 4)
        n = rng.randint(2, 3)
        c[i:i + n] = c[i:i + n][::-1]
