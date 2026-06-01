"""
Label Parser — moteur d'extraction structurée pour libellés bancaires.

Conçu pour compenser une faible couverture IBAN : on extrait le maximum
d'information *structurée* du libellé brut (références facture, numéros
de bordereau, dates, IBAN inline, montants, codes métier...) pour
permettre à C1/C2 de matcher *sans* dépendre de la jointure IBAN.

Approche : 100% déterministe, regex pur, zéro IA.

────────────────────────────────────────────────────────────────────
DSL de templates
────────────────────────────────────────────────────────────────────
Chaque template est une chaîne avec des placeholders typés :

    <NUM>   séquence numérique (1-15 chiffres)
    <REF>   référence alphanumérique mixte
    <IBAN>  IBAN (format international)
    <DATE>  date (multi-format FR/EN/ISO)
    <AMT>   montant (FR ou US format)
    <TEXT>  texte libre court

Le compilateur traduit le template en regex avec groupes nommés
*uniques* (même si le placeholder est répété), permettant d'extraire
toutes les occurrences en un seul `match()`.

Exemples de templates couverts :
    /MID <REF>/NBT <NUM>/SDT <NUM>/RBR <REF>
    BORDEREAU <NUM> <DATE>/INV/<NUM> <DATE>
    DISPO/REMISE <NUM>/SDT <NUM>/RBA <REF>
    CAT D <NUM>
    FACTURE <NUM>
    /INV/<NUM> <DATE>/INV/<NUM> <DATE>

────────────────────────────────────────────────────────────────────
Sortie : ``ParsedLabel``
────────────────────────────────────────────────────────────────────
Structure riche qui agrège tous les signaux extractibles :

    invoice_refs       : list[str]   candidats référence facture
    bordereau_refs     : list[str]   numéros de bordereau
    iban_refs          : list[str]   IBAN trouvés inline
    dates              : list[date]  dates parsées
    amounts            : list[float] montants parsés (hors montant paiement)
    sepa_fields        : dict        /ROC/, /RFB/, /INV/, /BNF/, /TRF/, ...
    factoring_codes    : dict        MID, NBT, SDT, RBR, RBA, CAT, ...
    document_types     : set[str]    {FACTURE, BORDEREAU, CHQ, LCR, TRAITE, ...}
    keywords           : set[str]    {URGENT, FOREIGN, ACOMPTE, AVOIR, ...}
    templates_matched  : list[str]   templates ayant matché
    confidence         : float       confiance composite
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime


# =============================================================================
# DSL : placeholders typés
# =============================================================================
#: regex pour chaque type de placeholder. Volontairement permissif :
#: la qualité est assurée par les templates qui les entourent de séparateurs
#: caractéristiques.
PLACEHOLDER_REGEX: dict[str, str] = {
    "NUM":   r"\d{1,15}",
    "REF":   r"[A-Z0-9][A-Z0-9\-/\.\*]{2,30}",
    "IBAN":  r"[A-Z]{2}\d{2}(?:[\s\-]*[A-Z0-9]){10,30}",
    "DATE":  r"(?:\d{2}[/\-.\s]\d{2}[/\-.\s]\d{2,4}|\d{4}[/\-.]\d{2}[/\-.]\d{2}|\d{8})",
    "AMT":   r"\d{1,3}(?:[ .,]\d{3})*(?:[.,]\d{2})?",
    "TEXT":  r"[A-Z0-9\s\-/\.]{2,40}",
}


def _escape_literal(text: str) -> str:
    """Échappe un segment littéral pour usage dans un regex.

    - Whitespace interne ou aux extrémités -> ``\\s+`` (au moins un espace).
    - Chaque caractère spécial regex est escapé proprement.
    """
    if not text:
        return ""
    # Tokenize en chunks alternant whitespace / non-whitespace
    out_parts: list[str] = []
    for chunk in re.findall(r"\s+|\S+", text):
        if chunk.isspace():
            out_parts.append(r"\s+")
        else:
            out_parts.append(re.escape(chunk))
    return "".join(out_parts)


def _compile_template(tpl: str) -> tuple[re.Pattern[str], list[tuple[str, str]]]:
    """Transforme un template DSL en regex compilée.

    Génère des noms de groupes uniques pour permettre la répétition
    de placeholders dans un même template (ex. ``/INV/<NUM> <DATE>/INV/<NUM> <DATE>``).
    Les séparateurs littéraux (``/``, ``-``, ...) sont préservés ; les
    whitespaces deviennent ``\\s+``.
    """
    parts = re.split(r"(<\w+>)", tpl)
    pieces: list[str] = []
    groups: list[tuple[str, str]] = []
    counter = 0
    for part in parts:
        if not part:
            continue
        m = re.fullmatch(r"<(\w+)>", part)
        if m:
            kind = m.group(1)
            if kind not in PLACEHOLDER_REGEX:
                pieces.append(_escape_literal(part))
                continue
            name = f"{kind.lower()}_{counter}"
            counter += 1
            pieces.append(f"(?P<{name}>{PLACEHOLDER_REGEX[kind]})")
            groups.append((name, kind))
        else:
            pieces.append(_escape_literal(part))
    return re.compile("".join(pieces), re.IGNORECASE), groups


# =============================================================================
# Bibliothèque de templates
# =============================================================================
# Format : (template, label_name, confidence)
# Ordre = priorité de matching. Les templates les plus spécifiques d'abord.
TEMPLATES: list[tuple[str, str, float]] = [
    # ── SEPA / ISO 20022 fields (très haute spécificité) ────────────────
    ("/MID <REF>/NBT <NUM>/SDT <NUM>/RBR <REF>", "sepa_mid_nbt_sdt_rbr",       0.98),
    ("/MID <NUM>/NBT <NUM>/SDT <NUM>/RBR <REF>", "sepa_mid_n_nbt_sdt_rbr",     0.98),
    ("MID <REF>/NBT <NUM>/SDT <NUM>/RBR <REF>",  "sepa_mid_nbt_sdt_rbr_ns",    0.97),
    ("MID <NUM>/NBT <NUM>/SDT <NUM>",            "sepa_mid_nbt_sdt",           0.95),
    ("/INV/<NUM> <DATE>/INV/<NUM> <DATE>",       "iso_multi_inv_dated",        0.99),
    ("/INV/<NUM> <DATE>",                        "iso_inv_num_dated",          0.97),
    ("/INV/<REF> <DATE>",                        "iso_inv_ref_dated",          0.97),
    ("/INV/<NUM>",                               "iso_inv_num",                0.93),
    ("/INV/<REF>",                               "iso_inv_ref",                0.93),
    ("/ROC/<REF>",                               "iso_roc",                    0.95),
    ("/RFB/<REF>",                               "iso_rfb",                    0.95),
    ("/RFB/<NUM>",                               "iso_rfb_num",                0.93),
    ("/BNF/<REF>",                               "iso_bnf",                    0.85),
    ("/TRF/<REF>",                               "iso_trf",                    0.85),
    ("/RUR/<REF>",                               "iso_rur",                    0.88),
    ("/CDS/<REF>",                               "iso_cds",                    0.85),

    # ── Factoring spécifique ────────────────────────────────────────────
    ("DISPO/REMISE <NUM>/SDT <NUM>/RBA <REF>",   "factoring_dispo_full",       0.98),
    ("DISPO/REMISE <NUM>/RBA <REF>",             "factoring_dispo_rba",        0.95),
    ("DISPO/REMISE <NUM>",                       "factoring_dispo_simple",     0.92),
    ("DISPO <NUM>",                              "factoring_dispo",            0.88),
    ("REMISE <NUM>",                             "factoring_remise",           0.88),
    ("BORDEREAU <NUM> <DATE>/INV/<NUM> <DATE>",  "factoring_bordereau_inv",    0.98),
    ("BORDEREAU <NUM> <DATE>",                   "factoring_bordereau_dated",  0.96),
    ("BORDEREAU <NUM>",                          "factoring_bordereau",        0.92),
    ("BDR <NUM>",                                "factoring_bdr",              0.88),
    ("BDX <NUM>",                                "factoring_bdx",              0.86),

    # ── Catégories internes ─────────────────────────────────────────────
    ("CAT D <IBAN>",                             "category_d_iban",            0.92),
    ("CAT D <NUM>",                              "category_d_num",             0.88),
    ("CAT <REF> <NUM>",                          "category_ref_num",           0.82),

    # ── Avances / advice ────────────────────────────────────────────────
    ("ADV/<NUM> <DATE>",                         "advice_dated",               0.90),
    ("ADV/<NUM>",                                "advice",                     0.85),
    ("ADVANCE <NUM>",                            "advance",                    0.85),
    ("ACOMPTE <NUM>",                            "acompte",                    0.85),

    # ── Asterisque ──────────────────────────────────────────────────────
    ("*<NUM> <NUM>",                             "star_num_num",               0.78),
    ("*<NUM>",                                   "star_num",                   0.72),

    # ── Documents commerciaux (multilingue) ────────────────────────────
    ("FACTURE N <NUM> <DATE>",                   "facture_n_num_dated",        0.96),
    ("FACTURE N <NUM>",                          "facture_n_num",              0.94),
    ("FACTURE <NUM> <DATE>",                     "facture_num_dated",          0.94),
    ("FACTURE <NUM>",                            "facture_num",                0.93),
    ("FACTURE <REF>",                            "facture_ref",                0.92),
    ("FACT <NUM>",                               "fact_num",                   0.90),
    ("FAC <NUM>",                                "fac_num",                    0.90),
    ("FAC <REF>",                                "fac_ref",                    0.88),
    ("FRA <NUM>",                                "fra_num",                    0.88),
    ("INVOICE <NUM>",                            "invoice_num",                0.93),
    ("INV <NUM>",                                "inv_num",                    0.90),
    ("BILL <NUM>",                               "bill_num",                   0.85),
    ("RECHNUNG <NUM>",                           "rechnung_num",               0.93),
    ("RG <NUM>",                                 "rg_num",                     0.85),
    ("BELEG <NUM>",                              "beleg_num",                  0.85),
    ("FATTURA <NUM>",                            "fattura_num",                0.93),
    ("FATT <NUM>",                               "fatt_num",                   0.88),
    ("FT <NUM>",                                 "ft_num",                     0.82),
    ("FACTURA <NUM>",                            "factura_num",                0.93),
    ("FACTUUR <NUM>",                            "factuur_num",                0.93),
    ("FAKTURA <NUM>",                            "faktura_num",                0.93),
    ("FV <NUM>",                                 "fv_num",                     0.85),
    ("FATURA <NUM>",                             "fatura_num",                 0.93),  # PT
    # Variantes "collées" sans séparateur (cas très fréquent : FAC2024001)
    ("FACTURE<NUM>",                             "facture_glued",              0.92),
    ("FAC<NUM>",                                 "fac_glued",                  0.92),
    ("FACT<NUM>",                                "fact_glued",                 0.92),
    ("FRA<NUM>",                                 "fra_glued",                  0.88),
    ("INV<NUM>",                                 "inv_glued",                  0.92),
    ("RG<NUM>",                                  "rg_glued",                   0.85),
    ("FT<NUM>",                                  "ft_glued",                   0.82),
    ("FV<NUM>",                                  "fv_glued",                   0.85),

    # ── Documents annexes (bons, contrats) ──────────────────────────────
    ("BL <NUM>",                                 "bl_num",                     0.85),
    ("BON DE LIVRAISON <NUM>",                   "bdl_full",                   0.90),
    ("CMR <NUM>",                                "cmr_num",                    0.85),
    ("DAE <NUM>",                                "dae_num",                    0.85),
    ("PO <NUM>",                                 "po_num",                     0.85),
    ("BC <NUM>",                                 "bc_num",                     0.85),
    ("BDC <NUM>",                                "bdc_num",                    0.85),
    ("CMD <NUM>",                                "cmd_num",                    0.85),
    ("COMMANDE <NUM>",                           "commande_num",               0.88),
    ("ORDER <NUM>",                              "order_num",                  0.85),
    ("AUFTRAG <NUM>",                            "auftrag_num",                0.85),
    ("CONTRAT <NUM>",                            "contrat_num",                0.82),
    ("CONTRACT <NUM>",                           "contract_num",               0.82),

    # ── Instruments de paiement ────────────────────────────────────────
    ("URG GN<NUM> N CHQ TRAITE",                 "urg_chq_traite",             0.85),
    ("CHEQUE N <NUM>",                           "cheque_n",                   0.85),
    ("CHQ <NUM>",                                "cheque",                     0.82),
    ("TRAITE <NUM>",                             "traite",                     0.82),
    ("LCR <NUM>",                                "lcr",                        0.82),
    ("BOR <NUM>",                                "bor",                        0.75),

    # ── Indicateurs (très peu spécifiques) ─────────────────────────────
    ("FOREIGN TRANSFER",                         "foreign_transfer_kw",        0.30),
    ("INTERNATIONAL TRANSFER",                   "intl_transfer_kw",           0.30),
    ("URGENT",                                   "urgent_kw",                  0.25),

    # ── Fallbacks structurés ───────────────────────────────────────────
    ("<REF> <NUM> <NUM>",                        "ref_num_num",                0.55),
    ("<NUM> <NUM> <NUM>",                        "three_nums",                 0.45),
    ("<NUM> <NUM>",                              "two_nums",                   0.40),

    # ── Fallbacks atomiques ────────────────────────────────────────────
    ("<IBAN>",                                   "iban_only",                  0.75),
    ("<REF>",                                    "ref_only",                   0.55),
    ("<NUM>",                                    "num_only",                   0.40),
]


#: Compilation à l'import — fait une fois pour toutes.
def _build_compiled() -> list[tuple[re.Pattern[str], list[tuple[str, str]], str, float]]:
    out = []
    for t, name, conf in TEMPLATES:
        pat, groups = _compile_template(t)
        out.append((pat, groups, name, conf))
    return out


_COMPILED = _build_compiled()


# =============================================================================
# Codes métier reconnus (dictionnaire à des fins d'extraction ciblée)
# =============================================================================
#: Codes factoring / SEPA / banque. Les noms canoniques utilisés dans
#: ``ParsedLabel.factoring_codes`` et ``sepa_fields``.
CODE_DEFINITIONS: dict[str, str] = {
    # SEPA / ISO 20022
    "ROC":      "Référence Créancier (Creditor Reference)",
    "RFB":      "Référence pour Bénéficiaire (Reference For Beneficiary)",
    "INV":      "Numéro de facture",
    "BNF":      "Identifiant Bénéficiaire",
    "TRF":      "Référence de transfert",
    "RUR":      "Référence unique remise (Reference Unique Remise)",
    "CDS":      "Identifiant créancier (Creditor Scheme)",
    "RUM":      "Référence Unique Mandat (SEPA prélèvement)",
    "E2E":      "End-To-End ID",
    # Factoring spécifique (codes vus en prod)
    "MID":      "Message/Mandate ID",
    "NBT":      "Numéro de Bordereau Transmis (factoring)",
    "SDT":      "Statement Date / Solde Daté",
    "RBR":      "Référence Bordereau Restant",
    "RBA":      "Référence Bordereau Avoir / d'Anomalie",
    "BDR":      "Bordereau (forme abrégée)",
    "BDX":      "Bordereau (variante)",
    "CAT":      "Catégorie (segmentation interne)",
    "ADV":      "Advance / Advice (avis)",
    # Documents commerciaux
    "FAC":      "Facture",
    "FRA":      "Facture (variante)",
    "FACT":     "Facture (variante longue)",
    "INV":      "Invoice (EN)",
    "BILL":     "Bill (EN)",
    "RECHN":    "Rechnung (DE)",
    "RG":       "Rechnung (DE, abrégé)",
    "FATT":     "Fattura (IT)",
    "FT":       "Fattura (IT, abrégé)",
    "FACTURA":  "Factura (ES)",
    "FACTUUR":  "Factuur (NL)",
    "FAKTURA":  "Faktura (PL)",
    "FV":       "Faktura (PL, abrégé)",
    "FATURA":   "Fatura (PT)",
    "BL":       "Bon de livraison",
    "BDL":      "Bon de livraison (forme alternative)",
    "CMR":      "Lettre de voiture internationale",
    "DAE":      "Document Accompagnement Export",
    "PO":       "Purchase Order",
    "BC":       "Bon de commande",
    "BDC":      "Bon de commande (forme alternative)",
    "CMD":      "Commande",
    # Instruments
    "CHQ":      "Chèque",
    "CHEQUE":   "Chèque",
    "LCR":      "Lettre de Change Relevé",
    "TRAITE":   "Traite",
    "BOR":      "Bordereau (instrument)",
}


# =============================================================================
# Mots-clés métier (sets pour détection rapide)
# =============================================================================
KEYWORDS_FACTORING = {
    "BORDEREAU", "BDR", "BDX", "DISPO", "REMISE", "DISPO/REMISE",
    "ACOMPTE", "AVOIR", "AVANCE", "REGUL", "REGULARISATION",
    "COMPENSATION", "COMPENSE", "ENCAISSEMENT", "ESCOMPTE",
    "RETENUE", "RETENUE GARANTIE", "RFA", "COMMISSION", "FRAIS",
}
KEYWORDS_PAYMENT_TYPE = {
    "VIR", "VIREMENT", "VRT", "REGLT", "REGLEMENT", "REGL",
    "PAIEMENT", "PAYMENT", "TRANSFER", "TRANSFERT",
    "CHQ", "CHEQUE", "LCR", "TRAITE", "BOR",
    "SEPA", "SWIFT", "SCT", "DIRECT DEBIT",
}
KEYWORDS_URGENCY = {
    "URGENT", "URG", "EXPRESS", "PRIORITY", "PRIO",
}
KEYWORDS_INTERNATIONAL = {
    "FOREIGN", "INTERNATIONAL", "CROSS BORDER", "INTL",
}
KEYWORDS_CREDIT_NOTE = {
    "AVOIR", "AVO", "NOTE DE CREDIT", "CREDIT NOTE",
    "RIMBORSO", "RECHTSCHRIFT", "GUTSCHRIFT", "ABONO",
}
KEYWORDS_PARTIAL = {
    "ACOMPTE", "PARTIEL", "PARTIAL", "ADVANCE",
    "A VALOIR", "A COMPTE", "PARZIALE", "TEILZAHLUNG",
}
KEYWORDS_FINAL = {
    "SOLDE", "FINAL", "DERNIER", "CLOTURE", "BALANCE",
    "SALDO", "RESTBETRAG", "SALDO FINAL",
}

#: Mots qu'on ne veut JAMAIS voir dans ``invoice_refs`` même si capturés
#: par un fallback ``<REF>``. Ce sont des mots métier de transport, pas
#: des références facture.
REF_STOPWORDS: set[str] = {
    # Types de paiement (FR)
    "VIR", "VIREMENT", "VRT", "REGLT", "REGLEMENT", "REGL", "RGLT", "RGT",
    "PAIEMENT", "PAIE", "PMT",
    # Types de paiement (EN)
    "PAYMENT", "TRANSFER", "TRANSFERT", "WIRE", "PAY",
    # Réseaux
    "SEPA", "SWIFT", "SCT", "SDD", "SEPACT", "ACH",
    # Pays / langues / monnaies
    "FR", "EN", "EUR", "USD", "GBP", "CHF",
    # Mots-clés sans info de référence
    "FOREIGN", "INTERNATIONAL", "INTL", "URGENT", "URG", "EXPRESS",
    "DOMESTIC", "STANDARD", "CREDIT", "DEBIT", "DR", "CR",
    "FROM", "TO", "VIA", "CPTE", "COMPTE",
    # Documents génériques sans numéro (peuvent apparaître seuls)
    "FACTURE", "FACT", "INVOICE", "BILL", "BORDEREAU",
    "RECHNUNG", "FATTURA", "FACTURA", "FACTUUR", "FAKTURA",
}


# =============================================================================
# Patterns de date (multilingue)
# =============================================================================
DATE_PATTERNS_TPL = [
    (re.compile(r"\b(\d{2})[/\-.](\d{2})[/\-.](\d{4})\b"), "%d/%m/%Y"),
    (re.compile(r"\b(\d{2})[/\-.](\d{2})[/\-.](\d{2})\b"), "%d/%m/%y"),
    (re.compile(r"\b(\d{4})[/\-.](\d{2})[/\-.](\d{2})\b"), "%Y-%m-%d"),
    (re.compile(r"\b(\d{8})\b"), "%Y%m%d"),
]


# =============================================================================
# Pattern IBAN inline
# =============================================================================
_IBAN_INLINE = re.compile(
    r"\b([A-Z]{2}\d{2}(?:[\s\-]*[A-Z0-9]){10,30})\b",
    re.IGNORECASE,
)


# =============================================================================
# Pattern montant inline (FR ou US)
# =============================================================================
_AMOUNT_INLINE = re.compile(
    r"(\d{1,3}(?:[.\s]\d{3})*,\d{2}|\d{1,3}(?:,\s?\d{3})*\.\d{2}|\d+[.,]\d{2})"
)


# =============================================================================
# Sortie structurée
# =============================================================================
@dataclass
class ParsedLabel:
    """Résultat de l'analyse d'un libellé bancaire.

    Toutes les listes sont triées par ordre d'apparition dans le libellé,
    et déduplicées dans la mesure du possible.
    """
    raw: str
    normalized: str

    # ── Sorties primaires (consommées par C1/C2/C3) ─────────────────────
    invoice_refs: list[str] = field(default_factory=list)
    bordereau_refs: list[str] = field(default_factory=list)
    iban_refs: list[str] = field(default_factory=list)
    dates: list[date] = field(default_factory=list)
    amounts: list[float] = field(default_factory=list)

    # ── Sorties secondaires (contexte / scoring) ────────────────────────
    sepa_fields: dict[str, str] = field(default_factory=dict)
    factoring_codes: dict[str, str] = field(default_factory=dict)
    document_types: set[str] = field(default_factory=set)
    keywords: set[str] = field(default_factory=set)

    # ── Méta (debug / observabilité) ────────────────────────────────────
    templates_matched: list[str] = field(default_factory=list)
    confidence: float = 0.0

    def all_refs(self) -> list[str]:
        """Toutes les références extraites, dédupliquées."""
        seen: set[str] = set()
        out: list[str] = []
        for r in self.invoice_refs + self.bordereau_refs:
            c = _canonical(r)
            if c and c not in seen:
                seen.add(c)
                out.append(c)
        return out


# =============================================================================
# Parser
# =============================================================================
_NORM_NOISE = re.compile(r"\s+")


def _normalize(label: str) -> str:
    """Uppercase + compacte les whitespaces. Pas plus, pour ne pas perdre
    les séparateurs significatifs comme `/`."""
    return _NORM_NOISE.sub(" ", label.upper()).strip()


def _canonical(ref: str) -> str:
    """Forme canonique d'une référence : uppercase, sans séparateurs."""
    return re.sub(r"[^A-Z0-9]", "", ref.upper())


