#!/usr/bin/env python3
"""
=============================================================================
STRESS TEST — Réconciliation Paiement-Facture à Grande Échelle
=============================================================================
20 débiteurs | ~2000 factures | ~1500+ paiements | 12 mois (Jan-Déc 2024)

Simule un portefeuille de factoring réaliste sur une année complète.
Volume 5x supérieur à la démo standard pour tester la robustesse.

Usage :
    python -m examples.demo_stress_test
    python examples/demo_stress_test.py
    python examples/demo_stress_test.py --debtors 30 --months 24
=============================================================================
"""

from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.models import (
    CreditNote, Currency, Debtor, Invoice, ISO20022Fields,
    LabelClass, MatchMethod, Payment, PaymentSignals,
)
from reconciliation.config import ReconciliationConfig
from reconciliation.orchestrator import ReconciliationOrchestrator

# ── Logging silencieux ──
logging.getLogger("reconciliation").setLevel(logging.CRITICAL)

# ============================================================
# CONSTANTES
# ============================================================

SEASONAL_FACTORS = {
    1: 0.9, 2: 0.85, 3: 1.0, 4: 1.0, 5: 0.95, 6: 0.9,
    7: 0.8, 8: 0.5, 9: 1.0, 10: 1.1, 11: 1.3, 12: 1.5,
}

MONTH_NAMES_FR = {
    1: "JANVIER", 2: "FEVRIER", 3: "MARS", 4: "AVRIL",
    5: "MAI", 6: "JUIN", 7: "JUILLET", 8: "AOUT",
    9: "SEPTEMBRE", 10: "OCTOBRE", 11: "NOVEMBRE", 12: "DECEMBRE",
}

TVA_RATES = {
    "FR": 0.20, "DE": 0.19, "IT": 0.22, "ES": 0.21, "SE": 0.25,
    "PL": 0.23, "GB": 0.20, "MA": 0.20, "TN": 0.19, "BE": 0.21,
    "NL": 0.21, "PT": 0.23, "CH": 0.077, "US": 0.0, "BR": 0.17,
    "DZ": 0.19, "TR": 0.18, "RO": 0.19, "CZ": 0.21, "HU": 0.27,
}

SECTORS = [
    "ALIMENTAIRE", "BTP", "IMPORT", "DISTRIBUTION", "TRANSPORT",
    "PHARMA", "AUTO", "IT_SERVICES", "TEXTILE", "ENERGIE",
    "CHIMIE", "METALLURGIE", "LOGISTIQUE", "LUXE", "AGRI",
]

AMOUNT_RANGES = {
    "ALIMENTAIRE":  (800, 18_000),
    "BTP":          (8_000, 120_000),
    "IMPORT":       (3_000, 50_000),
    "DISTRIBUTION": (5_000, 150_000),
    "TRANSPORT":    (2_000, 35_000),
    "PHARMA":       (4_000, 70_000),
    "AUTO":         (1_500, 40_000),
    "IT_SERVICES":  (3_000, 80_000),
    "TEXTILE":      (2_000, 25_000),
    "ENERGIE":      (10_000, 200_000),
    "CHIMIE":       (5_000, 60_000),
    "METALLURGIE":  (8_000, 90_000),
    "LOGISTIQUE":   (1_500, 20_000),
    "LUXE":         (10_000, 250_000),
    "AGRI":         (2_000, 30_000),
}

COUNTRIES_SEPA = ["FR", "DE", "IT", "ES", "BE", "NL", "PT", "SE", "PL", "CZ", "HU", "RO", "AT", "FI", "DK", "IE", "LU", "SK", "SI", "LT", "LV", "EE", "HR", "BG", "GR", "CY", "MT"]
COUNTRIES_NON_SEPA = ["MA", "TN", "TR", "US", "BR", "CH", "GB", "DZ", "EG", "SN", "CI", "CM", "IN", "CN", "JP", "KR", "AE", "SA", "MX", "CO", "CL", "AU", "ZA", "NG", "IL"]

# ---------------------------------------------------------------------------
# Libellés cryptiques / ambigus par langue — vrais verbatims bancaires
# ---------------------------------------------------------------------------
CRYPTIC_TEMPLATES = [
    # FR — trésorerie, comptabilité interne
    "XJ7 TRANSAC {n}", "REF INT {n}", "OP {n} VIR",
    "TRESORERIE MVMT {n}", "{n}", "BANQUE OP{n}",
    "TX{n}ZZ", "CASH MGMT {n}", "VIRT {n}",
    "PROV REGUL {n}", "MOUVEMENT DIVERS",
    "VIREMENT COMMERCIAL", "OPERATION TRESORERIE",
    "CREDIT COMPTE", "REMISE CHEQUES", "ENCAISSEMENT DIVERS",
    "REGUL COMPTA {n}", "ORD PERM {n}", "PRELEVEMENT {n}",
    "VERSEMENT {n}", "COMPENSATION {n}", "CLEARING {n}",
    "CENTRALISATION TRESORERIE", "NIVELLEMENT INTER-SOCIETES",
    "RAPATRIEMENT FONDS {n}", "DOTATION COMPTE {n}",
    "MOUVEMENT INTERNE REF {n}", "REGULARISATION ECART",
    # EN — treasury, corporate
    "TREASURY TRANSFER {n}", "INTERCO PAYMENT {n}",
    "WIRE TRANSFER {n}", "ACH PAYMENT {n}",
    "CORPORATE SWEEP {n}", "CASH CONCENTRATION {n}",
    "BALANCE TRANSFER", "NOSTRO CREDIT {n}",
    "FX SETTLEMENT {n}", "TRADE PAYMENT {n}",
    "SUPPLIER PMT {n}", "PAYROLL SWEEP {n}",
    "BANK CHARGES REVERSAL", "CREDIT ADJUSTMENT {n}",
    "MISC CREDIT {n}", "RETURN ITEM {n}",
    "CHAPS PAYMENT {n}", "FASTER PAYMENT {n}",
    "BACS CREDIT {n}", "SWIFT TRANSFER {n}",
    # DE — Zahlungsverkehr
    "SAMMELÜBERWEISUNG {n}", "DAUERAUFTRAG {n}",
    "GUTSCHRIFT {n}", "ZAHLUNGSEINGANG {n}",
    "ÜBERWEISUNG INLAND {n}", "KONTOAUSGLEICH {n}",
    "VERRECHNUNGSKONTO {n}", "KONZERNCLEARING {n}",
    "INTERNE UMBUCHUNG {n}", "RECHNUNGSAUSGLEICH",
    "ZAHLUNG DIVERSE", "BANKEINZUG {n}",
    # NL — betalingsverkeer
    "BETALING ONTVANGEN {n}", "OVERBOEKING {n}",
    "INCASSO {n}", "SPOEDBETALING {n}",
    "SALARISBETALING {n}", "INTERNE BOEKING {n}",
    "CREDITERING {n}", "VERREKENING FACTUREN",
    # ES — pagos
    "TRANSFERENCIA RECIBIDA {n}", "PAGO PROVEEDOR {n}",
    "ABONO EN CUENTA {n}", "LIQUIDACION {n}",
    "COBRO FACTURA", "INGRESO CHEQUE {n}",
    "TRASPASO INTERNO {n}", "COMPENSACION {n}",
    "RECIBO DOMICILIADO {n}", "GIRO COMERCIAL {n}",
    # IT — pagamenti
    "BONIFICO RICEVUTO {n}", "PAGAMENTO FORNITORE {n}",
    "ACCREDITO {n}", "INCASSO EFFETTI {n}",
    "GIROCONTO INTERNO {n}", "VERSAMENTO {n}",
    "COMPENSAZIONE {n}", "ADDEBITO DIRETTO {n}",
    # PT — pagamentos
    "TRANSFERÊNCIA RECEBIDA {n}", "PAGAMENTO FORNECEDOR {n}",
    "CRÉDITO EM CONTA {n}", "LIQUIDAÇÃO {n}",
    # AR (Maghreb) — paiements
    "TAHWIL {n}", "DAFA {n}",
    "HAW BANK {n}", "PAYMENT ORDER {n} SWIFT",
    "MUQASSA {n}", "CREDIT TRANSFER OUR {n}",
    # TR — ödeme
    "HAVALE GELEN {n}", "EFT ALINDI {n}",
    "ODEME {n}", "TAHSILAT {n}",
    "VIRMAN {n}", "FATURA ODEMESI {n}",
    # PL/CZ/HU — CEE
    "PRZELEW PRZYCHODZACY {n}", "PLATBA PRIJATA {n}",
    "ÁTUTALÁS {n}", "WPŁATA {n}",
    "INKASO {n}", "ELSZÁMOLÁS {n}",
    # JP/CN/KR — Asie
    "送金受領 {n}", "收到汇款 {n}",
    "입금확인 {n}", "TELEGRAPHIC TRANSFER {n}",
    "REMITTANCE ADVICE {n}", "T/T RECEIVED {n}",
    # Divers — codes internes bancaires
    "MSG{n}PROC", "CLR{n}NET", "SETL{n}FIN",
    "REF//{n}//CRED", "NONREF", "/BNF/{n}",
    "NTRF {n}", "RNCN{n}", "BENM//NAME NOT PROVIDED",
]

