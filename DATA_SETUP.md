# Brancher Streamlit sur tes vraies données

> **Objectif** : qu'à la fin de cette page, tu n'aies plus qu'à lancer
> `streamlit run app/streamlit_app.py` pour voir le dashboard tourner sur
> tes fichiers de production. Sans toucher au code.

---

## TL;DR (30 secondes)

```bash
# 1) Mets tes 3 CSV dans un même dossier, avec ces noms exacts :
#    debtors_all.csv
#    invoices_all.csv
#    payments_all.csv

# 2) Indique ce dossier via une variable d'environnement :
export FACTORING_DATA_DIR=/chemin/absolu/vers/le/dossier

# 3) Lance Streamlit :
streamlit run app/streamlit_app.py
```

C'est tout. La sidebar affichera `Mode : Données réelles` avec le chemin
détecté. Sans variable d'env (ou si un CSV manque), Streamlit retombe en
mode simulation comme avant.

---

## 1. Où poser les fichiers

Les 3 fichiers doivent être **dans le même dossier** et **nommés
exactement** comme ceci (sensible à la casse) :

```
mon_dossier_data/
├── debtors_all.csv
├── invoices_all.csv
└── payments_all.csv
```

Le dossier peut être **n'importe où** sur le disque — pas besoin de le
mettre dans le repo. Recommandé : **en dehors** du repo pour éviter de
committer accidentellement des données client.

Exemples :
- `~/data/factoring/`
- `/Users/joseph/Documents/factoring_data/`
- `D:\factoring\data\`
- `/mnt/data/`

---

## 2. Comment dire à Streamlit où chercher

Une seule variable d'environnement : `FACTORING_DATA_DIR`.

### Linux / macOS (bash, zsh)

```bash
# Pour la session courante
export FACTORING_DATA_DIR=/chemin/absolu/vers/le/dossier
streamlit run app/streamlit_app.py

