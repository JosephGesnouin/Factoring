#!/usr/bin/env python3
"""
=============================================================================
SIMULATION MASSIVE — Réconciliation Paiement-Facture
=============================================================================
12 débiteurs | ~400 factures | ~500 paiements | 6 mois (Juillet-Décembre 2024)

Couvre TOUTES les couches C0→C6 avec des scénarios réalistes :
  - Paiements exacts avec référence (C1)
  - ISO 20022 / SEPA structuré (C1)
  - IBAN + montant unique (C1)
  - PO / BL matching (C1)
  - Solde total débiteur (C1)
  - Frais SWIFT internationaux (C2)
  - Escompte contractuel (C2)
  - Retenue de garantie BTP (C2)
  - RFA fin d'année (C2)
  - Avoirs / notes de crédit (C2)
  - Subset sum multi-factures (C2)
  - Acomptes / versements partiels (C2)
  - Patterns temporels (C2)
  - Retenue à la source (C2)
  - Fuzzy matching avec typos (C3)
  - Labels cryptiques → revue humaine (C6)

Usage :
    python -m examples.demo_large_simulation
    python examples/demo_large_simulation.py
=============================================================================
"""

from __future__ import annotations

import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

# ── Path setup ──────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.models import (
    CreditNote, Currency, Debtor, Invoice, ISO20022Fields,
    LabelClass, MatchMethod, Payment, PaymentSignals,
)
from reconciliation.config import ReconciliationConfig
from reconciliation.orchestrator import ReconciliationOrchestrator

# ============================================================
# CONSTANTES
# ============================================================

MONTHS = [7, 8, 9, 10, 11, 12]  # Juillet → Décembre 2024
YEAR = 2024

# Volume saisonnier : août creux, Q4 en hausse
SEASONAL_FACTORS = {7: 0.8, 8: 0.5, 9: 0.9, 10: 1.0, 11: 1.2, 12: 1.4}

# Plages de montant par secteur (EUR)
AMOUNT_RANGES = {
    "ALIMENTAIRE":  (1_000, 15_000),
    "BTP":          (10_000, 80_000),
    "IMPORT":       (5_000, 40_000),
    "DISTRIBUTION": (10_000, 120_000),
    "TRANSPORT":    (3_000, 25_000),
    "PHARMA":       (5_000, 50_000),
    "AUTO":         (2_000, 30_000),
    "IT_SERVICES":  (5_000, 60_000),
    "TEXTILE":      (3_000, 20_000),
    "ENERGIE":      (15_000, 100_000),
}

# Taux de TVA par pays
TVA_RATES = {
    "FR": 0.20, "DE": 0.19, "IT": 0.22, "ES": 0.21,
    "SE": 0.25, "PL": 0.23, "GB": 0.20, "MA": 0.20,
    "TN": 0.19,
}


# ============================================================
# 1. PROFILS DÉBITEURS (12 profils réalistes)
# ============================================================

@dataclass
class DebtorProfile:
    debtor: Debtor
    invoices_per_month: int
    amount_range: tuple[float, float]
    scenario_weights: dict[str, float]
    payment_day: int | None = None       # jour fixe de paiement (None=variable)
    avg_delay_days: float = 5.0          # retard moyen vs échéance
    has_po: bool = False
    has_bl: bool = False
    label_style: str = "reference"       # reference, iso20022, cryptic, period, mixed