WHT_RATES = {
    "MA": 0.20, "TN": 0.15, "TR": 0.18, "BR": 0.15, "DZ": 0.24,
    "EG": 0.20, "IN": 0.10, "SN": 0.20, "CI": 0.20, "CM": 0.15,
    "SA": 0.05, "AE": 0.0, "NG": 0.10, "ZA": 0.15, "IL": 0.25,
    "MX": 0.10, "CO": 0.10, "CL": 0.15,
}

# Scénarios et leurs poids typiques par "archétype" de débiteur
ARCHETYPES = {
    "exemplaire": {
        "C1_EXACT_REF": 0.75, "C1_IBAN_AMOUNT": 0.10, "C2_ROUNDING": 0.05,
        "C1_FULL_BALANCE": 0.05, "C6_CRYPTIC": 0.05,
    },
    "iso20022": {
        "C1_ISO20022": 0.55, "C1_EXACT_REF": 0.15, "C2_HT_ERROR": 0.10,
        "C2_ROUNDING": 0.05, "C3_FUZZY": 0.05, "C6_CRYPTIC": 0.10,
    },
    "btp_retention": {
        "C2_RETENTION": 0.45, "C1_EXACT_REF": 0.10, "C2_SUBSET_SUM": 0.15,
        "C2_INSTALLMENT": 0.10, "C2_ROUNDING": 0.05, "C6_CRYPTIC": 0.15,
    },
    "distribution": {
        "C2_DISCOUNT": 0.25, "C2_RFA": 0.10, "C2_CREDIT_NOTE": 0.15,
        "C2_SUBSET_SUM": 0.15, "C1_EXACT_REF": 0.10, "C1_FULL_BALANCE": 0.05,
        "C2_ROUNDING": 0.05, "C6_CRYPTIC": 0.15,
    },
    "international_fees": {
        "C2_SWIFT_FEES": 0.35, "C2_WHT": 0.20, "C1_EXACT_REF": 0.15,
        "C2_ROUNDING": 0.05, "C6_CRYPTIC": 0.25,
    },
    "multi_facture": {
        "C2_SUBSET_SUM": 0.40, "C1_EXACT_REF": 0.10, "C1_IBAN_AMOUNT": 0.10,
        "C3_FUZZY": 0.10, "C6_CRYPTIC": 0.30,
    },
    "po_bl": {
        "C1_PO_MATCH": 0.45, "C1_BL_MATCH": 0.15, "C1_EXACT_REF": 0.15,
        "C2_ROUNDING": 0.10, "C3_FUZZY": 0.05, "C6_CRYPTIC": 0.10,
    },
    "installments": {
        "C2_INSTALLMENT": 0.45, "C1_EXACT_REF": 0.20, "C2_ROUNDING": 0.10,
        "C3_FUZZY": 0.05, "C6_CRYPTIC": 0.20,
    },
    "fuzzy_typos": {
        "C3_FUZZY": 0.45, "C1_EXACT_REF": 0.15, "C2_ROUNDING": 0.10,
        "C2_SUBSET_SUM": 0.10, "C6_CRYPTIC": 0.20,
    },
    "temporel": {
        "C2_TEMPORAL": 0.35, "C1_EXACT_REF": 0.15, "C2_SUBSET_SUM": 0.15,
        "C1_FULL_BALANCE": 0.10, "C2_ROUNDING": 0.10, "C6_CRYPTIC": 0.15,
    },
    # Nouveaux archétypes pour plus de diversité
    "chaotique": {
        "C6_CRYPTIC": 0.50, "C3_FUZZY": 0.20, "C1_EXACT_REF": 0.10,
        "C2_ROUNDING": 0.10, "C2_SUBSET_SUM": 0.10,
    },
    "grand_compte": {
        "C1_ISO20022": 0.30, "C2_DISCOUNT": 0.15, "C2_CREDIT_NOTE": 0.10,
        "C2_SUBSET_SUM": 0.20, "C1_FULL_BALANCE": 0.10,
        "C2_RFA": 0.05, "C6_CRYPTIC": 0.10,
    },
    "pme_rigoureux": {
        "C1_EXACT_REF": 0.65, "C2_ROUNDING": 0.10, "C1_IBAN_AMOUNT": 0.10,
        "C6_CRYPTIC": 0.05, "C3_FUZZY": 0.10,
    },
    "africain_mix": {
        "C2_SWIFT_FEES": 0.25, "C2_WHT": 0.20, "C6_CRYPTIC": 0.25,
        "C1_EXACT_REF": 0.15, "C2_ROUNDING": 0.05, "C3_FUZZY": 0.10,
    },
    "asiatique": {
        "C1_EXACT_REF": 0.20, "C2_SWIFT_FEES": 0.20, "C6_CRYPTIC": 0.30,
        "C1_ISO20022": 0.10, "C3_FUZZY": 0.10, "C2_ROUNDING": 0.10,
    },
    "americain": {
        "C1_EXACT_REF": 0.30, "C2_SWIFT_FEES": 0.15, "C1_IBAN_AMOUNT": 0.15,
        "C2_INSTALLMENT": 0.10, "C6_CRYPTIC": 0.20, "C2_ROUNDING": 0.10,
    },
    "scandinave": {
        "C1_ISO20022": 0.40, "C1_EXACT_REF": 0.25, "C2_ROUNDING": 0.10,
        "C2_SUBSET_SUM": 0.10, "C6_CRYPTIC": 0.15,
    },
}


# ============================================================
# 1. GÉNÉRATION PROCÉDURALE DE DÉBITEURS
# ============================================================

@dataclass
class DebtorProfile:
    debtor: Debtor
    invoices_per_month: int
    amount_range: tuple[float, float]
    scenario_weights: dict[str, float]
    payment_day: int | None = None
    avg_delay_days: float = 5.0
    has_po: bool = False
    has_bl: bool = False


