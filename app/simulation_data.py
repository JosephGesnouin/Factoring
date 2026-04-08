"""
Backend de donnees pour la demo Streamlit / HTML.
Genere massivement des donnees et execute la simulation.
Cible : 10 000+ paiements avec diversite maximale.
"""
from __future__ import annotations

import logging
import random
import time
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

import pandas as pd

logging.getLogger("reconciliation").setLevel(logging.CRITICAL)

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.models import (
    CreditNote, Currency, Debtor, Invoice, ISO20022Fields,
    Payment, PaymentSignals,
)
from reconciliation.config import ReconciliationConfig
from reconciliation.orchestrator import ReconciliationOrchestrator

# ============================================================
# CONSTANTES MASSIVES
# ============================================================

SEASONAL = {1:0.9, 2:0.85, 3:1.0, 4:1.0, 5:0.95, 6:0.90,
            7:0.80, 8:0.50, 9:1.0, 10:1.1, 11:1.3, 12:1.5}
MONTHS_FR = {1:"Janvier",2:"Fevrier",3:"Mars",4:"Avril",5:"Mai",6:"Juin",
             7:"Juillet",8:"Aout",9:"Septembre",10:"Octobre",11:"Novembre",12:"Decembre"}
TVA = {"FR":0.20,"DE":0.19,"IT":0.22,"ES":0.21,"SE":0.25,"PL":0.23,
       "GB":0.20,"MA":0.20,"TR":0.18,"BE":0.21,"NL":0.21,"CH":0.077,
       "US":0.0,"PT":0.23,"RO":0.19,"CZ":0.21,"TN":0.19,"DZ":0.19,
       "AT":0.20,"IE":0.23,"JP":0.10,"IN":0.18,"BR":0.17,"AE":0.05}
WHT = {"MA":0.20,"TR":0.18,"TN":0.15,"DZ":0.24,"IN":0.10,"BR":0.15}

STYLES = ["exemplaire","iso20022","btp_retention","distribution","bl_match",
          "international","multi_facture","po_match","installments","fuzzy_typos","temporel"]
SCENARIO_W = {
    "exemplaire":     {"C1_EXACT_REF":0.70,"C1_IBAN":0.15,"C2_ROUND":0.05,"C6":0.10},
    "iso20022":       {"C1_ISO":0.50,"C1_EXACT_REF":0.15,"C2_HT":0.10,"C3_FUZZY":0.05,"C6":0.20},
    "btp_retention":  {"C2_RETENTION":0.45,"C1_EXACT_REF":0.10,"C2_SUBSET":0.15,"C2_INSTALL":0.10,"C6":0.20},
    "distribution":   {"C2_DISCOUNT":0.25,"C2_RFA":0.10,"C2_CREDIT":0.10,"C2_SUBSET":0.15,"C1_EXACT_REF":0.15,"C6":0.25},
    "bl_match":       {"C1_BL":0.40,"C1_EXACT_REF":0.20,"C1_BALANCE":0.10,"C2_ROUND":0.10,"C6":0.20},
    "international":  {"C2_SWIFT":0.30,"C2_WHT":0.20,"C1_EXACT_REF":0.15,"C6":0.35},
    "multi_facture":  {"C2_SUBSET":0.40,"C1_EXACT_REF":0.10,"C3_FUZZY":0.10,"C6":0.40},
    "po_match":       {"C1_PO":0.50,"C1_EXACT_REF":0.20,"C2_ROUND":0.10,"C6":0.20},
    "installments":   {"C2_INSTALL":0.40,"C1_EXACT_REF":0.25,"C6":0.35},
    "fuzzy_typos":    {"C3_FUZZY":0.40,"C1_EXACT_REF":0.20,"C2_ROUND":0.10,"C6":0.30},
    "temporel":       {"C2_TEMPORAL":0.30,"C1_EXACT_REF":0.15,"C2_SUBSET":0.15,"C1_BALANCE":0.10,"C6":0.30},
}

