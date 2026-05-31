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

### `payments_all.csv`

Colonnes obligatoires (les autres sont ignorées) :

| Colonne          | Description                                  | Mapping vers `Payment`     |
|------------------|----------------------------------------------|----------------------------|
| `DT_REGLT`       | Date de règlement (FR `dd/mm/yyyy` ou ISO)   | `Payment.date`             |
| `DT_VAL`         | Date valeur (fallback si `DT_REGLT` vide)    | `Payment.date` (fallback)  |
| `LIB_REGLT`      | Libellé du règlement (libellé bancaire brut) | `Payment.label_raw`        |
| `LIB_SAISIE`     | Libellé de saisie (concaténé au précédent)   | `Payment.label_raw`        |
| `CODE_DEV`       | Code devise ISO (`EUR`, `USD`, `GBP`, `CHF`) | `Payment.currency`         |
| `MT_REGLT_DEV`   | Montant en devise (FR `1 234,56` accepté)    | `Payment.amount`           |
| `IBAN_EMETT`     | IBAN de l'émetteur du virement               | `Payment.iban_source`      |
| `IBAN_BENEF`     | IBAN bénéficiaire (factor) — *non utilisé*   | —                          |

### `debtors_all.csv`

| Colonne                  | Description                          | Mapping                   |
|--------------------------|--------------------------------------|---------------------------|
| `client_debtor_number`   | Identifiant débiteur (clé jointure)  | `Debtor.id`               |
| `legacy_debtor_number`   | Identifiant legacy (fallback)        | `Debtor.id` (fallback)    |
| `debtor_name`            | Nom commercial                       | `Debtor.name`             |
| `IBAN`                   | IBAN du débiteur                     | `Debtor.iban` + index IBAN→débiteur |
| `country_code`           | Pays (ISO 2)                         | `Debtor.country`          |

### `invoices_all.csv`

| Colonne                     | Description                                   | Mapping                   |
|-----------------------------|-----------------------------------------------|---------------------------|
| `document_number`           | Référence facture                             | `Invoice.reference`       |
| `debtor_number`             | ID débiteur (joint avec `debtors`)            | `Invoice.debtor_id`       |
| `debtor_legacy_nr`          | ID legacy (fallback)                          | `Invoice.debtor_id`       |
| `document_date`             | Date d'émission                               | `Invoice.issue_date`      |
| `due_date`                  | Date d'échéance                               | `Invoice.due_date`        |
| `document_amount`           | Montant TTC                                   | `Invoice.amount`          |
| `document_balance_amount`   | Solde restant dû (filtré : `> 0` = ouverte)   | filtre + `metadata.balance` |
| `currency`                  | Devise                                        | `Invoice.currency`        |
| `order_number`              | Numéro de commande (PO)                       | `Invoice.po_number` *(utilisé par C1-R006)* |
| `reference_invoice_number`  | BL / référence interne                        | `Invoice.bl_number` *(utilisé par C1-R007)* |

> **Filtre par défaut** : seules les factures avec `document_balance_amount > 0`
> sont chargées (= factures encore ouvertes). Pour charger toutes les
> factures, modifier l'appel à `load_from_dir(..., only_open_invoices=False)`.

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

---

## 7. Pour aller plus loin

- Voir `ONBOARDING.md` pour comprendre l'architecture du pipeline.
- Voir `reconciliation/loaders.py` pour ajouter un format de date,
  changer le filtre des factures, ou supporter une devise supplémentaire.
- Voir `examples/run_real_data.py` pour intégrer le pipeline dans un job
  batch (cron, Airflow, etc.).