COMPANY_NAMES = {
    "FR": [
        "Boulangerie Dupont", "Construction Martin", "Groupe Leclerc", "Transport Duval",
        "Pharma Santé", "Énergie Verte", "Chimie Rhône", "Métaux Loire",
        "Logistique Express", "Luxe Parisien", "Agri Beauce", "Industries Normandie",
        "Services Île-de-France", "Tech Lyon", "Distribution Sud", "BTP Atlantique",
        "Alimentaire Provence", "Plastiques Grenoble", "Carrelages Méditerranée",
        "Vins Bourgogne", "Mobilier Scandinave", "Cablâge Alsace", "Fromageries du Jura",
        "Imprimerie Toulouse", "Emballages Loire-Atlantique", "Charcuterie Auvergne",
        "Menuiserie Bretagne", "Pièces Auto Strasbourg", "Laiteries du Nord",
        "Béton Armé Normandie", "Conserveries Nantaises", "Robinetterie Rhône-Alpes",
    ],
    "DE": [
        "Schmidt Import", "Bayern Industrie", "Hamburg Logistics", "Berlin Tech",
        "Frankfurter Maschinenbau", "Dresden Elektronik", "Nürnberger Werkzeuge",
        "Stuttgarter Chemie", "Kölner Verpackung", "Hannover Stahl", "Düsseldorf Textil",
        "München Lebensmittel", "Leipzig Kunststoff", "Bremerhaven Shipping",
    ],
    "IT": [
        "Rossi Transport", "Milano Fashion", "Roma Alimentari", "Napoli Conserve",
        "Torino Meccanica", "Firenze Pelletteria", "Bologna Packaging",
        "Verona Marmi", "Padova Farmaceutica", "Genova Shipping", "Bergamo Tessuti",
    ],
    "ES": [
        "Iberia Foods", "Barcelona Auto", "Madrid Distribución", "Valencia Cerámica",
        "Sevilla Aceites", "Bilbao Aceros", "Zaragoza Textil", "Málaga Frutas",
        "Alicante Calzados", "Murcia Conservas", "Vigo Pesca", "Cádiz Naviera",
    ],
    "BE": ["Bruxelles Commerce", "Flandres Textiles", "Anvers Diamant", "Liège Sidérurgie",
           "Gand Chimie", "Charleroi Métallurgie", "Bruges Chocolaterie"],
    "NL": ["Amsterdam Trading", "Rotterdam Shipping", "Eindhoven Tech", "Utrecht Pharma",
           "Den Haag Consulting", "Groningen Agri", "Maastricht Céramiques"],
    "SE": ["Nordic Pharma", "Stockholm Electronics", "Göteborg Volvo Parts",
           "Malmö Biotech", "Uppsala Instruments", "Linköping Aero"],
    "PL": ["Warszawa AutoParts", "Kraków Steel", "Gdańsk Shipyard", "Wrocław Electronics",
           "Łódź Textiles", "Poznań Food Processing", "Katowice Mining Equipment"],
    "GB": ["London Tech Solutions", "Manchester Industries", "Birmingham Steel",
           "Liverpool Shipping", "Edinburgh Pharma", "Bristol Aerospace",
           "Leeds Packaging", "Glasgow Engineering", "Cardiff Energy"],
    "MA": ["Maroc Export", "Casablanca Trading", "Tanger Med Logistics", "Rabat Textiles",
           "Fès Artisanat", "Marrakech Agri-Business", "Agadir Conserveries"],
    "TN": ["Tunisie Textiles", "Tunis Commerce", "Sfax Industries", "Sousse Huileries",
           "Bizerte Électronique", "Gabès Chimie"],
    "TR": ["Istanbul Import", "Ankara Metals", "Izmir Tekstil", "Bursa Otomotiv",
           "Antalya Gıda", "Gaziantep Makine", "Konya Tarım"],
    "CH": ["Zürich Precision", "Geneva Trading", "Basel Pharma", "Bern Instruments",
           "Lausanne Horlogerie", "Winterthur Engineering"],
    "US": ["New York Imports", "Chicago Distribution", "Houston Energy", "Detroit Auto Parts",
           "Los Angeles Tech", "Miami Trade", "Seattle Aerospace", "Atlanta Logistics",
           "Boston Biotech", "San Francisco Digital", "Dallas Manufacturing"],
    "PT": ["Lisboa Logistics", "Porto Wine Export", "Braga Textiles", "Faro Conservas"],
    "RO": ["Bucharest Manufacturing", "Cluj Engineering", "Timișoara Auto", "Iași Pharma"],
    "CZ": ["Praha Engineering", "Brno Machinery", "Ostrava Steel", "Plzeň Brewing Equipment"],
    "HU": ["Budapest Chemicals", "Debrecen Pharma", "Szeged Agri", "Győr Auto"],
    "AT": ["Wien Maschinenbau", "Graz Elektronik", "Linz Stahl", "Salzburg Tourismus"],
    "FI": ["Helsinki Electronics", "Tampere Machinery", "Turku Shipbuilding"],
    "DK": ["København Pharma", "Aarhus Wind Energy", "Odense Robotics"],
    "IE": ["Dublin Tech", "Cork Pharma", "Galway Biomedical"],
    "BR": ["São Paulo Trading", "Rio Agronegócio", "Belo Horizonte Mining",
           "Curitiba Auto Peças", "Porto Alegre Calçados"],
    "DZ": ["Alger Import", "Oran Industries", "Constantine Commerce"],
    "EG": ["Cairo Trading", "Alexandria Textiles", "Suez Shipping"],
    "SN": ["Dakar Commerce", "Saint-Louis Pêche"],
    "CI": ["Abidjan Trading", "San Pedro Cacao Export"],
    "CM": ["Douala Export", "Yaoundé Industries"],
    "IN": ["Mumbai Textiles", "Delhi Auto Parts", "Bangalore Tech", "Chennai Manufacturing"],
    "CN": ["Shanghai Trading", "Shenzhen Electronics", "Guangzhou Manufacturing",
           "Beijing Import-Export", "Hangzhou Digital"],
    "JP": ["Tokyo Electronics", "Osaka Manufacturing", "Nagoya Auto Parts"],
    "KR": ["Seoul Electronics", "Busan Shipping", "Incheon Trading"],
    "AE": ["Dubai Trading", "Abu Dhabi Energy", "Sharjah Industries"],
    "SA": ["Riyadh Trading", "Jeddah Import", "Dammam Petrochemicals"],
    "MX": ["Ciudad de México Trading", "Monterrey Industries", "Guadalajara Electronics"],
    "CO": ["Bogotá Trading", "Medellín Textiles"],
    "CL": ["Santiago Mining", "Valparaíso Trading"],
    "AU": ["Sydney Trading", "Melbourne Manufacturing", "Perth Mining"],
    "ZA": ["Johannesburg Mining", "Cape Town Trading", "Durban Shipping"],
    "NG": ["Lagos Trading", "Abuja Industries"],
    "IL": ["Tel Aviv Tech", "Haifa Chemicals"],
    "LU": ["Luxembourg Finance", "Esch-sur-Alzette Steel"],
    "SK": ["Bratislava Auto", "Košice Steel"],
    "SI": ["Ljubljana Pharma", "Maribor Manufacturing"],
    "LT": ["Vilnius Tech", "Kaunas Manufacturing"],
    "LV": ["Riga Trading", "Liepāja Shipping"],
    "EE": ["Tallinn Digital", "Tartu Biotech"],
    "HR": ["Zagreb Industries", "Split Shipping"],
    "BG": ["Sofia Manufacturing", "Plovdiv Textiles"],
    "GR": ["Athens Shipping", "Thessaloniki Trading"],
    "CY": ["Nicosia Trading", "Limassol Shipping"],
    "MT": ["Valletta Trading", "Malta Pharma"],
}

LEGAL_SUFFIXES = {
    "FR": ["SARL", "SA", "SAS", "EURL", "SCI", "SNC"],
    "DE": ["GmbH", "AG", "KG", "GmbH & Co. KG", "e.K."],
    "IT": ["Srl", "SpA", "Sas", "Snc"],
    "ES": ["SL", "SA", "SLU", "SAU"],
    "BE": ["SPRL", "SA", "SRL", "SC"],
    "NL": ["BV", "NV", "VOF"],
    "SE": ["AB", "HB"],
    "PL": ["Sp. z o.o.", "SA", "Sp.k."],
    "GB": ["Ltd", "PLC", "LLP"],
    "MA": ["SARL", "SA", "SNC"],
    "TN": ["SA", "SARL", "SUARL"],
    "TR": ["A.Ş.", "Ltd. Şti.", "Tic. A.Ş."],
    "CH": ["AG", "SA", "GmbH", "Sàrl"],
    "US": ["Inc", "LLC", "Corp", "LP"],
    "PT": ["Lda", "SA", "Unipessoal Lda"],
    "RO": ["SRL", "SA", "SCA"],
    "CZ": ["s.r.o.", "a.s.", "v.o.s."],
    "HU": ["Kft", "Zrt", "Bt"],
    "AT": ["GmbH", "AG", "KG"],
    "FI": ["Oy", "Oyj", "Ky"],
    "DK": ["A/S", "ApS", "I/S"],
    "IE": ["Ltd", "PLC", "DAC"],
    "BR": ["Ltda", "SA", "EIRELI"],
    "DZ": ["SARL", "SPA", "EURL"],
    "EG": ["SAE", "LLC"],
    "SN": ["SARL", "SA"],
    "CI": ["SARL", "SA"],
    "CM": ["SARL", "SA"],
    "IN": ["Pvt Ltd", "Ltd", "LLP"],
    "CN": ["Co., Ltd", "Trading Co."],
    "JP": ["K.K.", "Co., Ltd", "株式会社"],
    "KR": ["Co., Ltd", "Corp"],
    "AE": ["LLC", "FZ-LLC", "FZCO"],
    "SA": ["LLC", "Co."],
    "MX": ["SA de CV", "SAPI"],
    "CO": ["SAS", "SA", "Ltda"],
    "CL": ["SpA", "SA", "Ltda"],
    "AU": ["Pty Ltd", "Ltd"],
    "ZA": ["Pty Ltd", "Ltd"],
    "NG": ["Ltd", "PLC"],
    "IL": ["Ltd", "בע״מ"],
    "LU": ["SA", "Sàrl", "SCA"],
    "SK": ["s.r.o.", "a.s."],
    "SI": ["d.o.o.", "d.d."],
    "LT": ["UAB", "AB"],
    "LV": ["SIA", "AS"],
    "EE": ["OÜ", "AS"],
    "HR": ["d.o.o.", "d.d."],
    "BG": ["EOOD", "OOD", "AD"],
    "GR": ["ΕΠΕ", "ΑΕ", "ΙΚΕ"],
    "CY": ["Ltd", "PLC"],
    "MT": ["Ltd", "PLC"],
}


