# Moteur de parsing des libellés bancaires

> Quand l'IBAN ne suffit pas : tout extraire du libellé avec des regex
> exhaustives, déterministes, sans IA.

Implémenté dans `reconciliation/label_parser.py`. Couvre les templates
observés en production (factoring français, SEPA ISO 20022, multilingue
FR/EN/DE/IT/ES/NL/PL/PT).

---

## TL;DR

```python
from reconciliation.label_parser import parse

r = parse("BORDEREAU 5555 15/10/2024/INV/12345 15/10/2024")

r.bordereau_refs      # ['5555']
r.invoice_refs        # ['12345']
r.dates               # [date(2024, 10, 15)]
r.factoring_codes     # {'BORDEREAU': '5555'}
r.sepa_fields         # {'INV': '12345'}
r.templates_matched   # ['factoring_bordereau_inv', 'iso_inv_num_dated', ...]
r.confidence          # 0.99
```

Auto-intégré dans C0 : le résultat est attaché à
`payment.signals.parsed_label`, et toutes les références extraites sont
aussi poussées dans `payment.signals.raw_refs` pour le hash index C1.

---

## 1. Architecture

```
┌─ Libellé brut ──────────────────────────────────┐
│ "BORDEREAU 5555 15/10/2024/INV/12345 15/10/2024"│
└────────────┬────────────────────────────────────┘
             │
             ▼
   ┌─ Phase 1 : Templates spécifiques ─┐
   │  confiance ≥ 0.65                  │
   │  ~50 templates (SEPA, factoring,   │
   │  documents, instruments)           │
   └────────────┬───────────────────────┘
                │ marque les zones "covered"
                ▼
   ┌─ Phase 2 : Fallbacks génériques ──┐
   │  <NUM>, <REF>, <NUM> <NUM>, etc.  │
   │  uniquement zones NON couvertes   │
   └────────────┬───────────────────────┘
                │
                ▼
   ┌─ Phase 3 : Extraction atomique ───┐
   │  IBAN inline, dates, montants,    │
   │  mots-clés métier                 │
   └────────────┬───────────────────────┘
                │
                ▼
   ┌─ ParsedLabel ──────────────────────┐
   │ invoice_refs, bordereau_refs,      │
   │ iban_refs, dates, amounts,         │
   │ factoring_codes, sepa_fields,      │
   │ document_types, keywords,          │
   │ templates_matched, confidence      │
   └────────────────────────────────────┘
```

## 2. DSL de templates

Format : chaîne avec des placeholders entourés de `< >`.

| Placeholder | Regex sous-jacent                                | Exemple        |
|-------------|--------------------------------------------------|----------------|
| `<NUM>`     | `\d{1,15}`                                       | `12345`        |
| `<REF>`     | `[A-Z0-9][A-Z0-9\-/\.\*]{2,30}`                  | `FAC2024-001`  |
| `<IBAN>`    | `[A-Z]{2}\d{2}([\s\-]*[A-Z0-9]){10,30}`          | `FR76 3000...` |
| `<DATE>`    | `dd/mm/yyyy` ou `dd-mm-yyyy` ou `yyyy-mm-dd` ou `yyyymmdd` | `15/10/2024` |
| `<AMT>`     | montant FR ou US                                  | `1 234,56`     |
| `<TEXT>`    | texte libre                                       | `URGENT FOO`   |

Les whitespaces littéraux dans le template deviennent `\s+` (tolère
les écarts). Tous les templates sont compilés en regex à l'import.

Exemple : le template
```
BORDEREAU <NUM> <DATE>/INV/<NUM> <DATE>
```
compile en
```
BORDEREAU\s+(?P<num_0>\d{1,15})\s+(?P<date_1>...)/INV/(?P<num_2>\d{1,15})\s+(?P<date_3>...)
```

## 3. Bibliothèque de templates

Liste complète dans `TEMPLATES` (`reconciliation/label_parser.py`).
~70 templates organisés par famille, ordonnés par spécificité décroissante.

### 3.1 SEPA structuré factoring

| Template                                         | Confiance | Champs extraits                 |
|---------------------------------------------------|-----------|---------------------------------|
| `/MID <REF>/NBT <NUM>/SDT <NUM>/RBR <REF>`        | 0.98      | MID, NBT, SDT, RBR + bordereau  |
| `/MID <NUM>/NBT <NUM>/SDT <NUM>/RBR <REF>`        | 0.98      | idem (MID numérique)            |
| `MID <REF>/NBT <NUM>/SDT <NUM>/RBR <REF>`         | 0.97      | idem sans slash initial         |
| `MID <NUM>/NBT <NUM>/SDT <NUM>`                   | 0.95      | partiel                         |

