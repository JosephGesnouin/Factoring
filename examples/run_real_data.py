#!/usr/bin/env python3
"""
Lance le pipeline de réconciliation sur des CSV de production.

Fichiers attendus dans ``--data-dir`` (séparateur ';') :
    debtors_all.csv
    invoices_all.csv
    payments_all.csv

Voir ``reconciliation/loaders.py`` pour le détail des colonnes attendues.

Usage :
    python -m examples.run_real_data --data-dir /chemin/vers/csv
    python -m examples.run_real_data --data-dir . --limit 500 --out r.csv -v
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.config import ReconciliationConfig
from reconciliation.loaders import load_from_dir
from reconciliation.orchestrator import ReconciliationOrchestrator


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--data-dir", type=Path, default=Path("."),
                    help="Répertoire contenant les 3 CSV (défaut: cwd)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Limiter le nombre de paiements traités (smoke test)")
    ap.add_argument("--out", type=Path, default=Path("reconciliation_results.csv"),
                    help="Fichier CSV de sortie")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="Active les logs DEBUG")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    log = logging.getLogger("run_real_data")

    # 1) Chargement via le loader canonique du package
    loaded = load_from_dir(args.data_dir, payments_limit=args.limit)
    log.info("Construits : %d debtors, %d invoices ouvertes, %d payments "
             "(%d IBAN connus)",
             len(loaded.debtors), len(loaded.invoices),
             len(loaded.payments), len(loaded.iban_map))

    if not loaded.invoices or not loaded.payments:
        log.error("Pas assez de données pour lancer l'orchestrateur. Stop.")
        return 1

    # 2) Orchestrateur
    orch = ReconciliationOrchestrator(ReconciliationConfig())
    orch.setup(loaded.invoices, debtors=loaded.debtors,
               iban_debtor_map=loaded.iban_map)
    log.info("Lancement de process_batch sur %d paiements...", len(loaded.payments))
    contexts = orch.process_batch(loaded.payments, loaded.invoices,
                                  rebuild_every=100)

    # 3) Métriques agrégées
    log.info("=" * 60)
    log.info("RÉCAPITULATIF")
    log.info("=" * 60)
    for k, v in orch.metrics.summary.items():
        log.info("  %-22s %s", k, v)

    # 4) Export CSV résultats
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([
            "payment_id", "payment_amount", "payment_currency", "payment_date",
            "payment_label", "payment_iban",
            "matched", "match_method", "layer", "rule_id", "confidence",
            "invoice_refs", "allocated_total", "flags", "explanation",
        ])
        for ctx in contexts:
            p, fm = ctx.payment, ctx.final_match
            if fm:
                w.writerow([
                    p.id, f"{p.amount:.2f}", p.currency.value,
                    p.date.isoformat() if p.date else "",
                    p.label_raw, p.iban_source,
                    "YES", fm.method.value, fm.layer, fm.rule_id,
                    f"{fm.confidence:.3f}",
                    ",".join(inv.reference for inv in fm.invoices),
                    f"{fm.total_allocated:.2f}",
                    ",".join(fm.flags), fm.explanation,
                ])
            else:
                w.writerow([
                    p.id, f"{p.amount:.2f}", p.currency.value,
                    p.date.isoformat() if p.date else "",
                    p.label_raw, p.iban_source,
                    "NO", "", "", "", "", "", "", "", "",
                ])

    log.info("Résultats écrits dans %s", args.out.resolve())
    return 0


if __name__ == "__main__":
    sys.exit(main())