def _parse_date(raw: str) -> date | None:
    for pat, fmt in DATE_PATTERNS_TPL:
        m = pat.search(raw)
        if m:
            try:
                return datetime.strptime(m.group(0), fmt).date()
            except ValueError:
                continue
    return None


def _parse_amount(raw: str) -> float | None:
    s = raw.strip().replace(" ", "")
    if "," in s and s.count(",") == 1 and (s.count(".") == 0 or s.rfind(",") > s.rfind(".")):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


#: Seuil au-dessus duquel un template est considéré comme "spécifique" :
#: il bloque l'application des fallbacks génériques sur sa zone.
SPECIFIC_THRESHOLD = 0.65


def _overlaps(span: tuple[int, int], covered: list[tuple[int, int]]) -> bool:
    """Vrai si ``span`` chevauche au moins un span de ``covered``."""
    s, e = span
    for cs, ce in covered:
        if s < ce and e > cs:
            return True
    return False


def parse(label: str) -> ParsedLabel:
    """Parse un libellé bancaire et renvoie une ``ParsedLabel`` riche.

    Stratégie en 2 phases :
    1. Phase spécifique : on essaie tous les templates avec confiance
       >= ``SPECIFIC_THRESHOLD``. Chaque zone matchée est marquée.
    2. Phase fallback : on essaie les templates génériques (<NUM>,
       <REF>, <NUM> <NUM>...) UNIQUEMENT sur les zones non couvertes.
    3. Phase atomique : on extrait IBAN inline, dates, montants,
       mots-clés à part. Toujours fait.
    """
    if not label:
        return ParsedLabel(raw="", normalized="")

    norm = _normalize(label)
    out = ParsedLabel(raw=label, normalized=norm)
    confidences: list[float] = []
    covered: list[tuple[int, int]] = []  # spans déjà matchés par des templates spécifiques

    # ── Phase 1 : templates spécifiques (>= seuil) ──────────────────────
    for pattern, groups, tname, conf in _COMPILED:
        if conf < SPECIFIC_THRESHOLD:
            continue
        for m in pattern.finditer(norm):
            out.templates_matched.append(tname)
            confidences.append(conf)
            covered.append(m.span())
            _route_match(out, tname, groups, m)

    # ── Phase 2 : fallbacks génériques (< seuil) ───────────────────────
    for pattern, groups, tname, conf in _COMPILED:
        if conf >= SPECIFIC_THRESHOLD:
            continue
        for m in pattern.finditer(norm):
            if _overlaps(m.span(), covered):
                continue
            out.templates_matched.append(tname)
            confidences.append(conf)
            covered.append(m.span())
            _route_match(out, tname, groups, m)

    # ── Extraction atomique (toujours fait) ─────────────────────────────
    # IBAN inline (au cas où aucun template <IBAN> n'a tiré)
    for m in _IBAN_INLINE.finditer(norm):
        iban = _canonical(m.group(1))
        if iban and iban not in out.iban_refs:
            out.iban_refs.append(iban)

    # Dates (peuvent venir d'un template OU directement)
    for pat, fmt in DATE_PATTERNS_TPL:
        for m in pat.finditer(norm):
            try:
                d = datetime.strptime(m.group(0), fmt).date()
                if d not in out.dates:
                    out.dates.append(d)
            except ValueError:
                continue

    # Montants
    for m in _AMOUNT_INLINE.finditer(norm):
        amt = _parse_amount(m.group(1))
        if amt is not None and amt > 0 and amt not in out.amounts:
            out.amounts.append(amt)

    # Mots-clés métier (sets de présence)
    for kw_set, tag in (
        (KEYWORDS_FACTORING, "factoring"),
        (KEYWORDS_PAYMENT_TYPE, "payment_type"),
        (KEYWORDS_URGENCY, "urgency"),
        (KEYWORDS_INTERNATIONAL, "international"),
        (KEYWORDS_CREDIT_NOTE, "credit_note"),
        (KEYWORDS_PARTIAL, "partial"),
        (KEYWORDS_FINAL, "final"),
    ):
        for kw in kw_set:
            if re.search(rf"\b{re.escape(kw)}\b", norm):
                out.keywords.add(kw)

    # Documents reconnus
    for keyword in ("FACTURE", "FACT", "FAC", "FRA", "INVOICE", "INV", "BILL",
                    "RECHNUNG", "RG", "FATTURA", "FT", "FACTURA", "FACTUUR",
                    "FAKTURA", "FV", "FATURA",
                    "BORDEREAU", "BDR", "BDX",
                    "BL", "CMR", "DAE", "PO", "BC", "BDC", "CMD", "COMMANDE",
                    "CHQ", "CHEQUE", "LCR", "TRAITE", "BOR"):
        if re.search(rf"\b{re.escape(keyword)}\b", norm):
            out.document_types.add(keyword)

    # ── Confiance composite ─────────────────────────────────────────────
    if confidences:
        # max boosté légèrement par la diversité des matches
        out.confidence = min(0.99,
                             max(confidences) + 0.01 * (len(confidences) - 1))
    elif out.iban_refs or out.dates or out.amounts:
        out.confidence = 0.40
    else:
        out.confidence = 0.0

    # ── Déduplication finale des refs ──────────────────────────────────
    out.invoice_refs = _dedupe_preserve(out.invoice_refs)
    out.bordereau_refs = _dedupe_preserve(out.bordereau_refs)
    out.iban_refs = _dedupe_preserve(out.iban_refs)

    return out