# De manière persistante : ajoute la ligne export ... dans ~/.bashrc ou ~/.zshrc
```

### Windows (PowerShell)

```powershell
$env:FACTORING_DATA_DIR = "D:\factoring\data"
streamlit run app/streamlit_app.py
```

### Windows (cmd)

```cmd
set FACTORING_DATA_DIR=D:\factoring\data
streamlit run app/streamlit_app.py
```

### Via un fichier `.env` (optionnel)

Si tu utilises `python-dotenv`, tu peux mettre dans `.env` à la racine du
repo :

```
FACTORING_DATA_DIR=/chemin/absolu/vers/le/dossier
```

(Le `.env` est déjà dans `.gitignore`, donc pas de risque de commit.)

---

## 3. Comment Streamlit décide du mode

Décision prise au lancement (`app/streamlit_app.py`) :

| `FACTORING_DATA_DIR` | Les 3 CSV présents ? | Mode      |
|----------------------|----------------------|-----------|
| Non défini           | n/a                  | Simulation (50 débiteurs, 5 000 paiements générés) |
| Défini, existe       | Oui                  | **Données réelles**, badge vert dans la sidebar |
| Défini, existe       | Non (1+ manquant)    | Simulation, **avertissement** dans la sidebar avec la liste manquante |
| Défini, n'existe pas | n/a                  | Simulation, avertissement |

---

## 4. Colonnes attendues dans chaque CSV

Les CSV doivent être au format `;` (point-virgule). Encoding au choix :
UTF-8, UTF-8-BOM, Latin-1 ou CP1252 — auto-détecté.

### `payments_all.csv` (Règlements — cash, délais, flux)

| Colonne          | Description                                       | Mapping vers `Payment`     |
|------------------|---------------------------------------------------|----------------------------|
| `MT_REGLT_DEV`   | Montant du paiement (devise)                      | `Payment.amount`           |
| `DT_REGLT`       | Date de règlement (paiement reçu)                 | `Payment.date`             |
| `DT_VAL`         | Date de valeur (crédit effectif)                  | metadata + fallback date   |
| `DT_SAISIE`      | Date de saisie                                    | metadata                   |
| `IBAN_BENEF`     | **CLÉ** : IBAN bénéficiaire = vIBAN dédié débiteur côté factor | `Payment.iban_source` |
| `_source_extract`| Période / extract de données                      | metadata                   |
| `CODE_DEV`       | Code devise (optionnel)                           | `Payment.currency`         |

> ⚠️ **C'est `IBAN_BENEF` la clé**, PAS `IBAN_EMETT`. En factoring, le débiteur
> paye sur un vIBAN (compte virtuel) dédié à lui chez la factor. Ce vIBAN se
> retrouve dans `IBAN_BENEF` côté paiement et doit matcher la colonne `IBAN`
> du débiteur.

> Ce schéma N'A PAS de libellé bancaire (`LIB_REGLT`/`LIB_SAISIE`).
> L'identification du débiteur repose donc **uniquement** sur le mapping
> IBAN_BENEF → IBAN débiteur. Si ton extract contient quand même un libellé,
> il sera chargé en bonus (le parseur template-based l'exploitera).

### `debtors_all.csv` (Débiteurs — risque, géographie, solvabilité)

| Colonne                | Description                          | Mapping                          |
|------------------------|--------------------------------------|----------------------------------|
| `client_debtor_number` | Identifiant unique débiteur          | `Debtor.id`                      |
| `debtor_name`          | Nom du débiteur                      | `Debtor.name`                    |
| `country_code`         | Pays                                 | `Debtor.country`                 |
| `language_code`        | Langue                               | `Debtor.language_code`           |
| `currency_code`        | Devise                               | `Debtor.currency_code`           |
| `credit_limit_request` | Limite de crédit (exposition max)    | `Debtor.credit_limit_request`    |
| `funding_limit`        | Limite de financement                | `Debtor.funding_limit`           |
| `IBAN` ⮕ `mandate_id_RUM` ⮕ `identifiers_3` | IBAN du débiteur (essai dans l'ordre) | `Debtor.iban` + index IBAN→débiteur |

> Le loader essaie les colonnes IBAN dans l'ordre `IBAN`,
> `mandate_id_RUM`, `identifiers_3` (cf. `IBAN_DEBTOR_FALLBACK_COLS`).
> Si tes IBAN sont ailleurs, ajoute la colonne dans cette constante.

### `invoices_all.csv` (Factures — activité, encours, risque)

| Colonne                   | Description                                   | Mapping                                       |
|---------------------------|-----------------------------------------------|-----------------------------------------------|
| `document_number`         | Numéro de facture                             | `Invoice.reference`                           |
| `document_amount`         | Montant de la facture                         | `Invoice.amount`                              |
| `document_balance_amount` | Solde restant dû (encours)                    | filtre `> 0` (ouvertes) + `metadata.balance`  |
| `document_date`           | Date d'émission                               | `Invoice.issue_date`                          |
| `due_date`                | Date d'échéance                               | `Invoice.due_date`                            |
| `document_type`           | Facture / Avoir                               | `metadata.document_type` + `is_credit_note`   |
| `debtor_number`           | ID débiteur (joint avec `debtors`)            | `Invoice.debtor_id`                           |
| `client_number`           | Client (cédant)                               | `metadata.client_number`                      |
| `agreement_number`        | Contrat de factoring                          | `metadata.agreement_number`                   |
| `dispute_reason_code`     | Code litige (facture bloquée)                 | `metadata.disputed=True` si non vide          |
| `currency`                | Devise                                        | `Invoice.currency`                            |
| `_source_extract`         | Période / extract                             | `metadata.source_extract`                     |

> **Filtre par défaut** : seules les factures avec `document_balance_amount > 0`
> sont chargées. Désactiver avec `load_from_dir(..., only_open_invoices=False)`.

---

## 5. Vérifier que ça marche sans lancer Streamlit

Si tu veux d'abord smoke-tester en CLI (utile pour valider que tes CSV
sont bien parsés avant d'ouvrir le dashboard) :

```bash
# Test rapide sur 500 paiements seulement
python -m examples.run_real_data --data-dir $FACTORING_DATA_DIR --limit 500 -v