### 3.2 ISO 20022

| Template                                         | Confiance | Champs                           |
|---------------------------------------------------|-----------|----------------------------------|
| `/INV/<NUM> <DATE>/INV/<NUM> <DATE>`              | 0.99      | 2 factures + 2 dates             |
| `/INV/<NUM> <DATE>`                               | 0.97      | INV + date                       |
| `/INV/<REF> <DATE>`                               | 0.97      | INV alphanum + date              |
| `/INV/<NUM>` / `/INV/<REF>`                       | 0.93      | INV nu                           |
| `/ROC/<REF>`                                      | 0.95      | Creditor Reference               |
| `/RFB/<REF>` / `/RFB/<NUM>`                       | 0.93-0.95 | Reference For Beneficiary        |
| `/BNF/<REF>`                                      | 0.85      | Beneficiary                      |
| `/TRF/<REF>`                                      | 0.85      | Transfer                         |
| `/RUR/<REF>`                                      | 0.88      | Reference Unique Remise          |
| `/CDS/<REF>`                                      | 0.85      | Creditor Scheme                  |

### 3.3 Factoring spécifique

| Template                                         | Confiance | Champs                           |
|---------------------------------------------------|-----------|----------------------------------|
| `DISPO/REMISE <NUM>/SDT <NUM>/RBA <REF>`          | 0.98      | DISPO_REMISE, SDT, RBA           |
| `DISPO/REMISE <NUM>/RBA <REF>`                    | 0.95      | DISPO_REMISE, RBA                |
| `DISPO/REMISE <NUM>`                              | 0.92      | DISPO_REMISE                     |
| `BORDEREAU <NUM> <DATE>/INV/<NUM> <DATE>`         | 0.98      | BORDEREAU + INV + 2 dates        |
| `BORDEREAU <NUM> <DATE>`                          | 0.96      | BORDEREAU + date                 |
| `BORDEREAU <NUM>`                                 | 0.92      | BORDEREAU                        |
| `BDR <NUM>`                                       | 0.88      | BORDEREAU (forme courte)         |

### 3.4 Catégories + advances

| Template                                         | Confiance | Champs                           |
|---------------------------------------------------|-----------|----------------------------------|
| `CAT D <IBAN>`                                    | 0.92      | CAT_D + IBAN                     |
| `CAT D <NUM>`                                     | 0.88      | CAT_D                            |
| `ADV/<NUM> <DATE>`                                | 0.90      | ADV + date                       |
| `ADV/<NUM>`                                       | 0.85      | ADV                              |
| `ACOMPTE <NUM>`                                   | 0.85      | ADV                              |

### 3.5 Documents commerciaux (multilingue)

| Langue | Mot-clé    | Template          | Confiance |
|--------|------------|-------------------|-----------|
| FR     | FACTURE    | `FACTURE <NUM>`   | 0.93      |
| FR     | FAC        | `FAC <NUM>`       | 0.90      |
| FR     | FRA        | `FRA <NUM>`       | 0.88      |
| EN     | INVOICE    | `INVOICE <NUM>`   | 0.93      |
| EN     | INV        | `INV <NUM>`       | 0.90      |
| EN     | BILL       | `BILL <NUM>`      | 0.85      |
| DE     | RECHNUNG   | `RECHNUNG <NUM>`  | 0.93      |
| DE     | RG         | `RG <NUM>`        | 0.85      |
| DE     | BELEG      | `BELEG <NUM>`     | 0.85      |
| IT     | FATTURA    | `FATTURA <NUM>`   | 0.93      |
| IT     | FATT/FT    | `FT <NUM>`        | 0.82-0.88 |
| ES     | FACTURA    | `FACTURA <NUM>`   | 0.93      |
| NL     | FACTUUR    | `FACTUUR <NUM>`   | 0.93      |
| PL     | FAKTURA/FV | `FV <NUM>`        | 0.85-0.93 |
| PT     | FATURA     | `FATURA <NUM>`    | 0.93      |

**Variantes "collées"** (sans séparateur) : `FACTURE<NUM>`,
`FAC<NUM>`, `INV<NUM>`, `RG<NUM>`, `FV<NUM>`, etc. (conf 0.85-0.92).
Indispensables pour gérer `FAC2024001`, `INV5678`, etc.