def generate_debtors(n: int, rng: random.Random) -> list[DebtorProfile]:
    """Génère N profils de débiteurs procéduralement."""
    profiles = []
    archetype_list = list(ARCHETYPES.keys())

    for i in range(n):
        did = f"D{i+1:03d}"

        # Choisir pays (70% SEPA, 30% non-SEPA)
        if rng.random() < 0.70:
            country = rng.choice(COUNTRIES_SEPA)
        else:
            country = rng.choice(COUNTRIES_NON_SEPA)

        # Nom de société
        names_pool = COMPANY_NAMES.get(country, COMPANY_NAMES["FR"])
        base_name = rng.choice(names_pool)
        suffix = rng.choice(LEGAL_SUFFIXES.get(country, ["SA"]))
        name = f"{base_name} {suffix}"

        # Secteur
        sector = rng.choice(SECTORS)
        amount_range = AMOUNT_RANGES.get(sector, (5_000, 50_000))

        # Archétype de comportement de paiement
        archetype = rng.choice(archetype_list)
        weights = dict(ARCHETYPES[archetype])

        # Paramètres financiers
        payment_terms = rng.choice([30, 30, 30, 45, 45, 60, 60, 90])
        discount_rate = rng.choice([0.0, 0.0, 0.0, 0.0, 0.01, 0.02, 0.03]) if archetype == "distribution" else 0.0
        retention_rate = rng.choice([0.03, 0.05, 0.10]) if archetype == "btp_retention" else 0.0
        rfa_rate = rng.choice([0.0, 0.0, 0.02, 0.03]) if archetype == "distribution" else 0.0

        # Volume de factures par mois (2-15)
        invoices_per_month = rng.randint(3, 15)

        # Comportement de paiement
        avg_delay = round(rng.gauss(8, 6), 1)
        avg_delay = max(0, min(avg_delay, 30))
        regularity = round(rng.uniform(0.4, 0.98), 2)
        risk = round(1.0 - regularity + rng.uniform(-0.1, 0.1), 2)
        risk = max(0.05, min(risk, 0.95))

        # Jour fixe de paiement (40% des débiteurs)
        payment_day = rng.choice([10, 15, 20, 25, 28]) if rng.random() < 0.40 else None

        has_po = archetype in ("po_bl", "btp_retention") or rng.random() < 0.15
        has_bl = archetype == "po_bl" or (sector == "TRANSPORT" and rng.random() < 0.5)

        # IBAN fictif
        iban = f"{country}{rng.randint(10,99)}{''.join(str(rng.randint(0,9)) for _ in range(20))}"

        debtor = Debtor(
            id=did, name=name, iban=iban,
            bic=f"BANK{country}XX", country=country,
            sector=sector, payment_terms=payment_terms,
            discount_rate=discount_rate, retention_rate=retention_rate,
            rfa_rate=rfa_rate, avg_payment_delay=avg_delay,
            payment_regularity_score=regularity, risk_score=risk,
            known_payment_patterns=[archetype],
            usual_invoice_counts_per_payment=rng.randint(1, 4),
        )

        profiles.append(DebtorProfile(
            debtor=debtor,
            invoices_per_month=invoices_per_month,
            amount_range=amount_range,
            scenario_weights=weights,
            payment_day=payment_day,
            avg_delay_days=avg_delay,
            has_po=has_po,
            has_bl=has_bl,
        ))

    return profiles


# ============================================================
# 2. GÉNÉRATION DES FACTURES
# ============================================================

def generate_invoices(
    profiles: list[DebtorProfile], months: list[int], year: int, rng: random.Random
) -> list[Invoice]:
    invoices: list[Invoice] = []
    seq = 0

    for month in months:
        factor = SEASONAL_FACTORS.get(month, 1.0)
        if month == 12:
            max_day = 31
        elif month in (4, 6, 9, 11):
            max_day = 30
        elif month == 2:
            max_day = 29 if year % 4 == 0 else 28
        else:
            max_day = 31

        # Calculer l'année réelle (si months > 12 pour simulations multi-années)
        actual_year = year + (month - 1) // 12
        actual_month = ((month - 1) % 12) + 1

        for profile in profiles:
            count = max(1, round(profile.invoices_per_month * factor))
            country = profile.debtor.country or "FR"
            tva = TVA_RATES.get(country, 0.20)
            lo, hi = profile.amount_range

            for _ in range(count):
                seq += 1
                did = profile.debtor.id
                did_num = int(did[1:])

                amount_ht = round(rng.uniform(lo, hi), 2)
                amount_ttc = round(amount_ht * (1 + tva), 2)

                day = rng.choice([1, 2, 3, 5, 7, 8, 10, 12, 14, 15, 17, 18, 20, 22, 24, 25, 27, 28])
                day = min(day, max_day)
                issue = date(actual_year, actual_month, day)
                due = issue + timedelta(days=profile.debtor.payment_terms)

                ref = f"FAC-{actual_year}-{did_num:03d}{seq:05d}"

                inv = Invoice(
                    id=f"INV-{seq:06d}",
                    reference=ref,
                    debtor_id=did,
                    amount=amount_ttc,
                    amount_ht=amount_ht,
                    currency=Currency.EUR,
                    issue_date=issue,
                    due_date=due,
                    batch_date=issue,
                    po_number=f"PO-{actual_year}-{rng.randint(10000,99999)}" if profile.has_po else None,
                    bl_number=f"BL-{actual_year}-{rng.randint(10000,99999)}" if profile.has_bl else None,
                )
                invoices.append(inv)

    invoices.sort(key=lambda i: i.issue_date)
    return invoices


# ============================================================
# 3. GÉNÉRATION DES AVOIRS
# ============================================================