def create_debtor_profiles() -> list[DebtorProfile]:
    """Crée 12 profils de débiteurs avec comportements variés."""
    profiles = []

    # ── D01 Boulangerie Dupont (FR) ─ Payeur modèle, toujours la ref ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D01", name="Boulangerie Dupont SARL", iban="FR7630001007941234567890185",
            bic="BNPAFRPP", country="FR", group_id=None, sector="ALIMENTAIRE",
            payment_terms=30, discount_rate=0.0, retention_rate=0.0, rfa_rate=0.0,
            avg_payment_delay=2.0, payment_regularity_score=0.95, risk_score=0.1,
            known_payment_patterns=["always_ref", "single_invoice"],
            usual_invoice_counts_per_payment=1,
        ),
        invoices_per_month=8, amount_range=AMOUNT_RANGES["ALIMENTAIRE"],
        payment_day=15,  # paie toujours le 15
        avg_delay_days=2.0, label_style="reference",
        scenario_weights={
            "C1_EXACT_REF": 0.80, "C1_IBAN_AMOUNT": 0.10,
            "C2_ROUNDING": 0.05, "C6_CRYPTIC": 0.05,
        },
    ))

    # ── D02 Construction Martin (FR/BTP) ─ Retenue de garantie 5% ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D02", name="Construction Martin SA", iban="FR7610011000201234567890188",
            bic="PSSTFRPP", country="FR", sector="BTP",
            payment_terms=60, retention_rate=0.05,
            avg_payment_delay=15.0, payment_regularity_score=0.65, risk_score=0.4,
            known_payment_patterns=["retention_5pct", "late_payer"],
            usual_invoice_counts_per_payment=1,
        ),
        invoices_per_month=6, amount_range=AMOUNT_RANGES["BTP"],
        has_po=True, avg_delay_days=15.0, label_style="mixed",
        scenario_weights={
            "C1_EXACT_REF": 0.10, "C2_RETENTION": 0.50, "C2_SUBSET_SUM": 0.15,
            "C2_ROUNDING": 0.05, "C2_INSTALLMENT": 0.10, "C6_CRYPTIC": 0.10,
        },
    ))

    # ── D03 Schmidt Import GmbH (DE) ─ ISO 20022, parfois erreur HT ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D03", name="Schmidt Import GmbH", iban="DE89370400440532013000",
            bic="COBADEFF", country="DE", sector="IMPORT",
            payment_terms=30,
            avg_payment_delay=3.0, payment_regularity_score=0.85, risk_score=0.2,
            known_payment_patterns=["iso20022", "occasional_ht_error"],
            usual_invoice_counts_per_payment=1,
        ),
        invoices_per_month=9, amount_range=AMOUNT_RANGES["IMPORT"],
        avg_delay_days=3.0, label_style="iso20022",
        scenario_weights={
            "C1_ISO20022": 0.55, "C1_EXACT_REF": 0.15, "C2_HT_ERROR": 0.10,
            "C2_ROUNDING": 0.05, "C3_FUZZY": 0.05, "C6_CRYPTIC": 0.10,
        },
    ))

    # ── D04 Groupe Leclerc Distribution (FR) ─ Escompte+RFA+Avoirs ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D04", name="Groupe Leclerc Distribution", iban="FR7620041010050500013M02606",
            bic="CEPAFRPP", country="FR", sector="DISTRIBUTION",
            payment_terms=45, discount_rate=0.02, rfa_rate=0.03,
            avg_payment_delay=5.0, payment_regularity_score=0.80, risk_score=0.15,
            known_payment_patterns=["discount_2pct", "rfa_3pct", "credit_deduction", "bulk"],
            usual_invoice_counts_per_payment=3,
        ),
        invoices_per_month=12, amount_range=AMOUNT_RANGES["DISTRIBUTION"],
        payment_day=28,  # paie en fin de mois
        avg_delay_days=5.0, label_style="reference",
        scenario_weights={
            "C1_EXACT_REF": 0.15, "C2_DISCOUNT": 0.25, "C2_RFA": 0.10,
            "C2_CREDIT_NOTE": 0.15, "C2_SUBSET_SUM": 0.15,
            "C1_FULL_BALANCE": 0.05, "C2_ROUNDING": 0.05, "C6_CRYPTIC": 0.10,
        },
    ))

    # ── D05 Transport Rossi Srl (IT) ─ Refs BL, solde total ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D05", name="Transport Rossi Srl", iban="IT60X0542811101000000123456",
            bic="BPMOIT22", country="IT", sector="TRANSPORT",
            payment_terms=30,
            avg_payment_delay=7.0, payment_regularity_score=0.75, risk_score=0.3,
            known_payment_patterns=["bl_reference", "full_balance"],
            usual_invoice_counts_per_payment=2,
        ),
        invoices_per_month=6, amount_range=AMOUNT_RANGES["TRANSPORT"],
        has_bl=True, avg_delay_days=7.0, label_style="reference",
        scenario_weights={
            "C1_BL_MATCH": 0.40, "C1_EXACT_REF": 0.15, "C1_FULL_BALANCE": 0.15,
            "C2_ROUNDING": 0.10, "C3_FUZZY": 0.10, "C6_CRYPTIC": 0.10,
        },
    ))

    # ── D06 Maroc Export SARL (MA) ─ SWIFT fees + retenue source 20% ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D06", name="Maroc Export SARL", iban="MA64011519000001205000534921",
            bic="BMCEMAMC", country="MA", sector="EXPORT",
            payment_terms=30,
            avg_payment_delay=10.0, payment_regularity_score=0.60, risk_score=0.5,
            known_payment_patterns=["swift_fees", "withholding_tax_20pct"],
            usual_invoice_counts_per_payment=1,
        ),
        invoices_per_month=5, amount_range=AMOUNT_RANGES["IMPORT"],
        avg_delay_days=10.0, label_style="mixed",
        scenario_weights={
            "C2_SWIFT_FEES": 0.35, "C2_WHT": 0.25, "C1_EXACT_REF": 0.15,
            "C2_ROUNDING": 0.05, "C6_CRYPTIC": 0.20,
        },
    ))

    # ── D07 Pharma Nordic AB (SE) ─ Subset sum, labels cryptiques ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D07", name="Pharma Nordic AB", iban="SE4550000000058398257466",
            bic="ESSESESS", country="SE", sector="PHARMA",
            payment_terms=45,
            avg_payment_delay=8.0, payment_regularity_score=0.70, risk_score=0.35,
            known_payment_patterns=["multi_invoice", "cryptic_labels"],
            usual_invoice_counts_per_payment=4,
        ),
        invoices_per_month=8, amount_range=AMOUNT_RANGES["PHARMA"],
        avg_delay_days=8.0, label_style="cryptic",
        scenario_weights={
            "C2_SUBSET_SUM": 0.45, "C1_EXACT_REF": 0.10, "C1_IBAN_AMOUNT": 0.10,
            "C3_FUZZY": 0.10, "C6_CRYPTIC": 0.25,
        },
    ))

    # ── D08 AutoParts Polska (PL) ─ Refs PO systématiques ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D08", name="AutoParts Polska Sp. z o.o.", iban="PL61109010140000071219812874",
            bic="WBKPPLPP", country="PL", sector="AUTO",
            payment_terms=30,
            avg_payment_delay=4.0, payment_regularity_score=0.85, risk_score=0.2,
            known_payment_patterns=["po_reference"],
            usual_invoice_counts_per_payment=1,
        ),
        invoices_per_month=7, amount_range=AMOUNT_RANGES["AUTO"],
        has_po=True, avg_delay_days=4.0, label_style="reference",
        scenario_weights={
            "C1_PO_MATCH": 0.60, "C1_EXACT_REF": 0.15, "C2_ROUNDING": 0.10,
            "C3_FUZZY": 0.05, "C6_CRYPTIC": 0.10,
        },
    ))

    # ── D09 Tech Solutions Ltd (GB) ─ Acomptes 30%/70% ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D09", name="Tech Solutions Ltd", iban="GB29NWBK60161331926819",
            bic="NWBKGB2L", country="GB", sector="IT_SERVICES",
            payment_terms=30,
            avg_payment_delay=5.0, payment_regularity_score=0.80, risk_score=0.25,
            known_payment_patterns=["installments_30_70"],
            usual_invoice_counts_per_payment=1,
        ),
        invoices_per_month=6, amount_range=AMOUNT_RANGES["IT_SERVICES"],
        avg_delay_days=5.0, label_style="reference",
        scenario_weights={
            "C2_INSTALLMENT": 0.45, "C1_EXACT_REF": 0.25,
            "C2_ROUNDING": 0.10, "C3_FUZZY": 0.05, "C6_CRYPTIC": 0.15,
        },
    ))

    # ── D10 Tunisie Textiles SA (TN) ─ WHT 15%, labels vides ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D10", name="Tunisie Textiles SA", iban="TN5910006035183598478831",
            bic="BTEETNTT", country="TN", sector="TEXTILE",
            payment_terms=45,
            avg_payment_delay=12.0, payment_regularity_score=0.55, risk_score=0.6,
            known_payment_patterns=["withholding_tax_15pct", "empty_labels"],
            usual_invoice_counts_per_payment=1,
        ),
        invoices_per_month=5, amount_range=AMOUNT_RANGES["TEXTILE"],
        avg_delay_days=12.0, label_style="cryptic",
        scenario_weights={
            "C2_WHT": 0.30, "C2_SWIFT_FEES": 0.20, "C1_EXACT_REF": 0.10,
            "C6_CRYPTIC": 0.40,
        },
    ))

    # ── D11 Iberia Foods SL (ES) ─ Typos systématiques ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D11", name="Iberia Foods SL", iban="ES9121000418450200051332",
            bic="CABOREBB", country="ES", sector="ALIMENTAIRE",
            payment_terms=30,
            avg_payment_delay=6.0, payment_regularity_score=0.70, risk_score=0.3,
            known_payment_patterns=["typos_in_ref", "inconsistent_labels"],
            usual_invoice_counts_per_payment=1,
        ),
        invoices_per_month=7, amount_range=AMOUNT_RANGES["ALIMENTAIRE"],
        avg_delay_days=6.0, label_style="reference",
        scenario_weights={
            "C3_FUZZY": 0.45, "C1_EXACT_REF": 0.20, "C2_ROUNDING": 0.10,
            "C2_SUBSET_SUM": 0.10, "C6_CRYPTIC": 0.15,
        },
    ))

    # ── D12 Groupe Énergie SA (FR) ─ Paiements par période ──
    profiles.append(DebtorProfile(
        debtor=Debtor(
            id="D12", name="Groupe Energie SA", iban="FR7630004000031234567890143",
            bic="BNPAFRPP", country="FR", group_id="GRP-ENERGIE", sector="ENERGIE",
            payment_terms=60,
            avg_payment_delay=5.0, payment_regularity_score=0.85, risk_score=0.15,
            known_payment_patterns=["period_label", "batch_payment"],
            usual_invoice_counts_per_payment=5,
        ),
        invoices_per_month=9, amount_range=AMOUNT_RANGES["ENERGIE"],
        payment_day=25,  # paie le 25
        avg_delay_days=5.0, label_style="period",
        scenario_weights={
            "C2_TEMPORAL": 0.35, "C1_EXACT_REF": 0.15, "C2_SUBSET_SUM": 0.15,
            "C1_FULL_BALANCE": 0.10, "C2_ROUNDING": 0.10, "C6_CRYPTIC": 0.15,
        },
    ))

    return profiles