### 3.6 Documents annexes

`BL <NUM>`, `BON DE LIVRAISON <NUM>`, `CMR <NUM>`, `DAE <NUM>`,
`PO <NUM>`, `BC <NUM>`, `BDC <NUM>`, `CMD <NUM>`, `COMMANDE <NUM>`,
`ORDER <NUM>`, `AUFTRAG <NUM>`, `CONTRAT <NUM>`, `CONTRACT <NUM>`.

### 3.7 Instruments de paiement

`CHQ <NUM>`, `CHEQUE N <NUM>`, `TRAITE <NUM>`, `LCR <NUM>`,
`BOR <NUM>`, et le combiné `URG GN<NUM> N CHQ TRAITE`.

### 3.8 Fallbacks génériques (conf < 0.65)

`<REF> <NUM> <NUM>`, `<NUM> <NUM> <NUM>`, `<NUM> <NUM>`, `<IBAN>`,
`<REF>`, `<NUM>`. Activés *uniquement* hors des zones déjà couvertes
par les templates spécifiques.

## 4. Dictionnaire des codes

Tous les codes reconnus par le moteur, leur signification, et où ils
sont rangés en sortie.

### 4.1 ISO 20022 (rangés dans `sepa_fields`)

| Code | Signification                                  | Cas typique                  |
|------|------------------------------------------------|------------------------------|
| ROC  | Référence Créancier (Creditor Reference)       | `/ROC/REF12345`              |
| RFB  | Reference For Beneficiary                       | `/RFB/2024-001`              |
| INV  | Numéro de facture                               | `/INV/12345 15/10/2024`      |
| BNF  | Bénéficiaire                                    | `/BNF/...`                   |
| TRF  | Référence de transfert                          | `/TRF/...`                   |
| RUR  | Reference Unique Remise                         | `/RUR/...`                   |
| CDS  | Creditor Scheme Identifier                      | `/CDS/...`                   |
| RUM  | Référence Unique Mandat (SEPA prélèvement)     | dans `mandate_id_RUM` colonne|
| E2E  | End-To-End ID                                   | `E2E: ABCD123`               |

### 4.2 Factoring (rangés dans `factoring_codes`)

| Code           | Signification                                | Sens métier                                    |
|----------------|----------------------------------------------|------------------------------------------------|
| MID            | Mandate ID / Message ID                      | Identifiant du mandat de cession               |
| NBT            | Numéro de Bordereau Transmis                 | Référence du bordereau (= bordereau_refs)      |
| SDT            | Statement Date / Solde Daté                  | Date du relevé/solde                           |
| RBR            | Référence Bordereau Restant                  | Sous-référence dans le bordereau               |
| RBA            | Référence Bordereau Avoir / d'Anomalie       | Référence d'avoir ou anomalie                  |
| BORDEREAU      | Numéro de bordereau (forme native)           | = bordereau_refs                               |
| DISPO_REMISE   | Numéro de disposition / remise               | Identifiant de la remise factor                |
| CAT_D          | Catégorie D (segmentation interne)           | Indicateur catégoriel débiteur                 |
| CAT            | Catégorie (générique)                         | Idem                                           |
| ADV            | Advance / advice (avis)                       | Référence d'avis ou d'avance                   |
| INSTRUMENT     | Numéro d'instrument (chèque, traite, LCR)    | Identifiant de l'instrument                    |

### 4.3 Mots-clés (rangés dans `keywords` / `document_types`)

- **Documents** : FACTURE, FACT, FAC, FRA, INVOICE, INV, BILL, RECHNUNG, RG, FATTURA, FT, FACTURA, FACTUUR, FAKTURA, FV, FATURA, BORDEREAU, BDR, BL, CMR, DAE, PO, BC, BDC, CMD, COMMANDE, CHQ, CHEQUE, LCR, TRAITE, BOR
- **Factoring** : REMISE, DISPO, ACOMPTE, AVOIR, AVANCE, REGUL, COMPENSATION, ENCAISSEMENT, ESCOMPTE, RETENUE, RFA, COMMISSION, FRAIS
- **Type de paiement** : VIR, VIREMENT, REGLT, REGLEMENT, PAIEMENT, PAYMENT, TRANSFER, SEPA, SWIFT, SCT
- **Urgence** : URGENT, URG, EXPRESS, PRIORITY
- **International** : FOREIGN, INTERNATIONAL, INTL
- **Note de crédit** : AVOIR, AVO, NOTE DE CREDIT, GUTSCHRIFT, ABONO
- **Partiel** : ACOMPTE, PARTIEL, PARTIAL, A VALOIR
- **Final** : SOLDE, FINAL, DERNIER, BALANCE, SALDO