# ── 50 debiteurs pre-definis pour diversite maximale ──
NAMES = [
    ("FR","Boulangerie Dupont","SARL","Alimentaire",30,(1000,12000),"exemplaire",0,0,0,2,0.95),
    ("FR","Construction Martin","SA","BTP",60,(15000,80000),"btp_retention",0,0.05,0,15,0.60),
    ("DE","Schmidt Import","GmbH","Import",30,(5000,35000),"iso20022",0,0,0,3,0.88),
    ("FR","Groupe Leclerc","SA","Distribution",45,(10000,90000),"distribution",0.02,0,0.03,5,0.80),
    ("IT","Rossi Transport","Srl","Transport",30,(3000,20000),"bl_match",0,0,0,7,0.75),
    ("MA","Maroc Export","SARL","Export",30,(5000,30000),"international",0,0,0,10,0.60),
    ("SE","Pharma Nordic","AB","Pharma",45,(8000,45000),"multi_facture",0,0,0,8,0.70),
    ("PL","AutoParts Polska","Sp. z o.o.","Automobile",30,(2000,25000),"po_match",0,0,0,4,0.85),
    ("GB","Tech Solutions","Ltd","IT Services",30,(8000,55000),"installments",0,0,0,5,0.80),
    ("ES","Iberia Foods","SL","Alimentaire",30,(1500,15000),"fuzzy_typos",0,0,0,6,0.70),
    ("TR","Istanbul Import","A.S.","Import",30,(4000,25000),"international",0,0,0,8,0.65),
    ("FR","Groupe Energie","SA","Energie",60,(15000,120000),"temporel",0,0,0,5,0.85),
    ("BE","Bruxelles Commerce","SA","Distribution",45,(5000,40000),"distribution",0.015,0,0.02,4,0.82),
    ("NL","Rotterdam Shipping","BV","Logistique",30,(3000,30000),"po_match",0,0,0,3,0.90),
    ("CH","Zurich Precision","AG","Industrie",30,(10000,80000),"iso20022",0,0,0,2,0.92),
    ("PT","Lisboa Logistics","Lda","Transport",30,(2000,18000),"bl_match",0,0,0,6,0.72),
    ("AT","Wien Maschinenbau","GmbH","Industrie",45,(8000,60000),"exemplaire",0,0,0,3,0.90),
    ("RO","Bucharest Manufacturing","SRL","Industrie",30,(3000,25000),"fuzzy_typos",0,0,0,7,0.68),
    ("CZ","Praha Engineering","s.r.o.","Industrie",30,(5000,40000),"exemplaire",0,0,0,4,0.87),
    ("IE","Dublin Pharma","Ltd","Pharma",30,(10000,70000),"iso20022",0,0,0,3,0.91),
    ("FR","Conserveries Nantaises","SAS","Alimentaire",30,(2000,15000),"exemplaire",0,0,0,2,0.94),
    ("FR","Menuiserie Bretagne","SARL","BTP",60,(8000,50000),"btp_retention",0,0.05,0,12,0.62),
    ("DE","Bayern Industrie","AG","Automobile",45,(5000,45000),"po_match",0,0,0,5,0.84),
    ("DE","Hamburg Logistics","KG","Logistique",30,(2000,22000),"bl_match",0,0,0,4,0.80),
    ("IT","Milano Fashion","SpA","Textile",30,(5000,50000),"fuzzy_typos",0,0,0,5,0.72),
    ("IT","Napoli Conserve","Srl","Alimentaire",30,(1000,12000),"exemplaire",0,0,0,4,0.88),
    ("ES","Valencia Ceramica","SL","Industrie",45,(3000,30000),"temporel",0,0,0,6,0.76),
    ("ES","Bilbao Aceros","SA","Metallurgie",60,(10000,70000),"multi_facture",0,0,0,8,0.65),
    ("GB","Birmingham Steel","PLC","Metallurgie",30,(8000,60000),"multi_facture",0,0,0,6,0.70),
    ("GB","Edinburgh Pharma","Ltd","Pharma",45,(15000,90000),"installments",0,0,0,4,0.82),
    ("US","Chicago Distribution","LLC","Distribution",30,(5000,50000),"distribution",0.01,0,0,5,0.78),
    ("US","Houston Energy","Corp","Energie",30,(20000,150000),"international",0,0,0,10,0.60),
    ("BR","Sao Paulo Trading","Ltda","Import",30,(3000,25000),"international",0,0,0,12,0.55),
    ("DZ","Alger Import","SPA","Import",30,(4000,20000),"international",0,0,0,10,0.58),
    ("TN","Sfax Industries","SA","Textile",45,(2000,15000),"international",0,0,0,11,0.56),
    ("IN","Mumbai Textiles","Pvt Ltd","Textile",30,(2000,18000),"international",0,0,0,9,0.62),
    ("JP","Tokyo Electronics","Co. Ltd","Electronique",30,(5000,40000),"iso20022",0,0,0,3,0.90),
    ("FR","Vins Bourgogne","SAS","Alimentaire",30,(3000,25000),"exemplaire",0,0,0,3,0.92),
    ("FR","Plastiques Grenoble","SA","Chimie",45,(5000,35000),"temporel",0,0,0,4,0.83),
    ("FR","Imprimerie Toulouse","SARL","Services",30,(1500,12000),"exemplaire",0,0,0,2,0.93),
    ("NL","Amsterdam Trading","NV","Import",30,(4000,35000),"iso20022",0,0,0,3,0.89),
    ("DZ","Oran Industries","SARL","Industrie",30,(3000,20000),"international",0,0,0,10,0.57),
    ("SE","Goteborg Volvo Parts","AB","Automobile",30,(5000,40000),"po_match",0,0,0,4,0.86),
    ("FR","BTP Atlantique","SAS","BTP",60,(12000,70000),"btp_retention",0,0.10,0,14,0.58),
    ("FR","Distribution Sud","SA","Distribution",45,(8000,60000),"distribution",0.02,0,0.03,5,0.79),
    ("BE","Anvers Diamant","SA","Luxe",30,(20000,200000),"exemplaire",0,0,0,2,0.95),
    ("PL","Gdansk Shipyard","SA","Transport",45,(10000,50000),"bl_match",0,0,0,6,0.74),
    ("FR","Agri Beauce","SARL","Agriculture",30,(2000,20000),"temporel",0,0,0,3,0.85),
    ("AE","Dubai Trading","FZCO","Import",30,(10000,80000),"international",0,0,0,7,0.68),
    ("FR","Fromageries du Jura","SAS","Alimentaire",30,(1500,10000),"exemplaire",0,0,0,2,0.96),
]

