#!/usr/bin/env python3
"""
Generate data/verbatims.json — a massive corpus of realistic payment labels.

Each entry is a template with {ref}, {amount}, {date}, {month}, {year},
{po}, {bl}, {cn}, {n} placeholders that the simulation fills at runtime.

Run once:  python data/generate_verbatims.py
Output:    data/verbatims.json
"""

import json
from pathlib import Path

verbatims = {

# ================================================================
# EXACT REFERENCE — Label mentions the invoice reference
# ================================================================
"exact_ref": {
    "fr": [
        "REGLT {ref}",
        "REGLEMENT {ref}",
        "PAIEMENT {ref}",
        "VIREMENT {ref}",
        "VIR SEPA {ref}",
        "RGT {ref}",
        "PMT {ref}",
        "REGL FACTURE {ref}",
        "PAIEMENT FOURNISSEUR {ref}",
        "VIR SCT {ref}",
        "REGL ECHEANCE {ref}",
        "PAIEMENT ECHEANCE {ref}",
        "VIR REGL {ref}",
        "REGLEMENT VOTRE FACTURE {ref}",
        "SOLDE FACTURE {ref}",
        "REGLT VOTRE FACTURE {ref} DU {date}",
        "VIRT SEPA REF {ref}",
        "REGLEMENT FAC {ref} MERCI",
        "PAIEMENT FACTURE NO {ref}",
        "REGL {ref} ECH {date}",
        "VIR {ref} MONTANT {amount}",
        "VIRT {ref}",
        "REGLT FACT {ref}",
        "PAIEMENT SELON FACTURE {ref}",
        "REGLEMENT CONVENU {ref}",
        "REGL VOTRE RELEVE {ref}",
        "VERSEMENT {ref}",
        "ACQUITTEMENT {ref}",
        "VOTRE REF {ref} / NOTRE REF INT {n}",
    ],
    "en": [
        "PAYMENT {ref}",
        "PMT {ref}",
        "PAYMENT FOR INV {ref}",
        "SETTLEMENT {ref}",
        "WIRE TRANSFER {ref}",
        "BANK TRANSFER {ref}",
        "PAYMENT OF INVOICE {ref}",
        "PMT REF {ref}",
        "REMITTANCE {ref}",
        "PAYMENT AS PER INVOICE {ref}",
        "SETTLEMENT OF INVOICE {ref}",
        "TRF {ref}",
        "CREDIT TRANSFER {ref}",
        "PYMT {ref}",
        "PAY {ref}",
        "PAYMENT FOR {ref}",
        "FUNDS TRANSFER {ref}",
        "SUPPLIER PAYMENT {ref}",
        "VENDOR PAYMENT {ref}",
        "TRADE SETTLEMENT {ref}",
        "PAYMENT ADVICE {ref}",
        "CHAPS PAYMENT {ref}",
        "FASTER PAYMENT {ref}",
        "BACS CREDIT {ref}",
        "ACH PAYMENT {ref}",
        "RE: INVOICE {ref} DATED {date}",
        "PAY RUN {n} - INV {ref}",
        "PMT PER STATEMENT {ref}",
        "AS AGREED INV {ref}",
        "FINAL PMT {ref}",
    ],
    "de": [
        "ZAHLUNG {ref}",
        "ÜBERWEISUNG {ref}",
        "BEZAHLUNG RECHNUNG {ref}",
        "RECHNUNGSBEGLEICHUNG {ref}",
        "ZAHLUNGSANWEISUNG {ref}",
        "GUTSCHRIFT {ref}",
        "BEGLEICHUNG {ref}",
        "AUSGLEICH RECHNUNG {ref}",
        "ZAHLUNGSAUSGLEICH {ref}",
        "BANKÜBERWEISUNG {ref}",
        "SEPA-ÜBERWEISUNG {ref}",
        "ZAHLUNG GEM. RECHNUNG {ref}",
        "BEZAHLUNG IHRE RECHNUNG {ref} VOM {date}",
        "RECHNUNGSNR {ref} BEGLICHEN",
        "RE {ref} BETRAG {amount} EUR",
    ],
    "nl": [
        "BETALING {ref}",
        "OVERBOEKING {ref}",
        "BETALING FACTUUR {ref}",
        "VOLDOENING {ref}",
        "BANKOVERSCHRIJVING {ref}",
        "CREDITOVERSCHRIJVING {ref}",
        "BETALING REF {ref}",
        "FACTUUR VOLDAAN {ref}",
        "SEPA OVERBOEKING {ref}",
        "BET FACT {ref}",
        "BETALING CONFORM FACTUUR {ref} DD {date}",
    ],
    "es": [
        "PAGO {ref}",
        "TRANSFERENCIA {ref}",
        "PAGO FACTURA {ref}",
        "ABONO {ref}",
        "LIQUIDACION {ref}",
        "PAGO A PROVEEDOR {ref}",
        "TRANSFERENCIA REF {ref}",
        "GIRO BANCARIO {ref}",
        "PAGO SEGUN FACTURA {ref}",
        "ABONO EN CUENTA {ref}",
        "PAGO FACTURA NRO {ref} DEL {date}",
        "TRANSFERENCIA POR FACTURA {ref}",
    ],
    "it": [
        "PAGAMENTO {ref}",
        "BONIFICO {ref}",
        "PAGAMENTO FATTURA {ref}",
        "SALDO FATTURA {ref}",
        "BONIFICO BANCARIO {ref}",
        "PAGAMENTO RIF {ref}",
        "VERSAMENTO {ref}",
        "ACCREDITO {ref}",
        "BONIFICO SEPA {ref}",
        "REGOLAMENTO FATTURA {ref}",
        "PAG FATT {ref} DEL {date}",
        "NS BONIFICO PER FATT {ref}",
    ],
    "pt": [
        "PAGAMENTO {ref}",
        "TRANSFERENCIA {ref}",
        "PAGAMENTO FATURA {ref}",
        "LIQUIDACAO {ref}",
        "TRANSFERENCIA BANCARIA {ref}",
        "PAGAMENTO REF {ref}",
        "CREDITO {ref}",
    ],
    "tr": [
        "ODEME {ref}",
        "HAVALE {ref}",
        "FATURA ODEMESI {ref}",
        "BANKA HAVALESI {ref}",
        "EFT ODEMESI {ref}",
        "ODEME REF {ref}",
        "VIRMAN {ref}",
    ],
    "pl": [
        "PLATNOSC {ref}",
        "PRZELEW {ref}",
        "ZAPLATA FAKTURY {ref}",
        "PRZELEW BANKOWY {ref}",
        "WPLATA {ref}",
        "PRZELEW ZA FAKTURE {ref}",
        "PLATNOSC REF {ref}",
    ],
    "ar": [
        "TAHWIL {ref}",
        "DAFA {ref}",
        "TASDID FATOURA {ref}",
        "HAW BANK {ref}",
        "SADDAD {ref}",
    ],
    "ja": [
        "振込 {ref}",
        "送金 {ref}",
        "お支払い {ref}",
        "代金支払 {ref}",
        "請求書 {ref} 振込済",
    ],
    "zh": [
        "付款 {ref}",
        "汇款 {ref}",
        "转账 {ref}",
        "支付货款 {ref}",
        "电汇 {ref}",
    ],
    "ko": [
        "결제 {ref}",
        "송금 {ref}",
        "대금지급 {ref}",
        "이체 {ref}",
    ],
},

# ================================================================
# GENERIC — No reference, just a transfer label
# ================================================================
"generic": {
    "fr": [
        "VIREMENT", "REGLEMENT", "PAIEMENT", "CREDIT COMPTE",
        "VIREMENT COMMERCIAL", "PAIEMENT FOURNISSEUR", "VERSEMENT",
        "VIR RECU", "VIR SCT", "REGLEMENT FOURNISSEUR",
        "VIREMENT RECU", "CREDIT", "ENCAISSEMENT",
    ],
    "en": [
        "WIRE TRANSFER", "PAYMENT", "BANK TRANSFER", "REMITTANCE",
        "CREDIT TRANSFER", "SUPPLIER PAYMENT", "VENDOR PMT",
        "TRADE PAYMENT", "ACH PAYMENT", "FASTER PAYMENT",
        "CHAPS PAYMENT", "BACS CREDIT", "INCOMING WIRE",
    ],
    "de": [
        "ÜBERWEISUNG", "ZAHLUNG", "GUTSCHRIFT", "BANKÜBERWEISUNG",
        "SEPA ÜBERWEISUNG", "ZAHLUNGSEINGANG", "EINGANG",
    ],
    "nl": [
        "BETALING", "OVERBOEKING", "CREDITOVERSCHRIJVING",
        "SEPA OVERBOEKING", "ONTVANGEN BETALING",
    ],
    "es": [
        "TRANSFERENCIA", "PAGO", "ABONO EN CUENTA", "GIRO",
        "TRANSFERENCIA RECIBIDA", "COBRO",
    ],
    "it": [
        "BONIFICO", "PAGAMENTO", "ACCREDITO", "VERSAMENTO",
        "BONIFICO RICEVUTO", "INCASSO",
    ],
},

# ================================================================
# PO / BL — Purchase Order and Bill of Lading references
# ================================================================
"po_match": [
    "REGLT COMMANDE {po}",
    "PMT PO {po}",
    "PAYMENT ORDER {po}",
    "ZAHLUNG BESTELLUNG {po}",
    "PAGO PEDIDO {po}",
    "PAGAMENTO ORDINE {po}",
    "BETALING ORDER {po}",
    "PRZELEW ZAMOWIENIE {po}",
    "REGLEMENT BON DE COMMANDE {po}",
    "PAYMENT AS PER PO {po}",
    "RE PO# {po} / INV {ref}",
    "SETTLEMENT PO {po}",
    "VIR COMMANDE {po}",
    "ORDER {po} PAYMENT",
    "BESTELLUNG {po} BEZAHLT",
],
"bl_match": [
    "REGLEMENT {bl}",
    "PMT DELIVERY {bl}",
    "PAYMENT BOL {bl}",
    "ZAHLUNG LIEFERSCHEIN {bl}",
    "PAGAMENTO DDT {bl}",
    "BOLLA {bl}",
    "PAIEMENT LIVRAISON {bl}",
    "SETTLEMENT DELIVERY {bl}",
    "BL {bl} REGLE",
    "BETALING LEVERING {bl}",
    "REGLT CMR {bl}",
    "TRANSPORT {bl} PAID",
],

# ================================================================
# FULL BALANCE — Payment covers entire debtor balance
# ================================================================
"full_balance": [
    "SOLDE TOTAL COMPTE",
    "REGLEMENT INTEGRAL",
    "APUREMENT SOLDE",
    "SOLDE DE TOUT COMPTE",
    "FULL BALANCE PAYMENT",
    "ACCOUNT SETTLEMENT",
    "CLEARING ALL INVOICES",
    "FULL SETTLEMENT",
    "KOMPLETTAUSGLEICH",
    "KONTOAUSGLEICH",
    "SALDENAUSGLEICH",
    "PAGO TOTAL PENDIENTE",
    "LIQUIDACION COMPLETA",
    "SALDO TOTAL",
    "SALDO TOTALE CONTO",
    "PAGAMENTO INTEGRALE",
    "ALGEHELE BETALING",
    "VOLLEDIGE BETALING",
    "全額支払",
    "SOLDE INTEGRAL FACTURES EN COURS",
    "PAYMENT OF ALL OUTSTANDING INVOICES",
    "REGLEMENT GLOBAL SOLDE",
],

# ================================================================
# DISCOUNT / ESCOMPTE
# ================================================================
"discount": [
    "REGLT {ref} ESC {pct}%",
    "PMT {ref} EARLY DISCOUNT {pct}%",
    "ZAHLUNG {ref} SKONTO {pct}%",
    "PAGO {ref} DESCUENTO {pct}%",
    "PAGAMENTO {ref} SCONTO {pct}%",
    "{ref} ESCOMPTE DEDUIT",
    "PAYMENT {ref} LESS {pct}% DISCOUNT",
    "REGLT {ref} DEDUCTION ESCOMPTE {pct} POUR CENT",
    "BETALING {ref} KORTING {pct}%",
    "SETTLEMENT {ref} MINUS EARLY PAY DISCOUNT",
    "{ref} CASH DISCOUNT TAKEN {pct}%",
    "REGLEMENT {ref} ESCOMPTE 2% CONTRACTUEL DEDUIT",
],

# ================================================================
# RETENTION (BTP / Construction)
# ================================================================
"retention": [
    "REGLT {ref} RET {pct}%",
    "REGLT CHANTIER {ref} RETENUE GARANTIE {pct}%",
    "PMT {ref} RETENTION {pct}%",
    "{ref} LESS RETENTION {pct}%",
    "ZAHLUNG {ref} EINBEHALT {pct}%",
    "PAGO {ref} RETENCION GARANTIA",
    "REGLEMENT {ref} SOUS DEDUCTION RG {pct}%",
    "PAYMENT {ref} RETENTION HELD PER CONTRACT",
    "{ref} NET OF {pct}% RETENTION",
    "REGLT MARCHE {ref} RETENUE DE GARANTIE",
    "CHANTIER {n} - REGLT {ref} - RG {pct}%",
    "REGLEMENT SITUATION {ref} RETENUE {pct}%",
],

# ================================================================
# RFA — Year-end rebate
# ================================================================
"rfa": [
    "REGLT {ref} RFA {pct}%",
    "REGLT {ref} DED RFA ANNUELLE",
    "PMT {ref} YEAR END REBATE {pct}%",
    "ZAHLUNG {ref} JAHRESBONUS {pct}%",
    "{ref} REMISE FIN ANNEE DEDUITE",
    "REGLEMENT {ref} DEDUCTION RFA CONTRACTUELLE",
    "PAYMENT {ref} ANNUAL VOLUME REBATE",
    "{ref} LESS ANNUAL REBATE PER AGREEMENT",
    "PAGO {ref} RAPPEL ANUAL {pct}%",
],

# ================================================================
# CREDIT NOTE — Avoir deducted
# ================================================================
"credit_note": [
    "REGLT {ref} DED {cn}",
    "REGLT {ref} DEDUCTION AVOIR {cn}",
    "PAYMENT {ref} LESS CREDIT NOTE {cn}",
    "{ref} NET OF CN {cn}",
    "ZAHLUNG {ref} ABZUG GUTSCHRIFT {cn}",
    "PAGO {ref} DEDUCCION NC {cn}",
    "PAGAMENTO {ref} DEDOTTA NC {cn}",
    "REGLEMENT {ref} SOUS DEDUCTION AVOIR {cn}",
    "BETALING {ref} MIN CREDITNOTA {cn}",
    "{ref} APRES DEDUCTION AVOIR {cn} DU {date}",
],

# ================================================================
# ROUNDING — Small delta
# ================================================================
"rounding": [
    "REGLT {ref}",
    "VIR {ref}",
    "VIREMENT {ref}",
    "PAYMENT {ref}",
    "ZAHLUNG {ref}",
    "BETALING {ref}",
    "PAGO {ref}",
    "PAGAMENTO {ref}",
],

# ================================================================
# SWIFT FEES — International transfer with fee deducted
# ================================================================
"swift_fees": [
    "REGLT {ref}",
    "PAYMENT {ref}",
    "VIREMENT {ref}",
    "TRANSFER {ref}",
    "WIRE {ref}",
    "ZAHLUNG {ref}",
    "ODEME {ref}",
    "TAHWIL {ref}",
    "SWIFT TRANSFER {ref}",
    "T/T {ref}",
    "TELEGRAPHIC TRANSFER {ref}",
],

# ================================================================
# WITHHOLDING TAX
# ================================================================
"wht": [
    "PAYMENT {ref}",
    "REGLEMENT {ref}",
    "TAHWIL {ref}",
    "ODEME {ref}",
    "HAVALE {ref}",
    "WIRE {ref}",
],

# ================================================================
# HT ERROR — Paid HT instead of TTC
# ================================================================
"ht_error": [
    "PAYMENT INVOICE {ref}",
    "SETTLEMENT {ref}",
    "ZAHLUNG RECHNUNG {ref}",
    "PAGO FACTURA {ref}",
    "BETALING FACTUUR {ref}",
],

# ================================================================
# SUBSET SUM — Multi-invoice grouped payment
# ================================================================
"subset_sum": [
    "REGLEMENT FACTURES EN COURS",
    "PAIEMENT GROUPE FACTURES",
    "VIR GLOBAL FACTURES OUVERTES",
    "PAYMENT MULTIPLE INVOICES",
    "SETTLEMENT OPEN INVOICES",
    "BULK PAYMENT OUTSTANDING",
    "SAMMELZAHLUNG RECHNUNGEN",
    "BETALING OPENSTAANDE FACTUREN",
    "PAGO FACTURAS PENDIENTES",
    "PAGAMENTO FATTURE IN SOSPESO",
    "REGLEMENT {n} FACTURES",
    "PAYMENT OF {n} INVOICES",
    "ZBIOROWY PRZELEW ZA FAKTURY",
    "VIR REGL FACTURES DIVERSES",
    "REGLT GLOBAL FACTURES A CE JOUR",
    "CLEARING OUTSTANDING BALANCE",
    "BATCH PAYMENT - {n} ITEMS",
    "REGLEMENT LOT DU {date}",
    "COMBINED PAYMENT REF {n}",
    "REGLEMENT RELEVE DU {date}",
    "PAIEMENT SELON RELEVE",
    "ZAHLUNG DIVERSE RECHNUNGEN",
    "一括支払い {n}件",
    "批量付款 {n}笔",
],

# ================================================================
# INSTALLMENT / ACOMPTE — Partial payment
# ================================================================
"installment_first": [
    "ACOMPTE {pct}% {ref}",
    "AVANCE {pct}% {ref}",
    "PARTIAL PMT {pct}% {ref}",
    "ADVANCE PAYMENT {pct}% {ref}",
    "ANZAHLUNG {pct}% {ref}",
    "PAGO ANTICIPADO {pct}% {ref}",
    "ACCONTO {pct}% {ref}",
    "1ERE ECHEANCE {ref}",
    "FIRST INSTALLMENT {ref}",
    "DOWN PAYMENT {ref}",
    "ACOMPTE SUR FACTURE {ref}",
    "VERSEMENT 1/2 {ref}",
    "DEPOSIT {pct}% {ref}",
    "AANBETALING {pct}% {ref}",
    "前払い {pct}% {ref}",
    "预付款 {pct}% {ref}",
],
"installment_final": [
    "SOLDE {pct}% {ref}",
    "FINAL PAYMENT {ref}",
    "BALANCE DUE {ref}",
    "RESTZAHLUNG {ref}",
    "SALDO {ref}",
    "DERNIER VERSEMENT {ref}",
    "2EME ECHEANCE {ref}",
    "COMPLEMENTO PAGO {ref}",
    "LAST INSTALLMENT {ref}",
    "REMAINING BALANCE {ref}",
    "VERSEMENT 2/2 {ref}",
    "RESTBETALING {ref}",
    "残金支払 {ref}",
    "尾款 {ref}",
],

# ================================================================
# TEMPORAL — Payment for a period
# ================================================================
"temporal": [
    "REGLEMENT FACTURES {month} {year}",
    "PAYMENT INVOICES {month_en} {year}",
    "ZAHLUNG RECHNUNGEN {month_de} {year}",
    "PAGO FACTURAS {month_es} {year}",
    "REGLT MENSUEL {month_short} {year}",
    "MONTHLY PAYMENT {month_en_short} {year}",
    "PAGAMENTO FATTURE {month_it} {year}",
    "BETALING FACTUREN {month_nl} {year}",
    "FACTURES DU MOIS DE {month}",
    "SETTLEMENT FOR {month_en} {year}",
    "REGLEMENT PERIODE {month_short}/{year}",
    "RELEVE MENSUEL {month} {year}",
    "PAIEMENT LOT {month} {year}",
    "{month} {year} INVOICES SETTLEMENT",
    "MONATLICHE ZAHLUNG {month_de} {year}",
],

# ================================================================
# CRYPTIC / OPAQUE — No useful info, bank or treasury internal
# ================================================================
"cryptic": [
    # FR trésorerie
    "TRESORERIE MVMT {n}", "REF INT {n}", "OP {n} VIR",
    "VIREMENT COMMERCIAL", "OPERATION TRESORERIE",
    "CREDIT COMPTE", "REMISE CHEQUES", "ENCAISSEMENT DIVERS",
    "REGUL COMPTA {n}", "ORD PERM {n}", "PRELEVEMENT {n}",
    "VERSEMENT {n}", "COMPENSATION {n}", "CLEARING {n}",
    "CENTRALISATION TRESORERIE", "NIVELLEMENT INTER-SOCIETES",
    "RAPATRIEMENT FONDS {n}", "DOTATION COMPTE {n}",
    "MOUVEMENT INTERNE REF {n}", "REGULARISATION ECART",
    "MOUVEMENT DIVERS", "PROV REGUL {n}",
    # EN corporate
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
    # DE
    "SAMMELÜBERWEISUNG {n}", "DAUERAUFTRAG {n}",
    "GUTSCHRIFT {n}", "ZAHLUNGSEINGANG {n}",
    "ÜBERWEISUNG INLAND {n}", "KONTOAUSGLEICH {n}",
    "VERRECHNUNGSKONTO {n}", "KONZERNCLEARING {n}",
    "INTERNE UMBUCHUNG {n}", "RECHNUNGSAUSGLEICH",
    "ZAHLUNG DIVERSE", "BANKEINZUG {n}",
    # NL
    "BETALING ONTVANGEN {n}", "OVERBOEKING {n}",
    "INCASSO {n}", "SPOEDBETALING {n}",
    "SALARISBETALING {n}", "INTERNE BOEKING {n}",
    "CREDITERING {n}", "VERREKENING FACTUREN",
    # ES
    "TRANSFERENCIA RECIBIDA {n}", "PAGO PROVEEDOR {n}",
    "ABONO EN CUENTA {n}", "LIQUIDACION {n}",
    "COBRO FACTURA", "INGRESO CHEQUE {n}",
    "TRASPASO INTERNO {n}", "COMPENSACION {n}",
    "RECIBO DOMICILIADO {n}", "GIRO COMERCIAL {n}",
    # IT
    "BONIFICO RICEVUTO {n}", "PAGAMENTO FORNITORE {n}",
    "ACCREDITO {n}", "INCASSO EFFETTI {n}",
    "GIROCONTO INTERNO {n}", "VERSAMENTO {n}",
    "COMPENSAZIONE {n}", "ADDEBITO DIRETTO {n}",
    # PT
    "TRANSFERÊNCIA RECEBIDA {n}", "PAGAMENTO FORNECEDOR {n}",
    "CRÉDITO EM CONTA {n}", "LIQUIDAÇÃO {n}",
    # TR
    "HAVALE GELEN {n}", "EFT ALINDI {n}",
    "ODEME {n}", "TAHSILAT {n}",
    "VIRMAN {n}", "FATURA ODEMESI {n}",
    # PL/CZ/HU
    "PRZELEW PRZYCHODZACY {n}", "PLATBA PRIJATA {n}",
    "ÁTUTALÁS {n}", "WPŁATA {n}",
    "INKASO {n}", "ELSZÁMOLÁS {n}",
    # JP/CN/KR
    "送金受領 {n}", "收到汇款 {n}", "입금확인 {n}",
    "TELEGRAPHIC TRANSFER {n}", "REMITTANCE ADVICE {n}",
    "T/T RECEIVED {n}",
    # Bank codes / opaque
    "MSG{n}PROC", "CLR{n}NET", "SETL{n}FIN",
    "REF//{n}//CRED", "NONREF", "/BNF/{n}",
    "NTRF {n}", "RNCN{n}", "BENM//NAME NOT PROVIDED",
    "{n}", "TX{n}ZZ", "BANQUE OP{n}",
    "CASH MGMT {n}", "VIRT {n}",
    # Bank routing noise prefixed
    "/RFB/{n}/NOTPROVIDED",
    "//CH{n}/CRED/BENEFICIARY",
    "E2E/{n}",
    "/TRTP/SEPA OVERBOEKING/IBAN/{n}",
    "/CNTP/{n}///NOTPROVIDED",
    "INST/{n}/UNKNOWN",
],

# ================================================================
# BANK NOISE PREFIXES — Added before a real label
# ================================================================
"noise_prefixes": [
    "/RFB/", "/ROC/", "E2E/", "//", "/BNF/",
    "NOTPROVIDED/", "/TRTP/SEPA/", "/CNTP/",
    "CRED/", "INST/",
],
}

# Write
out = Path(__file__).parent / "verbatims.json"
out.write_text(json.dumps(verbatims, indent=2, ensure_ascii=False), encoding="utf-8")

# Stats
total = 0
for k, v in verbatims.items():
    if isinstance(v, dict):
        n = sum(len(lst) for lst in v.values())
    elif isinstance(v, list):
        n = len(v)
    else:
        n = 0
    total += n
    print(f"  {k}: {n} templates")

print(f"\nTotal: {total} verbatim templates")
print(f"Written to: {out} ({out.stat().st_size // 1024} KB)")

