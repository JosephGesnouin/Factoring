"""
CSV loaders for production data.

Charge ``debtors_all.csv``, ``invoices_all.csv``, ``payments_all.csv``
(séparateur ';') et les convertit en objets ``Debtor`` / ``Invoice`` /
``Payment`` directement consommables par l'orchestrateur.

Schéma de référence (aligné sur la production observée) :

**payments_all.csv** (Règlements — cash, délais, flux de paiement)
    MT_REGLT_DEV    → Montant du paiement (devise)
    DT_REGLT        → Date de règlement (paiement reçu)
    DT_VAL          → Date de valeur (crédit effectif)
    DT_SAISIE       → Date de saisie
    IBAN_BENEF      → IBAN bénéficiaire = vIBAN dédié au débiteur côté
                       factor. C'est la CLÉ d'identification du débiteur.
    _source_extract → Période / extract de données
    (CODE_DEV       → Code devise — optionnel selon extract)

    Note : ce schéma N'A PAS de libellé bancaire (LIB_REGLT/LIB_SAISIE).
    L'identification du débiteur repose donc ENTIÈREMENT sur IBAN_BENEF.

**debtors_all.csv** (Débiteurs — risque, géographie, solvabilité)
    client_debtor_number  → Identifiant unique débiteur
    debtor_name           → Nom du débiteur
    country_code          → Pays
    language_code         → Langue
    credit_limit_request  → Limite de crédit (exposition max)
    funding_limit         → Limite de financement
    IBAN                  → IBAN disponible (paiement automatisé)
    currency_code         → Devise
    mandate_id_RUM        → RUM SEPA (fallback IBAN si présent)
    identifiers_3         → Fallback IBAN secondaire

**invoices_all.csv** (Factures — activité + encours + risque)
    document_number          → Numéro de facture
    document_amount          → Montant de la facture
    document_balance_amount  → Solde restant dû (encours)
    document_date            → Date d'émission
    due_date                 → Date d'échéance
    document_type            → Facture / Avoir
    debtor_number            → Identifiant débiteur
    client_number            → Client (cédant)
    agreement_number         → Contrat de factoring
    dispute_reason_code      → Code litige (facture bloquée)
    currency                 → Devise
    _source_extract          → Période / extract

Encoding : auto (utf-8, utf-8-sig, latin-1, cp1252).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from .models import Currency, Debtor, Invoice, Payment

logger = logging.getLogger(__name__)


# IBAN : tout ce qui n'est pas alphanumérique est du bruit (espaces,
# tirets, slashes, points, deux-points, virgules, retours chariot...).
_IBAN_NOISE = re.compile(r"[^A-Z0-9]")
# Pattern strict pour valider qu'on a bien un IBAN après nettoyage.
_IBAN_STRICT = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")
# Recherche d'un IBAN dans une chaîne potentiellement bruitée
# (ex. "IBAN: FR76 3000...", "FR7630001007941234567890185/BNP").
_IBAN_SEARCH = re.compile(r"[A-Z]{2}\d{2}(?:[\s.\-]*[A-Z0-9]){10,30}")


# =============================================================================
# Lecture CSV robuste
# =============================================================================

def read_csv(path: Path, sep: str = ";") -> pd.DataFrame:
    """Lecture tolérante : essaie plusieurs encodings, force ``str``,
    convertit les NaN en chaîne vide.
    """
    path = Path(path)
    last: Exception | None = None
    for enc in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(
                path, sep=sep, dtype=str, keep_default_na=False, encoding=enc,
            )
            return df.fillna("").astype(str)
        except UnicodeDecodeError as e:
            last = e
            continue
    raise RuntimeError(f"Impossible de décoder {path} : {last}")


# =============================================================================
# Parsers atomiques
# =============================================================================

def _s(v: Any) -> str:
    if v is None:
        return ""
    s = str(v)
    return "" if s.lower() in ("nan", "none") else s


def parse_amount(v: Any) -> float | None:
    """Parse '1 234,56' / '1234.56' / '1,234.56'. Retourne ``None`` si vide."""
    s = _s(v).strip().replace(" ", "").replace(" ", "")
    if not s:
        return None
    # Virgule décimale (format FR) si elle est seule ou plus à droite que le point.
    if "," in s and s.count(",") == 1 and (s.count(".") == 0 or s.rfind(",") > s.rfind(".")):
        s = s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None


def parse_date(v: Any) -> date | None:
    s = _s(v).strip()
    if not s:
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


_CURRENCY_MAP = {"EUR": Currency.EUR, "USD": Currency.USD,
                 "GBP": Currency.GBP, "CHF": Currency.CHF}


def parse_currency(v: Any) -> Currency:
    return _CURRENCY_MAP.get(_s(v).strip().upper(), Currency.EUR)


def normalise_iban(v: Any) -> str:
    """Extrait un IBAN canonique d'une valeur potentiellement bruitée.

    - strip de tout caractère non alphanumérique (espaces, tirets,
      slashes, points, deux-points...) après uppercase ;
    - si après nettoyage on a un IBAN valide (format
      ``[A-Z]{2}\\d{2}[A-Z0-9]{10,30}``), on le renvoie ;
    - sinon, tente d'extraire un IBAN intégré dans la chaîne d'origine
      (cas ``"IBAN: FR76 3000 ..."`` ou ``"FR76.../BNP"``).
    """
    raw = _s(v).upper().strip()
    if not raw:
        return ""
    cleaned = _IBAN_NOISE.sub("", raw)
    if _IBAN_STRICT.fullmatch(cleaned):
        return cleaned
    m = _IBAN_SEARCH.search(raw)
    if m:
        candidate = _IBAN_NOISE.sub("", m.group(0))
        if _IBAN_STRICT.fullmatch(candidate):
            return candidate
    # Dernier recours : valeur nettoyée même si ne match pas le pattern
    # (on ne lèvera pas une erreur silencieusement, le diagnostic le verra).
    return cleaned


# =============================================================================
# Mappers DataFrame -> dataclasses
# =============================================================================

#: Colonnes du fichier débiteurs susceptibles de contenir l'IBAN.
#: Essayées dans l'ordre, première non vide gagne. Couvre les schémas
#: où l'IBAN est rangé dans une colonne d'identifiants secondaires.
IBAN_DEBTOR_FALLBACK_COLS = ("mandate_id_RUM", "identifiers_3", "IBAN")


def _extract_iban(row: pd.Series) -> str:
    """Retourne le premier IBAN non vide trouvé dans les colonnes
    candidates de ``row`` (déjà nettoyé via ``normalise_iban``).
    """
    for col in IBAN_DEBTOR_FALLBACK_COLS:
        val = normalise_iban(row.get(col))
        if val:
            return val
    return ""


def build_debtors(df: pd.DataFrame) -> tuple[list[Debtor], dict[str, str]]:
    """Retourne ``(debtors, iban_to_debtor_id)``.

    Renseigne aussi les champs métier exposés par le schéma :
    ``language_code``, ``currency_code``, ``credit_limit_request``,
    ``funding_limit`` — utilisés downstream pour le scoring risque et
    le profilage débiteur.

    L'IBAN est cherché dans plusieurs colonnes (cf.
    ``IBAN_DEBTOR_FALLBACK_COLS``) car selon les exports il peut être
    dans ``IBAN``, ``mandate_id_RUM`` ou ``identifiers_3``.
    """
    debtors: list[Debtor] = []
    iban_map: dict[str, str] = {}
    for _, row in df.iterrows():
        did = (_s(row.get("client_debtor_number")).strip()
               or _s(row.get("legacy_debtor_number")).strip())
        if not did:
            continue
        iban = _extract_iban(row)
        d = Debtor(
            id=did,
            name=_s(row.get("debtor_name")).strip(),
            iban=iban or None,
            country=_s(row.get("country_code")).strip() or None,
            payment_terms=30,
            language_code=_s(row.get("language_code")).strip() or None,
            currency_code=_s(row.get("currency_code")).strip() or None,
            credit_limit_request=parse_amount(row.get("credit_limit_request")),
            funding_limit=parse_amount(row.get("funding_limit")),
        )
        debtors.append(d)
        if iban:
            iban_map[iban] = did
    return debtors, iban_map


def build_invoices(df: pd.DataFrame, only_open: bool = True) -> list[Invoice]:
    """Construit la liste d'``Invoice`` depuis ``invoices_all.csv``.

    Schéma supporté (cf. en-tête du module) :
        document_number, document_amount, document_balance_amount,
        document_date, due_date, document_type, debtor_number,
        client_number, agreement_number, dispute_reason_code, currency.

    Si ``only_open`` (défaut), ne garde que les factures avec
    ``document_balance_amount > 0`` (encours non soldé).

    Les factures avec ``dispute_reason_code`` non vide sont marquées
    comme litigieuses dans la metadata (``disputed=True``) — elles
    restent chargées mais downstream peut les déprioriser.
    """
    invoices: list[Invoice] = []
    for _, row in df.iterrows():
        doc_num = _s(row.get("document_number")).strip()
        if not doc_num:
            continue

        amount = parse_amount(row.get("document_amount")) or 0.0
        balance = parse_amount(row.get("document_balance_amount"))
        if only_open and balance is not None and balance <= 0:
            continue

        debtor_id = (_s(row.get("debtor_number")).strip()
                     or _s(row.get("debtor_legacy_nr")).strip())

        dispute_code = _s(row.get("dispute_reason_code")).strip()
        doc_type = _s(row.get("document_type")).strip()
        # On standardise le document_type : "Avoir" / "Facture" → marquage.
        is_credit_note = doc_type.upper().startswith(("AV", "CR"))

        invoices.append(Invoice(
            id=f"INV-{doc_num}",
            reference=doc_num,
            debtor_id=debtor_id,
            amount=amount,
            amount_ht=amount,  # pas de HT explicite dans le schéma
            currency=parse_currency(row.get("currency") or row.get("currency_code")),
            issue_date=parse_date(row.get("document_date")),
            due_date=parse_date(row.get("due_date")),
            po_number=_s(row.get("order_number")).strip() or None,
            bl_number=_s(row.get("reference_invoice_number")).strip() or None,
            status="open" if (balance is None or balance > 0) else "closed",
            metadata={
                "balance": balance,
                "document_type": doc_type,
                "is_credit_note": is_credit_note,
                "disputed": bool(dispute_code),
                "dispute_reason_code": dispute_code or None,
                "agreement_number": _s(row.get("agreement_number")),
                "client_number": _s(row.get("client_number")),
                "source_extract": (_s(row.get("_source_extract")).strip()
                                   or _s(row.get("source_extract")).strip()
                                   or None),
            },
        ))
    return invoices


def build_payments(
    df: pd.DataFrame,
    limit: int | None = None,
    dedup: bool = True,
) -> list[Payment]:
    """Construit la liste de ``Payment`` depuis ``payments_all.csv``.

    Schéma supporté :
        MT_REGLT_DEV     → ``Payment.amount`` (montant)
        DT_REGLT         → ``Payment.date`` (date de règlement)
        DT_VAL           → fallback date
        DT_SAISIE        → conservé en metadata
        IBAN_BENEF       → ``Payment.iban_source`` (CLÉ d'identification
                           du débiteur : vIBAN dédié côté factor)
        _source_extract  → metadata (période / extract)
        (CODE_DEV        → devise — optionnel)

    Note : ce schéma N'A PAS de libellé bancaire (LIB_REGLT/LIB_SAISIE),
    donc ``Payment.label_raw`` reste vide. L'identification du débiteur
    repose entièrement sur le lookup ``IBAN_BENEF → debtor.IBAN``.
    Si optionnellement LIB_REGLT ou LIB_SAISIE sont présents (extracts
    enrichis), ils sont chargés comme bonus.

    Si ``dedup`` (défaut), retire les doublons exacts du CSV. La clé
    est ``IBAN_BENEF + MT_REGLT_DEV + DT_REGLT`` (+ libellé si présent).
    """
    if dedup and len(df):
        before = len(df)
        # Clé : tout ce qui identifie l'opération métier
        candidate_keys = ("IBAN_BENEF", "MT_REGLT_DEV", "DT_REGLT",
                          "LIB_REGLT", "LIB_SAISIE")
        key_cols = [c for c in candidate_keys if c in df.columns]
        if key_cols:
            df = df.drop_duplicates(subset=key_cols, keep="first").reset_index(drop=True)
            dropped = before - len(df)
            if dropped > 0:
                logger.info(
                    "Dédoublonnage paiements : %d lignes retirées sur %d "
                    "(clé = %s)", dropped, before, " + ".join(key_cols),
                )

    payments: list[Payment] = []
    for idx, row in df.iterrows():
        if limit and len(payments) >= limit:
            break
        amount = parse_amount(row.get("MT_REGLT_DEV"))
        if amount is None or amount == 0.0:
            continue

        # Libellé : optionnel dans ce schéma. Si présent dans l'extract
        # (LIB_REGLT/LIB_SAISIE), on les concatène. Sinon vide.
        lib_reglt = _s(row.get("LIB_REGLT")).strip()
        lib_saisie = _s(row.get("LIB_SAISIE")).strip()
        label_raw = " | ".join(s for s in (lib_reglt, lib_saisie) if s)

        p = Payment(
            id=f"PAY-{idx:06d}",
            amount=amount,
            currency=parse_currency(row.get("CODE_DEV") or row.get("currency_code")),
            date=parse_date(row.get("DT_REGLT")) or parse_date(row.get("DT_VAL")),
            label_raw=label_raw,
            # ⚠️ IBAN_BENEF (et NON IBAN_EMETT) : c'est l'IBAN sur lequel
            # le débiteur a payé, qui correspond au vIBAN dédié à ce
            # débiteur côté factor → permet le mapping inverse débiteur.
            iban_source=normalise_iban(row.get("IBAN_BENEF")),
        )
        # Conserve DT_VAL, DT_SAISIE et _source_extract en metadata
        # pour exploitation downstream (analyse cash, audit).
        p.metadata = {
            "dt_val": _s(row.get("DT_VAL")).strip() or None,
            "dt_saisie": _s(row.get("DT_SAISIE")).strip() or None,
            "source_extract": (_s(row.get("_source_extract")).strip()
                               or _s(row.get("source_extract")).strip()
                               or None),
        }
        payments.append(p)
    return payments


# =============================================================================
# Bundle haut-niveau
# =============================================================================

@dataclass
class LoadedData:
    debtors: list[Debtor]
    invoices: list[Invoice]
    payments: list[Payment]
    iban_map: dict[str, str]
    diagnostic: dict[str, Any] | None = None


def diagnose(
    debtors: list[Debtor],
    invoices: list[Invoice],
    payments: list[Payment],
    iban_map: dict[str, str],
) -> dict[str, Any]:
    """Calcule un rapport de qualité des données.

    Vise une question : "pourquoi mon taux de matching est-il bas ?"
    Identifie les ruptures de jointure entre les 3 tables.
    """
    debtor_ids = {d.id for d in debtors}

    # ── IBAN payments vs IBAN debtors ────────────────────────────────────
    pay_ibans = [p.iban_source for p in payments if p.iban_source]
    pay_iban_known = sum(1 for ib in pay_ibans if ib in iban_map)
    pay_iban_empty = sum(1 for p in payments if not p.iban_source)

    # ── debtor_number factures vs id débiteurs ───────────────────────────
    inv_debtors_ok = sum(1 for inv in invoices
                         if inv.debtor_id and inv.debtor_id in debtor_ids)
    inv_debtors_empty = sum(1 for inv in invoices if not inv.debtor_id)
    inv_debtors_unknown = len(invoices) - inv_debtors_ok - inv_debtors_empty

    # ── Devises ──────────────────────────────────────────────────────────
    from collections import Counter
    pay_currencies = Counter(p.currency.value for p in payments)
    inv_currencies = Counter(inv.currency.value for inv in invoices)

    # ── Libellés (qualité) ───────────────────────────────────────────────
    import re
    empty_labels = sum(1 for p in payments if not p.label_raw.strip())
    short_labels = sum(1 for p in payments if 0 < len(p.label_raw.strip()) < 8)

    # Détection de motifs de référence facture dans le libellé.
    # Une réconciliation par libellé suppose qu'on trouve au moins une
    # séquence numérique longue (≥ 5 chiffres) ou un motif type FAC/INV.
    pat_long_num = re.compile(r"\d{5,}")
    pat_inv_kw   = re.compile(r"\b(FAC|FACT|INV|INVOICE|RECHN|FT|REC)\b", re.I)
    labels_with_long_num = sum(1 for p in payments if pat_long_num.search(p.label_raw))
    labels_with_inv_kw   = sum(1 for p in payments if pat_inv_kw.search(p.label_raw))

    # Échantillon de libellés bruts pour inspection visuelle
    sample_labels = [
        {"id": p.id, "amount": p.amount, "label": p.label_raw[:120]}
        for p in payments if p.label_raw.strip()
    ][:30]

    # ── Échantillons pour visualisation ──────────────────────────────────
    sample_unknown_iban = [
        {"id": p.id, "iban_paiement": p.iban_source, "amount": p.amount,
         "label": p.label_raw[:80]}
        for p in payments
        if p.iban_source and p.iban_source not in iban_map
    ][:20]

    # Échantillon des IBAN connus côté débiteurs : utile pour comparer
    # visuellement avec sample_unknown_iban et détecter un problème de
    # format / longueur / source.
    sample_known_iban = [
        {"debtor_id": did, "debtor_name": next(
            (d.name for d in debtors if d.id == did), ""),
         "iban_debiteur": ib, "length": len(ib)}
        for ib, did in list(iban_map.items())[:20]
    ]

    sample_invoices_orphan = [
        {"id": inv.id, "ref": inv.reference, "debtor_id": inv.debtor_id,
         "amount": inv.amount}
        for inv in invoices
        if inv.debtor_id and inv.debtor_id not in debtor_ids
    ][:20]

    return {
        # Totaux
        "n_debtors": len(debtors),
        "n_invoices": len(invoices),
        "n_payments": len(payments),

        # Pont IBAN
        "iban_in_debtors": len(iban_map),
        "payments_with_iban": len(pay_ibans),
        "payments_without_iban": pay_iban_empty,
        "payments_iban_known": pay_iban_known,
        "payments_iban_unknown": len(pay_ibans) - pay_iban_known,
        "iban_match_rate": (pay_iban_known / len(payments)) if payments else 0.0,

        # Pont débiteur factures
        "invoices_debtor_known": inv_debtors_ok,
        "invoices_debtor_unknown": inv_debtors_unknown,
        "invoices_debtor_empty": inv_debtors_empty,
        "invoice_debtor_match_rate": (inv_debtors_ok / len(invoices)) if invoices else 0.0,

        # Devises
        "pay_currencies": dict(pay_currencies),
        "inv_currencies": dict(inv_currencies),

        # Qualité libellés
        "labels_empty": empty_labels,
        "labels_short": short_labels,
        "labels_with_long_num": labels_with_long_num,
        "labels_with_inv_kw": labels_with_inv_kw,
        "sample_labels": sample_labels,

        # Échantillons
        "sample_unknown_iban": sample_unknown_iban,
        "sample_known_iban": sample_known_iban,
        "sample_invoices_orphan": sample_invoices_orphan,

        # Histogrammes de longueur IBAN — révèle un mismatch de format
        # (préfixe, troncature, espacement perdu...)
        "iban_pay_lengths": dict(Counter(len(p.iban_source) for p in payments if p.iban_source)),
        "iban_deb_lengths": dict(Counter(len(ib) for ib in iban_map.keys())),
    }


REQUIRED_FILES = ("debtors_all.csv", "invoices_all.csv", "payments_all.csv")


def data_dir_is_ready(data_dir: Path) -> bool:
    """Vrai si les 3 CSV obligatoires sont présents dans ``data_dir``."""
    data_dir = Path(data_dir)
    return all((data_dir / f).exists() for f in REQUIRED_FILES)


def _sample_raw_iban_columns(df: pd.DataFrame, n: int = 10) -> dict[str, list[str]]:
    """Échantillonne les premières valeurs non vides de chaque colonne
    candidate IBAN, pour permettre une inspection visuelle des formats.
    """
    out: dict[str, list[str]] = {}
    for col in IBAN_DEBTOR_FALLBACK_COLS:
        if col not in df.columns:
            continue
        vals = df[col].astype(str).map(lambda s: s.strip())
        vals = vals[(vals != "") & (vals.str.lower() != "nan")]
        if len(vals) == 0:
            continue
        out[col] = vals.head(n).tolist()
    return out


def load_from_dir(
    data_dir: Path,
    *,
    only_open_invoices: bool = True,
    payments_limit: int | None = None,
    dedup_payments: bool = True,
) -> LoadedData:
    """Charge les 3 CSV depuis ``data_dir`` et renvoie tout ce qu'il faut
    pour appeler ``ReconciliationOrchestrator.setup()`` puis
    ``process_batch()``.

    Paramètres
    ----------
    only_open_invoices : ne garder que les factures dont
        ``document_balance_amount > 0`` (défaut).
    payments_limit : optionnel, limite le nombre de paiements (smoke test).
    dedup_payments : retirer les doublons exacts du CSV paiements
        (défaut). Cas typique : plusieurs extractions concaténées avec
        recouvrement, qui sinon génèrent un spam de "EXACT_DUPLICATE".

    Lève ``FileNotFoundError`` si un fichier obligatoire manque.
    """
    data_dir = Path(data_dir)
    missing = [f for f in REQUIRED_FILES if not (data_dir / f).exists()]
    if missing:
        raise FileNotFoundError(
            f"Fichiers manquants dans {data_dir} : {', '.join(missing)}"
        )

    logger.info("Chargement des CSV depuis %s", data_dir)
    df_debtors  = read_csv(data_dir / "debtors_all.csv")
    df_invoices = read_csv(data_dir / "invoices_all.csv")
    df_payments = read_csv(data_dir / "payments_all.csv")
    logger.info("  debtors=%d invoices=%d payments=%d",
                len(df_debtors), len(df_invoices), len(df_payments))

    debtors, iban_map = build_debtors(df_debtors)
    invoices = build_invoices(df_invoices, only_open=only_open_invoices)
    payments = build_payments(df_payments, limit=payments_limit,
                              dedup=dedup_payments)
    diag = diagnose(debtors, invoices, payments, iban_map)
    # Échantillon des valeurs brutes des colonnes candidates IBAN —
    # utile pour debug quand le format empêche le match.
    diag["raw_iban_columns_sample"] = _sample_raw_iban_columns(df_debtors)
    # Échantillon IBAN_BENEF (la clé d'identification du débiteur dans
    # ce schéma — pas IBAN_EMETT qui n'existe pas).
    diag["raw_payments_iban_sample"] = (
        df_payments["IBAN_BENEF"].astype(str).map(lambda s: s.strip())
        .pipe(lambda s: s[(s != "") & (s.str.lower() != "nan")])
        .head(10).tolist()
        if "IBAN_BENEF" in df_payments.columns else []
    )
    logger.info(
        "Data quality : IBAN match=%.1f%% (%d/%d), invoice→debtor match=%.1f%% (%d/%d)",
        diag["iban_match_rate"] * 100, diag["payments_iban_known"], diag["n_payments"],
        diag["invoice_debtor_match_rate"] * 100,
        diag["invoices_debtor_known"], diag["n_invoices"],
    )
    if diag["iban_match_rate"] < 0.1:
        logger.warning(
            "Très peu d'IBAN paiement matchent un débiteur (%d%%). "
            "Le taux de réconciliation sera bas. "
            "Vérifie que IBAN_BENEF (payments) correspond à la colonne IBAN (debtors).",
            int(diag["iban_match_rate"] * 100),
        )
    return LoadedData(debtors=debtors, invoices=invoices,
                      payments=payments, iban_map=iban_map, diagnostic=diag)
