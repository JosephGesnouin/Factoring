#!/usr/bin/env python3
"""
Lance le pipeline de réconciliation sur des données réelles
(CSV de production, séparateur ';').

Fichiers attendus dans le répertoire courant (ou via --data-dir) :
    payments_all.csv   colonnes : DT_REGLT, DT_VAL, DT_SAISIE, LIB_REGLT,
                                  LIB_SAISIE, CODE_DEV, MT_REGLT_DEV,
                                  IBAN_BENEF, IBAN_EMETT, ...
    debtors_all.csv    colonnes : client_number, client_debtor_number,
                                  debtor_name, IBAN, country_code,
                                  currency_code, funding_limit, ...
    invoices_all.csv   colonnes : client_number, agreement_number,
                                  debtor_number (ou debtor_legacy_nr),
                                  document_number, document_type, currency,
                                  document_date, due_date, document_amount,
                                  document_balance_amount, order_number,
                                  reference_invoice_number, ...

Usage :
    python -m examples.run_real_data
    python -m examples.run_real_data --data-dir /chemin/vers/csv
    python -m examples.run_real_data --limit 500 --out results.csv
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

# Permet l'import direct du package reconciliation/ depuis ce script.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from reconciliation.config import ReconciliationConfig
from reconciliation.models import (
    Currency,
    Debtor,
    Invoice,
    Payment,
)
from reconciliation.orchestrator import ReconciliationOrchestrator


# =============================================================================
# Loaders CSV — robustes (encoding, dtype, séparateur, valeurs vides)
# =============================================================================

def _read_csv(path: Path) -> pd.DataFrame:
    """Lecture robuste : tente utf-8 puis latin-1, tout en string, sep=';'.

    Force ``dtype=str`` pour éviter les DtypeWarning et garder la main sur
    le parsing des montants et dates plus tard.
    """
    last_err: Exception | None = None
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(
                path, sep=";", dtype=str, keep_default_na=False, encoding=enc,
            )
            # Garde-fou : que tout reste en str (jamais de NaN float)
            return df.fillna("").astype(str)
        except UnicodeDecodeError as e:
            last_err = e
            continue
    raise RuntimeError(f"Impossible de lire {path} : {last_err}")


def _s(v: Any) -> str:
    """Conversion sûre en str (gère None et NaN)."""
    if v is None:
        return ""
    s = str(v)
    return "" if s.lower() in ("nan", "none") else s


# =============================================================================
# Parsers — montants, dates, devises
# =============================================================================

def parse_amount(v: Any) -> float | None:
    """Parse '1 234,56', '1234.56', '1,234.56'. Retourne None si vide."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    s = s.replace(" ", "").replace(" ", "")
    # Si présence d'une virgule, on suppose qu'elle est décimale (FR)
    if "," in s and s.count(",") == 1 and (s.count(".") == 0 or s.rfind(",") > s.rfind(".")):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(v: Any) -> date | None:
    """Tolère plusieurs formats : ISO, FR, US, avec ou sans heure."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    for fmt in (
        "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d",
        "%d.%m.%Y", "%Y%m%d",
        "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M:%S",
    ):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def parse_currency(v: Any) -> Currency:
    s = (str(v) if v is not None else "").strip().upper()
    mapping = {"EUR": Currency.EUR, "USD": Currency.USD,
               "GBP": Currency.GBP, "CHF": Currency.CHF}
    return mapping.get(s, Currency.EUR)


def normalise_iban(v: Any) -> str:
    if v is None:
        return ""
    return str(v).replace(" ", "").upper().strip()


# =============================================================================
# Mappers DataFrame -> dataclasses du package reconciliation/
# =============================================================================

def build_debtors(df: pd.DataFrame) -> tuple[list[Debtor], dict[str, str]]:
    """Retourne (debtors, iban_to_debtor_id)."""
    debtors: list[Debtor] = []
    iban_map: dict[str, str] = {}
    for _, row in df.iterrows():
        did = _s(row.get("client_debtor_number")).strip() \
              or _s(row.get("legacy_debtor_number")).strip()
        if not did:
            continue
        iban = normalise_iban(row.get("IBAN"))
        d = Debtor(
            id=did,
            name=_s(row.get("debtor_name")).strip(),
            iban=iban or None,
            country=_s(row.get("country_code")).strip() or None,
            payment_terms=30,
        )
        debtors.append(d)
        if iban:
            iban_map[iban] = did
    return debtors, iban_map


def build_invoices(df: pd.DataFrame, only_open: bool = True) -> list[Invoice]:
    """Construit la liste d'Invoice. Par défaut, ne garde que les factures
    avec ``document_balance_amount > 0`` (encore à payer).
    """
    invoices: list[Invoice] = []
    for idx, row in df.iterrows():
        doc_num = _s(row.get("document_number")).strip()
        if not doc_num:
            continue

        amount = parse_amount(row.get("document_amount")) or 0.0
        balance = parse_amount(row.get("document_balance_amount"))
        if only_open and balance is not None and balance <= 0:
            continue

        debtor_id = (
            _s(row.get("debtor_number")).strip()
            or _s(row.get("debtor_legacy_nr")).strip()
        )

        inv = Invoice(
            id=f"INV-{doc_num}",
            reference=doc_num,
            debtor_id=debtor_id,
            amount=amount,
            amount_ht=amount,  # pas de HT explicite -> on garde TTC
            currency=parse_currency(row.get("currency")),
            issue_date=parse_date(row.get("document_date")),
            due_date=parse_date(row.get("due_date")),
            po_number=_s(row.get("order_number")).strip() or None,
            bl_number=_s(row.get("reference_invoice_number")).strip() or None,
            status="open" if (balance is None or balance > 0) else "closed",
            metadata={
                "balance": balance,
                "document_type": _s(row.get("document_type")),
                "agreement_number": _s(row.get("agreement_number")),
                "client_number": _s(row.get("client_number")),
            },
        )
        invoices.append(inv)
    return invoices


def build_payments(df: pd.DataFrame, limit: int | None = None) -> list[Payment]:
    payments: list[Payment] = []
    for idx, row in df.iterrows():
        if limit and len(payments) >= limit:
            break
        amount = parse_amount(row.get("MT_REGLT_DEV"))
        if amount is None or amount == 0.0:
            continue

        lib_reglt = _s(row.get("LIB_REGLT")).strip()
        lib_saisie = _s(row.get("LIB_SAISIE")).strip()
        # On concatène les deux libellés si disponibles : le matcher exploitera
        # les références/montants détectés dans l'un comme dans l'autre.
        label_raw = " | ".join(s for s in (lib_reglt, lib_saisie) if s)

        p = Payment(
            id=f"PAY-{idx:06d}",
            amount=amount,
            currency=parse_currency(row.get("CODE_DEV")),
            date=parse_date(row.get("DT_REGLT")) or parse_date(row.get("DT_VAL")),
            label_raw=label_raw,
            iban_source=normalise_iban(row.get("IBAN_EMETT")),
        )
        payments.append(p)
    return payments


# =============================================================================
# Main
# =============================================================================

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data-dir", type=Path, default=Path("."),
                    help="Répertoire contenant les 3 CSV (défaut: cwd)")
    ap.add_argument("--limit", type=int, default=None,
                    help="Limiter le nombre de paiements traités (smoke test)")
    ap.add_argument("--out", type=Path, default=Path("reconciliation_results.csv"),
                    help="Fichier CSV de sortie (défaut: reconciliation_results.csv)")
    ap.add_argument("--verbose", "-v", action="store_true",
                    help="Active les logs DEBUG")
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    log = logging.getLogger("run_real_data")

    # ── 1. Chargement des CSV ────────────────────────────────────────────
    log.info("Chargement des CSV depuis %s", args.data_dir.resolve())
    df_debtors  = _read_csv(args.data_dir / "debtors_all.csv")
    df_invoices = _read_csv(args.data_dir / "invoices_all.csv")
    df_payments = _read_csv(args.data_dir / "payments_all.csv")
    log.info("  debtors  : %d lignes", len(df_debtors))
    log.info("  invoices : %d lignes", len(df_invoices))
    log.info("  payments : %d lignes", len(df_payments))

    # ── 2. Construction des objets métier ────────────────────────────────
    debtors, iban_map = build_debtors(df_debtors)
    invoices = build_invoices(df_invoices, only_open=True)
    payments = build_payments(df_payments, limit=args.limit)

    log.info("Construits : %d debtors, %d invoices ouvertes, %d payments",
             len(debtors), len(invoices), len(payments))
    log.info("  IBAN connus pour matching : %d", len(iban_map))

    if not invoices or not payments:
        log.error("Pas assez de données pour lancer l'orchestrateur. Stop.")
        return 1

    # ── 3. Orchestrateur ────────────────────────────────────────────────
    config = ReconciliationConfig()
    orch = ReconciliationOrchestrator(config)
    orch.setup(invoices, debtors=debtors, iban_debtor_map=iban_map)

    log.info("Lancement de process_batch sur %d paiements...", len(payments))
    contexts = orch.process_batch(payments, invoices, rebuild_every=100)

    # ── 4. Métriques agrégées ───────────────────────────────────────────
    m = orch.metrics
    log.info("")
    log.info("=" * 60)
    log.info("RÉCAPITULATIF")
    log.info("=" * 60)
    for k, v in m.summary.items():
        log.info("  %-22s %s", k, v)

    # ── 5. Export CSV résultats ─────────────────────────────────────────
    with args.out.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow([
            "payment_id", "payment_amount", "payment_currency", "payment_date",
            "payment_label", "payment_iban",
            "matched", "match_method", "layer", "rule_id", "confidence",
            "invoice_refs", "allocated_total",
            "flags", "explanation",
        ])
        for ctx in contexts:
            p = ctx.payment
            fm = ctx.final_match
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
