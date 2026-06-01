"""
Diagnostic post-batch : pourquoi un paiement n'a-t-il pas matché ?

Pour chaque paiement non-résolu, classifie la **cause** de l'échec en
remontant la trace :
- 1. Pas d'IBAN_EMETT sur le paiement.
- 2. IBAN présent mais inconnu dans la map débiteurs.
- 3. IBAN connu mais le débiteur n'a aucune facture ouverte.
- 4. Aucune référence extraite du libellé (C0 vide).
- 5. Refs extraites mais aucune ne match l'index hash de C1.
- 6. Hash match trouvé mais montant trop éloigné (C1 + tolérances C2).
- 7. Match candidat mais sous le seuil de confiance.

Sortie : un rapport texte exhaustif à imprimer ou écrire dans un log.
"""
from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from .models import Invoice, Payment, ReconciliationContext

logger = logging.getLogger(__name__)


# ─── Catégories de raisons d'échec ───────────────────────────────────────
R_NO_IBAN_NO_REFS = "1_no_iban_no_refs"
R_NO_IBAN_HAS_REFS = "2_no_iban_but_refs_extracted"
R_IBAN_UNKNOWN_NO_REFS = "3_iban_unknown_no_refs"
R_IBAN_UNKNOWN_HAS_REFS = "4_iban_unknown_but_refs_extracted"
R_DEBTOR_NO_OPEN_INVOICES = "5_debtor_known_but_no_open_invoices"
R_REFS_DONT_HASH_MATCH = "6_refs_extracted_but_no_invoice_hash_match"
R_AMOUNT_MISMATCH = "7_candidate_found_but_amount_mismatch"
R_CONFIDENCE_LOW = "8_match_below_confidence_threshold"
R_OTHER = "9_other"

REASON_LABELS = {
    R_NO_IBAN_NO_REFS:          "Aucun IBAN_EMETT ET aucune référence dans le libellé",
    R_NO_IBAN_HAS_REFS:         "Pas d'IBAN_EMETT, mais des refs extraites du libellé (pas matchées en BDD)",
    R_IBAN_UNKNOWN_NO_REFS:     "IBAN_EMETT renseigné mais inconnu, ET aucune réf dans le libellé",
    R_IBAN_UNKNOWN_HAS_REFS:    "IBAN_EMETT renseigné mais inconnu — match repose donc sur les refs (non matchées)",
    R_DEBTOR_NO_OPEN_INVOICES:  "Débiteur identifié mais sans facture ouverte sur la fenêtre",
    R_REFS_DONT_HASH_MATCH:     "Refs extraites du libellé mais aucune ne match une facture en BDD (formats divergents ?)",
    R_AMOUNT_MISMATCH:          "Facture candidate trouvée mais écart de montant trop important",
    R_CONFIDENCE_LOW:           "Match calculé mais sous le seuil de confiance",
    R_OTHER:                    "Cause non identifiée — voir processing_log du paiement",
}


@dataclass
class PaymentDiagnostic:
    payment_id: str
    amount: float
    label_raw: str
    iban_source: str
    iban_known: bool
    debtor_id: str | None
    refs_extracted: list[str] = field(default_factory=list)
    bordereau_refs: list[str] = field(default_factory=list)
    dates_extracted: list[str] = field(default_factory=list)
    factoring_codes: dict[str, str] = field(default_factory=dict)
    layers_attempted: list[int] = field(default_factory=list)
    candidate_matches_count: int = 0
    reason: str = R_OTHER


@dataclass
class DiagnosticReport:
    total_payments: int
    matched_auto: int
    unmatched: int
    reasons_breakdown: Counter
    sample_per_reason: dict[str, list[PaymentDiagnostic]]

    # Stats hash index / refs
    avg_refs_per_payment: float
    payments_with_zero_refs: int
    payments_with_iban_known: int
    payments_with_iban_unknown: int
    payments_with_no_iban: int

    # Hash index coverage
    invoice_refs_in_hash: int
    sample_invoice_refs_in_hash: list[str]


