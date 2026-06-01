"""
Reference extractor — extraction multilingue et robuste de références
factures depuis un libellé bancaire brut.

Stratégie :
- patterns scorés par niveau de confiance (HIGH > MEDIUM > LOW) ;
- couverture multilingue : FR / EN / DE / IT / ES / NL / PL ;
- support des champs ISO 20022 inline (``/ROC/``, ``/RFB/``, ``/INV/``,
  ``RF`` Creditor Reference ISO 11649) ;
- support des amorces contextuelles (« REF: », « N° », « VOTRE FACTURE… »);
- déduplication intelligente (une référence ne compte qu'une fois, on
  garde la version la plus longue + plus haute confiance) ;
- génération de variantes (avec/sans séparateurs/padding) pour matcher
  les références en base.

Pourquoi un module séparé : permet de tester chaque pattern isolément,
d'ajouter / désactiver / scorer une stratégie sans toucher au pipeline,
et de fournir des hooks pour de l'analyse offline (mining de patterns
récurrents non couverts).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


# ============================================================================
# Niveaux de confiance
# ============================================================================
HIGH = 0.95     # mot-clé métier explicite + numéro structuré
MEDIUM = 0.78   # amorce contextuelle (REF, N°, NUM) + numéro
LOW = 0.55      # séquence numérique pure (pas de keyword)
ISO = 0.92      # champs ISO 20022


@dataclass(frozen=True)
class RefMatch:
    """Une référence extraite + métadonnées."""
    raw: str            # texte tel qu'extrait du libellé
    canonical: str      # forme normalisée (uppercase, sans séparateurs)
    confidence: float
    source: str         # nom du pattern responsable
    span: tuple[int, int] = (0, 0)


# ============================================================================
# Patterns ISO 20022 — confiance maximale
# ============================================================================
# /ROC/ Creditor Reference, /RFB/ Reference For Beneficiary,
# /INV/ Invoice number, /BNF/ Beneficiary, /TRF/ Transfer reference.
_ISO_FIELDS = re.compile(
    r"/(ROC|RFB|INV|BNF|TRF|RUR|REF|NUM)/\s*([A-Z0-9][A-Z0-9\-/\s.]{2,40})",
    re.IGNORECASE,
)
# ISO 11649 Creditor Reference : RF + 2 chiffres + 1-21 caractères alphanumériques.
_ISO_11649 = re.compile(r"\bRF\d{2}\s?[A-Z0-9]{1,21}\b", re.IGNORECASE)
# EndToEndId (souvent visible en clair) : suite alphanumérique de 8-35 chars
# précédée du mot-clé E2E ou END-TO-END
_E2E = re.compile(
    r"\b(?:E2E|END[\-\s]?TO[\-\s]?END)[\s:]*([A-Z0-9][A-Z0-9\-/]{6,34})\b",
    re.IGNORECASE,
)


# ============================================================================
# Mots-clés métier multilingues (HIGH confidence)
# ============================================================================
#: Famille « facture ». Couvre toutes les abréviations vues en pratique.
INVOICE_KEYWORDS = (
    # Français
    r"FAC(?:T(?:URE)?)?", r"FRA", r"F\.",  r"FR\b",
    # Anglais
    r"INV(?:OICE)?", r"BILL",
    # Allemand
    r"RECHN(?:UNG)?", r"RG", r"BEL(?:EG)?",
    # Italien
    r"FATT(?:URA)?", r"FT\b",
    # Espagnol / Portugais
    r"FACTURA", r"FACT", r"FATURA",
    # Néerlandais
    r"FACTUUR",
    # Polonais
    r"FAKTURA", r"FV\b",
    # Forme compacte
    r"FC\b",
)

INVOICE_KW_RE = "|".join(INVOICE_KEYWORDS)

#: Numéro structuré qui suit un mot-clé : permet jusqu'à 4 segments
#: séparés par tiret / slash / point / espace.
#: Ex : "2024-001-A", "2024/001234", "FAC.2024.001"
_NUM_BLOCK = r"\d{2,10}(?:[.\-/\s]\d{1,10}){0,3}[A-Z]?"

# Pattern haute confiance : mot-clé facture + séparateur optionnel + numéro
HIGH_CONFIDENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        rf"\b(?:{INVOICE_KW_RE})\s*[\.\-/:#°N]*\s*({_NUM_BLOCK})\b",
        re.IGNORECASE,
    ), "invoice_keyword"),
    # BL, BC, CMD, PO : bons de livraison / commande
    (re.compile(
        r"\b(?:BL|BON\s+DE\s+LIVRAISON|CMR|DAE|LIEFERSCHEIN)\s*[\.\-/:#]*\s*"
        r"(" + _NUM_BLOCK + r")\b",
        re.IGNORECASE,
    ), "delivery_doc"),
    (re.compile(
        r"\b(?:PO|BC|BDC|CMD|COMMANDE|ORDER|ORDEN|AUFTRAG|BESTELLUNG)\s*"
        r"[\.\-/:#N°]*\s*(" + _NUM_BLOCK + r")\b",
        re.IGNORECASE,
    ), "purchase_order"),
    # Référence client / contrat : « CONTRAT XYZ-123 »
    (re.compile(
        r"\b(?:CONTRAT|CONTRACT|VERTRAG|CONTRATTO)\s*[\.\-/:#N°]*\s*"
        r"([A-Z0-9][A-Z0-9\-/]{2,20})\b",
        re.IGNORECASE,
    ), "contract"),
]


# ============================================================================
# Amorces contextuelles génériques (MEDIUM confidence)
# ============================================================================
#: « REF: 12345 », « N° 12345 », « Nº 12345 », « NUM 12345 », « OUR REF »
_CONTEXT_PREFIXES = (
    r"REF(?:ERENCE)?", r"N[°ºo]", r"NUM(?:ERO)?",
    r"NR(?:\.|\b)", r"NUMMER", r"NUMERO",
    r"OUR\s*REF", r"VOTRE\s*REF", r"YOUR\s*REF",
    r"DOC(?:UMENT)?", r"ID\s+CL",
)
_CONTEXT_RE = "|".join(_CONTEXT_PREFIXES)

MEDIUM_CONFIDENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(
        rf"\b(?:{_CONTEXT_RE})\s*[:\-#.]*\s*([A-Z0-9][A-Z0-9\-/.]{{4,25}})\b",
        re.IGNORECASE,
    ), "context_prefix"),
    # Référence "vos références" / "votre numero" multilingue
    (re.compile(
        r"\b(?:VOTRE|VOS|YOUR|IHRE?|SUA)\s+(?:FACTURE|INVOICE|RECHNUNG|FATTURA|FACTURA)"
        r"\s+(?:N[°ºo]\s*)?([A-Z0-9][A-Z0-9\-/.]{3,20})\b",
        re.IGNORECASE,
    ), "your_invoice"),
]


# ============================================================================
# Patterns numériques nus (LOW confidence)
# ============================================================================
LOW_CONFIDENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Année + tiret / slash + numéro : 2024-001234, 2024/01234
    (re.compile(r"\b((?:19|20)\d{2}[\-/.\s]\d{3,10})\b"), "year_dash_num"),
    # Année courte + tiret + numéro : 24-001234 (préfixé par non-digit)
    (re.compile(r"(?<![\d-])\b(\d{2}[\-/.]\d{3,10})\b"), "yy_dash_num"),
    # Séquence pure : 6-12 chiffres pas collés à un IBAN
    (re.compile(r"(?<![A-Za-z])(?<!\d)(\d{6,12})(?!\d)"), "pure_numeric"),
    # Code alpha-numérique de type code interne : 3-5 lettres + tiret + chiffres
    (re.compile(r"\b([A-Z]{2,5}[\-/]\d{4,10})\b"), "alpha_dash_num"),
]


# ============================================================================
# API publique
# ============================================================================
def extract_all(label: str) -> list[RefMatch]:
    """Renvoie toutes les références extraites avec leur score de confiance,
    dans l'ordre décroissant de confiance (puis longueur).
    """
    if not label:
        return []

    matches: list[RefMatch] = []

    # ── ISO 20022 ─────────────────────────────────────────────────────────
    for m in _ISO_FIELDS.finditer(label):
        ref = m.group(2).strip()
        matches.append(RefMatch(
            raw=m.group(0), canonical=_canonicalise(ref),
            confidence=ISO, source=f"iso_{m.group(1).lower()}",
            span=m.span(),
        ))
    for m in _ISO_11649.finditer(label):
        ref = m.group(0)
        matches.append(RefMatch(
            raw=ref, canonical=_canonicalise(ref),
            confidence=ISO, source="iso_11649", span=m.span(),
        ))
    for m in _E2E.finditer(label):
        ref = m.group(1)
        matches.append(RefMatch(
            raw=m.group(0), canonical=_canonicalise(ref),
            confidence=ISO, source="iso_e2e", span=m.span(),
        ))

    # ── HIGH confidence ───────────────────────────────────────────────────
    for pat, name in HIGH_CONFIDENCE_PATTERNS:
        for m in pat.finditer(label):
            ref = m.group(1)
            matches.append(RefMatch(
                raw=m.group(0), canonical=_canonicalise(ref),
                confidence=HIGH, source=name, span=m.span(),
            ))

    # ── MEDIUM confidence ─────────────────────────────────────────────────
    for pat, name in MEDIUM_CONFIDENCE_PATTERNS:
        for m in pat.finditer(label):
            ref = m.group(1)
            matches.append(RefMatch(
                raw=m.group(0), canonical=_canonicalise(ref),
                confidence=MEDIUM, source=name, span=m.span(),
            ))

    # ── LOW confidence ────────────────────────────────────────────────────
    for pat, name in LOW_CONFIDENCE_PATTERNS:
        for m in pat.finditer(label):
            ref = m.group(1)
            matches.append(RefMatch(
                raw=m.group(0), canonical=_canonicalise(ref),
                confidence=LOW, source=name, span=m.span(),
            ))

    return _dedupe(matches)


def extract_canonical_refs(label: str, min_confidence: float = LOW) -> list[str]:
    """Renvoie juste les références canoniques uniques, triées par
    confiance décroissante. Compatible avec ``Payment.signals.raw_refs``.
    """
    matches = extract_all(label)
    seen: set[str] = set()
    out: list[str] = []
    for m in matches:
        if m.confidence < min_confidence:
            continue
        if m.canonical in seen:
            continue
        seen.add(m.canonical)
        out.append(m.canonical)
    return out


def generate_variants(canonical: str) -> list[str]:
    """À partir d'une référence canonique (« FAC2024001 »), génère
    les variantes susceptibles d'exister en base : avec tirets,
    sans le préfixe alphabétique, padding zéros, etc.

    Utile pour le matching en aval (ex. ``InvoiceHashIndex`` côté C1).
    """
    if not canonical:
        return []
    variants = {canonical}

    # Séparer la partie alpha de la partie numérique
    m = re.match(r"^([A-Z]+)(\d.*)$", canonical)
    if m:
        alpha, num = m.groups()
        variants.add(num)                          # sans préfixe
        variants.add(f"{alpha}-{num}")
        variants.add(f"{alpha}/{num}")
        variants.add(f"{alpha} {num}")
        # padding zéros côté gauche (3 longueurs typiques)
        for L in (6, 8, 10):
            if len(num) < L:
                variants.add(num.zfill(L))
                variants.add(f"{alpha}{num.zfill(L)}")

    # Splitter aussi sur les digits consécutifs (année + numéro)
    m2 = re.match(r"^([A-Z]*)(\d{4})(\d+)$", canonical)
    if m2:
        alpha, year, num = m2.groups()
        for sep in ("-", "/", "."):
            variants.add(f"{alpha}{year}{sep}{num}")
            variants.add(f"{year}{sep}{num}")
    return sorted(variants, key=len, reverse=True)


# ============================================================================
# Helpers internes
# ============================================================================
_NORM_RE = re.compile(r"[^A-Z0-9]")


def _canonicalise(ref: str) -> str:
    """Canonicalise une référence : uppercase + strip de tout séparateur."""
    return _NORM_RE.sub("", ref.upper())


def _dedupe(matches: Iterable[RefMatch]) -> list[RefMatch]:
    """Pour chaque référence canonique, garde la meilleure occurrence
    (plus haute confiance, puis plus long ``raw``).
    """
    best: dict[str, RefMatch] = {}
    for m in matches:
        if not m.canonical or len(m.canonical) < 4:
            continue
        key = m.canonical
        if key not in best or (
            m.confidence > best[key].confidence
            or (m.confidence == best[key].confidence and len(m.raw) > len(best[key].raw))
        ):
            best[key] = m
    return sorted(best.values(),
                  key=lambda x: (-x.confidence, -len(x.canonical)))
