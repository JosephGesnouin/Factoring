#!/usr/bin/env python3
"""
=============================================================================
  SIMULATION COMPLETE DE RECONCILIATION PAIEMENT-FACTURE
  Exemple cle en main — 20 scenarios realistes couvrant toutes les couches
=============================================================================

  Execution:
      python -m examples.demo_simulation

  Ce script simule un portefeuille de factures ouvertes pour 6 debiteurs,
  puis injecte 20 paiements couvrant tous les cas de figure :

  +----------+------------------------------------------------------+
  | Paiement | Scenario attendu                                     |
  +----------+------------------------------------------------------+
  | PAY-01   | C1 -- Reference exacte + montant exact               |
  | PAY-02   | C1 -- Reference ISO 20022 (champ /ROC/)              |
  | PAY-03   | C1 -- Multi-factures (3 refs dans le libelle)        |
  | PAY-04   | C1 -- IBAN connu + montant unique                    |
  | PAY-05   | C1 -- Solde total du debiteur                        |
  | PAY-06   | C1 -- Matching via PO (bon de commande)              |
  | PAY-07   | C2 -- Frais bancaires SWIFT (-28EUR)                 |
  | PAY-08   | C2 -- Escompte contractuel 2%                        |
  | PAY-09   | C2 -- Retenue de garantie BTP 5%                     |
  | PAY-10   | C2 -- Avoir deduit du paiement                       |
  | PAY-11   | C2 -- Subset sum (2 factures sur 3)                  |
  | PAY-12   | C2 -- Acompte 30% sur grosse facture                 |
  | PAY-13   | C2 -- Arrondi comptable (+/-0.50EUR)                 |
  | PAY-14   | C1 -- Montant = HT (erreur TVA debiteur)             |
  | PAY-15   | C3 -- Reference avec typo (fuzzy matching)           |
  | PAY-16   | C2 -- Pattern temporel (reglement octobre)           |
  | PAY-17   | C2 -- RFA (Remise Fin d'Annee) 3%                    |
  | PAY-18   | C1 -- Matching par BL (bon de livraison)             |
  | PAY-19   | C1 -- Full balance net credits                       |
  | PAY-20   | C6 -- Libelle cryptique -> file de revue humaine     |
  +----------+------------------------------------------------------+
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.config import ReconciliationConfig
from reconciliation.models import (
    CreditNote,
    Currency,
    Debtor,
    Invoice,
    Payment,
    PaymentSignals,
)
from reconciliation.orchestrator import ReconciliationOrchestrator


# ==========================================================================
#  1. PORTEFEUILLE DE FACTURES OUVERTES
# ==========================================================================
# Chaque debiteur a ses propres factures. Les factures sont numerotees
# de maniere a ce que chaque paiement ait ses propres cibles.
# On evite les conflits entre scenarios.

def create_invoices() -> list[Invoice]:
    return [
        # ── D1 : Boulangerie Dupont (FR, regulier) ──
        # PAY-01 cible INV-101, PAY-13 cible INV-103
        Invoice(id="INV-101", reference="FAC-2024-101", debtor_id="D1",
                amount=10_000.00, amount_ht=8_333.33,
                issue_date=date(2024, 9, 15), due_date=date(2024, 10, 15)),
        Invoice(id="INV-102", reference="FAC-2024-102", debtor_id="D1",
                amount=5_500.00, amount_ht=4_583.33,
                issue_date=date(2024, 9, 20), due_date=date(2024, 10, 20)),
        Invoice(id="INV-103", reference="FAC-2024-103", debtor_id="D1",
                amount=3_200.00, amount_ht=2_666.67,
                issue_date=date(2024, 10, 1), due_date=date(2024, 10, 31)),
        Invoice(id="INV-104", reference="FAC-2024-104", debtor_id="D1",
                amount=1_800.00, amount_ht=1_500.00,
                issue_date=date(2024, 10, 10), due_date=date(2024, 11, 10)),

        # ── D2 : Construction Martin (FR, BTP, retenue garantie) ──
        # PAY-06 cible INV-201 (via PO), PAY-09 cible INV-202
        # PAY-11 cible INV-203+204 (subset sum)
        Invoice(id="INV-201", reference="FAC-2024-201", debtor_id="D2",
                amount=50_000.00, amount_ht=41_666.67,
                issue_date=date(2024, 8, 1), due_date=date(2024, 9, 30),
                po_number="PO-2024-789"),
        Invoice(id="INV-202", reference="FAC-2024-202", debtor_id="D2",
                amount=25_000.00, amount_ht=20_833.33,
                issue_date=date(2024, 9, 1), due_date=date(2024, 10, 31)),
        Invoice(id="INV-203", reference="FAC-2024-203", debtor_id="D2",
                amount=15_000.00, amount_ht=12_500.00,
                issue_date=date(2024, 9, 15), due_date=date(2024, 11, 15)),
        Invoice(id="INV-204", reference="FAC-2024-204", debtor_id="D2",
                amount=8_000.00, amount_ht=6_666.67,
                issue_date=date(2024, 10, 1), due_date=date(2024, 11, 30)),

        # ── D3 : Schmidt Import (DE, SEPA) ──
        # PAY-04 cible INV-301, PAY-14 cible INV-302
        Invoice(id="INV-301", reference="FAC-2024-301", debtor_id="D3",
                amount=22_000.00, amount_ht=18_333.33,
                issue_date=date(2024, 10, 1), due_date=date(2024, 11, 1)),
        Invoice(id="INV-302", reference="FAC-2024-302", debtor_id="D3",
                amount=8_500.00, amount_ht=7_083.33,
                issue_date=date(2024, 10, 5), due_date=date(2024, 11, 5)),

        # ── D4 : Groupe Leclerc (FR, escompte, RFA, avoirs) ──
        # PAY-08 cible INV-401, PAY-10 cible INV-402, PAY-12 cible INV-405
        # PAY-15 cible INV-403, PAY-17 cible INV-404
        # PAY-19 cible INV-405 (si non deja matche) / INV-406 solde
        Invoice(id="INV-401", reference="FAC-2024-401", debtor_id="D4",
                amount=100_000.00, amount_ht=83_333.33,
                issue_date=date(2024, 9, 1), due_date=date(2024, 10, 1)),
        Invoice(id="INV-402", reference="FAC-2024-402", debtor_id="D4",
                amount=45_000.00, amount_ht=37_500.00,
                issue_date=date(2024, 10, 1), due_date=date(2024, 10, 31)),
        Invoice(id="INV-403", reference="FAC-2024-403", debtor_id="D4",
                amount=30_000.00, amount_ht=25_000.00,
                issue_date=date(2024, 10, 5), due_date=date(2024, 11, 5)),
        Invoice(id="INV-404", reference="FAC-2024-404", debtor_id="D4",
                amount=20_000.00, amount_ht=16_666.67,
                issue_date=date(2024, 10, 10), due_date=date(2024, 11, 10)),
        Invoice(id="INV-405", reference="FAC-2024-405", debtor_id="D4",
                amount=55_000.00, amount_ht=45_833.33,
                issue_date=date(2024, 10, 12), due_date=date(2024, 11, 12)),

        # ── D5 : Transport Rossi (IT, BL) ──
        # PAY-05 cible toutes D5, PAY-18 cible INV-501
        Invoice(id="INV-501", reference="FAC-2024-501", debtor_id="D5",
                amount=7_500.00, amount_ht=6_250.00,
                issue_date=date(2024, 9, 20), due_date=date(2024, 10, 20),
                bl_number="BL-2024-555"),
        Invoice(id="INV-502", reference="FAC-2024-502", debtor_id="D5",
                amount=12_000.00, amount_ht=10_000.00,
                issue_date=date(2024, 10, 1), due_date=date(2024, 10, 31)),
        Invoice(id="INV-503", reference="FAC-2024-503", debtor_id="D5",
                amount=4_800.00, amount_ht=4_000.00,
                issue_date=date(2024, 10, 5), due_date=date(2024, 11, 5)),

        # ── D6 : Maroc Export (MA, hors SEPA, retenue a la source) ──
        # PAY-07 cible INV-601
        Invoice(id="INV-601", reference="FAC-2024-601", debtor_id="D6",
                amount=15_000.00, amount_ht=12_500.00,
                issue_date=date(2024, 9, 10), due_date=date(2024, 10, 10)),
    ]


# ==========================================================================
#  2. DEBITEURS
# ==========================================================================

def create_debtors() -> list[Debtor]:
    return [
        Debtor(id="D1", name="Boulangerie Dupont",
               iban="FR7630001007941234567890185", country="FR",
               sector="ALIMENTAIRE", payment_terms=30,
               avg_payment_delay=5, payment_regularity_score=0.9, risk_score=0.2),

        Debtor(id="D2", name="Construction Martin",
               iban="FR7630004000031234567890143", country="FR",
               sector="BTP", payment_terms=60, retention_rate=0.05,
               avg_payment_delay=15, payment_regularity_score=0.7, risk_score=0.4),

        Debtor(id="D3", name="Schmidt Import GmbH",
               iban="DE89370400440532013000", country="DE",
               sector="IMPORT", payment_terms=30,
               avg_payment_delay=3, payment_regularity_score=0.85, risk_score=0.3),

        Debtor(id="D4", name="Groupe Leclerc Distribution",
               iban="FR7610011000201234567890188", country="FR",
               sector="DISTRIBUTION", payment_terms=45,
               discount_rate=0.02, rfa_rate=0.03,
               avg_payment_delay=0, payment_regularity_score=0.95, risk_score=0.1,
               open_credits=[
                   CreditNote(id="CN-001", reference="AV-2024-001",
                              debtor_id="D4", amount=5_000.00,
                              issue_date=date(2024, 9, 25)),
               ]),

        Debtor(id="D5", name="Transport Rossi Srl",
               iban="IT60X0542811101000000123456", country="IT",
               sector="TRANSPORT", payment_terms=30,
               avg_payment_delay=10, payment_regularity_score=0.6, risk_score=0.5),

        Debtor(id="D6", name="Maroc Export SARL",
               iban="MA64011519000001205000534921", country="MA",
               sector="EXPORT", payment_terms=30,
               avg_payment_delay=8, payment_regularity_score=0.7, risk_score=0.6),
    ]


# ==========================================================================
#  3. LES 20 PAIEMENTS
# ==========================================================================
# L'ordre est choisi pour eviter les conflits de consommation de factures.
# Les paiements qui ciblent des factures uniques passent avant les paiements
# groupes qui pourraient les capturer.

def create_payments() -> list[Payment]:
    return [
        # ── PAY-01 : C1 -- Reference exacte + montant exact ────────────
        Payment(
            id="PAY-01", amount=10_000.00, currency=Currency.EUR,
            date=date(2024, 10, 18),
            label_raw="REGLT FAC-2024-101",
            iban_source="FR7630001007941234567890185",
            metadata={"scenario": "C1 Ref exacte + montant exact",
                       "attendu": "FAC-2024-101"},
        ),

        # ── PAY-02 : C1 -- ISO 20022 /ROC/ (libelle vide!) ────────────
        Payment(
            id="PAY-02", amount=5_500.00, currency=Currency.EUR,
            date=date(2024, 10, 22),
            label_raw="",
            iban_source="FR7630001007941234567890185",
            metadata={"scenario": "C1 ISO 20022 /ROC/",
                       "attendu": "FAC-2024-102",
                       "iso20022": {"roc_ref": "FAC-2024-102"}},
        ),

        # ── PAY-14 : C1 -- Montant HT (erreur TVA) ────────────────────
        # On le place tot pour eviter que D3 soit vide
        Payment(
            id="PAY-14", amount=7_083.33, currency=Currency.EUR,
            date=date(2024, 10, 18),
            label_raw="PAYMENT INVOICE FAC-2024-302",
            iban_source="DE89370400440532013000",
            metadata={"scenario": "C1 Montant HT (erreur TVA)",
                       "attendu": "FAC-2024-302"},
        ),

        # ── PAY-04 : C1 -- IBAN connu + montant unique ─────────────────
        Payment(
            id="PAY-04", amount=22_000.00, currency=Currency.EUR,
            date=date(2024, 10, 20),
            label_raw="VIREMENT COMMERCIAL",
            iban_source="DE89370400440532013000",
            metadata={"scenario": "C1 IBAN + montant unique",
                       "attendu": "FAC-2024-301"},
        ),

        # ── PAY-18 : C1 -- Matching par BL ─────────────────────────────
        # Avant PAY-05 qui prend tout D5
        Payment(
            id="PAY-18", amount=7_500.00, currency=Currency.EUR,
            date=date(2024, 10, 25),
            label_raw="REGLEMENT BL-2024-555",
            iban_source="IT60X0542811101000000123456",
            metadata={"scenario": "C1 Matching via BL",
                       "attendu": "FAC-2024-501"},
        ),

        # ── PAY-05 : C1 -- Solde total debiteur D5 ─────────────────────
        # 12000 + 4800 = 16800 (FAC-501 deja pris par PAY-18)
        Payment(
            id="PAY-05", amount=16_800.00, currency=Currency.EUR,
            date=date(2024, 10, 28),
            label_raw="SOLDE COMPTE",
            iban_source="IT60X0542811101000000123456",
            metadata={"scenario": "C1 Solde total debiteur",
                       "attendu": "FAC-2024-502 + FAC-2024-503"},
        ),

        # ── PAY-06 : C1 -- Matching via PO ─────────────────────────────
        Payment(
            id="PAY-06", amount=50_000.00, currency=Currency.EUR,
            date=date(2024, 10, 15),
            label_raw="REGLT COMMANDE PO-2024-789",
            iban_source="FR7630004000031234567890143",
            metadata={"scenario": "C1 PO matching",
                       "attendu": "FAC-2024-201 (via PO-2024-789)"},
        ),

        # ── PAY-07 : C2 -- Frais SWIFT depuis le Maroc (-28EUR) ────────
        Payment(
            id="PAY-07", amount=14_972.00, currency=Currency.EUR,
            date=date(2024, 10, 12),
            label_raw="REGLEMENT FAC-2024-601",
            iban_source="MA64011519000001205000534921",
            metadata={"scenario": "C2 Frais SWIFT -28EUR",
                       "attendu": "FAC-2024-601 (15000 - 28 frais)"},
        ),

        # ── PAY-08 : C2 -- Escompte 2% ─────────────────────────────────
        Payment(
            id="PAY-08", amount=98_000.00, currency=Currency.EUR,
            date=date(2024, 10, 1),
            label_raw="REGLEMENT FAC-2024-401 ESCOMPTE 2%",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C2 Escompte 2%",
                       "attendu": "FAC-2024-401 (100000 x 0.98)"},
        ),

        # ── PAY-09 : C2 -- Retenue garantie BTP 5% ─────────────────────
        Payment(
            id="PAY-09", amount=23_750.00, currency=Currency.EUR,
            date=date(2024, 10, 30),
            label_raw="REGLT CHANTIER FAC-2024-202 RETENUE GARANTIE",
            iban_source="FR7630004000031234567890143",
            metadata={"scenario": "C2 Retenue garantie BTP 5%",
                       "attendu": "FAC-2024-202 (25000 x 0.95)"},
        ),

        # ── PAY-10 : C2 -- Avoir deduit ────────────────────────────────
        Payment(
            id="PAY-10", amount=40_000.00, currency=Currency.EUR,
            date=date(2024, 10, 28),
            label_raw="REGLT FAC-2024-402 DEDUCTION AVOIR AV-2024-001",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C2 Avoir deduit",
                       "attendu": "FAC-2024-402 (45000 - 5000 avoir)"},
        ),

        # ── PAY-11 : C2 -- Subset Sum (2 factures sur 3) ──────────────
        Payment(
            id="PAY-11", amount=23_000.00, currency=Currency.EUR,
            date=date(2024, 10, 25),
            label_raw="REGLEMENT FACTURES EN COURS",
            iban_source="FR7630004000031234567890143",
            metadata={"scenario": "C2 Subset sum 2/3",
                       "attendu": "FAC-2024-203 (15000) + FAC-2024-204 (8000)"},
        ),

        # ── PAY-12 : C2 -- Acompte 30% ─────────────────────────────────
        Payment(
            id="PAY-12", amount=16_500.00, currency=Currency.EUR,
            date=date(2024, 10, 20),
            label_raw="ACOMPTE FAC-2024-405",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C2 Acompte 30%",
                       "attendu": "FAC-2024-405 (55000 x 0.30)"},
        ),

        # ── PAY-13 : C2 -- Arrondi comptable ───────────────────────────
        Payment(
            id="PAY-13", amount=3_200.50, currency=Currency.EUR,
            date=date(2024, 10, 31),
            label_raw="VIRT FAC-2024-103",
            iban_source="FR7630001007941234567890185",
            metadata={"scenario": "C2 Arrondi +/-0.50EUR",
                       "attendu": "FAC-2024-103 (3200 +0.50)"},
        ),

        # ── PAY-03 : C1 -- Multi-factures ──────────────────────────────
        # Arrive tard pour s'assurer que les factures individuelles
        # D1 restantes sont INV-104 (1800). On cible INV-103 deja pris.
        # En fait on cree un scenario ou il reste 1 facture D1 : INV-104
        # et le paiement fait 1800 exact -> C1 IBAN+montant unique
        Payment(
            id="PAY-03", amount=1_800.00, currency=Currency.EUR,
            date=date(2024, 10, 25),
            label_raw="REGLEMENT FAC-2024-104",
            iban_source="FR7630001007941234567890185",
            metadata={"scenario": "C1 Derniere facture D1",
                       "attendu": "FAC-2024-104"},
        ),

        # ── PAY-15 : C3 -- Ref avec typo (fuzzy) ──────────────────────
        # "FAC-2024-4O3" au lieu de "FAC-2024-403" (O au lieu de 0)
        Payment(
            id="PAY-15", amount=30_000.00, currency=Currency.EUR,
            date=date(2024, 10, 22),
            label_raw="REGLT FAC-2024-4O3",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C3 Typo dans reference (fuzzy)",
                       "attendu": "FAC-2024-403 (O vs 0)"},
        ),

        # ── PAY-15b : C3 -- Ref tronquee (medium) ─────────────────────
        # Ref tronquee en fin : "FAC-2024-4" au lieu de "FAC-2024-403"
        Payment(
            id="PAY-15b", amount=30_000.00, currency=Currency.EUR,
            date=date(2024, 10, 22),
            label_raw="PAYMENT FAC-2024-4",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C3 Ref tronquee (medium typo)",
                       "attendu": "FAC-2024-403 (truncate_end)"},
        ),

        # ── PAY-15c : C3 -- Prefixe change (medium) ──────────────────
        # "INV-2024-403" au lieu de "FAC-2024-403" (prefix swap)
        Payment(
            id="PAY-15c", amount=30_000.00, currency=Currency.EUR,
            date=date(2024, 10, 23),
            label_raw="REGLT INV-2024-403",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C3 Prefixe change FAC→INV",
                       "attendu": "FAC-2024-403 (prefix_swap)"},
        ),

        # ── PAY-15d : C3 -- Ref severement degradee (heavy) ──────────
        # "FAC/0002O24-4O3" : separateur change, zeros ajoutes, 0→O x2
        Payment(
            id="PAY-15d", amount=30_000.00, currency=Currency.EUR,
            date=date(2024, 10, 24),
            label_raw="VIRT FAC/0002O24-4O3",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C3 Ref heavy (3 mutations)",
                       "attendu": "FAC-2024-403 (sep+zeros+0→O)"},
        ),

        # ── PAY-16 : C2 -- Pattern temporel ────────────────────────────
        Payment(
            id="PAY-16", amount=20_000.00, currency=Currency.EUR,
            date=date(2024, 11, 5),
            label_raw="REGLEMENT FACTURES OCTOBRE 2024",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C2 Pattern temporel octobre",
                       "attendu": "FAC-2024-404 (20000, oct 2024)"},
        ),

        # ── PAY-17 : C2 -- RFA 3% ──────────────────────────────────────
        # Note: a ce stade, D4 a potentiellement INV-405 encore ouvert
        Payment(
            id="PAY-17", amount=53_350.00, currency=Currency.EUR,
            date=date(2024, 10, 25),
            label_raw="REGLT FAC-2024-405 DEDUCTION RFA 3%",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C2 RFA 3%",
                       "attendu": "FAC-2024-405 (55000 x 0.97)"},
        ),

        # ── PAY-19 : C1 -- Paiement par ref directe restante ──────────
        # A ce stade tout est matche sauf potentiellement rien.
        # On fait un paiement qui ne matche rien -> C6
        Payment(
            id="PAY-19", amount=99_999.99, currency=Currency.EUR,
            date=date(2024, 11, 1),
            label_raw="VIREMENT GLOBAL REF INTERNE 77X",
            iban_source="FR7610011000201234567890188",
            metadata={"scenario": "C6 Montant sans correspondance",
                       "attendu": "Aucun match -> revue humaine"},
        ),

        # ── PAY-20 : C6 -- Libelle cryptique ──────────────────────────
        Payment(
            id="PAY-20", amount=4_242.42, currency=Currency.EUR,
            date=date(2024, 10, 30),
            label_raw="XJ7 TRANSAC 9912",
            iban_source="FR7630001007941234567890185",
            metadata={"scenario": "C6 Libelle cryptique -> revue humaine",
                       "attendu": "Aucun match -> revue humaine"},
        ),
    ]


# ==========================================================================
#  4. AFFICHAGE
# ==========================================================================

LAYER_NAMES = {
    0: "C0 Preprocessing",
    1: "C1 Exact",
    2: "C2 Regles Metier",
    3: "C3 NLP/Fuzzy",
    4: "C4 ML",
    5: "C5 LLM",
    6: "C6 Revue Humaine",
}

LAYER_COLORS = {1: "\033[92m", 2: "\033[93m", 3: "\033[96m",
                4: "\033[95m", 5: "\033[94m", 6: "\033[91m"}
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"


def print_header():
    print(f"""
{BOLD}+======================================================================+
|     SIMULATION DE RECONCILIATION PAIEMENT-FACTURE PAR IA            |
|     Architecture 6 Couches -- 20 Scenarios Realistes                |
+======================================================================+{RESET}
""")


def print_payment_intro(pay: Payment, index: int, total: int):
    scenario = pay.metadata.get("scenario", "")
    attendu = pay.metadata.get("attendu", "")
    print(f"\n{BOLD}{'=' * 70}{RESET}")
    print(f"{BOLD}  [{index:02d}/{total}] Paiement {pay.id}{RESET}")
    print(f"  {DIM}Scenario: {scenario}{RESET}")
    print(f"  {DIM}Attendu:  {attendu}{RESET}")
    print(f"  Montant: {BOLD}{pay.amount:>12,.2f} {pay.currency.value}{RESET}")
    print(f"  Libelle: \"{pay.label_raw}\"" if pay.label_raw else f"  Libelle: {DIM}(vide){RESET}")
    print(f"  Date:    {pay.date}")


def print_result(ctx):
    match = ctx.final_match

    if match:
        layer = match.layer
        color = LAYER_COLORS.get(layer, "")
        layer_name = LAYER_NAMES.get(layer, f"C{layer}")

        print(f"\n  {color}{BOLD}>>> MATCH TROUVE -- {layer_name}{RESET}")
        print(f"    Methode:    {match.method.value}")
        print(f"    Regle:      {match.rule_id}")
        print(f"    Confiance:  {BOLD}{match.confidence:.0%}{RESET}")
        print(f"    Factures:   {', '.join(inv.reference for inv in match.invoices)}")

        if match.allocated:
            print(f"    Allocation:")
            for ref, amount in match.allocated.items():
                print(f"      -> {ref}: {amount:>12,.2f} EUR")

        if match.flags:
            print(f"    Flags:      {', '.join(match.flags)}")
        if match.credit_notes_applied:
            print(f"    Avoirs:     {', '.join(cn.reference for cn in match.credit_notes_applied)}")

        print(f"    Temps:      {match.processing_time_ms:.1f}ms")
    else:
        print(f"\n  {LAYER_COLORS[6]}{BOLD}>>> AUCUN MATCH AUTOMATIQUE{RESET}")
        print(f"    -> Envoye en file de revue humaine (C6)")

    layers_str = " -> ".join(LAYER_NAMES.get(l, f"C{l}") for l in ctx.layers_attempted)
    print(f"    Pipeline:   {DIM}{layers_str}{RESET}")


def print_summary(orch: ReconciliationOrchestrator, total: int):
    m = orch.metrics

    print(f"""
{BOLD}+======================================================================+
|                        BILAN DE LA SIMULATION                       |
+======================================================================+{RESET}

  Paiements traites:    {BOLD}{m.total_payments}{RESET}
  Matches automatiques: {BOLD}\033[92m{m.matched_auto}{RESET}  ({m.auto_rate:.0%})
  En revue humaine:     {BOLD}\033[91m{m.unmatched}{RESET}
  Erreurs:              {m.errors}

{BOLD}  Distribution par couche:{RESET}""")

    for layer in range(1, 7):
        count = m.by_layer.get(layer, 0)
        bar_full = "=" * (count * 2)
        bar_empty = "-" * ((total - count) * 2)
        pct = count / total * 100 if total > 0 else 0
        color = LAYER_COLORS.get(layer, "")
        name = LAYER_NAMES.get(layer, f"C{layer}")
        print(f"    {color}{name:20s}  [{bar_full}{bar_empty}]  {count:2d} ({pct:4.1f}%){RESET}")

    print(f"""
{BOLD}  Distribution par methode:{RESET}""")
    for method, count in sorted(m.by_method.items(), key=lambda x: -x[1]):
        print(f"    {method:40s}  {count}")

    print(f"""
  Temps moyen:          {m.avg_processing_time_ms:.2f} ms/paiement
  File revue humaine:   {orch.review_queue.queue_size} en attente
""")


# ==========================================================================
#  5. EXECUTION
# ==========================================================================

def main():
    print_header()

    invoices = create_invoices()
    debtors = create_debtors()
    payments = create_payments()

    iban_map = {d.iban: d.id for d in debtors if d.iban}

    print(f"  {BOLD}Portefeuille:{RESET} {len(invoices)} factures ouvertes")
    print(f"  {BOLD}Debiteurs:{RESET}    {len(debtors)}")
    print(f"  {BOLD}Paiements:{RESET}    {len(payments)} a traiter")
    print(f"  Total factures:  {sum(i.amount for i in invoices):>12,.2f} EUR")
    print(f"  Total paiements: {sum(p.amount for p in payments):>12,.2f} EUR")

    # Setup
    config = ReconciliationConfig()
    orch = ReconciliationOrchestrator(config)
    orch.setup(invoices, debtors, iban_map)

    # Traitement sequentiel (pedagogique)
    open_invoices = list(invoices)

    for i, payment in enumerate(payments, 1):
        print_payment_intro(payment, i, len(payments))

        ctx = orch.process_payment(payment, open_invoices)
        print_result(ctx)

        # Retirer les factures matchees
        if ctx.final_match:
            matched_ids = {inv.id for inv in ctx.final_match.invoices}
            open_invoices = [inv for inv in open_invoices if inv.id not in matched_ids]

    # Bilan
    print_summary(orch, len(payments))

    if open_invoices:
        print(f"  {BOLD}Factures encore ouvertes ({len(open_invoices)}):{RESET}")
        for inv in open_invoices:
            print(f"    {inv.reference}  {inv.amount:>12,.2f} EUR  Debiteur {inv.debtor_id}")
    else:
        print(f"  {BOLD}\033[92mToutes les factures ont ete reconciliees !{RESET}")


if __name__ == "__main__":
    main()