def classify(
    ctx: ReconciliationContext,
    payment: Payment,
    iban_map: dict[str, str],
    debtor_to_invoices: dict[str, list[Invoice]],
) -> str:
    """Classifie la raison d'échec d'un paiement non-matché."""
    has_iban = bool(payment.iban_source)
    iban_known = has_iban and payment.iban_source in iban_map
    refs = ctx.payment.signals.raw_refs if ctx.payment.signals else []
    has_refs = bool(refs)

    if not has_iban:
        return R_NO_IBAN_HAS_REFS if has_refs else R_NO_IBAN_NO_REFS

    if not iban_known:
        return R_IBAN_UNKNOWN_HAS_REFS if has_refs else R_IBAN_UNKNOWN_NO_REFS

    # IBAN known
    debtor_id = iban_map.get(payment.iban_source)
    if debtor_id and not debtor_to_invoices.get(debtor_id):
        return R_DEBTOR_NO_OPEN_INVOICES

    if ctx.candidate_matches:
        # Des candidats ont été produits mais aucun n'a passé le seuil
        return R_CONFIDENCE_LOW

    if has_refs:
        return R_REFS_DONT_HASH_MATCH

    return R_OTHER


def build_report(
    payments: list[Payment],
    contexts: list[ReconciliationContext],
    invoices: list[Invoice],
    iban_map: dict[str, str],
) -> DiagnosticReport:
    debtor_to_invoices = defaultdict(list)
    for inv in invoices:
        if inv.debtor_id:
            debtor_to_invoices[inv.debtor_id].append(inv)

    reasons = Counter()
    sample_per_reason: dict[str, list[PaymentDiagnostic]] = defaultdict(list)
    total = len(contexts)
    matched = 0
    refs_counts: list[int] = []
    n_no_iban = 0
    n_iban_known = 0
    n_iban_unknown = 0

    for ctx in contexts:
        p = ctx.payment
        # Refs counter (toujours, matché ou non)
        n_refs = len(p.signals.raw_refs) if p.signals else 0
        refs_counts.append(n_refs)
        if not p.iban_source:
            n_no_iban += 1
        elif p.iban_source in iban_map:
            n_iban_known += 1
        else:
            n_iban_unknown += 1

        if ctx.final_match is not None:
            matched += 1
            continue

        reason = classify(ctx, p, iban_map, debtor_to_invoices)
        reasons[reason] += 1

        # Échantillon pour chaque cause (max 5 par cause)
        if len(sample_per_reason[reason]) < 5:
            parsed = (p.signals.parsed_label if p.signals else None)
            sample_per_reason[reason].append(PaymentDiagnostic(
                payment_id=p.id,
                amount=p.amount,
                label_raw=p.label_raw[:140],
                iban_source=p.iban_source or "",
                iban_known=(p.iban_source in iban_map) if p.iban_source else False,
                debtor_id=p.debtor_id,
                refs_extracted=list(p.signals.raw_refs[:8]) if p.signals else [],
                bordereau_refs=list(parsed.bordereau_refs[:5]) if parsed else [],
                dates_extracted=[d.isoformat() for d in (parsed.dates[:3] if parsed else [])],
                factoring_codes=dict(parsed.factoring_codes) if parsed else {},
                layers_attempted=list(ctx.layers_attempted),
                candidate_matches_count=len(ctx.candidate_matches),
                reason=reason,
            ))

    # Hash index stats : combien d'invoice refs disponibles à matcher ?
    invoice_refs = [inv.reference for inv in invoices if inv.reference]

    return DiagnosticReport(
        total_payments=total,
        matched_auto=matched,
        unmatched=total - matched,
        reasons_breakdown=reasons,
        sample_per_reason=dict(sample_per_reason),
        avg_refs_per_payment=(sum(refs_counts) / total) if total else 0.0,
        payments_with_zero_refs=sum(1 for n in refs_counts if n == 0),
        payments_with_iban_known=n_iban_known,
        payments_with_iban_unknown=n_iban_unknown,
        payments_with_no_iban=n_no_iban,
        invoice_refs_in_hash=len(invoice_refs),
        sample_invoice_refs_in_hash=invoice_refs[:10],
    )