# Run complet, export CSV des résultats
python -m examples.run_real_data --data-dir $FACTORING_DATA_DIR --out results.csv
```

Tu dois voir un récapitulatif type :

```
RÉCAPITULATIF
============================================================
  total_payments         500
  matched_auto           428
  matched_human          0
  unmatched              72
  auto_rate              85.6%
  avg_time_ms            3.2
  by_layer               {0: 0, 1: 254, 2: 119, 3: 55, 4: 0, 5: 0, 6: 72}
  by_method              {'C1_EXACT_REF': 188, 'C1_IBAN_AMOUNT': 66, ...}
```

---

## 6. Dépannage

### Streamlit reste en mode simulation alors que j'ai défini la variable

1. Vérifie que la variable est bien visible dans le shell où tu lances
   Streamlit : `echo $FACTORING_DATA_DIR` (Linux/macOS) ou
   `echo %FACTORING_DATA_DIR%` (Windows cmd).
2. Vérifie les **3 noms exacts** des fichiers (sensibles à la casse,
   surtout sur Linux/macOS) :
   ```bash
   ls $FACTORING_DATA_DIR | grep -E 'debtors_all|invoices_all|payments_all'
   ```
3. La sidebar de Streamlit affiche un message d'avertissement si la
   variable est définie mais qu'un fichier manque — lis-le.

### Tous mes paiements partent en C6 (revue humaine)

Causes fréquentes :
- **IBAN émetteur incorrect ou absent** dans `payments_all.csv` →
  C1-R004 (IBAN+montant) ne peut pas matcher.
- **`debtor_number` des factures ne correspond pas à `client_debtor_number`
  des débiteurs** → vérifier la jointure.
- **`document_balance_amount` à 0 ou vide** sur toutes les factures
  → tout filtré par défaut. Lance la CLI avec
  `python -m examples.run_real_data --data-dir ... -v` pour voir le
  nombre de factures ouvertes effectivement chargées.

### Les montants ne sont pas reconnus

Le parser supporte `1 234,56` (FR), `1234.56` (US), `1,234.56` (US-formal).
Pas les notations exotiques type `1.234,56` mixée. Si tu en as,
pré-traite le CSV.

### Les dates ne sont pas reconnues

Formats acceptés : `dd/mm/yyyy`, `yyyy-mm-dd`, `dd-mm-yyyy`, `yyyy/mm/dd`,
`dd.mm.yyyy`, `yyyymmdd` (+ variantes avec heure). Si ton format est
différent, ajoute-le dans `reconciliation/loaders.py:parse_date`.

### Streamlit met longtemps à charger

Streamlit met le résultat en cache (`@st.cache_data`). La première
exécution traite tous les paiements ; les suivantes sont instantanées
tant que rien ne change. Pour invalider le cache : menu Streamlit
(en haut à droite) → *Clear cache*.

### J'ai un flot de "Exact duplicate: PAY-XXX ↔ PAY-YYY" dans la console

Cause typique : ton `payments_all.csv` est la **concaténation de
plusieurs extractions** (`_source_file` / `_source_extract` différents)
qui se chevauchent. Les mêmes opérations bancaires apparaissent donc
plusieurs fois.

**Fix automatique** : le loader dédoublonne par défaut sur la clé
``IBAN_EMETT + MT_REGLT_DEV + DT_REGLT + LIB_REGLT`` et logue un
récapitulatif unique :

```
Dédoublonnage paiements : 4753 lignes retirées sur 9506 (clé = IBAN_EMETT + MT_REGLT_DEV + DT_REGLT + LIB_REGLT)
```

Pour désactiver (par ex. si tu veux que C2 produise des
`DuplicateAlert` métier sur ces doublons) :

```python
from reconciliation.loaders import load_from_dir
loaded = load_from_dir(data_dir, dedup_payments=False)
```

Le log par paiement `Exact duplicate: …` du pipeline est descendu de
`WARNING` à `DEBUG` — invisible par défaut, mais toujours compté dans
`metrics.duplicate_alerts`.

---

## 7. Pour aller plus loin

- Voir `ONBOARDING.md` pour comprendre l'architecture du pipeline.
- Voir `reconciliation/loaders.py` pour ajouter un format de date,
  changer le filtre des factures, ou supporter une devise supplémentaire.
- Voir `examples/run_real_data.py` pour intégrer le pipeline dans un job
  batch (cron, Airflow, etc.).