# ============================================================
# 2. GÉNÉRATION DES FACTURES (~400 sur 6 mois)
# ============================================================

def generate_invoices(profiles: list[DebtorProfile], rng: random.Random) -> list[Invoice]:
    """Génère toutes les factures sur 6 mois avec volume saisonnier."""
    invoices: list[Invoice] = []
    seq = 0

    for month in MONTHS:
        factor = SEASONAL_FACTORS[month]
        days_in_month = (date(YEAR, month + 1, 1) - timedelta(days=1)).day if month < 12 else 31

        for profile in profiles:
            count = max(1, round(profile.invoices_per_month * factor))
            country = profile.debtor.country or "FR"
            tva = TVA_RATES.get(country, 0.20)
            lo, hi = profile.amount_range

            for _ in range(count):
                seq += 1
                did = profile.debtor.id
                did_num = int(did[1:])

                # Montant TTC avec centimes réalistes
                amount_ht = round(rng.uniform(lo, hi), 2)
                amount_ttc = round(amount_ht * (1 + tva), 2)

                # Date d'émission : jours courants du mois
                day = rng.choice([1, 2, 3, 5, 8, 10, 12, 15, 18, 20, 22, 25])
                day = min(day, days_in_month)
                issue = date(YEAR, month, day)
                due = issue + timedelta(days=profile.debtor.payment_terms)

                ref = f"FAC-{YEAR}-{did_num:02d}{seq:04d}"

                inv = Invoice(
                    id=f"INV-{seq:05d}",
                    reference=ref,
                    debtor_id=did,
                    amount=amount_ttc,
                    amount_ht=amount_ht,
                    currency=Currency.EUR,
                    issue_date=issue,
                    due_date=due,
                    batch_date=issue,
                    po_number=f"PO-{YEAR}-{rng.randint(10000,99999)}" if profile.has_po else None,
                    bl_number=f"BL-{YEAR}-{rng.randint(10000,99999)}" if profile.has_bl else None,
                )
                invoices.append(inv)

    rng.shuffle(invoices)
    invoices.sort(key=lambda i: i.issue_date)
    return invoices


# ============================================================
# 3. GÉNÉRATION DES AVOIRS (pour D04 Leclerc)
# ============================================================