def format_report(report: DiagnosticReport) -> str:
    """Formate le rapport en texte lisible. À imprimer ou logger."""
    out: list[str] = []
    p = out.append

    p("=" * 78)
    p(" RAPPORT DIAGNOSTIC POST-BATCH")
    p("=" * 78)
    p("")
    p(f"  Paiements traités       : {report.total_payments:>8,}")
    p(f"  Matched (auto)          : {report.matched_auto:>8,}  "
      f"({report.matched_auto * 100 / max(report.total_payments,1):.1f}%)")
    p(f"  Unmatched               : {report.unmatched:>8,}  "
      f"({report.unmatched * 100 / max(report.total_payments,1):.1f}%)")
    p("")
    p("─" * 78)
    p(" Qualité signal C0 (référence extraction)")
    p("─" * 78)
    p(f"  Refs moyennes / paiement    : {report.avg_refs_per_payment:>7.2f}")
    p(f"  Paiements avec 0 ref        : {report.payments_with_zero_refs:>7,} "
      f"({report.payments_with_zero_refs*100/max(report.total_payments,1):.1f}%)")
    p(f"  Factures dispo hash index   : {report.invoice_refs_in_hash:>7,}")
    p(f"  Exemple refs factures BDD   : {report.sample_invoice_refs_in_hash[:5]}")
    p("")
    p("─" * 78)
    p(" Couverture IBAN")
    p("─" * 78)
    p(f"  Paiements IBAN connu        : {report.payments_with_iban_known:>7,} "
      f"({report.payments_with_iban_known*100/max(report.total_payments,1):.1f}%)")
    p(f"  Paiements IBAN inconnu      : {report.payments_with_iban_unknown:>7,} "
      f"({report.payments_with_iban_unknown*100/max(report.total_payments,1):.1f}%)")
    p(f"  Paiements sans IBAN_EMETT   : {report.payments_with_no_iban:>7,} "
      f"({report.payments_with_no_iban*100/max(report.total_payments,1):.1f}%)")
    p("")
    p("─" * 78)
    p(" Causes d'échec (paiements non-matchés)")
    p("─" * 78)
    for reason, count in report.reasons_breakdown.most_common():
        pct = count * 100 / max(report.unmatched, 1)
        label = REASON_LABELS.get(reason, reason)
        p(f"  [{count:>6,}  {pct:>5.1f}%] {label}")
    p("")
    p("─" * 78)
    p(" Échantillons par cause (5 paiements / cause)")
    p("─" * 78)
    for reason in sorted(report.sample_per_reason):
        samples = report.sample_per_reason[reason]
        if not samples:
            continue
        p("")
        p(f"▼ {reason} — {REASON_LABELS.get(reason, '')}")
        for s in samples:
            p(f"  ┌─ {s.payment_id}  amount={s.amount:,.2f}  iban={s.iban_source or 'EMPTY'!r}")
            p(f"  │  label    : {s.label_raw!r}")
            p(f"  │  refs C0  : {s.refs_extracted}")
            if s.bordereau_refs:
                p(f"  │  bordereau: {s.bordereau_refs}")
            if s.factoring_codes:
                p(f"  │  factoring: {s.factoring_codes}")
            if s.dates_extracted:
                p(f"  │  dates   : {s.dates_extracted}")
            p(f"  │  layers  : {s.layers_attempted}  candidates={s.candidate_matches_count}")
            p(f"  └────")
    p("")
    p("=" * 78)
    return "\n".join(out)


def run_diagnostic(
    payments: list[Payment],
    contexts: list[ReconciliationContext],
    invoices: list[Invoice],
    iban_map: dict[str, str],
) -> str:
    """Construit + formate le rapport en une seule étape."""
    report = build_report(payments, contexts, invoices, iban_map)
    return format_report(report)
