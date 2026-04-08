"""
Backend de donnees pour la demo Streamlit.
Genere les donnees et execute la simulation, cache les resultats.
"""
from __future__ import annotations

import logging
import random
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
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


# ── Debtor profiles for the demo (curated, not random) ──

DEBTOR_PROFILES = [
    {"id": "D01", "name": "Boulangerie Dupont SARL", "country": "FR", "sector": "Alimentaire",
     "terms": 30, "style": "exemplaire", "inv_per_month": 6, "amount": (1000, 12000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 2, "regularity": 0.95},
    {"id": "D02", "name": "Construction Martin SA", "country": "FR", "sector": "BTP",
     "terms": 60, "style": "btp_retention", "inv_per_month": 4, "amount": (15000, 80000),
     "discount": 0, "retention": 0.05, "rfa": 0, "delay": 15, "regularity": 0.60},
    {"id": "D03", "name": "Schmidt Import GmbH", "country": "DE", "sector": "Import",
     "terms": 30, "style": "iso20022", "inv_per_month": 5, "amount": (5000, 35000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 3, "regularity": 0.88},
    {"id": "D04", "name": "Groupe Leclerc Distribution", "country": "FR", "sector": "Distribution",
     "terms": 45, "style": "distribution", "inv_per_month": 8, "amount": (10000, 90000),
     "discount": 0.02, "retention": 0, "rfa": 0.03, "delay": 5, "regularity": 0.80},
    {"id": "D05", "name": "Rossi Transport Srl", "country": "IT", "sector": "Transport",
     "terms": 30, "style": "bl_match", "inv_per_month": 4, "amount": (3000, 20000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 7, "regularity": 0.75},
    {"id": "D06", "name": "Maroc Export SARL", "country": "MA", "sector": "Export",
     "terms": 30, "style": "international", "inv_per_month": 3, "amount": (5000, 30000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 10, "regularity": 0.60},
    {"id": "D07", "name": "Pharma Nordic AB", "country": "SE", "sector": "Pharma",
     "terms": 45, "style": "multi_facture", "inv_per_month": 5, "amount": (8000, 45000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 8, "regularity": 0.70},
    {"id": "D08", "name": "AutoParts Polska Sp. z o.o.", "country": "PL", "sector": "Automobile",
     "terms": 30, "style": "po_match", "inv_per_month": 5, "amount": (2000, 25000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 4, "regularity": 0.85},
    {"id": "D09", "name": "Tech Solutions Ltd", "country": "GB", "sector": "IT Services",
     "terms": 30, "style": "installments", "inv_per_month": 3, "amount": (8000, 55000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 5, "regularity": 0.80},
    {"id": "D10", "name": "Iberia Foods SL", "country": "ES", "sector": "Alimentaire",
     "terms": 30, "style": "fuzzy_typos", "inv_per_month": 5, "amount": (1500, 15000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 6, "regularity": 0.70},
    {"id": "D11", "name": "Istanbul Import A.S.", "country": "TR", "sector": "Import",
     "terms": 30, "style": "international", "inv_per_month": 3, "amount": (4000, 25000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 8, "regularity": 0.65},
    {"id": "D12", "name": "Groupe Energie SA", "country": "FR", "sector": "Energie",
     "terms": 60, "style": "temporel", "inv_per_month": 6, "amount": (15000, 120000),
     "discount": 0, "retention": 0, "rfa": 0, "delay": 5, "regularity": 0.85},
]

TVA = {"FR": 0.20, "DE": 0.19, "IT": 0.22, "ES": 0.21, "SE": 0.25, "PL": 0.23,
       "GB": 0.20, "MA": 0.20, "TR": 0.18}

SCENARIO_WEIGHTS = {
    "exemplaire":     {"C1_EXACT_REF": 0.70, "C1_IBAN": 0.15, "C2_ROUND": 0.05, "C6": 0.10},
    "btp_retention":  {"C2_RETENTION": 0.45, "C1_EXACT_REF": 0.10, "C2_SUBSET": 0.15, "C2_INSTALL": 0.10, "C6": 0.20},
    "iso20022":       {"C1_ISO": 0.50, "C1_EXACT_REF": 0.15, "C2_HT": 0.10, "C3_FUZZY": 0.05, "C6": 0.20},
    "distribution":   {"C2_DISCOUNT": 0.25, "C2_RFA": 0.10, "C2_CREDIT": 0.10, "C2_SUBSET": 0.15, "C1_EXACT_REF": 0.15, "C6": 0.25},
    "bl_match":       {"C1_BL": 0.40, "C1_EXACT_REF": 0.20, "C1_BALANCE": 0.10, "C2_ROUND": 0.10, "C6": 0.20},
    "international":  {"C2_SWIFT": 0.30, "C2_WHT": 0.20, "C1_EXACT_REF": 0.15, "C6": 0.35},
    "multi_facture":  {"C2_SUBSET": 0.40, "C1_EXACT_REF": 0.10, "C3_FUZZY": 0.10, "C6": 0.40},
    "po_match":       {"C1_PO": 0.50, "C1_EXACT_REF": 0.20, "C2_ROUND": 0.10, "C6": 0.20},
    "installments":   {"C2_INSTALL": 0.40, "C1_EXACT_REF": 0.25, "C6": 0.35},
    "fuzzy_typos":    {"C3_FUZZY": 0.40, "C1_EXACT_REF": 0.20, "C2_ROUND": 0.10, "C6": 0.30},
    "temporel":       {"C2_TEMPORAL": 0.30, "C1_EXACT_REF": 0.15, "C2_SUBSET": 0.15, "C1_BALANCE": 0.10, "C6": 0.30},
}

MONTHS_FR = {1:"Janvier",2:"Fevrier",3:"Mars",4:"Avril",5:"Mai",6:"Juin",
             7:"Juillet",8:"Aout",9:"Septembre",10:"Octobre",11:"Novembre",12:"Decembre"}
SEASONAL = {1:0.9, 2:0.85, 3:1.0, 4:1.0, 5:0.95, 6:0.90, 7:0.80, 8:0.50, 9:1.0, 10:1.1, 11:1.3, 12:1.5}

WHT_RATES = {"MA": 0.20, "TR": 0.18, "TN": 0.15}

REF_LABELS = ["REGLT","REGLEMENT","PAIEMENT","VIREMENT","PMT","VIR SEPA","RGT"]
CRYPTIC = ["TRESORERIE MVMT {n}","REF INT {n}","VIREMENT COMMERCIAL","OP {n}",
           "TX{n}ZZ","CASH MGMT {n}","CREDIT COMPTE","MOUVEMENT DIVERS",
           "TREASURY TRANSFER {n}","WIRE TRANSFER {n}","SAMMELÜBERWEISUNG {n}",
           "BETALING {n}","TRANSFERENCIA {n}","BONIFICO {n}"]


def _pick(weights, rng):
    items = list(weights.keys())
    probs = list(weights.values())
    return rng.choices(items, weights=probs, k=1)[0]


def _typo(ref, rng):
    chars = list(ref)
    if len(chars) < 5: return ref
    op = rng.choice(["swap","drop","0O","digit"])
    if op == "swap":
        i = rng.randint(2, len(chars)-2)
        chars[i], chars[i+1] = chars[i+1], chars[i]
    elif op == "drop":
        chars.pop(rng.randint(2, len(chars)-1))
    elif op == "0O":
        for i,c in enumerate(chars):
            if c == "0": chars[i] = "O"; break
    else:
        ds = [i for i,c in enumerate(chars) if c.isdigit()]
        if ds:
            i = rng.choice(ds)
            chars[i] = str((int(chars[i])+rng.randint(1,3))%10)
    return "".join(chars)


def generate_all(seed=42, months=range(1,13)):
    """Generate invoices, payments, run simulation, return DataFrames."""
    rng = random.Random(seed)
    year = 2024

    # Build debtors
    debtors = []
    for dp in DEBTOR_PROFILES:
        d = Debtor(
            id=dp["id"], name=dp["name"],
            iban=f"{dp['country']}{rng.randint(10,99)}{''.join(str(rng.randint(0,9)) for _ in range(20))}",
            bic=f"BANK{dp['country']}XX", country=dp["country"], sector=dp["sector"],
            payment_terms=dp["terms"], discount_rate=dp["discount"],
            retention_rate=dp["retention"], rfa_rate=dp["rfa"],
            avg_payment_delay=dp["delay"], payment_regularity_score=dp["regularity"],
            risk_score=round(1-dp["regularity"]+rng.uniform(-0.1,0.1), 2),
        )
        debtors.append(d)

    # Generate invoices
    invoices = []
    seq = 0
    for month in months:
        factor = SEASONAL.get(month, 1.0)
        am, ay = ((month-1)%12)+1, year+(month-1)//12
        max_day = 28 if am == 2 else 30 if am in (4,6,9,11) else 31
        for dp, debtor in zip(DEBTOR_PROFILES, debtors):
            count = max(1, round(dp["inv_per_month"] * factor))
            lo, hi = dp["amount"]
            tva = TVA.get(dp["country"], 0.20)
            for _ in range(count):
                seq += 1
                ht = round(rng.uniform(lo, hi), 2)
                ttc = round(ht * (1+tva), 2)
                day = rng.choice([1,3,5,8,10,12,15,18,20,22,25])
                day = min(day, max_day)
                issue = date(ay, am, day)
                due = issue + timedelta(days=dp["terms"])
                inv = Invoice(
                    id=f"INV-{seq:05d}", reference=f"FAC-{ay}-{int(dp['id'][1:]):02d}{seq:04d}",
                    debtor_id=dp["id"], amount=ttc, amount_ht=ht, currency=Currency.EUR,
                    issue_date=issue, due_date=due, batch_date=issue,
                    po_number=f"PO-{ay}-{rng.randint(10000,99999)}" if dp["style"]=="po_match" else None,
                    bl_number=f"BL-{ay}-{rng.randint(10000,99999)}" if dp["style"]=="bl_match" else None,
                )
                invoices.append(inv)

    # Generate credit notes for D04
    credit_notes = []
    d04_invs = [i for i in invoices if i.debtor_id == "D04"]
    for i in range(min(8, len(d04_invs)//6)):
        linked = rng.choice(d04_invs)
        cn = CreditNote(id=f"CN-{i+1:03d}", reference=f"AV-2024-{i+1:03d}",
                        debtor_id="D04", amount=round(rng.uniform(500,5000),2),
                        issue_date=linked.issue_date+timedelta(days=rng.randint(5,20)),
                        linked_invoice_ref=linked.reference)
        credit_notes.append(cn)
    for d in debtors:
        if d.id == "D04":
            d.open_credits = credit_notes

    # Generate payments
    payments = []
    pay_seq = 0
    consumed = set()
    cn_used = set()
    ground_truth = {}  # payment_id -> intended invoice reference (for C6 payments)
    inv_by_d = defaultdict(list)
    for inv in invoices:
        inv_by_d[inv.debtor_id].append(inv)

    for dp, debtor in zip(DEBTOR_PROFILES, debtors):
        avail = sorted(inv_by_d[dp["id"]], key=lambda i: i.due_date)
        weights = SCENARIO_WEIGHTS.get(dp["style"], {"C1_EXACT_REF": 0.50, "C6": 0.50})
        idx = 0
        while idx < len(avail):
            inv = avail[idx]
            if inv.id in consumed: idx += 1; continue
            scenario = _pick(weights, rng)
            pay_seq += 1
            pid = f"PAY-{pay_seq:05d}"
            base_dt = inv.due_date + timedelta(days=int(dp["delay"] + rng.gauss(0,3)))
            while base_dt.weekday() >= 5: base_dt += timedelta(days=1)
            dt = max(base_dt, date(year, 1, 15))

            def mkp(amt, label, refs, kw=None):
                p = Payment(id=pid, amount=round(amt,2), currency=Currency.EUR, date=dt,
                    label_raw=label, label_normalized=label.upper(),
                    iban_source=debtor.iban, bic_source=debtor.bic or "",
                    debtor_id=debtor.id, debtor=debtor,
                    signals=PaymentSignals(raw_refs=[r.replace("-","").upper() for r in refs] if refs else []))
                if kw: p.signals.keywords = kw
                return p

            if scenario == "C1_EXACT_REF":
                payments.append(mkp(inv.amount, f"{rng.choice(REF_LABELS)} {inv.reference}", [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C1_ISO":
                p = mkp(inv.amount, "", [])
                p.iso20022 = ISO20022Fields(roc_ref=inv.reference)
                p.signals.raw_refs = [inv.reference.replace("-","").upper()]
                payments.append(p); consumed.add(inv.id); idx += 1
            elif scenario == "C1_IBAN":
                payments.append(mkp(inv.amount, "VIREMENT COMMERCIAL", []))
                consumed.add(inv.id); idx += 1
            elif scenario == "C1_PO" and inv.po_number:
                payments.append(mkp(inv.amount, f"REGLT COMMANDE {inv.po_number}", [inv.po_number]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C1_BL" and inv.bl_number:
                payments.append(mkp(inv.amount, f"REGLEMENT {inv.bl_number}", [inv.bl_number]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C1_BALANCE":
                rem = [i for i in avail[idx:] if i.id not in consumed][:8]
                if len(rem) >= 2:
                    payments.append(mkp(sum(i.amount for i in rem), "SOLDE TOTAL COMPTE", []))
                    for i in rem: consumed.add(i.id)
                    idx += len(rem)
                else: idx += 1; continue
            elif scenario == "C2_SWIFT":
                fee = round(rng.uniform(15,35),2)
                payments.append(mkp(inv.amount-fee, f"{rng.choice(REF_LABELS)} {inv.reference}", [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_WHT":
                rate = WHT_RATES.get(dp["country"], 0.15)
                payments.append(mkp(round(inv.amount*(1-rate),2), f"PAYMENT {inv.reference}", [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_DISCOUNT" and dp["discount"] > 0:
                payments.append(mkp(round(inv.amount*(1-dp["discount"]),2), f"REGLT {inv.reference} ESC {dp['discount']*100:.0f}%", [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_RETENTION" and dp["retention"] > 0:
                payments.append(mkp(round(inv.amount*(1-dp["retention"]),2), f"REGLT {inv.reference} RET GAR {dp['retention']*100:.0f}%", [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_RFA" and dp["rfa"] > 0:
                payments.append(mkp(round(inv.amount*(1-dp["rfa"]),2), f"REGLT {inv.reference} DED RFA", [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_CREDIT":
                ok = [cn for cn in credit_notes if cn.id not in cn_used and cn.amount < inv.amount]
                if ok:
                    cn = ok[0]
                    payments.append(mkp(round(inv.amount-cn.amount,2), f"REGLT {inv.reference} DED {cn.reference}", [inv.reference]))
                    consumed.add(inv.id); cn_used.add(cn.id); idx += 1
                else: idx += 1; continue
            elif scenario == "C2_ROUND":
                delta = round(rng.uniform(-0.99,0.99),2)
                if abs(delta) < 0.01: delta = 0.50
                payments.append(mkp(inv.amount+delta, f"{rng.choice(REF_LABELS)} {inv.reference}", [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_SUBSET":
                rem = [i for i in avail[idx:] if i.id not in consumed]
                n = min(rng.randint(2,4), len(rem))
                if n >= 2:
                    grp = rem[:n]
                    payments.append(mkp(round(sum(i.amount for i in grp),2), "REGLEMENT FACTURES EN COURS", []))
                    for i in grp: consumed.add(i.id)
                    idx += n
                else: idx += 1; continue
            elif scenario == "C2_INSTALL":
                pct = rng.choice([0.30, 0.50, 0.70])
                amt1 = round(inv.amount * pct, 2)
                payments.append(mkp(amt1, f"ACOMPTE {int(pct*100)}% {inv.reference}", [inv.reference],
                    kw={"partial":True,"advance":True,"credit_note":False,"final":False}))
                pay_seq += 1
                pid2 = f"PAY-{pay_seq:05d}"
                dt2 = dt + timedelta(days=rng.randint(15,30))
                while dt2.weekday() >= 5: dt2 += timedelta(days=1)
                rest = round(inv.amount - amt1, 2)
                p2 = Payment(id=pid2, amount=rest, currency=Currency.EUR, date=dt2,
                    label_raw=f"SOLDE {int((1-pct)*100)}% {inv.reference}",
                    label_normalized=f"SOLDE {int((1-pct)*100)}% {inv.reference}".upper(),
                    iban_source=debtor.iban, bic_source=debtor.bic or "",
                    debtor_id=debtor.id, debtor=debtor,
                    signals=PaymentSignals(raw_refs=[inv.reference.replace("-","").upper()],
                        keywords={"partial":False,"advance":False,"credit_note":False,"final":True}))
                payments.append(p2)
                consumed.add(inv.id); idx += 1
            elif scenario == "C2_TEMPORAL":
                tm = inv.issue_date.month
                same = [i for i in avail[idx:] if i.id not in consumed and i.issue_date.month == tm][:6]
                if len(same) >= 2:
                    total = round(sum(i.amount for i in same),2)
                    mname = MONTHS_FR.get(tm, str(tm)).upper()
                    p = mkp(total, f"REGLEMENT FACTURES {mname} {inv.issue_date.year}", [])
                    p.signals.label_periods = [f"{mname} {inv.issue_date.year}"]
                    payments.append(p)
                    for i in same: consumed.add(i.id)
                    idx += len(same)
                else: idx += 1; continue
            elif scenario == "C2_HT":
                payments.append(mkp(inv.amount_ht, f"PAYMENT INVOICE {inv.reference}", [inv.reference]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C3_FUZZY":
                typo = _typo(inv.reference, rng)
                payments.append(mkp(inv.amount, f"REGLT {typo}", [typo]))
                consumed.add(inv.id); idx += 1
            elif scenario == "C6":
                tmpl = rng.choice(CRYPTIC)
                label = tmpl.format(n=rng.randint(1000,9999))
                amt = inv.amount if rng.random() < 0.3 else round(rng.uniform(500,50000),2)
                payments.append(mkp(amt, label, []))
                ground_truth[pid] = inv.reference  # track the intended invoice
                if rng.random() < 0.3: consumed.add(inv.id)
                idx += 1
            else:
                payments.append(mkp(inv.amount, f"{rng.choice(REF_LABELS)} {inv.reference}", [inv.reference]))
                consumed.add(inv.id); idx += 1

    payments.sort(key=lambda p: p.date or date(year,1,1))

    # Run orchestrator
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
            matched_ids = {inv.id for inv in ctx.final_match.invoices}
            open_inv = [inv for inv in open_inv if inv.id not in matched_ids]
    wall = time.time() - t0

    # Build DataFrames
    rows = []
    for ctx in results:
        p = ctx.payment
        fm = ctx.final_match
        rows.append({
            "payment_id": p.id,
            "date": p.date,
            "month": p.date.month if p.date else 0,
            "month_name": MONTHS_FR.get(p.date.month, "") if p.date else "",
            "amount": p.amount,
            "label": p.label_raw,
            "debtor_id": p.debtor_id,
            "debtor_name": p.debtor.name if p.debtor else "",
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

    inv_rows = []
    for inv in invoices:
        inv_rows.append({
            "invoice_id": inv.id, "reference": inv.reference,
            "debtor_id": inv.debtor_id, "amount": inv.amount,
            "amount_ht": inv.amount_ht, "issue_date": inv.issue_date,
            "due_date": inv.due_date,
        })
    df_inv = pd.DataFrame(inv_rows)

    debtor_rows = []
    for dp in DEBTOR_PROFILES:
        debtor_rows.append({
            "id": dp["id"], "name": dp["name"], "country": dp["country"],
            "sector": dp["sector"], "style": dp["style"], "terms": dp["terms"],
            "delay": dp["delay"], "regularity": dp["regularity"],
            "discount": dp["discount"], "retention": dp["retention"], "rfa": dp["rfa"],
        })
    df_debtors = pd.DataFrame(debtor_rows)

    metrics = orch.metrics

    return {
        "df": df,
        "df_inv": df_inv,
        "df_debtors": df_debtors,
        "metrics": metrics,
        "results": results,
        "invoices": invoices,
        "payments": payments,
        "debtors": debtors,
        "wall_time": wall,
        "n_invoices": len(invoices),
        "n_payments": len(payments),
        "n_debtors": len(debtors),
        "credit_notes": credit_notes,
        "ground_truth": ground_truth,
    }