def generate_credit_notes(
    profiles: list[DebtorProfile], invoices: list[Invoice], rng: random.Random
) -> list[CreditNote]:
    """Génère des avoirs pour les débiteurs qui en déduisent."""
    credits: list[CreditNote] = []
    seq = 0

    for profile in profiles:
        if profile.debtor.discount_rate > 0 or profile.debtor.rfa_rate > 0:
            debtor_invs = [i for i in invoices if i.debtor_id == profile.debtor.id]
            # 1 avoir tous les ~8 factures
            n_credits = max(1, len(debtor_invs) // 8)
            for _ in range(n_credits):
                seq += 1
                linked = rng.choice(debtor_invs)
                amount = round(rng.uniform(500, min(8000, linked.amount * 0.3)), 2)
                cn = CreditNote(
                    id=f"CN-{seq:04d}",
                    reference=f"AV-{YEAR}-{seq:04d}",
                    debtor_id=profile.debtor.id,
                    amount=amount,
                    issue_date=linked.issue_date + timedelta(days=rng.randint(5, 20)),
                    linked_invoice_ref=linked.reference,
                )
                credits.append(cn)

    return credits


# ============================================================
# 4. UTILITAIRES POUR PAIEMENTS
# ============================================================

MONTH_NAMES_FR = {
    1: "JANVIER", 2: "FEVRIER", 3: "MARS", 4: "AVRIL",
    5: "MAI", 6: "JUIN", 7: "JUILLET", 8: "AOUT",
    9: "SEPTEMBRE", 10: "OCTOBRE", 11: "NOVEMBRE", 12: "DECEMBRE",
}

CRYPTIC_TEMPLATES = [
    "XJ7 TRANSAC {n}", "REF INT {n}", "OP {n} VIR",
    "TRESORERIE MVMT {n}", "{n}", "BANQUE OP{n}",
    "TX{n}ZZ", "CASH MGMT {n}", "VIRT {n}",
    "PROV REGUL {n}", "MOUVEMENT DIVERS",
    "VIREMENT COMMERCIAL", "OPERATION TRESORERIE",
    "CREDIT COMPTE", "REMISE CHEQUES", "ENCAISSEMENT DIVERS",
]


def introduce_typo(ref: str, rng: random.Random) -> str:
    """Introduit une faute réaliste dans une référence."""
    ops = ["swap", "drop", "replace_0_O", "extra_digit", "wrong_digit"]
    op = rng.choice(ops)
    chars = list(ref)
    if len(chars) < 4:
        return ref

    if op == "swap" and len(chars) > 5:
        i = rng.randint(2, len(chars) - 2)
        chars[i], chars[i + 1] = chars[i + 1], chars[i]
    elif op == "drop":
        i = rng.randint(2, len(chars) - 1)
        chars.pop(i)
    elif op == "replace_0_O":
        for i, c in enumerate(chars):
            if c == "0":
                chars[i] = "O"
                break
    elif op == "extra_digit":
        i = rng.randint(2, len(chars) - 1)
        chars.insert(i, str(rng.randint(0, 9)))
    elif op == "wrong_digit":
        digit_positions = [i for i, c in enumerate(chars) if c.isdigit()]
        if digit_positions:
            i = rng.choice(digit_positions)
            chars[i] = str((int(chars[i]) + rng.randint(1, 3)) % 10)

    return "".join(chars)


def make_payment_date(
    due_date: date, avg_delay: float, payment_day: int | None, rng: random.Random
) -> date:
    """Calcule une date de paiement réaliste."""
    base = due_date + timedelta(days=int(avg_delay + rng.gauss(0, 3)))
    if payment_day:
        # Caler sur le jour fixe du mois suivant l'échéance
        m = base.month
        y = base.year
        if base.day > payment_day:
            m += 1
            if m > 12:
                m = 1
                y += 1
        try:
            base = date(y, m, min(payment_day, 28))
        except ValueError:
            pass
    # Pas de weekend
    while base.weekday() >= 5:
        base += timedelta(days=1)
    # Pas avant juillet 2024
    if base < date(YEAR, 7, 1):
        base = date(YEAR, 7, 1)
    return base


# ============================================================
# 5. GÉNÉRATION DES PAIEMENTS (~500 sur 6 mois)
# ============================================================

def generate_payments(
    profiles: list[DebtorProfile],
    invoices: list[Invoice],
    credit_notes: list[CreditNote],
    rng: random.Random,
) -> list[Payment]:
    """Génère tous les paiements en suivant les profils de comportement."""
    payments: list[Payment] = []
    pay_seq = 0
    consumed: set[str] = set()              # invoice IDs déjà allouées
    partial_remaining: dict[str, float] = {}  # inv_id → montant restant (acomptes)
    cn_used: set[str] = set()

    # Grouper les factures par débiteur
    inv_by_debtor: dict[str, list[Invoice]] = defaultdict(list)
    for inv in invoices:
        inv_by_debtor[inv.debtor_id].append(inv)

    cn_by_debtor: dict[str, list[CreditNote]] = defaultdict(list)
    for cn in credit_notes:
        cn_by_debtor[cn.debtor_id].append(cn)

    for profile in profiles:
        did = profile.debtor.id
        avail = [i for i in inv_by_debtor[did]]
        avail.sort(key=lambda i: i.due_date)
        debtor_cns = [cn for cn in cn_by_debtor[did]]

        idx = 0  # curseur dans la liste triée
        while idx < len(avail):
            inv = avail[idx]
            if inv.id in consumed:
                idx += 1
                continue

            # Choisir le scénario
            scenario = _pick_scenario(profile.scenario_weights, rng)
            pay_seq += 1
            pay_id = f"PAY-{pay_seq:05d}"

            pay_date = make_payment_date(
                inv.due_date, profile.avg_delay_days, profile.payment_day, rng
            )

            # ── C1_EXACT_REF ────────────────────────────
            if scenario == "C1_EXACT_REF":
                label = _ref_label(inv.reference, rng)
                p = _make_payment(pay_id, inv.amount, pay_date, profile, label,
                                  refs=[inv.reference])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C1_ISO20022 ─────────────────────────────
            elif scenario == "C1_ISO20022":
                p = _make_payment(pay_id, inv.amount, pay_date, profile,
                                  label="", refs=[])
                p.iso20022 = ISO20022Fields(roc_ref=inv.reference)
                p.signals.raw_refs = [inv.reference.replace("-", "").upper()]
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C1_IBAN_AMOUNT ──────────────────────────
            elif scenario == "C1_IBAN_AMOUNT":
                label = rng.choice(["VIREMENT COMMERCIAL", "REGLEMENT", "PAIEMENT"])
                p = _make_payment(pay_id, inv.amount, pay_date, profile, label, refs=[])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C1_PO_MATCH ─────────────────────────────
            elif scenario == "C1_PO_MATCH" and inv.po_number:
                label = f"REGLT COMMANDE {inv.po_number}"
                refs = [inv.po_number.replace("-", "").upper()]
                p = _make_payment(pay_id, inv.amount, pay_date, profile, label, refs=refs)
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C1_BL_MATCH ─────────────────────────────
            elif scenario == "C1_BL_MATCH" and inv.bl_number:
                label = f"REGLEMENT {inv.bl_number}"
                refs = [inv.bl_number.replace("-", "").upper()]
                p = _make_payment(pay_id, inv.amount, pay_date, profile, label, refs=refs)
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C1_FULL_BALANCE ─────────────────────────
            elif scenario == "C1_FULL_BALANCE":
                remaining = [i for i in avail[idx:] if i.id not in consumed][:8]
                if len(remaining) >= 2:
                    total = sum(i.amount for i in remaining)
                    label = "SOLDE TOTAL COMPTE"
                    p = _make_payment(pay_id, total, pay_date, profile, label, refs=[])
                    payments.append(p)
                    for i in remaining:
                        consumed.add(i.id)
                    idx += len(remaining)
                else:
                    idx += 1
                    continue

            # ── C2_SWIFT_FEES ───────────────────────────
            elif scenario == "C2_SWIFT_FEES":
                fee = round(rng.uniform(15, 35), 2)
                amount = round(inv.amount - fee, 2)
                label = _ref_label(inv.reference, rng)
                p = _make_payment(pay_id, amount, pay_date, profile, label,
                                  refs=[inv.reference])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C2_DISCOUNT (escompte) ──────────────────
            elif scenario == "C2_DISCOUNT" and profile.debtor.discount_rate > 0:
                rate = profile.debtor.discount_rate
                amount = round(inv.amount * (1 - rate), 2)
                pct_str = f"{rate*100:.0f}"
                label = f"REGLT {inv.reference} ESC {pct_str}%"
                p = _make_payment(pay_id, amount, pay_date, profile, label,
                                  refs=[inv.reference])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C2_RETENTION (BTP) ──────────────────────
            elif scenario == "C2_RETENTION" and profile.debtor.retention_rate > 0:
                rate = profile.debtor.retention_rate
                amount = round(inv.amount * (1 - rate), 2)
                label = f"REGLT CHANTIER {inv.reference} RET GAR {rate*100:.0f}%"
                p = _make_payment(pay_id, amount, pay_date, profile, label,
                                  refs=[inv.reference])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C2_RFA (remise fin d'année) ─────────────
            elif scenario == "C2_RFA" and profile.debtor.rfa_rate > 0:
                rate = profile.debtor.rfa_rate
                amount = round(inv.amount * (1 - rate), 2)
                label = f"REGLT {inv.reference} DED RFA {rate*100:.0f}%"
                p = _make_payment(pay_id, amount, pay_date, profile, label,
                                  refs=[inv.reference])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C2_CREDIT_NOTE ──────────────────────────
            elif scenario == "C2_CREDIT_NOTE" and debtor_cns:
                available_cns = [cn for cn in debtor_cns if cn.id not in cn_used
                                 and cn.amount < inv.amount]
                if available_cns:
                    cn = available_cns[0]
                    amount = round(inv.amount - cn.amount, 2)
                    label = f"REGLT {inv.reference} DED AVOIR {cn.reference}"
                    p = _make_payment(pay_id, amount, pay_date, profile, label,
                                      refs=[inv.reference])
                    payments.append(p)
                    consumed.add(inv.id)
                    cn_used.add(cn.id)
                    idx += 1
                else:
                    idx += 1
                    continue

            # ── C2_ROUNDING ─────────────────────────────
            elif scenario == "C2_ROUNDING":
                delta = round(rng.uniform(-0.99, 0.99), 2)
                if abs(delta) < 0.01:
                    delta = 0.50
                amount = round(inv.amount + delta, 2)
                label = _ref_label(inv.reference, rng)
                p = _make_payment(pay_id, amount, pay_date, profile, label,
                                  refs=[inv.reference])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C2_SUBSET_SUM ───────────────────────────
            elif scenario == "C2_SUBSET_SUM":
                remaining = [i for i in avail[idx:] if i.id not in consumed]
                n = min(rng.randint(2, 4), len(remaining))
                if n >= 2:
                    group = remaining[:n]
                    total = round(sum(i.amount for i in group), 2)
                    label = "REGLEMENT FACTURES EN COURS"
                    p = _make_payment(pay_id, total, pay_date, profile, label, refs=[])
                    payments.append(p)
                    for i in group:
                        consumed.add(i.id)
                    idx += n
                else:
                    idx += 1
                    continue

            # ── C2_INSTALLMENT ──────────────────────────
            elif scenario == "C2_INSTALLMENT":
                pct = rng.choice([0.30, 0.50, 0.70])
                amount = round(inv.amount * pct, 2)
                label = f"ACOMPTE {int(pct*100)}% {inv.reference}"
                p = _make_payment(pay_id, amount, pay_date, profile, label,
                                  refs=[inv.reference])
                p.signals.keywords = {"partial": True, "advance": True,
                                      "credit_note": False, "final": False}
                payments.append(p)
                partial_remaining[inv.id] = round(inv.amount - amount, 2)

                # Paiement du solde 15-30j plus tard
                pay_seq += 1
                pay_id2 = f"PAY-{pay_seq:05d}"
                date2 = pay_date + timedelta(days=rng.randint(15, 30))
                while date2.weekday() >= 5:
                    date2 += timedelta(days=1)
                rest = partial_remaining[inv.id]
                label2 = f"SOLDE {int((1-pct)*100)}% {inv.reference}"
                p2 = _make_payment(pay_id2, rest, date2, profile, label2,
                                   refs=[inv.reference])
                p2.signals.keywords = {"partial": False, "advance": False,
                                       "credit_note": False, "final": True}
                payments.append(p2)
                consumed.add(inv.id)
                idx += 1

            # ── C2_TEMPORAL ─────────────────────────────
            elif scenario == "C2_TEMPORAL":
                # Payer toutes les factures d'un même mois
                target_month = inv.issue_date.month
                same_month = [
                    i for i in avail[idx:] if i.id not in consumed
                    and i.issue_date.month == target_month
                ][:6]
                if len(same_month) >= 2:
                    total = round(sum(i.amount for i in same_month), 2)
                    mname = MONTH_NAMES_FR.get(target_month, str(target_month))
                    label = f"REGLEMENT FACTURES {mname} {YEAR}"
                    p = _make_payment(pay_id, total, pay_date, profile, label,
                                      refs=[])
                    p.signals.label_periods = [f"{mname} {YEAR}"]
                    payments.append(p)
                    for i in same_month:
                        consumed.add(i.id)
                    idx += len(same_month)
                else:
                    idx += 1
                    continue

            # ── C2_WHT (retenue à la source) ────────────
            elif scenario == "C2_WHT":
                wht_rates = {"MA": 0.20, "TN": 0.15}
                rate = wht_rates.get(profile.debtor.country, 0.15)
                amount = round(inv.amount * (1 - rate), 2)
                label = _ref_label(inv.reference, rng)
                p = _make_payment(pay_id, amount, pay_date, profile, label,
                                  refs=[inv.reference])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C2_HT_ERROR ─────────────────────────────
            elif scenario == "C2_HT_ERROR":
                amount = inv.amount_ht  # paie HT au lieu de TTC
                label = f"PAYMENT INVOICE {inv.reference}"
                p = _make_payment(pay_id, amount, pay_date, profile, label,
                                  refs=[inv.reference])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C3_FUZZY (typo dans la ref) ─────────────
            elif scenario == "C3_FUZZY":
                typo_ref = introduce_typo(inv.reference, rng)
                label = f"REGLT {typo_ref}"
                refs = [typo_ref.replace("-", "").upper()]
                p = _make_payment(pay_id, inv.amount, pay_date, profile, label,
                                  refs=refs)
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

            # ── C6_CRYPTIC (label inutilisable) ────────
            elif scenario == "C6_CRYPTIC":
                tmpl = rng.choice(CRYPTIC_TEMPLATES)
                label = tmpl.format(n=rng.randint(1000, 9999))
                # Montant parfois juste, parfois décalé
                if rng.random() < 0.3:
                    amount = inv.amount  # montant correct mais label cryptique
                else:
                    amount = round(rng.uniform(500, 50000), 2)  # montant aléatoire
                p = _make_payment(pay_id, amount, pay_date, profile, label, refs=[])
                payments.append(p)
                if rng.random() < 0.3:
                    consumed.add(inv.id)
                idx += 1

            else:
                # Fallback : paiement exact avec ref
                label = _ref_label(inv.reference, rng)
                p = _make_payment(pay_id, inv.amount, pay_date, profile, label,
                                  refs=[inv.reference])
                payments.append(p)
                consumed.add(inv.id)
                idx += 1

    # Tri chronologique
    payments.sort(key=lambda p: p.date or date(YEAR, 7, 1))
    return payments


def _pick_scenario(weights: dict[str, float], rng: random.Random) -> str:
    scenarios = list(weights.keys())
    probs = list(weights.values())
    total = sum(probs)
    probs = [p / total for p in probs]
    return rng.choices(scenarios, weights=probs, k=1)[0]


def _ref_label(ref: str, rng: random.Random) -> str:
    prefixes = [
        "REGLT", "REGLEMENT", "PAIEMENT", "VIRT", "VIREMENT",
        "RGT", "PMT", "VIR SEPA",
    ]
    return f"{rng.choice(prefixes)} {ref}"


def _make_payment(
    pay_id: str, amount: float, pay_date: date,
    profile: DebtorProfile, label: str, refs: list[str],
) -> Payment:
    return Payment(
        id=pay_id,
        amount=round(amount, 2),
        currency=Currency.EUR,
        date=pay_date,
        label_raw=label,
        label_normalized=label.upper(),
        iban_source=profile.debtor.iban or "",
        bic_source=profile.debtor.bic or "",
        debtor_id=profile.debtor.id,
        debtor=profile.debtor,
        signals=PaymentSignals(raw_refs=[r.replace("-", "").upper() for r in refs] if refs else []),
    )


# ============================================================
# 6. ANALYTICS & REPORTING
# ============================================================

LAYER_NAMES = {
    0: "C0 Pre-traitement",
    1: "C1 Exact/Deterministe",
    2: "C2 Regles Metier",
    3: "C3 NLP/Fuzzy",
    4: "C4 Machine Learning",
    5: "C5 LLM",
    6: "C6 Revue Humaine",
}

LAYER_COLORS = {
    1: "\033[92m",  # vert
    2: "\033[93m",  # jaune
    3: "\033[96m",  # cyan
    6: "\033[91m",  # rouge
}
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def print_banner():
    print(f"""
{BOLD}{'='*78}
   SIMULATION MASSIVE — Reconciliation Paiement-Facture par IA
   Architecture 6 Couches | Factoring & Finance Receivables
{'='*78}{RESET}
""")


def print_data_summary(profiles, invoices, payments, credit_notes):
    print(f"{BOLD}--- DONNEES GENEREES ---{RESET}")
    print(f"  Debiteurs     : {len(profiles)}")
    print(f"  Factures      : {len(invoices)}")
    print(f"  Paiements     : {len(payments)}")
    print(f"  Avoirs        : {len(credit_notes)}")

    # Volume par mois
    inv_by_month = Counter(i.issue_date.month for i in invoices)
    pay_by_month = Counter(p.date.month for p in payments if p.date)
    print(f"\n  {'Mois':<12} {'Factures':>10} {'Paiements':>10}")
    print(f"  {'-'*34}")
    for m in MONTHS:
        mname = MONTH_NAMES_FR.get(m, str(m))[:8]
        print(f"  {mname:<12} {inv_by_month.get(m,0):>10} {pay_by_month.get(m,0):>10}")
    total_inv = sum(inv_by_month.values())
    total_pay = sum(pay_by_month.values())
    print(f"  {'TOTAL':<12} {total_inv:>10} {total_pay:>10}")

    # Volume par débiteur
    inv_by_debtor = Counter(i.debtor_id for i in invoices)
    pay_by_debtor = Counter(p.debtor_id for p in payments)
    debtor_names = {p.debtor.id: p.debtor.name[:30] for p in profiles}
    print(f"\n  {'Debiteur':<34} {'Factures':>8} {'Paiements':>10}")
    print(f"  {'-'*54}")
    for did in sorted(inv_by_debtor.keys()):
        name = debtor_names.get(did, did)
        print(f"  {name:<34} {inv_by_debtor[did]:>8} {pay_by_debtor.get(did,0):>10}")

    # Montants
    total_inv_amount = sum(i.amount for i in invoices)
    total_pay_amount = sum(p.amount for p in payments)
    print(f"\n  Montant total factures  : {total_inv_amount:>14,.2f} EUR")
    print(f"  Montant total paiements : {total_pay_amount:>14,.2f} EUR")
    print()


def print_processing_progress(i, total, ctx):
    """Affiche une barre de progression pendant le traitement."""
    if i % 50 == 0 or i == total - 1:
        pct = (i + 1) / total * 100
        bar_len = 40
        filled = int(bar_len * (i + 1) / total)
        bar = "█" * filled + "░" * (bar_len - filled)
        matched = "OK" if ctx.final_match else "--"
        layer = f"C{ctx.final_match.layer}" if ctx.final_match else "C6"
        print(f"\r  [{bar}] {pct:5.1f}% | {i+1}/{total} | {ctx.payment.id} -> {layer} {matched}", end="", flush=True)


def print_results(orch, results, invoices, payments):
    m = orch.metrics
    print(f"\n\n{BOLD}{'='*78}")
    print(f"   RESULTATS DE LA SIMULATION")
    print(f"{'='*78}{RESET}\n")

    # ── Taux global ──
    auto = m.matched_auto
    total = m.total_payments
    review = m.by_layer.get(6, 0)
    errors = m.errors
    auto_pct = auto / total * 100 if total else 0
    review_pct = review / total * 100 if total else 0

    print(f"  {BOLD}Taux d'automatisation : {auto_pct:.1f}%{RESET} ({auto}/{total} paiements)")
    print(f"  Revue humaine       : {review_pct:.1f}% ({review} paiements)")
    print(f"  Erreurs pipeline    : {errors}")
    print(f"  Temps moyen         : {m.avg_processing_time_ms:.2f} ms/paiement")
    print(f"  Temps total         : {m.total_processing_time_ms:.0f} ms")
    print()

    # ── Distribution par couche ──
    print(f"  {BOLD}--- Distribution par couche ---{RESET}")
    print(f"  {'Couche':<28} {'Nb':>6} {'%':>8}  {'Barre'}")
    print(f"  {'-'*60}")
    for layer in sorted(m.by_layer.keys()):
        count = m.by_layer[layer]
        pct = count / total * 100 if total else 0
        bar_len = int(pct / 2)
        color = LAYER_COLORS.get(layer, "")
        name = LAYER_NAMES.get(layer, f"C{layer}")
        bar = "█" * bar_len
        print(f"  {color}{name:<28} {count:>6} {pct:>7.1f}%  {bar}{RESET}")

    # ── Distribution par méthode ──
    print(f"\n  {BOLD}--- Distribution par methode de matching ---{RESET}")
    print(f"  {'Methode':<36} {'Nb':>6} {'%':>8}")
    print(f"  {'-'*52}")
    for method, count in sorted(m.by_method.items(), key=lambda x: -x[1]):
        pct = count / total * 100 if total else 0
        print(f"  {method:<36} {count:>6} {pct:>7.1f}%")

    # ── Résultats par débiteur ──
    print(f"\n  {BOLD}--- Resultats par debiteur ---{RESET}")
    debtor_results = defaultdict(lambda: {"auto": 0, "review": 0, "total": 0})
    for ctx in results:
        did = ctx.payment.debtor_id or "?"
        debtor_results[did]["total"] += 1
        if ctx.final_match and ctx.final_match.confidence >= 0.90:
            debtor_results[did]["auto"] += 1
        else:
            debtor_results[did]["review"] += 1

    debtor_names = {}
    for ctx in results:
        if ctx.payment.debtor:
            debtor_names[ctx.payment.debtor_id] = ctx.payment.debtor.name[:28]

    print(f"  {'Debiteur':<32} {'Total':>6} {'Auto':>6} {'Revue':>6} {'Taux':>7}")
    print(f"  {'-'*60}")
    for did in sorted(debtor_results.keys()):
        d = debtor_results[did]
        rate = d["auto"] / d["total"] * 100 if d["total"] else 0
        name = debtor_names.get(did, did)
        color = "\033[92m" if rate >= 80 else "\033[93m" if rate >= 60 else "\033[91m"
        print(f"  {name:<32} {d['total']:>6} {d['auto']:>6} {d['review']:>6} {color}{rate:>6.1f}%{RESET}")

    # ── Timeline mensuelle ──
    print(f"\n  {BOLD}--- Timeline mensuelle ---{RESET}")
    monthly = defaultdict(lambda: {"total": 0, "auto": 0})
    for ctx in results:
        if ctx.payment.date:
            m_key = ctx.payment.date.month
            monthly[m_key]["total"] += 1
            if ctx.final_match and ctx.final_match.confidence >= 0.90:
                monthly[m_key]["auto"] += 1

    print(f"  {'Mois':<12} {'Total':>6} {'Auto':>6} {'Taux':>7}")
    print(f"  {'-'*34}")
    for month in MONTHS:
        d = monthly[month]
        rate = d["auto"] / d["total"] * 100 if d["total"] else 0
        mname = MONTH_NAMES_FR.get(month, str(month))[:10]
        print(f"  {mname:<12} {d['total']:>6} {d['auto']:>6} {rate:>6.1f}%")

    # ── Échantillon détaillé : 20 paiements ──
    print(f"\n  {BOLD}--- Echantillon detaille (20 paiements) ---{RESET}")
    print(f"  {'ID':<12} {'Date':<12} {'Montant':>12} {'Debiteur':<20} {'Couche':<8} {'Methode':<24} {'Conf':>5} {'Flags'}")
    print(f"  {'-'*115}")
    sample = results[::max(1, len(results) // 20)][:20]
    for ctx in sample:
        p = ctx.payment
        fm = ctx.final_match
        if fm:
            layer = f"C{fm.layer}"
            method = fm.method.value[:22]
            conf = f"{fm.confidence:.2f}"
            flags = ", ".join(fm.flags[:2]) if fm.flags else ""
        else:
            layer = "C6"
            method = "HUMAN_REVIEW"
            conf = "---"
            flags = "QUEUE"
        dname = (p.debtor.name[:18] if p.debtor else p.debtor_id or "?")
        print(f"  {p.id:<12} {str(p.date):<12} {p.amount:>12,.2f} {dname:<20} {layer:<8} {method:<24} {conf:>5} {flags}")

    # ── File de revue humaine ──
    q = orch.review_queue
    print(f"\n  {BOLD}--- File de revue humaine ---{RESET}")
    print(f"  Taille de la file : {q.queue_size}")
    if q.queue_size > 0:
        print(f"  {'Paiement':<12} {'Montant':>12} {'Debiteur':<24} {'Label':<30} {'Priorite':>8}")
        print(f"  {'-'*90}")
        # Accès direct à la queue interne pour affichage (sans consommer)
        for item in q._queue[:15]:
            p = item.payment
            dname = p.debtor.name[:22] if p.debtor else "?"
            label = p.label_raw[:28] if p.label_raw else "(vide)"
            print(f"  {p.id:<12} {p.amount:>12,.2f} {dname:<24} {label:<30} {item.priority_score:>7.3f}")
    print()


# ============================================================
# 7. RUNNER PRINCIPAL
# ============================================================

def run_simulation(seed: int = 42, verbose: bool = True):
    """
    Lance la simulation complète :
      1. Génère les données (débiteurs, factures, avoirs, paiements)
      2. Configure l'orchestrateur
      3. Traite tous les paiements
      4. Affiche les résultats détaillés
    """
    rng = random.Random(seed)

    # Supprimer les warnings verbeux des couches optionnelles (sklearn, LLM, etc.)
    import logging
    logging.getLogger("reconciliation").setLevel(logging.CRITICAL)

    print_banner()

    # ── 1. Génération des données ──
    if verbose:
        print(f"{DIM}  Génération des données...{RESET}")
    profiles = create_debtor_profiles()
    invoices = generate_invoices(profiles, rng)
    credit_notes = generate_credit_notes(profiles, invoices, rng)

    # Rattacher les avoirs aux débiteurs
    cn_by_debtor = defaultdict(list)
    for cn in credit_notes:
        cn_by_debtor[cn.debtor_id].append(cn)
    for profile in profiles:
        profile.debtor.open_credits = cn_by_debtor.get(profile.debtor.id, [])

    payments = generate_payments(profiles, invoices, credit_notes, rng)

    if verbose:
        print_data_summary(profiles, invoices, payments, credit_notes)

    # ── 2. Configuration de l'orchestrateur ──
    config = ReconciliationConfig()
    orch = ReconciliationOrchestrator(config)

    debtors = [p.debtor for p in profiles]
    iban_map = {p.debtor.iban: p.debtor.id for p in profiles if p.debtor.iban}

    # Rattacher les factures ouvertes aux débiteurs
    inv_by_debtor = defaultdict(list)
    for inv in invoices:
        inv_by_debtor[inv.debtor_id].append(inv)
    for profile in profiles:
        profile.debtor.open_invoices = inv_by_debtor.get(profile.debtor.id, [])

    orch.setup(invoices, debtors=debtors, iban_debtor_map=iban_map)

    # ── 3. Traitement séquentiel (simule l'arrivée jour par jour) ──
    if verbose:
        print(f"{BOLD}--- TRAITEMENT DES PAIEMENTS ---{RESET}")
        print(f"  {len(payments)} paiements a traiter...\n")

    open_invoices = list(invoices)  # copie de travail
    results = []
    current_month = None

    t0 = time.time()
    for i, payment in enumerate(payments):
        # Afficher le mois en cours
        if verbose and payment.date and payment.date.month != current_month:
            current_month = payment.date.month
            mname = MONTH_NAMES_FR.get(current_month, str(current_month))
            print(f"\n  {BOLD}>> {mname} {YEAR}{RESET}")

        ctx = orch.process_payment(payment, open_invoices)
        results.append(ctx)

        # Retirer les factures matchées du portefeuille ouvert
        if ctx.final_match:
            matched_ids = {inv.id for inv in ctx.final_match.invoices}
            open_invoices = [inv for inv in open_invoices if inv.id not in matched_ids]

        if verbose:
            print_processing_progress(i, len(payments), ctx)

    wall_time = time.time() - t0

    # ── 4. Résultats ──
    if verbose:
        print_results(orch, results, invoices, payments)
        print(f"  {DIM}Temps reel total : {wall_time:.2f}s pour {len(payments)} paiements")
        print(f"  Debit : {len(payments)/wall_time:.0f} paiements/seconde{RESET}")
        print()

    return orch, results


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    run_simulation()