## 5. Routing (où va chaque capture)

Chaque template a une **règle de routing explicite** dans
`ROUTING_RULES` :

```python
"sepa_mid_nbt_sdt_rbr": [
    (0, "factoring:MID"),
    (1, "factoring:NBT"), (1, "bordereau"),  # NBT est AUSSI un bordereau
    (2, "factoring:SDT"),
    (3, "factoring:RBR"),
],
```

Format : `(index_du_groupe, "target")` où target peut être :

| Target              | Effet                                       |
|---------------------|---------------------------------------------|
| `"invoice"`         | ajouté à `invoice_refs`                     |
| `"bordereau"`       | ajouté à `bordereau_refs`                   |
| `"iban"`            | canonicalisé et ajouté à `iban_refs`        |
| `"factoring:CODE"`  | stocké dans `factoring_codes[CODE]`         |
| `"sepa:FIELD"`      | stocké dans `sepa_fields[FIELD]`            |

## 6. Stop-words

Mots qu'on ne veut **JAMAIS** voir dans `invoice_refs` même capturés
par un fallback `<REF>` :

- Types de paiement : VIR, VIREMENT, REGLT, REGLEMENT, PAIEMENT, PAYMENT, TRANSFER
- Réseaux : SEPA, SWIFT, SCT, SDD, ACH
- Mots vides : FOREIGN, INTERNATIONAL, URGENT, EXPRESS, FROM, TO, VIA
- Devises : EUR, USD, GBP, CHF
- Documents nus : FACTURE, INVOICE, BORDEREAU (sans numéro)

Liste complète dans `REF_STOPWORDS`.

## 7. Ajouter un nouveau template

Exemple : tu as repéré que tes paiements contiennent souvent
`SOLDE DOSSIER <NUM>` et tu veux l'extraire.

1. Ajouter le template dans `TEMPLATES` (label_parser.py) :
   ```python
   ("SOLDE DOSSIER <NUM>", "solde_dossier", 0.90),
   ```
2. Ajouter la règle de routing dans `ROUTING_RULES` :
   ```python
   "solde_dossier": [(0, "factoring:DOSSIER"), (0, "invoice")],
   ```
3. Ajouter un test dans `tests/test_label_parser.py` :
   ```python
   def test_solde_dossier(self):
       r = parse("SOLDE DOSSIER 12345")
       assert r.factoring_codes["DOSSIER"] == "12345"
       assert "12345" in r.invoice_refs
   ```
4. `python3 -m pytest tests/test_label_parser.py -v`

C'est tout. La compilation se fait à l'import, tu n'as rien d'autre à faire.

## 8. Intégration pipeline

Le parser est appelé automatiquement par **C0** dans `extract_signals`.
Deux effets :

1. **`signals.raw_refs`** est enrichi des `invoice_refs` + `bordereau_refs`
   + valeurs des codes factoring/SEPA + variantes (avec/sans tirets,
   padding). C1 hash index voit tous ces candidats.

2. **`signals.parsed_label`** expose la structure complète pour
   exploitation par C2/C3 (cross-check des dates, des montants, des
   bordereaux contre une table dédiée si tu en as une).

## 9. Tests

```bash
python3 -m pytest tests/test_label_parser.py -v
```

74+ tests couvrant :
- chaque template observé en prod ;
- chaque langue (FR/EN/DE/IT/ES/NL/PL/PT) ;
- extraction atomique (IBAN, dates, montants, keywords) ;
- compilation DSL (groupes répétés, whitespace flexible) ;
- robustesse (libellés vides, très longs, caractères spéciaux).

## 10. Limitations connues

- Les templates "collés" sans aucun délimiteur (ex. `FAC2024RGGN001234`)
  ne sont pas reconnus sans déclarer un template ad hoc.
- Les langues nordiques (SE, DK, NO, FI) ne sont pas couvertes par défaut.
- Les libellés multilignes (avec `\n`) sont compactés en single line
  par `_normalize`.
- Le scoring de confiance est heuristique, pas une probabilité.