# ── Libelles de paiement ultra-diversifies ──
LABEL_PREFIX = {
    "FR":["REGLT","REGLEMENT","PAIEMENT","VIRT","VIREMENT","RGT","PMT","VIR SEPA",
          "REGL FACTURE","PAIEMENT FOURNISSEUR","VIR SCT","REGL ECHEANCE","PAIEMENT ECHEANCE"],
    "EN":["PAYMENT","PMT","WIRE TRANSFER","SETTLEMENT","REMITTANCE","BANK TRANSFER",
          "CREDIT TRANSFER","SUPPLIER PAYMENT","VENDOR PMT","TRADE PAYMENT","ACH PAYMENT",
          "FASTER PAYMENT","CHAPS PAYMENT","BACS CREDIT"],
    "DE":["ZAHLUNG","ÜBERWEISUNG","BEZAHLUNG","RECHNUNGSBEGLEICHUNG","GUTSCHRIFT",
          "SEPA-ÜBERWEISUNG","ZAHLUNGSAUSGLEICH","BANKÜBERWEISUNG"],
    "NL":["BETALING","OVERBOEKING","BETALING FACTUUR","CREDITOVERSCHRIJVING","SEPA OVERBOEKING"],
    "ES":["PAGO","TRANSFERENCIA","PAGO FACTURA","ABONO","LIQUIDACION","GIRO BANCARIO"],
    "IT":["PAGAMENTO","BONIFICO","PAGAMENTO FATTURA","SALDO FATTURA","ACCREDITO","BONIFICO SEPA"],
    "PT":["PAGAMENTO","TRANSFERENCIA","PAGAMENTO FATURA","LIQUIDACAO"],
    "TR":["ODEME","HAVALE","FATURA ODEMESI","EFT ODEMESI"],
    "PL":["PLATNOSC","PRZELEW","ZAPLATA FAKTURY","PRZELEW BANKOWY"],
    "AR":["TAHWIL","DAFA","TASDID FATOURA","SADDAD"],
    "JA":["振込","送金","お支払い","代金支払"],
}
COUNTRY_LANG = {
    "FR":"FR","BE":"FR","LU":"FR","CH":"DE","DE":"DE","AT":"DE",
    "NL":"NL","ES":"ES","IT":"IT","PT":"PT","BR":"PT","TR":"TR",
    "PL":"PL","CZ":"PL","MA":"AR","TN":"AR","DZ":"AR","AE":"AR",
    "GB":"EN","IE":"EN","US":"EN","SE":"EN","RO":"EN","JP":"JA","IN":"EN",
}