#: Mappings explicites par template : pour chaque template, on déclare
#: dans quel champ de ``ParsedLabel`` va chaque groupe (par position).
#: Format : tname -> list[(group_index, target_field, ...)]
#:   target_field ∈ {
#:       "invoice", "bordereau", "iban",
#:       "factoring:CODE", "sepa:FIELD", "instrument",
#:   }
ROUTING_RULES: dict[str, list[tuple[int, str]]] = {
    # ── SEPA factoring : /MID/NBT/SDT/RBR ────────────────────────────
    "sepa_mid_nbt_sdt_rbr":      [(0, "factoring:MID"),
                                  (1, "factoring:NBT"), (1, "bordereau"),
                                  (2, "factoring:SDT"),
                                  (3, "factoring:RBR")],
    "sepa_mid_n_nbt_sdt_rbr":    [(0, "factoring:MID"),
                                  (1, "factoring:NBT"), (1, "bordereau"),
                                  (2, "factoring:SDT"),
                                  (3, "factoring:RBR")],
    "sepa_mid_nbt_sdt_rbr_ns":   [(0, "factoring:MID"),
                                  (1, "factoring:NBT"), (1, "bordereau"),
                                  (2, "factoring:SDT"),
                                  (3, "factoring:RBR")],
    "sepa_mid_nbt_sdt":          [(0, "factoring:MID"),
                                  (1, "factoring:NBT"), (1, "bordereau"),
                                  (2, "factoring:SDT")],
    # ── ISO 20022 /INV/ ──────────────────────────────────────────────
    "iso_multi_inv_dated":       [(0, "sepa:INV"), (0, "invoice"),
                                  (2, "sepa:INV"), (2, "invoice")],
    "iso_inv_num_dated":         [(0, "sepa:INV"), (0, "invoice")],
    "iso_inv_ref_dated":         [(0, "sepa:INV"), (0, "invoice")],
    "iso_inv_num":               [(0, "sepa:INV"), (0, "invoice")],
    "iso_inv_ref":               [(0, "sepa:INV"), (0, "invoice")],
    "iso_roc":                   [(0, "sepa:ROC"), (0, "invoice")],
    "iso_rfb":                   [(0, "sepa:RFB"), (0, "invoice")],
    "iso_rfb_num":               [(0, "sepa:RFB"), (0, "invoice")],
    "iso_bnf":                   [(0, "sepa:BNF")],
    "iso_trf":                   [(0, "sepa:TRF"), (0, "invoice")],
    "iso_rur":                   [(0, "sepa:RUR"), (0, "bordereau")],
    "iso_cds":                   [(0, "sepa:CDS")],
    # ── Factoring spécifique ─────────────────────────────────────────
    "factoring_dispo_full":      [(0, "factoring:DISPO_REMISE"), (0, "bordereau"),
                                  (1, "factoring:SDT"),
                                  (2, "factoring:RBA")],
    "factoring_dispo_rba":       [(0, "factoring:DISPO_REMISE"), (0, "bordereau"),
                                  (1, "factoring:RBA")],
    "factoring_dispo_simple":    [(0, "factoring:DISPO_REMISE"), (0, "bordereau")],
    "factoring_dispo":           [(0, "factoring:DISPO_REMISE"), (0, "bordereau")],
    "factoring_remise":          [(0, "factoring:DISPO_REMISE"), (0, "bordereau")],
    "factoring_bordereau_inv":   [(0, "factoring:BORDEREAU"), (0, "bordereau"),
                                  (2, "sepa:INV"), (2, "invoice")],
    "factoring_bordereau_dated": [(0, "factoring:BORDEREAU"), (0, "bordereau")],
    "factoring_bordereau":       [(0, "factoring:BORDEREAU"), (0, "bordereau")],
    "factoring_bdr":             [(0, "factoring:BORDEREAU"), (0, "bordereau")],
    "factoring_bdx":             [(0, "factoring:BORDEREAU"), (0, "bordereau")],
    # ── Catégories ───────────────────────────────────────────────────
    "category_d_iban":           [(0, "iban"), (0, "factoring:CAT_D")],
    "category_d_num":            [(0, "factoring:CAT_D"), (0, "invoice")],
    "category_ref_num":          [(0, "factoring:CAT"), (1, "invoice")],
    # ── Advances ─────────────────────────────────────────────────────
    "advice_dated":              [(0, "factoring:ADV"), (0, "invoice")],
    "advice":                    [(0, "factoring:ADV"), (0, "invoice")],
    "advance":                   [(0, "factoring:ADV"), (0, "invoice")],
    "acompte":                   [(0, "factoring:ADV"), (0, "invoice")],
    # ── Asterisque ───────────────────────────────────────────────────
    "star_num_num":              [(0, "invoice"), (1, "invoice")],
    "star_num":                  [(0, "invoice")],
    # ── Documents commerciaux ────────────────────────────────────────
    "facture_n_num_dated":       [(0, "invoice")],
    "facture_n_num":             [(0, "invoice")],
    "facture_num_dated":         [(0, "invoice")],
    "facture_num":               [(0, "invoice")],
    "facture_ref":               [(0, "invoice")],
    "fact_num":                  [(0, "invoice")],
    "fac_num":                   [(0, "invoice")],
    "fac_ref":                   [(0, "invoice")],
    "fra_num":                   [(0, "invoice")],
    "invoice_num":               [(0, "invoice")],
    "inv_num":                   [(0, "invoice")],
    "bill_num":                  [(0, "invoice")],
    "rechnung_num":              [(0, "invoice")],
    "rg_num":                    [(0, "invoice")],
    "beleg_num":                 [(0, "invoice")],
    "fattura_num":               [(0, "invoice")],
    "fatt_num":                  [(0, "invoice")],
    "ft_num":                    [(0, "invoice")],
    "factura_num":               [(0, "invoice")],
    "factuur_num":               [(0, "invoice")],
    "faktura_num":               [(0, "invoice")],
    "fv_num":                    [(0, "invoice")],
    "fatura_num":                [(0, "invoice")],
    # Variantes "collées"
    "facture_glued":             [(0, "invoice")],
    "fac_glued":                 [(0, "invoice")],
    "fact_glued":                [(0, "invoice")],
    "fra_glued":                 [(0, "invoice")],
    "inv_glued":                 [(0, "invoice")],
    "rg_glued":                  [(0, "invoice")],
    "ft_glued":                  [(0, "invoice")],
    "fv_glued":                  [(0, "invoice")],
    # Documents annexes
    "bl_num":                    [(0, "invoice")],
    "bdl_full":                  [(0, "invoice")],
    "cmr_num":                   [(0, "invoice")],
    "dae_num":                   [(0, "invoice")],
    "po_num":                    [(0, "invoice")],
    "bc_num":                    [(0, "invoice")],
    "bdc_num":                   [(0, "invoice")],
    "cmd_num":                   [(0, "invoice")],
    "commande_num":              [(0, "invoice")],
    "order_num":                 [(0, "invoice")],
    "auftrag_num":               [(0, "invoice")],
    "contrat_num":                [(0, "invoice")],
    "contract_num":              [(0, "invoice")],
    # Instruments
    "urg_chq_traite":            [(0, "factoring:INSTRUMENT"), (0, "invoice")],
    "cheque_n":                  [(0, "factoring:INSTRUMENT"), (0, "invoice")],
    "cheque":                    [(0, "factoring:INSTRUMENT"), (0, "invoice")],
    "traite":                    [(0, "factoring:INSTRUMENT"), (0, "invoice")],
    "lcr":                       [(0, "factoring:INSTRUMENT"), (0, "invoice")],
    "bor":                       [(0, "factoring:INSTRUMENT"), (0, "invoice")],
    # Indicateurs purs (pas de capture)
    "foreign_transfer_kw":       [],
    "intl_transfer_kw":          [],
    "urgent_kw":                 [],
    # Fallbacks
    "ref_num_num":               [(0, "invoice"), (1, "invoice"), (2, "invoice")],
    "three_nums":                [(0, "invoice"), (1, "invoice"), (2, "invoice")],
    "two_nums":                  [(0, "invoice"), (1, "invoice")],
    "iban_only":                 [(0, "iban")],
    "ref_only":                  [(0, "invoice")],
    "num_only":                  [(0, "invoice")],
}


