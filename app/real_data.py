"""
Backend Streamlit pour les données de production.

Reproduit exactement la forme du dict renvoyé par
``app.simulation_data.generate_all()`` mais alimenté par les CSV réels
chargés via ``reconciliation.loaders``.

Clés retournées identiques à ``generate_all`` :
    df, df_inv, df_debtors, metrics, results, invoices, payments,
    debtors, wall_time, n_invoices, n_payments, n_debtors,
    credit_notes, ground_truth, debtor_profiles
"""
from __future__ import annotations

import logging
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.config import ReconciliationConfig
from reconciliation.loaders import load_from_dir
from reconciliation.orchestrator import ReconciliationOrchestrator

logger = logging.getLogger(__name__)
logging.getLogger("reconciliation").setLevel(logging.WARNING)

MONTHS_FR = {1:"Janvier",2:"Fevrier",3:"Mars",4:"Avril",5:"Mai",6:"Juin",
             7:"Juillet",8:"Aout",9:"Septembre",10:"Octobre",11:"Novembre",12:"Decembre"}


def run_real(data_dir: str | Path, payments_limit: int | None = None) -> dict[str, Any]:
    """Charge les 3 CSV depuis ``data_dir`` et exécute le pipeline complet.

    Retourne le même dict que ``app.simulation_data.generate_all``.
    """
    data_dir = Path(data_dir)
    loaded = load_from_dir(data_dir, payments_limit=payments_limit)
    debtors  = loaded.debtors
    invoices = loaded.invoices
    payments = loaded.payments
    iban_map = loaded.iban_map

    # Pré-indexation : invoices par débiteur (utilisé par C1-R005 solde total)
    inv_by_debtor = defaultdict(list)
    for inv in invoices:
        inv_by_debtor[inv.debtor_id].append(inv)
    for d in debtors:
        d.open_invoices = inv_by_debtor.get(d.id, [])

    # Pipeline
    config = ReconciliationConfig()
    orch = ReconciliationOrchestrator(config)
    orch.setup(invoices, debtors=debtors, iban_debtor_map=iban_map)

    t0 = time.time()
    results = orch.process_batch(payments, invoices, rebuild_every=100)
    wall = time.time() - t0
    orch.debtor_profiler.learn(results)

    # ── DataFrame paiements (compatible avec toutes les pages Streamlit) ──
    rows = []
    for ctx in results:
        p = ctx.payment
        fm = ctx.final_match
        d = next((dd for dd in debtors if dd.id == p.debtor_id), None) if p.debtor_id else None
        rows.append({
            "payment_id": p.id,
            "date": p.date,
            "month": p.date.month if p.date else 0,
            "month_name": MONTHS_FR.get(p.date.month, "") if p.date else "",
            "amount": p.amount,
            "label": p.label_raw,
            "debtor_id": p.debtor_id or "",
            "debtor_name": d.name if d else "",
            "country": (d.country if d else "") or "",
            "sector": (d.sector if d else "") or "",
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

    # ── DataFrame débiteurs ──
    df_debtors = pd.DataFrame([{
        "id": d.id, "name": d.name, "country": d.country or "",
        "sector": d.sector or "", "style": "real",
        "terms": d.payment_terms,
        "delay": d.avg_payment_delay,
        "regularity": d.payment_regularity_score,
        "discount": d.discount_rate, "retention": d.retention_rate,
        "rfa": d.rfa_rate,
    } for d in debtors])

    # ── DataFrame factures ──
    df_inv = pd.DataFrame([{
        "id": inv.id, "reference": inv.reference,
        "debtor_id": inv.debtor_id,
        "amount": inv.amount, "currency": inv.currency.value,
        "issue_date": inv.issue_date, "due_date": inv.due_date,
        "po": inv.po_number or "", "bl": inv.bl_number or "",
        "balance": inv.metadata.get("balance"),
    } for inv in invoices])

    return {
        "df": df,
        "df_inv": df_inv,
        "df_debtors": df_debtors,
        "metrics": orch.metrics,
        "results": results,
        "invoices": invoices,
        "payments": payments,
        "debtors": debtors,
        "wall_time": wall,
        "n_invoices": len(invoices),
        "n_payments": len(payments),
        "n_debtors": len(debtors),
        "credit_notes": [],
        "ground_truth": {},
        "debtor_profiles": {
            k: v.to_dict() for k, v in orch.debtor_profiler.profiles.items()
        },
    }
