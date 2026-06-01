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
import os
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.config import ReconciliationConfig
from reconciliation.diagnose import run_diagnostic
from reconciliation.loaders import load_from_dir
from reconciliation.orchestrator import ReconciliationOrchestrator

logger = logging.getLogger(__name__)

# ── Logging ultra verbeux pour debug réel ──────────────────────────────
# Activé par défaut quand on est en mode données réelles. Désactivable
# via FACTORING_QUIET=1.
def _setup_logging() -> None:
    if os.environ.get("FACTORING_QUIET") == "1":
        return
    level = logging.DEBUG if os.environ.get("FACTORING_DEBUG") == "1" else logging.INFO
    root = logging.getLogger()
    # Évite la double config si Streamlit a déjà setup le root logger.
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))
        root.addHandler(h)
    root.setLevel(level)
    logging.getLogger("reconciliation").setLevel(level)


_setup_logging()


MONTHS_FR = {1:"Janvier",2:"Fevrier",3:"Mars",4:"Avril",5:"Mai",6:"Juin",
             7:"Juillet",8:"Aout",9:"Septembre",10:"Octobre",11:"Novembre",12:"Decembre"}


def run_real(data_dir: str | Path, payments_limit: int | None = None) -> dict[str, Any]:
    """Charge les 3 CSV depuis ``data_dir`` et exécute le pipeline complet.

    Retourne le même dict que ``app.simulation_data.generate_all``.

    À la fin, imprime un rapport diagnostic exhaustif sur stdout et
    écrit le même rapport dans ``<data_dir>/factoring_logs_<timestamp>.txt``.
    """
    data_dir = Path(data_dir)
    t_start = time.time()

    logger.info("=" * 78)
    logger.info(" PIPELINE FACTORING — RUN DÉMARRAGE")
    logger.info("=" * 78)
    logger.info("Data dir : %s", data_dir.resolve())

    loaded = load_from_dir(data_dir, payments_limit=payments_limit)
    debtors  = loaded.debtors
    invoices = loaded.invoices
    payments = loaded.payments
    iban_map = loaded.iban_map

    logger.info("Loaded   : %d debtors / %d invoices / %d payments",
                len(debtors), len(invoices), len(payments))
    logger.info("IBAN map : %d entries (couverture débiteurs : %.1f%%)",
                len(iban_map),
                len(iban_map) * 100 / max(len(debtors), 1))

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

    logger.info("Pipeline : process_batch(rebuild_every=100)")
    t0 = time.time()
    results = orch.process_batch(payments, invoices, rebuild_every=100)
    wall = time.time() - t0
    orch.debtor_profiler.learn(results)
    logger.info("Pipeline : terminé en %.1fs (%.0f paiements/s)",
                wall, len(payments) / max(wall, 0.001))

    # ── Diagnostic post-batch ──────────────────────────────────────────
    logger.info("Génération du rapport diagnostic...")
    report_text = run_diagnostic(payments, results, invoices, iban_map)
    # Print immédiat sur stdout (visible dans le terminal Streamlit)
    print(report_text, flush=True)
    # Sauvegarde dans un fichier daté à côté des CSV
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = data_dir / f"factoring_logs_{ts}.txt"
    try:
        log_path.write_text(report_text, encoding="utf-8")
        logger.info("Rapport écrit dans : %s", log_path)
    except Exception as e:
        logger.warning("Impossible d'écrire le log : %s", e)

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

    logger.info("Construction des DataFrames terminée. Run total : %.1fs",
                time.time() - t_start)

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
        # Spécifique au mode données réelles : rapport de qualité.
        "diagnostic": loaded.diagnostic,
        "diagnostic_report": report_text,
        "log_path": str(log_path) if log_path.exists() else None,
    }