CRYPTIC = [
    "TRESORERIE MVMT {n}","REF INT {n}","VIREMENT COMMERCIAL","OP {n}",
    "TX{n}ZZ","CASH MGMT {n}","CREDIT COMPTE","MOUVEMENT DIVERS",
    "TREASURY TRANSFER {n}","WIRE TRANSFER {n}","SAMMELÜBERWEISUNG {n}",
    "BETALING {n}","TRANSFERENCIA {n}","BONIFICO {n}","CLEARING {n}",
    "NOSTRO CREDIT {n}","FX SETTLEMENT {n}","INTERCO {n}","SWEEP {n}",
    "DAUERAUFTRAG {n}","INCASSO {n}","COMPENSATION {n}","REGUL COMPTA {n}",
    "CENTRALISATION TRESORERIE","RAPATRIEMENT FONDS {n}","NIVELLEMENT",
    "PRZELEW {n}","HAVALE {n}","ACH {n}","BACS {n}","CHAPS {n}",
    "{n}","NONREF","BENM//NAME NOT PROVIDED","MSG{n}PROC","CLR{n}NET",
    "ORD PERM {n}","MOUVEMENT INTERNE {n}","ENCAISSEMENT DIVERS",
    "REMISE CHEQUES {n}","VERSEMENT {n}","PROVISION {n}",
    "OPERATION DIVERSE {n}","REGULARISATION {n}","CREDIT ADJUSTMENT {n}",
    "MISC CREDIT {n}","RETURN ITEM {n}","BANKEINZUG {n}",
    "ODEME {n}","TAHSILAT {n}","VIRMAN {n}","PLATBA {n}",
    "送金 {n}","汇款 {n}","입금 {n}",
]

def _pick(w, rng):
    return rng.choices(list(w.keys()), weights=list(w.values()), k=1)[0]

def _typo(ref, rng):
    c = list(ref)
    if len(c) < 5: return ref
    op = rng.choice(["swap","drop","0O","digit","double"])
    if op == "swap" and len(c)>5:
        i = rng.randint(2,len(c)-2); c[i],c[i+1] = c[i+1],c[i]
    elif op == "drop": c.pop(rng.randint(2,len(c)-1))
    elif op == "0O":
        for i,ch in enumerate(c):
            if ch == "0": c[i] = "O"; break
    elif op == "double":
        i = rng.randint(2,len(c)-1); c.insert(i, c[i])
    else:
        ds = [i for i,ch in enumerate(c) if ch.isdigit()]
        if ds: i = rng.choice(ds); c[i] = str((int(c[i])+rng.randint(1,3))%10)
    return "".join(c)

def _lbl(ref, country, rng):
    lang = COUNTRY_LANG.get(country, "EN")
    pool = LABEL_PREFIX.get(lang, LABEL_PREFIX["EN"])
    pre = rng.choice(pool)
    if rng.random() < 0.12:
        noise = rng.choice(["/RFB/","/ROC/","E2E/","//",f"/{rng.randint(100000,999999)}/"])
        return f"{noise}{pre} {ref}"
    return f"{pre} {ref}"


# ============================================================
# GENERATEUR PRINCIPAL — 10k+ paiements
# ============================================================