def generate_credit_notes(
    profiles: list[DebtorProfile], invoices: list[Invoice], rng: random.Random
) -> list[CreditNote]:
    credits: list[CreditNote] = []
    seq = 0

    for profile in profiles:
        if profile.debtor.discount_rate > 0 or profile.debtor.rfa_rate > 0:
            debtor_invs = [i for i in invoices if i.debtor_id == profile.debtor.id]
            n = max(1, len(debtor_invs) // 6)
            for _ in range(n):
                seq += 1
                linked = rng.choice(debtor_invs)
                amount = round(rng.uniform(300, min(10000, linked.amount * 0.25)), 2)
                credits.append(CreditNote(
                    id=f"CN-{seq:04d}",
                    reference=f"AV-2024-{seq:04d}",
                    debtor_id=profile.debtor.id,
                    amount=amount,
                    issue_date=linked.issue_date + timedelta(days=rng.randint(5, 25)),
                    linked_invoice_ref=linked.reference,
                ))
    return credits


# ============================================================
# 4. GÉNÉRATION DES PAIEMENTS
# ============================================================

def introduce_typo(ref: str, rng: random.Random) -> str:
    chars = list(ref)
    if len(chars) < 4:
        return ref
    op = rng.choice(["swap", "drop", "replace_0_O", "extra_digit", "wrong_digit"])
    if op == "swap" and len(chars) > 5:
        i = rng.randint(2, len(chars) - 2)
        chars[i], chars[i+1] = chars[i+1], chars[i]
    elif op == "drop":
        chars.pop(rng.randint(2, len(chars)-1))
    elif op == "replace_0_O":
        for i, c in enumerate(chars):
            if c == "0": chars[i] = "O"; break
    elif op == "extra_digit":
        chars.insert(rng.randint(2, len(chars)-1), str(rng.randint(0,9)))
    elif op == "wrong_digit":
        digs = [i for i,c in enumerate(chars) if c.isdigit()]
        if digs:
            i = rng.choice(digs)
            chars[i] = str((int(chars[i]) + rng.randint(1,3)) % 10)
    return "".join(chars)


def make_payment_date(due: date, delay: float, pay_day: int | None, rng: random.Random) -> date:
    base = due + timedelta(days=int(delay + rng.gauss(0, 3)))
    if pay_day:
        m, y = base.month, base.year
        if base.day > pay_day:
            m += 1
            if m > 12: m, y = 1, y + 1
        try:
            base = date(y, m, min(pay_day, 28))
        except ValueError:
            pass
    while base.weekday() >= 5:
        base += timedelta(days=1)
    return max(base, date(2024, 1, 15))


def _pick(weights: dict[str, float], rng: random.Random) -> str:
    items = list(weights.keys())
    probs = list(weights.values())
    return rng.choices(items, weights=probs, k=1)[0]


# Libellés de paiement localisés par langue du pays d'origine
LABEL_PREFIXES_BY_LANG = {
    "FR": [
        "REGLT", "REGLEMENT", "PAIEMENT", "VIRT", "VIREMENT", "RGT", "PMT",
        "VIR SEPA", "REGL FACTURE", "PAIEMENT FACTURE", "VIREMENT REF",
        "REGLEMENT VOTRE FACTURE", "SOLDE FACTURE", "REGL ECHEANCE",
        "PAIEMENT ECHEANCE", "VIR REGL", "RGT FACTURE", "VIRT SEPA REF",
        "VIR SCT", "PAIEMENT FOURNISSEUR", "REGLEMENT FOURNISSEUR",
    ],
    "EN": [
        "PAYMENT", "PMT", "PAYMENT FOR INV", "SETTLEMENT", "WIRE TRANSFER",
        "BANK TRANSFER", "PAYMENT OF INVOICE", "PMT REF", "REMITTANCE",
        "PAYMENT AS PER INVOICE", "SETTLEMENT OF INVOICE", "TRF",
        "CREDIT TRANSFER", "PYMT", "PAY", "PAYMENT FOR", "FUNDS TRANSFER",
        "SUPPLIER PAYMENT", "VENDOR PAYMENT", "TRADE SETTLEMENT",
    ],
    "DE": [
        "ZAHLUNG", "ÜBERWEISUNG", "BEZAHLUNG RECHNUNG", "RECHNUNGSBEGLEICHUNG",
        "ZAHLUNGSANWEISUNG", "GUTSCHRIFT", "BEGLEICHUNG", "AUSGLEICH RECHNUNG",
        "ZAHLUNGSAUSGLEICH", "BANKÜBERWEISUNG", "SEPA-ÜBERWEISUNG",
    ],
    "NL": [
        "BETALING", "OVERBOEKING", "BETALING FACTUUR", "VOLDOENING",
        "BANKOVERSCHRIJVING", "CREDITOVERSCHRIJVING", "BETALING REF",
        "FACTUUR VOLDAAN", "SEPA OVERBOEKING",
    ],
    "ES": [
        "PAGO", "TRANSFERENCIA", "PAGO FACTURA", "ABONO", "LIQUIDACIÓN",
        "PAGO A PROVEEDOR", "TRANSFERENCIA REF", "GIRO BANCARIO",
        "PAGO SEGÚN FACTURA", "ABONO EN CUENTA",
    ],
    "IT": [
        "PAGAMENTO", "BONIFICO", "PAGAMENTO FATTURA", "SALDO FATTURA",
        "BONIFICO BANCARIO", "PAGAMENTO RIF", "VERSAMENTO",
        "ACCREDITO", "BONIFICO SEPA", "REGOLAMENTO FATTURA",
    ],
    "PT": [
        "PAGAMENTO", "TRANSFERÊNCIA", "PAGAMENTO FATURA", "LIQUIDAÇÃO",
        "TRANSFERÊNCIA BANCÁRIA", "PAGAMENTO REF", "CRÉDITO",
    ],
    "TR": [
        "ÖDEME", "HAVALE", "FATURA ÖDEMESI", "BANKA HAVALESI",
        "EFT ÖDEMESİ", "ÖDEME REF", "VİRMAN",
    ],
    "PL": [
        "PŁATNOŚĆ", "PRZELEW", "ZAPŁATA FAKTURY", "PRZELEW BANKOWY",
        "WPŁATA", "PRZELEW ZA FAKTURĘ", "PŁATNOŚĆ REF",
    ],
    "AR": [
        "TAHWIL", "DAFA", "TASDID FATOURA", "HAW BANK", "SADDAD",
    ],
    "ZH": [
        "付款", "汇款", "转账", "支付货款", "电汇",
    ],
    "JA": [
        "お支払い", "振込", "送金", "代金支払",
    ],
    "KO": [
        "결제", "송금", "대금지급", "이체",
    ],
}

# Pays → langue principale pour les labels
COUNTRY_LANG = {
    "FR": "FR", "BE": "FR", "LU": "FR", "MC": "FR", "SN": "FR", "CI": "FR",
    "CM": "FR", "DZ": "AR", "TN": "AR", "MA": "AR", "EG": "AR",
    "DE": "DE", "AT": "DE", "CH": "DE",
    "NL": "NL",
    "ES": "ES", "MX": "ES", "CO": "ES", "CL": "ES",
    "IT": "IT",
    "PT": "PT", "BR": "PT",
    "TR": "TR",
    "PL": "PL", "CZ": "PL", "SK": "PL",
    "HU": "EN", "RO": "EN", "BG": "EN", "HR": "EN", "SI": "EN",
    "SE": "EN", "DK": "EN", "FI": "EN", "NO": "EN",
    "GB": "EN", "IE": "EN", "US": "EN", "AU": "EN", "ZA": "EN", "NG": "EN",
    "IN": "EN", "AE": "EN", "SA": "AR", "IL": "EN",
    "CN": "ZH", "JP": "JA", "KR": "KO",
    "GR": "EN", "CY": "EN", "MT": "EN",
    "LT": "EN", "LV": "EN", "EE": "EN",
}


def _ref_label(ref: str, rng: random.Random, country: str = "FR") -> str:
    """Génère un libellé de paiement localisé selon le pays du débiteur."""
    lang = COUNTRY_LANG.get(country, "EN")
    prefixes = LABEL_PREFIXES_BY_LANG.get(lang, LABEL_PREFIXES_BY_LANG["EN"])
    pre = rng.choice(prefixes)
    # Parfois le libellé ajoute du bruit bancaire
    if rng.random() < 0.15:
        noise = rng.choice([
            "/RFB/", "/ROC/", "E2E/", "NOTPROVIDED/", "/BENM/", "//",
            f"/{rng.randint(100000,999999)}/", f"CRED/{rng.randint(1000,9999)}",
        ])
        return f"{noise}{pre} {ref}"
    return f"{pre} {ref}"


def _mkpay(pid, amt, dt, prof, label, refs):
    return Payment(
        id=pid, amount=round(amt, 2), currency=Currency.EUR, date=dt,
        label_raw=label, label_normalized=label.upper(),
        iban_source=prof.debtor.iban or "", bic_source=prof.debtor.bic or "",
        debtor_id=prof.debtor.id, debtor=prof.debtor,
        signals=PaymentSignals(raw_refs=[r.replace("-","").upper() for r in refs] if refs else []),
    )


def generate_payments(
    profiles: list[DebtorProfile], invoices: list[Invoice],
    credit_notes: list[CreditNote], rng: random.Random,
) -> list[Payment]:
    payments: list[Payment] = []
    pay_seq = 0
    consumed: set[str] = set()
    cn_used: set[str] = set()

    inv_by_debtor: dict[str, list[Invoice]] = defaultdict(list)
    for inv in invoices:
        inv_by_debtor[inv.debtor_id].append(inv)
    cn_by_debtor: dict[str, list[CreditNote]] = defaultdict(list)
    for cn in credit_notes:
        cn_by_debtor[cn.debtor_id].append(cn)

    for profile in profiles:
        did = profile.debtor.id
        avail = sorted(inv_by_debtor[did], key=lambda i: i.due_date)
        debtor_cns = cn_by_debtor[did]
        idx = 0

        while idx < len(avail):
            inv = avail[idx]
            if inv.id in consumed:
                idx += 1
                continue

            scenario = _pick(profile.scenario_weights, rng)
            pay_seq += 1
            pid = f"PAY-{pay_seq:06d}"
            dt = make_payment_date(inv.due_date, profile.avg_delay_days, profile.payment_day, rng)

            # ── C1_EXACT_REF ──
            if scenario == "C1_EXACT_REF":
                p = _mkpay(pid, inv.amount, dt, profile, _ref_label(inv.reference, rng, profile.debtor.country or "FR"), [inv.reference])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C1_ISO20022 ──
            elif scenario == "C1_ISO20022":
                p = _mkpay(pid, inv.amount, dt, profile, "", [])
                p.iso20022 = ISO20022Fields(roc_ref=inv.reference)
                p.signals.raw_refs = [inv.reference.replace("-","").upper()]
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C1_IBAN_AMOUNT ──
            elif scenario == "C1_IBAN_AMOUNT":
                lang = COUNTRY_LANG.get(profile.debtor.country, "EN")
                generic_labels = {
                    "FR": ["VIREMENT","REGLEMENT","PAIEMENT","VIREMENT COMMERCIAL","CREDIT COMPTE"],
                    "EN": ["WIRE TRANSFER","PAYMENT","BANK TRANSFER","CREDIT","REMITTANCE"],
                    "DE": ["ÜBERWEISUNG","ZAHLUNG","GUTSCHRIFT","BANKÜBERWEISUNG"],
                    "NL": ["BETALING","OVERBOEKING","CREDITOVERSCHRIJVING"],
                    "ES": ["TRANSFERENCIA","PAGO","ABONO EN CUENTA"],
                    "IT": ["BONIFICO","PAGAMENTO","ACCREDITO"],
                    "PT": ["TRANSFERÊNCIA","PAGAMENTO","CRÉDITO"],
                    "TR": ["HAVALE","ÖDEME","EFT"],
                    "PL": ["PRZELEW","PŁATNOŚĆ","WPŁATA"],
                    "AR": ["TAHWIL","HAW BANK","CREDIT TRANSFER"],
                    "ZH": ["汇款","转账","付款"],
                    "JA": ["振込","送金"],
                    "KO": ["송금","이체"],
                }
                pool = generic_labels.get(lang, generic_labels["EN"])
                p = _mkpay(pid, inv.amount, dt, profile, rng.choice(pool), [])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C1_PO_MATCH ──
            elif scenario == "C1_PO_MATCH" and inv.po_number:
                po_labels = {
                    "FR": [f"REGLT COMMANDE {inv.po_number}", f"PAIEMENT PO {inv.po_number}", f"VIR CMNDE {inv.po_number}"],
                    "EN": [f"PAYMENT PO {inv.po_number}", f"PMT ORDER {inv.po_number}", f"SETTLEMENT PO# {inv.po_number}"],
                    "DE": [f"ZAHLUNG BESTELLUNG {inv.po_number}", f"BESTELLNR {inv.po_number}"],
                    "ES": [f"PAGO PEDIDO {inv.po_number}", f"ORDEN DE COMPRA {inv.po_number}"],
                    "IT": [f"PAGAMENTO ORDINE {inv.po_number}", f"ORDINE {inv.po_number}"],
                }
                lang = COUNTRY_LANG.get(profile.debtor.country, "EN")
                pool = po_labels.get(lang, po_labels["EN"])
                p = _mkpay(pid, inv.amount, dt, profile, rng.choice(pool), [inv.po_number])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C1_BL_MATCH ──
            elif scenario == "C1_BL_MATCH" and inv.bl_number:
                bl_labels = {
                    "FR": [f"REGLEMENT {inv.bl_number}", f"PAIEMENT LIVRAISON {inv.bl_number}"],
                    "EN": [f"PMT DELIVERY {inv.bl_number}", f"PAYMENT BOL {inv.bl_number}"],
                    "DE": [f"ZAHLUNG LIEFERSCHEIN {inv.bl_number}"],
                    "IT": [f"PAGAMENTO DDT {inv.bl_number}", f"BOLLA {inv.bl_number}"],
                }
                lang = COUNTRY_LANG.get(profile.debtor.country, "EN")
                pool = bl_labels.get(lang, bl_labels["EN"])
                p = _mkpay(pid, inv.amount, dt, profile, rng.choice(pool), [inv.bl_number])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C1_FULL_BALANCE ──
            elif scenario == "C1_FULL_BALANCE":
                rem = [i for i in avail[idx:] if i.id not in consumed][:10]
                if len(rem) >= 2:
                    total = sum(i.amount for i in rem)
                    balance_labels = {
                        "FR": ["SOLDE TOTAL COMPTE","REGLEMENT INTEGRAL","APUREMENT SOLDE","SOLDE DE TOUT COMPTE"],
                        "EN": ["FULL BALANCE PAYMENT","ACCOUNT SETTLEMENT","CLEARING ALL INVOICES","FULL SETTLEMENT"],
                        "DE": ["KOMPLETTAUSGLEICH","KONTOAUSGLEICH","SALDENAUSGLEICH"],
                        "ES": ["PAGO TOTAL PENDIENTE","LIQUIDACIÓN COMPLETA","SALDO TOTAL"],
                        "IT": ["SALDO TOTALE CONTO","PAGAMENTO INTEGRALE"],
                    }
                    lang = COUNTRY_LANG.get(profile.debtor.country, "EN")
                    pool = balance_labels.get(lang, balance_labels["EN"])
                    p = _mkpay(pid, total, dt, profile, rng.choice(pool), [])
                    payments.append(p)
                    for i in rem: consumed.add(i.id)
                    idx += len(rem)
                else: idx += 1; continue

            # ── C2_SWIFT_FEES ──
            elif scenario == "C2_SWIFT_FEES":
                fee = round(rng.uniform(12, 35), 2)
                p = _mkpay(pid, inv.amount - fee, dt, profile, _ref_label(inv.reference, rng, profile.debtor.country or "FR"), [inv.reference])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C2_DISCOUNT ──
            elif scenario == "C2_DISCOUNT" and profile.debtor.discount_rate > 0:
                rate = profile.debtor.discount_rate
                amt = round(inv.amount * (1 - rate), 2)
                disc_labels = [
                    f"REGLT {inv.reference} ESC {rate*100:.0f}%",
                    f"PMT {inv.reference} EARLY DISCOUNT {rate*100:.0f}%",
                    f"ZAHLUNG {inv.reference} SKONTO {rate*100:.0f}%",
                    f"PAGO {inv.reference} DESCUENTO {rate*100:.0f}%",
                    f"PAGAMENTO {inv.reference} SCONTO {rate*100:.0f}%",
                    f"{inv.reference} ESCOMPTE DEDUIT",
                    f"PAYMENT {inv.reference} LESS {rate*100:.0f}% DISCOUNT",
                ]
                p = _mkpay(pid, amt, dt, profile, rng.choice(disc_labels), [inv.reference])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C2_RETENTION ──
            elif scenario == "C2_RETENTION" and profile.debtor.retention_rate > 0:
                rate = profile.debtor.retention_rate
                amt = round(inv.amount * (1 - rate), 2)
                ret_labels = [
                    f"REGLT {inv.reference} RET {rate*100:.0f}%",
                    f"REGLT CHANTIER {inv.reference} RETENUE GARANTIE {rate*100:.0f}%",
                    f"PMT {inv.reference} RETENTION {rate*100:.0f}%",
                    f"{inv.reference} LESS RETENTION {rate*100:.0f}%",
                    f"ZAHLUNG {inv.reference} EINBEHALT {rate*100:.0f}%",
                    f"PAGO {inv.reference} RETENCION GARANTIA",
                ]
                p = _mkpay(pid, amt, dt, profile, rng.choice(ret_labels), [inv.reference])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C2_RFA ──
            elif scenario == "C2_RFA" and profile.debtor.rfa_rate > 0:
                rate = profile.debtor.rfa_rate
                amt = round(inv.amount * (1 - rate), 2)
                rfa_labels = [
                    f"REGLT {inv.reference} RFA {rate*100:.0f}%",
                    f"REGLT {inv.reference} DED RFA ANNUELLE",
                    f"PMT {inv.reference} YEAR END REBATE {rate*100:.0f}%",
                    f"ZAHLUNG {inv.reference} JAHRESBONUS {rate*100:.0f}%",
                    f"{inv.reference} REMISE FIN ANNEE DEDUITE",
                ]
                p = _mkpay(pid, amt, dt, profile, rng.choice(rfa_labels), [inv.reference])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C2_CREDIT_NOTE ──
            elif scenario == "C2_CREDIT_NOTE" and debtor_cns:
                ok = [cn for cn in debtor_cns if cn.id not in cn_used and cn.amount < inv.amount]
                if ok:
                    cn = ok[0]
                    amt = round(inv.amount - cn.amount, 2)
                    p = _mkpay(pid, amt, dt, profile, f"REGLT {inv.reference} DED {cn.reference}", [inv.reference])
                    payments.append(p); consumed.add(inv.id); cn_used.add(cn.id); idx += 1
                else: idx += 1; continue

            # ── C2_ROUNDING ──
            elif scenario == "C2_ROUNDING":
                delta = round(rng.uniform(-0.99, 0.99), 2)
                if abs(delta) < 0.01: delta = 0.50
                p = _mkpay(pid, inv.amount + delta, dt, profile, _ref_label(inv.reference, rng, profile.debtor.country or "FR"), [inv.reference])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C2_SUBSET_SUM ──
            elif scenario == "C2_SUBSET_SUM":
                rem = [i for i in avail[idx:] if i.id not in consumed]
                n = min(rng.randint(2, 5), len(rem))
                if n >= 2:
                    grp = rem[:n]
                    total = round(sum(i.amount for i in grp), 2)
                    subset_labels = [
                        "REGLEMENT FACTURES EN COURS",
                        "PAIEMENT GROUPÉ FACTURES",
                        "VIR GLOBAL FACTURES OUVERTES",
                        "PAYMENT MULTIPLE INVOICES",
                        "SETTLEMENT OPEN INVOICES",
                        "BULK PAYMENT OUTSTANDING",
                        "SAMMELZAHLUNG RECHNUNGEN",
                        "BETALING OPENSTAANDE FACTUREN",
                        "PAGO FACTURAS PENDIENTES",
                        "PAGAMENTO FATTURE IN SOSPESO",
                        f"REGLEMENT {len(grp)} FACTURES",
                        f"PAYMENT OF {len(grp)} INVOICES",
                    ]
                    p = _mkpay(pid, total, dt, profile, rng.choice(subset_labels), [])
                    payments.append(p)
                    for i in grp: consumed.add(i.id)
                    idx += n
                else: idx += 1; continue

            # ── C2_INSTALLMENT ──
            elif scenario == "C2_INSTALLMENT":
                pct = rng.choice([0.30, 0.50, 0.70])
                amt1 = round(inv.amount * pct, 2)
                acompte_labels = [
                    f"ACOMPTE {int(pct*100)}% {inv.reference}",
                    f"AVANCE {int(pct*100)}% {inv.reference}",
                    f"PARTIAL PMT {int(pct*100)}% {inv.reference}",
                    f"ADVANCE PAYMENT {int(pct*100)}% {inv.reference}",
                    f"ANZAHLUNG {int(pct*100)}% {inv.reference}",
                    f"PAGO ANTICIPADO {int(pct*100)}% {inv.reference}",
                    f"ACCONTO {int(pct*100)}% {inv.reference}",
                    f"1ERE ECHEANCE {inv.reference}",
                    f"FIRST INSTALLMENT {inv.reference}",
                    f"DOWN PAYMENT {inv.reference}",
                ]
                p1 = _mkpay(pid, amt1, dt, profile, rng.choice(acompte_labels), [inv.reference])
                p1.signals.keywords = {"partial": True, "advance": True, "credit_note": False, "final": False}
                payments.append(p1)
                # Solde
                pay_seq += 1
                pid2 = f"PAY-{pay_seq:06d}"
                dt2 = dt + timedelta(days=rng.randint(15, 35))
                while dt2.weekday() >= 5: dt2 += timedelta(days=1)
                rest = round(inv.amount - amt1, 2)
                solde_labels = [
                    f"SOLDE {int((1-pct)*100)}% {inv.reference}",
                    f"FINAL PAYMENT {inv.reference}",
                    f"BALANCE DUE {inv.reference}",
                    f"RESTZAHLUNG {inv.reference}",
                    f"SALDO {inv.reference}",
                    f"DERNIER VERSEMENT {inv.reference}",
                    f"2EME ECHEANCE {inv.reference}",
                    f"COMPLEMENTO PAGO {inv.reference}",
                ]
                p2 = _mkpay(pid2, rest, dt2, profile, rng.choice(solde_labels), [inv.reference])
                p2.signals.keywords = {"partial": False, "advance": False, "credit_note": False, "final": True}
                payments.append(p2)
                consumed.add(inv.id); idx += 1

            # ── C2_TEMPORAL ──
            elif scenario == "C2_TEMPORAL":
                target_month = inv.issue_date.month
                same = [i for i in avail[idx:] if i.id not in consumed and i.issue_date.month == target_month][:7]
                if len(same) >= 2:
                    total = round(sum(i.amount for i in same), 2)
                    mname = MONTH_NAMES_FR.get(target_month, str(target_month))
                    MONTH_EN = {1:"JANUARY",2:"FEBRUARY",3:"MARCH",4:"APRIL",5:"MAY",6:"JUNE",
                                7:"JULY",8:"AUGUST",9:"SEPTEMBER",10:"OCTOBER",11:"NOVEMBER",12:"DECEMBER"}
                    MONTH_DE = {1:"JANUAR",2:"FEBRUAR",3:"MÄRZ",4:"APRIL",5:"MAI",6:"JUNI",
                                7:"JULI",8:"AUGUST",9:"SEPTEMBER",10:"OKTOBER",11:"NOVEMBER",12:"DEZEMBER"}
                    MONTH_ES = {1:"ENERO",2:"FEBRERO",3:"MARZO",4:"ABRIL",5:"MAYO",6:"JUNIO",
                                7:"JULIO",8:"AGOSTO",9:"SEPTIEMBRE",10:"OCTUBRE",11:"NOVIEMBRE",12:"DICIEMBRE"}
                    temporal_labels = [
                        f"REGLEMENT FACTURES {mname} 2024",
                        f"PAIEMENT FACTURES MOIS DE {mname}",
                        f"VIR GLOBAL {mname} 2024",
                        f"PAYMENT INVOICES {MONTH_EN.get(target_month,'')} 2024",
                        f"SETTLEMENT {MONTH_EN.get(target_month,'')} INVOICES",
                        f"ZAHLUNG RECHNUNGEN {MONTH_DE.get(target_month,'')} 2024",
                        f"PAGO FACTURAS {MONTH_ES.get(target_month,'')} 2024",
                        f"REGLT MENSUEL {mname[:3]} 2024",
                        f"MONTHLY PAYMENT {MONTH_EN.get(target_month,'')[:3]} 2024",
                    ]
                    label = rng.choice(temporal_labels)
                    p = _mkpay(pid, total, dt, profile, label, [])
                    p.signals.label_periods = [f"{mname} 2024"]
                    payments.append(p)
                    for i in same: consumed.add(i.id)
                    idx += len(same)
                else: idx += 1; continue

            # ── C2_WHT ──
            elif scenario == "C2_WHT":
                rate = WHT_RATES.get(profile.debtor.country, 0.15)
                amt = round(inv.amount * (1 - rate), 2)
                p = _mkpay(pid, amt, dt, profile, _ref_label(inv.reference, rng, profile.debtor.country or "FR"), [inv.reference])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C2_HT_ERROR ──
            elif scenario == "C2_HT_ERROR":
                p = _mkpay(pid, inv.amount_ht, dt, profile, f"PAYMENT INVOICE {inv.reference}", [inv.reference])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C3_FUZZY ──
            elif scenario == "C3_FUZZY":
                typo = introduce_typo(inv.reference, rng)
                fuzzy_labels = [
                    f"REGLT {typo}", f"PAIEMENT {typo}", f"PMT {typo}",
                    f"PAYMENT {typo}", f"ZAHLUNG {typo}", f"BETALING {typo}",
                    f"PAGO {typo}", f"PAGAMENTO {typo}", f"VIR {typo}",
                    f"TRANSFER {typo}", f"ÜBERWEISUNG {typo}",
                    f"SETTLEMENT {typo}", f"WIRE {typo}",
                ]
                p = _mkpay(pid, inv.amount, dt, profile, rng.choice(fuzzy_labels), [typo])
                payments.append(p); consumed.add(inv.id); idx += 1

            # ── C6_CRYPTIC ──
            elif scenario == "C6_CRYPTIC":
                tmpl = rng.choice(CRYPTIC_TEMPLATES)
                label = tmpl.format(n=rng.randint(1000, 9999))
                amt = inv.amount if rng.random() < 0.25 else round(rng.uniform(500, 80000), 2)
                p = _mkpay(pid, amt, dt, profile, label, [])
                payments.append(p)
                if rng.random() < 0.25: consumed.add(inv.id)
                idx += 1

            # ── Fallback ──
            else:
                p = _mkpay(pid, inv.amount, dt, profile, _ref_label(inv.reference, rng, profile.debtor.country or "FR"), [inv.reference])
                payments.append(p); consumed.add(inv.id); idx += 1

    payments.sort(key=lambda p: p.date or date(2024, 1, 1))
    return payments


# ============================================================
# 5. REPORTING
# ============================================================

BOLD  = "\033[1m"
DIM   = "\033[2m"
RESET = "\033[0m"
GREEN = "\033[92m"
YELLOW= "\033[93m"
RED   = "\033[91m"
CYAN  = "\033[96m"

LAYER_NAMES = {
    0: "C0 Pre-traitement", 1: "C1 Exact/Deterministe",
    2: "C2 Regles Metier", 3: "C3 NLP/Fuzzy",
    4: "C4 Machine Learning", 5: "C5 LLM", 6: "C6 Revue Humaine",
}
LCOLORS = {1: GREEN, 2: YELLOW, 3: CYAN, 6: RED}


def print_header(n_debtors, n_months):
    print(f"""
{BOLD}{'='*80}
  STRESS TEST — Reconciliation Paiement-Facture par IA
  {n_debtors} debiteurs | 12 mois | Architecture 6 Couches
{'='*80}{RESET}
""")


def print_data_summary(profiles, invoices, payments, credits):
    print(f"{BOLD}--- DONNEES GENEREES ---{RESET}")
    print(f"  Debiteurs       : {len(profiles)}")
    print(f"  Factures        : {len(invoices)}")
    print(f"  Paiements       : {len(payments)}")
    print(f"  Avoirs          : {len(credits)}")
    print(f"  Montant facture : {sum(i.amount for i in invoices):>15,.2f} EUR")
    print(f"  Montant paiemt  : {sum(p.amount for p in payments):>15,.2f} EUR")

    # Par mois
    inv_m = Counter(i.issue_date.month for i in invoices)
    pay_m = Counter(p.date.month for p in payments if p.date)
    print(f"\n  {'Mois':<12} {'Factures':>8} {'Paiements':>10}")
    print(f"  {'-'*32}")
    for m in range(1, 13):
        mn = MONTH_NAMES_FR.get(m, "?")[:10]
        print(f"  {mn:<12} {inv_m.get(m,0):>8} {pay_m.get(m,0):>10}")
    print(f"  {'TOTAL':<12} {sum(inv_m.values()):>8} {sum(pay_m.values()):>10}")

    # Par pays
    inv_c = Counter(next((p.debtor.country for p in profiles if p.debtor.id == i.debtor_id), "?") for i in invoices)
    print(f"\n  {'Pays':<6} {'Factures':>8}   {'Pays':<6} {'Factures':>8}")
    print(f"  {'-'*40}")
    items = sorted(inv_c.items(), key=lambda x: -x[1])
    half = (len(items) + 1) // 2
    for i in range(half):
        left = items[i] if i < len(items) else ("", 0)
        right = items[i + half] if i + half < len(items) else ("", 0)
        print(f"  {left[0]:<6} {left[1]:>8}   {right[0]:<6} {right[1]:>8}")
    print()


def print_progress(i, total, ctx):
    if i % 100 == 0 or i == total - 1:
        pct = (i+1) / total * 100
        filled = int(40 * (i+1) / total)
        bar = "█" * filled + "░" * (40 - filled)
        layer = f"C{ctx.final_match.layer}" if ctx.final_match else "C6"
        print(f"\r  [{bar}] {pct:5.1f}% | {i+1}/{total} | -> {layer}", end="", flush=True)


def print_results(orch, results, invoices, payments):
    m = orch.metrics
    total = m.total_payments
    auto = m.matched_auto
    review = m.by_layer.get(6, 0)

    print(f"\n\n{BOLD}{'='*80}")
    print(f"  RESULTATS DU STRESS TEST")
    print(f"{'='*80}{RESET}\n")

    auto_pct = auto / total * 100
    review_pct = review / total * 100
    color = GREEN if auto_pct >= 70 else YELLOW if auto_pct >= 50 else RED

    print(f"  {BOLD}Taux d'automatisation : {color}{auto_pct:.1f}%{RESET} ({auto}/{total})")
    print(f"  Revue humaine       : {review_pct:.1f}% ({review})")
    print(f"  Erreurs             : {m.errors}")
    print(f"  Temps moyen         : {m.avg_processing_time_ms:.2f} ms/paiement")
    print(f"  Temps total         : {m.total_processing_time_ms/1000:.1f}s")
    print()

    # Distribution couches
    print(f"  {BOLD}--- Distribution par couche ---{RESET}")
    print(f"  {'Couche':<28} {'Nb':>6} {'%':>8}  Barre")
    print(f"  {'-'*65}")
    for layer in sorted(m.by_layer.keys()):
        cnt = m.by_layer[layer]
        pct = cnt / total * 100
        c = LCOLORS.get(layer, "")
        name = LAYER_NAMES.get(layer, f"C{layer}")
        bar = "█" * int(pct / 2)
        print(f"  {c}{name:<28} {cnt:>6} {pct:>7.1f}%  {bar}{RESET}")

    # Méthodes
    print(f"\n  {BOLD}--- Top methodes ---{RESET}")
    print(f"  {'Methode':<36} {'Nb':>6} {'%':>8}")
    print(f"  {'-'*52}")
    for method, cnt in sorted(m.by_method.items(), key=lambda x: -x[1])[:15]:
        print(f"  {method:<36} {cnt:>6} {cnt/total*100:>7.1f}%")

    # Par débiteur
    debtor_stats = defaultdict(lambda: {"auto": 0, "review": 0, "total": 0})
    debtor_names = {}
    for ctx in results:
        did = ctx.payment.debtor_id or "?"
        debtor_stats[did]["total"] += 1
        if ctx.final_match and ctx.final_match.confidence >= 0.90:
            debtor_stats[did]["auto"] += 1
        else:
            debtor_stats[did]["review"] += 1
        if ctx.payment.debtor:
            debtor_names[did] = ctx.payment.debtor.name[:30]

    print(f"\n  {BOLD}--- Top 20 debiteurs ---{RESET}")
    print(f"  {'Debiteur':<34} {'Pays':>4} {'Total':>6} {'Auto':>6} {'Revue':>6} {'Taux':>7}")
    print(f"  {'-'*68}")
    sorted_debtors = sorted(debtor_stats.items(), key=lambda x: -x[1]["total"])[:20]
    for did, d in sorted_debtors:
        rate = d["auto"] / d["total"] * 100 if d["total"] else 0
        name = debtor_names.get(did, did)
        c = GREEN if rate >= 80 else YELLOW if rate >= 50 else RED
        country = ""
        for ctx in results:
            if ctx.payment.debtor_id == did and ctx.payment.debtor:
                country = ctx.payment.debtor.country or ""
                break
        print(f"  {name:<34} {country:>4} {d['total']:>6} {d['auto']:>6} {d['review']:>6} {c}{rate:>6.1f}%{RESET}")

    # Timeline trimestrielle
    print(f"\n  {BOLD}--- Timeline trimestrielle ---{RESET}")
    quarters = defaultdict(lambda: {"total": 0, "auto": 0})
    for ctx in results:
        if ctx.payment.date:
            q = (ctx.payment.date.month - 1) // 3 + 1
            y = ctx.payment.date.year
            qk = f"{y}-Q{q}"
            quarters[qk]["total"] += 1
            if ctx.final_match and ctx.final_match.confidence >= 0.90:
                quarters[qk]["auto"] += 1

    print(f"  {'Trimestre':<12} {'Total':>6} {'Auto':>6} {'Taux':>7}")
    print(f"  {'-'*34}")
    for qk in sorted(quarters.keys()):
        d = quarters[qk]
        rate = d["auto"] / d["total"] * 100 if d["total"] else 0
        print(f"  {qk:<12} {d['total']:>6} {d['auto']:>6} {rate:>6.1f}%")

    # File de revue
    q = orch.review_queue
    print(f"\n  {BOLD}--- File de revue humaine ---{RESET}")
    print(f"  Taille : {q.queue_size} paiements en attente")
    if q.queue_size > 0:
        print(f"  {'Paiement':<14} {'Montant':>12} {'Debiteur':<26} {'Label':<28} {'Prio':>6}")
        print(f"  {'-'*90}")
        for item in q._queue[:10]:
            p = item.payment
            dn = p.debtor.name[:24] if p.debtor else "?"
            lb = p.label_raw[:26] if p.label_raw else "(vide)"
            print(f"  {p.id:<14} {p.amount:>12,.2f} {dn:<26} {lb:<28} {item.priority_score:>5.3f}")
    print()


# ============================================================
# 6. RUNNER
# ============================================================

def run_stress_test(n_debtors: int = 20, n_months: int = 12, seed: int = 42):
    """
    Lance le stress test complet.
    Args:
        n_debtors: nombre de débiteurs (défaut 20)
        n_months:  nombre de mois (défaut 12 = année complète)
        seed:      graine aléatoire pour reproductibilité
    """
    rng = random.Random(seed)
    year = 2024
    months = list(range(1, n_months + 1))

    print_header(n_debtors, n_months)

    # ── 1. Données ──
    print(f"{DIM}  Generation des donnees...{RESET}")
    profiles = generate_debtors(n_debtors, rng)
    invoices = generate_invoices(profiles, months, year, rng)
    credit_notes = generate_credit_notes(profiles, invoices, rng)

    cn_by_debtor = defaultdict(list)
    for cn in credit_notes:
        cn_by_debtor[cn.debtor_id].append(cn)
    for p in profiles:
        p.debtor.open_credits = cn_by_debtor.get(p.debtor.id, [])

    payments = generate_payments(profiles, invoices, credit_notes, rng)
    print_data_summary(profiles, invoices, payments, credit_notes)

    # ── 2. Orchestrateur ──
    config = ReconciliationConfig()
    orch = ReconciliationOrchestrator(config)

    debtors = [p.debtor for p in profiles]
    iban_map = {p.debtor.iban: p.debtor.id for p in profiles if p.debtor.iban}

    inv_by_debtor = defaultdict(list)
    for inv in invoices:
        inv_by_debtor[inv.debtor_id].append(inv)
    for p in profiles:
        p.debtor.open_invoices = inv_by_debtor.get(p.debtor.id, [])

    orch.setup(invoices, debtors=debtors, iban_debtor_map=iban_map)

    # ── 3. Traitement ──
    print(f"{BOLD}--- TRAITEMENT DE {len(payments)} PAIEMENTS ---{RESET}\n")
    open_invoices = list(invoices)
    results = []
    t0 = time.time()

    for i, payment in enumerate(payments):
        ctx = orch.process_payment(payment, open_invoices)
        results.append(ctx)
        if ctx.final_match:
            matched_ids = {inv.id for inv in ctx.final_match.invoices}
            open_invoices = [inv for inv in open_invoices if inv.id not in matched_ids]
        print_progress(i, len(payments), ctx)

    wall = time.time() - t0

    # ── 4. Résultats ──
    print_results(orch, results, invoices, payments)
    print(f"  {DIM}Temps reel : {wall:.1f}s | Debit : {len(payments)/wall:.0f} paiements/s{RESET}\n")

    return orch, results


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stress test reconciliation")
    parser.add_argument("--debtors", type=int, default=20, help="Nombre de debiteurs (defaut: 20)")
    parser.add_argument("--months", type=int, default=12, help="Nombre de mois (defaut: 12)")
    parser.add_argument("--seed", type=int, default=42, help="Graine aleatoire (defaut: 42)")
    args = parser.parse_args()

    run_stress_test(n_debtors=args.debtors, n_months=args.months, seed=args.seed)