def _route_match(out: ParsedLabel, template_name: str,
                 groups: list[tuple[str, str]], m: re.Match[str]) -> None:
    """Route les captures d'un match selon les règles déclarées dans
    ``ROUTING_RULES``. Plus précis et plus auditable que l'ancien
    routing positionnel implicite.
    """
    rules = ROUTING_RULES.get(template_name)
    if rules is None:
        # Pas de règle déclarée -> fallback : tout dans invoice_refs
        for gname, kind in groups:
            val = m.group(gname)
            if not val:
                continue
            _apply(out, "invoice", val.strip())
        return

    for group_idx, target in rules:
        if group_idx >= len(groups):
            continue
        gname, kind = groups[group_idx]
        val = m.group(gname)
        if not val:
            continue
        _apply(out, target, val.strip())


def _apply(out: ParsedLabel, target: str, value: str) -> None:
    """Applique une valeur à un champ de la ParsedLabel."""
    if target == "invoice":
        out.invoice_refs.append(value)
    elif target == "bordereau":
        out.bordereau_refs.append(value)
    elif target == "iban":
        c = _canonical(value)
        if c and c not in out.iban_refs:
            out.iban_refs.append(c)
    elif target.startswith("factoring:"):
        code = target.split(":", 1)[1]
        out.factoring_codes.setdefault(code, value)
    elif target.startswith("sepa:"):
        code = target.split(":", 1)[1]
        out.sepa_fields[code] = value


def _dedupe_preserve(seq: list[str]) -> list[str]:
    """Déduplique en préservant l'ordre, sur la forme canonique."""
    seen: set[str] = set()
    out: list[str] = []
    for s in seq:
        c = _canonical(s)
        if c and c not in seen and c.upper() not in REF_STOPWORDS:
            seen.add(c)
            out.append(s)
    return out