def generate_all(seed=42, months=range(1,13), target_payments=10000):
    """Generate massive dataset: ~10k+ payments."""
    rng = random.Random(seed)
    year = 2024

    # ── Debiteurs ──
    # Calculer inv_per_month pour atteindre ~target_payments
    # target = n_debtors * avg_inv_per_month * n_months * avg_seasonal
    n_debtors = len(NAMES)
    n_months = len(list(months))
    avg_seasonal = sum(SEASONAL.get(m,1) for m in months) / n_months
    target_inv = int(target_payments * 1.15)  # generate more invoices than payments
    avg_inv = max(5, int(target_inv / (n_debtors * n_months * avg_seasonal)))

    print(f"  Generating {n_debtors} debtors, ~{avg_inv} inv/month/debtor")

    debtors = []
    profiles = []
    for i, (country,name,suffix,sector,terms,amt_range,style,disc,ret,rfa,delay,reg) in enumerate(NAMES):
        did = f"D{i+1:03d}"
        # Scale inv_per_month to hit target
        inv_pm = max(3, int(avg_inv * rng.uniform(0.5, 1.5)))
        d = Debtor(
            id=did, name=f"{name} {suffix}",
            iban=f"{country}{rng.randint(10,99)}{''.join(str(rng.randint(0,9)) for _ in range(20))}",
            bic=f"BANK{country}XX", country=country, sector=sector,
            payment_terms=terms, discount_rate=disc, retention_rate=ret, rfa_rate=rfa,
            avg_payment_delay=delay, payment_regularity_score=reg,
            risk_score=round(max(0.05,min(0.95,1-reg+rng.uniform(-0.1,0.1))),2),
        )
        debtors.append(d)
        profiles.append({"did":did,"d":d,"style":style,"inv_pm":inv_pm,
                         "amt":amt_range,"disc":disc,"ret":ret,"rfa":rfa})

    # ── Factures ──
    invoices = []
    seq = 0
    for month in months:
        factor = SEASONAL.get(month, 1.0)
        am = ((month-1)%12)+1
        ay = year + (month-1)//12
        max_day = 28 if am==2 else 30 if am in (4,6,9,11) else 31
        for p in profiles:
            count = max(1, round(p["inv_pm"] * factor))
            lo, hi = p["amt"]
            tva = TVA.get(p["d"].country, 0.20)
            for _ in range(count):
                seq += 1
                ht = round(rng.uniform(lo,hi),2)
                ttc = round(ht*(1+tva),2)
                day = rng.choice([1,2,3,5,7,8,10,12,14,15,17,18,20,22,24,25,27,28])
                day = min(day, max_day)
                issue = date(ay,am,day)
                due = issue + timedelta(days=p["d"].payment_terms)
                did_num = int(p["did"][1:])
                inv = Invoice(
                    id=f"INV-{seq:06d}", reference=f"FAC-{ay}-{did_num:03d}{seq:05d}",
                    debtor_id=p["did"], amount=ttc, amount_ht=ht, currency=Currency.EUR,
                    issue_date=issue, due_date=due, batch_date=issue,
                    po_number=f"PO-{ay}-{rng.randint(10000,99999)}" if p["style"]=="po_match" else None,
                    bl_number=f"BL-{ay}-{rng.randint(10000,99999)}" if p["style"]=="bl_match" else None,
                )
                invoices.append(inv)
    invoices.sort(key=lambda i: i.issue_date)

    # ── Avoirs ──
    credit_notes = []
    cn_seq = 0
    for p in profiles:
        if p["disc"] > 0 or p["rfa"] > 0:
            dinv = [i for i in invoices if i.debtor_id == p["did"]]
            for _ in range(max(1, len(dinv)//8)):
                cn_seq += 1
                linked = rng.choice(dinv)
                credit_notes.append(CreditNote(
                    id=f"CN-{cn_seq:04d}", reference=f"AV-{year}-{cn_seq:04d}",
                    debtor_id=p["did"], amount=round(rng.uniform(300,min(8000,linked.amount*0.25)),2),
                    issue_date=linked.issue_date+timedelta(days=rng.randint(5,20)),
                    linked_invoice_ref=linked.reference,
                ))
    for d in debtors:
        d.open_credits = [cn for cn in credit_notes if cn.debtor_id == d.id]

    # ── Paiements ──
    payments = []
    pay_seq = 0
    consumed = set()
    cn_used = set()
    ground_truth = {}
    inv_by_d = defaultdict(list)
    for inv in invoices: inv_by_d[inv.debtor_id].append(inv)

    for p in profiles:
        d = p["d"]
        avail = sorted(inv_by_d[p["did"]], key=lambda i: i.due_date)
        weights = SCENARIO_W.get(p["style"], {"C1_EXACT_REF":0.5,"C6":0.5})
        idx = 0
        while idx < len(avail):
            inv = avail[idx]
            if inv.id in consumed: idx += 1; continue
            scenario = _pick(weights, rng)
            pay_seq += 1
            pid = f"PAY-{pay_seq:06d}"
            base_dt = inv.due_date + timedelta(days=int(d.avg_payment_delay + rng.gauss(0,3)))
            while base_dt.weekday() >= 5: base_dt += timedelta(days=1)
            dt = max(base_dt, date(year,1,15))

            def mkp(amt, label, refs, kw=None):
                pp = Payment(id=pid, amount=round(amt,2), currency=Currency.EUR, date=dt,
                    label_raw=label, label_normalized=label.upper(),
                    iban_source=d.iban, bic_source=d.bic or "",
                    debtor_id=d.id, debtor=d,
                    signals=PaymentSignals(raw_refs=[r.replace("-","").upper() for r in refs] if refs else []))
                if kw: pp.signals.keywords = kw
                return pp

            if scenario == "C1_EXACT_REF":
                payments.append(mkp(inv.amount, _lbl(inv.reference,d.country,rng), [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C1_ISO":
                pp = mkp(inv.amount, "", [])
                pp.iso20022 = ISO20022Fields(roc_ref=inv.reference)
                pp.signals.raw_refs = [inv.reference.replace("-","").upper()]
                payments.append(pp); consumed.add(inv.id); idx += 1
            elif scenario == "C1_IBAN":
                lang = COUNTRY_LANG.get(d.country,"EN")
                pool = {"FR":["VIREMENT","REGLEMENT","PAIEMENT","CREDIT COMPTE"],
                        "EN":["WIRE TRANSFER","PAYMENT","BANK TRANSFER","REMITTANCE"],
                        "DE":["ÜBERWEISUNG","ZAHLUNG","GUTSCHRIFT"],
                        "NL":["BETALING","OVERBOEKING"]}.get(lang,["PAYMENT","TRANSFER"])
                payments.append(mkp(inv.amount, rng.choice(pool), []))
                consumed.add(inv.id); idx += 1
            elif scenario == "C1_PO" and inv.po_number:
                po_lbl = rng.choice([f"REGLT COMMANDE {inv.po_number}",f"PMT PO {inv.po_number}",
                    f"PAYMENT ORDER {inv.po_number}",f"ZAHLUNG BESTELLUNG {inv.po_number}"])
                payments.append(mkp(inv.amount, po_lbl, [inv.po_number]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C1_BL" and inv.bl_number:
                bl_lbl = rng.choice([f"REGLEMENT {inv.bl_number}",f"PMT DELIVERY {inv.bl_number}",
                    f"ZAHLUNG LIEFERSCHEIN {inv.bl_number}",f"PAGAMENTO DDT {inv.bl_number}"])
                payments.append(mkp(inv.amount, bl_lbl, [inv.bl_number]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C1_BALANCE":
                rem = [i for i in avail[idx:] if i.id not in consumed][:8]
                if len(rem) >= 2:
                    lbl = rng.choice(["SOLDE TOTAL COMPTE","FULL BALANCE","KONTOAUSGLEICH",
                        "APUREMENT SOLDE","CLEARING ALL INVOICES"])
                    payments.append(mkp(sum(i.amount for i in rem), lbl, []))
                    for i in rem: consumed.add(i.id)
                    idx += len(rem)
                else: idx += 1; continue
            elif scenario == "C2_SWIFT":
                fee = round(rng.uniform(12,35),2)
                payments.append(mkp(inv.amount-fee, _lbl(inv.reference,d.country,rng), [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_WHT":
                rate = WHT.get(d.country, 0.15)
                payments.append(mkp(round(inv.amount*(1-rate),2), _lbl(inv.reference,d.country,rng), [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_DISCOUNT" and p["disc"] > 0:
                disc_lbl = rng.choice([f"REGLT {inv.reference} ESC {p['disc']*100:.0f}%",
                    f"PMT {inv.reference} DISCOUNT {p['disc']*100:.0f}%",
                    f"{inv.reference} ESCOMPTE DEDUIT",f"ZAHLUNG {inv.reference} SKONTO"])
                payments.append(mkp(round(inv.amount*(1-p["disc"]),2), disc_lbl, [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_RETENTION" and p["ret"] > 0:
                ret_lbl = rng.choice([f"REGLT {inv.reference} RET GAR {p['ret']*100:.0f}%",
                    f"PMT {inv.reference} RETENTION {p['ret']*100:.0f}%",
                    f"REGLT CHANTIER {inv.reference} RETENUE GARANTIE"])
                payments.append(mkp(round(inv.amount*(1-p["ret"]),2), ret_lbl, [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_RFA" and p["rfa"] > 0:
                rfa_lbl = rng.choice([f"REGLT {inv.reference} DED RFA",
                    f"PMT {inv.reference} YEAR END REBATE",f"{inv.reference} RFA ANNUELLE"])
                payments.append(mkp(round(inv.amount*(1-p["rfa"]),2), rfa_lbl, [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_CREDIT":
                ok = [cn for cn in credit_notes if cn.debtor_id==d.id and cn.id not in cn_used and cn.amount<inv.amount]
                if ok:
                    cn = ok[0]
                    payments.append(mkp(round(inv.amount-cn.amount,2),
                        f"REGLT {inv.reference} DED {cn.reference}", [inv.reference]))
                    consumed.add(inv.id); cn_used.add(cn.id); idx += 1
                else: idx += 1; continue
            elif scenario == "C2_ROUND":
                delta = round(rng.uniform(-0.99,0.99),2)
                if abs(delta) < 0.01: delta = 0.50
                payments.append(mkp(inv.amount+delta, _lbl(inv.reference,d.country,rng), [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_SUBSET":
                rem = [i for i in avail[idx:] if i.id not in consumed]
                n = min(rng.randint(2,4), len(rem))
                if n >= 2:
                    grp = rem[:n]
                    lbl = rng.choice(["REGLEMENT FACTURES EN COURS","PAYMENT MULTIPLE INVOICES",
                        "SAMMELZAHLUNG","PAGO FACTURAS PENDIENTES","BETALING OPENSTAANDE FACTUREN",
                        f"REGLEMENT {len(grp)} FACTURES","BULK PAYMENT"])
                    payments.append(mkp(round(sum(i.amount for i in grp),2), lbl, []))
                    for i in grp: consumed.add(i.id)
                    idx += n
                else: idx += 1; continue
            elif scenario == "C2_INSTALL":
                pct = rng.choice([0.30,0.50,0.70])
                amt1 = round(inv.amount*pct,2)
                lbl1 = rng.choice([f"ACOMPTE {int(pct*100)}% {inv.reference}",
                    f"ADVANCE {int(pct*100)}% {inv.reference}",f"ANZAHLUNG {int(pct*100)}% {inv.reference}",
                    f"DOWN PAYMENT {inv.reference}",f"1ERE ECHEANCE {inv.reference}"])
                payments.append(mkp(amt1, lbl1, [inv.reference],
                    kw={"partial":True,"advance":True,"credit_note":False,"final":False}))
                pay_seq += 1
                pid2 = f"PAY-{pay_seq:06d}"
                dt2 = dt + timedelta(days=rng.randint(15,30))
                while dt2.weekday()>=5: dt2 += timedelta(days=1)
                rest = round(inv.amount-amt1,2)
                lbl2 = rng.choice([f"SOLDE {int((1-pct)*100)}% {inv.reference}",
                    f"FINAL PAYMENT {inv.reference}",f"BALANCE DUE {inv.reference}",
                    f"2EME ECHEANCE {inv.reference}",f"RESTZAHLUNG {inv.reference}"])
                p2 = Payment(id=pid2, amount=rest, currency=Currency.EUR, date=dt2,
                    label_raw=lbl2, label_normalized=lbl2.upper(),
                    iban_source=d.iban, bic_source=d.bic or "",
                    debtor_id=d.id, debtor=d,
                    signals=PaymentSignals(raw_refs=[inv.reference.replace("-","").upper()],
                        keywords={"partial":False,"advance":False,"credit_note":False,"final":True}))
                payments.append(p2)
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_TEMPORAL":
                tm = inv.issue_date.month
                same = [i for i in avail[idx:] if i.id not in consumed and i.issue_date.month==tm][:6]
                if len(same) >= 2:
                    total = round(sum(i.amount for i in same),2)
                    mname = MONTHS_FR.get(tm,"").upper()
                    lbl = rng.choice([f"REGLEMENT FACTURES {mname} {inv.issue_date.year}",
                        f"PAYMENT INVOICES {mname} {inv.issue_date.year}",
                        f"ZAHLUNG RECHNUNGEN {mname}",f"PAGO FACTURAS {mname} {inv.issue_date.year}",
                        f"REGLT MENSUEL {mname[:3]} {inv.issue_date.year}"])
                    pp = mkp(total, lbl, [])
                    pp.signals.label_periods = [f"{mname} {inv.issue_date.year}"]
                    payments.append(pp)
                    for i in same: consumed.add(i.id)
                    idx += len(same)
                else: idx += 1; continue
            elif scenario == "C2_HT":
                payments.append(mkp(inv.amount_ht, f"PAYMENT INVOICE {inv.reference}", [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C3_FUZZY":
                typo = _typo(inv.reference, rng)
                lbl = rng.choice([f"REGLT {typo}",f"PMT {typo}",f"PAYMENT {typo}",
                    f"ZAHLUNG {typo}",f"BETALING {typo}",f"PAGO {typo}"])
                payments.append(mkp(inv.amount, lbl, [typo]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C6":
                tmpl = rng.choice(CRYPTIC)
                lbl = tmpl.format(n=rng.randint(1000,9999))
                amt = inv.amount if rng.random() < 0.3 else round(rng.uniform(500,80000),2)
                payments.append(mkp(amt, lbl, []))
                ground_truth[pid] = inv.reference
                if rng.random() < 0.3: consumed.add(inv.id)
                idx += 1
            else:
                payments.append(mkp(inv.amount, _lbl(inv.reference,d.country,rng), [inv.reference]))
                consumed.add(inv.id); idx += 1

    payments.sort(key=lambda pp: pp.date or date(year,1,1))
    print(f"  Generated: {len(invoices)} invoices, {len(payments)} payments")

    # ── Run orchestrator ──
    print(f"  Running orchestrator on {len(payments)} payments...")
    config = ReconciliationConfig()
    orch = ReconciliationOrchestrator(config)
    iban_map = {d.iban: d.id for d in debtors}
    inv_by_d2 = defaultdict(list)
    for inv in invoices: inv_by_d2[inv.debtor_id].append(inv)
    for d in debtors: d.open_invoices = inv_by_d2.get(d.id, [])
    orch.setup(invoices, debtors=debtors, iban_debtor_map=iban_map)

    open_inv = list(invoices)
    results = []
    t0 = time.time()
    for payment in payments:
        ctx = orch.process_payment(payment, open_inv)
        results.append(ctx)
        if ctx.final_match:
            mids = {inv.id for inv in ctx.final_match.invoices}
            open_inv = [inv for inv in open_inv if inv.id not in mids]
    wall = time.time() - t0
    print(f"  Done in {wall:.1f}s ({len(payments)/wall:.0f} payments/s)")

    # ── Build DataFrames ──
    rows = []
    for ctx in results:
        p = ctx.payment
        fm = ctx.final_match
        rows.append({
            "payment_id": p.id, "date": p.date,
            "month": p.date.month if p.date else 0,
            "month_name": MONTHS_FR.get(p.date.month,"") if p.date else "",
            "amount": p.amount, "label": p.label_raw,
            "debtor_id": p.debtor_id, "debtor_name": p.debtor.name if p.debtor else "",
            "country": p.debtor.country if p.debtor else "",
            "sector": p.debtor.sector if p.debtor else "",
            "matched": fm is not None,
            "layer": fm.layer if fm else 6,
            "layer_name": f"C{fm.layer}" if fm else "C6",
            "method": fm.method.value if fm else "HUMAN_REVIEW",
            "confidence": fm.confidence if fm else 0.0,
            "flags": ", ".join(fm.flags) if fm and fm.flags else "",
            "invoices_matched": ", ".join(inv.reference for inv in fm.invoices) if fm else "",
            "n_invoices": len(fm.invoices) if fm else 0,
            "time_ms": fm.processing_time_ms if fm else 0,
            "layers_attempted": str(ctx.layers_attempted),
        })
    df = pd.DataFrame(rows)

    debtor_rows = [{"id":p["did"],"name":p["d"].name,"country":p["d"].country,
                    "sector":p["d"].sector,"style":p["style"],"terms":p["d"].payment_terms,
                    "delay":p["d"].avg_payment_delay,"regularity":p["d"].payment_regularity_score,
                    "discount":p["disc"],"retention":p["ret"],"rfa":p["rfa"]}
                   for p in profiles]
    df_debtors = pd.DataFrame(debtor_rows)
    m = orch.metrics

    return {
        "df": df, "df_inv": pd.DataFrame(), "df_debtors": df_debtors,
        "metrics": m, "results": results, "invoices": invoices,
        "payments": payments, "debtors": debtors, "wall_time": wall,
        "n_invoices": len(invoices), "n_payments": len(payments),
        "n_debtors": len(debtors), "credit_notes": credit_notes,
        "ground_truth": ground_truth,
    }
