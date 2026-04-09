# Reconciliation Paiement-Facture par IA

**Systeme intelligent de matching paiement-facture pour le factoring**
Architecture 6 couches | 60+ regles | 42 features ML | Pipeline MLOps

```
Paiement entrant
      |
      v
 +----------+     +----------+     +----------+     +----------+     +----------+     +----------+
 |    C0    | --> |    C1    | --> |    C2    | --> |    C3    | --> |    C4    | --> |    C5    |
 | Preproc. |     |  Exact   |     |  Regles  |     |NLP/Fuzzy |     |    ML    |     |   LLM    |
 | Normal.  |     | Determi. |     |  Metier  |     |Embeddings|     | Ensemble |     | Gen. AI  |
 +----------+     +----------+     +----------+     +----------+     +----------+     +----------+
   100%            30-40%           +20-25%          +12-18%          +8-12%           Residuel
                                                                                          |
                                                                                          v
                                                                                    +----------+
                                                                                    |    C6    |
                                                                                    |  Revue   |
                                                                                    | Humaine  |
                                                                                    +----------+
                                                                                      < 5%
```

## Demarrage rapide

```bash
# Cloner le repo
git clone <url-du-repo>
cd Factoring

# Installer les dependances minimales
pip install unidecode rapidfuzz numpy

# Lancer la simulation (20 scenarios)
python -m examples.demo_simulation
```

Vous verrez 20 paiements traites en temps reel avec le detail de chaque matching :

```
  [01/20] Paiement PAY-01
  Scenario: C1 Ref exacte + montant exact
  Montant:    10,000.00 EUR
  Libelle: "REGLT FAC-2024-101"

  >>> MATCH TROUVE -- C1 Exact
    Methode:    C1_IBAN_AMOUNT
    Regle:      R004-A
    Confiance:  98%
    Factures:   FAC-2024-101
    Allocation:
      -> FAC-2024-101:    10,000.00 EUR
```

## Architecture detaillee

### C0 — Preprocessing & Normalisation (100% des paiements)

14 transformations appliquees a chaque paiement entrant :

| ID   | Transformation | Exemple |
|------|---------------|---------|
| N001 | Uppercase | `fac-2024-001` → `FAC-2024-001` |
| N002 | Deaccentuation | `Reglmnt Letude` → `REGLMNT LETUDE` |
| N003 | Strip ponctuation | `FAC.001,TXT!` → `FAC001TXT` |
| N004 | Normalise separateurs | `FAC-001/F-002` → `FAC001 F002` |
| N005 | Normalise montants | `15.000,50 EUR` → `15000.50` |
| N006 | Dedoublonne espaces | `FAC  001` → `FAC 001` |
| N007 | Expand abreviations | `REGLT` → `REGLEMENT` |
| N008 | Normalise IBAN | `fr76 1234` → `FR761234...` |
| N009 | Normalise dates | `01/10/24` → `2024-10-01` |
| N010 | Normalise devises | `€` → `EUR` |
| N011 | Strip prefixes bancaires | `VIRT RECU DE ...` → `...` |
| N012 | Detection langue | `Payment invoices` → `lang=EN` |
| N013 | N-grams caracteres | `FAC2024` → `['FAC','202','024',...]` |
| N014 | Padding numerique | `FAC-123` → `FAC-000123` |

Plus : enrichissement debiteur (IBAN → profil), extraction de signaux (references, montants, periodes, mots-cles).

**Fichier :** `reconciliation/c0_preprocessing.py`

### C1 — Matching Exact & Deterministe (Confiance 95-100%)

7 regles avec precision ~100%, execution < 10ms :

| Regle | Description | Confiance |
|-------|-------------|-----------|
| R001 | Reference exacte + montant exact | 97-100% |
| R002 | Reference ISO 20022 SEPA (/ROC/, /RFB/, E2EId...) | 93-100% |
| R003 | Hash index multi-format (variantes de refs) | 98% |
| R004 | IBAN + montant unique / solde total / batch | 94-98% |
| R005 | Solde total debiteur (avec/sans avoirs) | 95-96% |
| R006 | Matching via Purchase Order (PO) | 88-96% |
| R007 | Matching via Bon de Livraison (BL/CMR/DAE) | 92-97% |

**Fichier :** `reconciliation/c1_exact_matching.py`

### C2 — Regles Metier Avancees (Confiance 85-99%)

Encode la connaissance metier du factoring, 100% deterministe :

**Tolerances montant (12 regles) :**

| Regle | Cas | Tolerance | Confiance |
|-------|-----|-----------|-----------|
| R-M001 | Frais SWIFT internationaux | -35€ max | 95% |
| R-M002 | Frais SEPA OUR | -15€ max | 96% |
| R-M003 | Escompte contractuel | facture × (1-taux) ±0.5% | 97% |
| R-M004 | Arrondi comptable | ±1€ | 99% |
| R-M005 | Retenue de garantie (BTP) | facture × (1-taux) | 93% |
| R-M006 | Avoir partiel deduit | facture - avoir ±1% | 95% |
| R-M007 | Avoir exact deduit | facture - avoir | 97% |
| R-M008 | Penalite retard | facture + penalite | 94% |
| R-M009 | RFA (Remise Fin d'Annee) | facture × (1-RFA) | 91% |
| R-M010 | Retenue TVA source (international) | taux par pays | 90% |
| R-M011 | Conversion devise | taux BCE ±1% | 90% |
| R-M012 | Acompte standard (30/40/50/70%) | facture × % ±1% | 88% |

Plus : subset sum multi-factures, patterns temporels, detection doublons, acomptes N-to-1.

**Fichier :** `reconciliation/c2_business_rules.py`

### C3 — NLP, Fuzzy Matching & Embeddings (Confiance 75-92%)

8 algorithmes fuzzy avec score composite pondere :

| Algorithme | Poids | Force |
|-----------|-------|-------|
| Levenshtein normalise | 15% | Distance d'edition classique |
| Jaro-Winkler | 15% | Bon pour les typos en debut |
| Token Sort Ratio | 10% | Mots dans le desordre |
| Token Set Ratio | 10% | Mots manquants/en trop |
| Partial Ratio | 15% | Sous-chaines partielles |
| N-gram Jaccard | 10% | Overlap de trigrammes |
| LCS Ratio | 10% | Plus longue sous-sequence |
| Numeric Ref Similarity | 15% | Compare les parties numeriques |

Plus : NER custom (10 entites) et TF-IDF character n-grams.
(Les embeddings semantiques via sentence-transformers ont ete desactives.)

**Fichier :** `reconciliation/c3_nlp_fuzzy.py`

### C4 — Machine Learning Supervise (Confiance 80-95%)

42 features en 4 groupes :

| Groupe | Features | Exemples |
|--------|----------|----------|
| G1 Amount (10) | Differences, ratios, logs | `amount_diff_pct`, `amount_match_exact` |
| G2 Reference (12) | Scores fuzzy, qualite label | `ref_composite_score`, `label_quality` |
| G3 Temporal (10) | Delais, echeances | `days_from_due`, `same_month` |
| G4 Behavioral (10) | Profil debiteur | `debtor_regularity`, `risk_score` |

Ensemble : LightGBM + XGBoost + Random Forest + meta-classifieur logistique.
LambdaRank pour le ranking 1-to-N.
Active Learning (6 strategies) + detection de drift (PSI).

**Fichier :** `reconciliation/c4_ml.py`

### C5 — LLM & IA Generative

3 prompts optimises : generique, cryptique, ambigu.
Validation anti-hallucination (5 controles).
Cache + optimisation des couts.

**Fichier :** `reconciliation/c5_llm.py`

### C6 — Revue Humaine Intelligente

File de revue priorisee (montant × anciennete × gap confiance × risque debiteur).
Capture structuree du feedback pour boucle d'apprentissage.

**Fichier :** `reconciliation/c6_human_review.py`

## Structure du projet

```
Factoring/
├── reconciliation/           # Package principal
│   ├── __init__.py
│   ├── config.py             # Configuration (seuils, tolerances, parametres)
│   ├── models.py             # Modeles de donnees (Payment, Invoice, MatchResult...)
│   ├── c0_preprocessing.py   # C0: Normalisation & enrichissement
│   ├── c1_exact_matching.py  # C1: Matching deterministe
│   ├── c2_business_rules.py  # C2: Regles metier avancees
│   ├── c3_nlp_fuzzy.py       # C3: NLP, fuzzy, embeddings
│   ├── c4_ml.py              # C4: ML ensemble (42 features)
│   ├── c5_llm.py             # C5: LLM (Claude/GPT)
│   ├── c6_human_review.py    # C6: Revue humaine
│   ├── orchestrator.py       # Pipeline end-to-end
│   └── mlops.py              # MLOps, monitoring, retraining
├── examples/
│   ├── demo_simulation.py          # Demo 20 scenarios didactiques
│   ├── demo_large_simulation.py    # 12 debiteurs, 500 factures, 6 mois
│   └── demo_stress_test.py         # 20-50 debiteurs, 2000+ factures, 40+ pays
├── tests/                    # 74 tests
│   ├── test_c0_preprocessing.py
│   ├── test_c1_exact_matching.py
│   ├── test_c2_business_rules.py
│   ├── test_c3_nlp_fuzzy.py
│   └── test_orchestrator.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

## Utilisation programmatique

```python
from reconciliation.config import ReconciliationConfig
from reconciliation.models import Invoice, Payment, Debtor, Currency
from reconciliation.orchestrator import ReconciliationOrchestrator
from datetime import date

# 1. Creer des factures ouvertes
invoices = [
    Invoice(id="INV-1", reference="FAC-2024-001", debtor_id="D1",
            amount=10000.00, amount_ht=8333.33,
            issue_date=date(2024, 9, 1), due_date=date(2024, 10, 1)),
]

# 2. Creer des debiteurs
debtors = [
    Debtor(id="D1", name="Mon Client",
           iban="FR7630001007941234567890185", country="FR"),
]

# 3. Configurer et lancer l'orchestrateur
config = ReconciliationConfig()
orch = ReconciliationOrchestrator(config)
orch.setup(invoices, debtors, {"FR7630001007941234567890185": "D1"})

# 4. Traiter un paiement
payment = Payment(
    id="PAY-1", amount=10000.00,
    date=date(2024, 10, 15),
    label_raw="REGLEMENT FAC-2024-001",
    iban_source="FR7630001007941234567890185",
)

ctx = orch.process_payment(payment, invoices)

if ctx.final_match:
    print(f"Match: {ctx.final_match.method.value}")
    print(f"Confiance: {ctx.final_match.confidence:.0%}")
    print(f"Factures: {[inv.reference for inv in ctx.final_match.invoices]}")
else:
    print("Pas de match -> revue humaine")
```

## Tests

```bash
# Installer les dependances de test
pip install pytest unidecode rapidfuzz numpy

# Lancer les 74 tests
python -m pytest tests/ -v

# Avec couverture
python -m pytest tests/ --cov=reconciliation --cov-report=term-missing
```

## Dependances

| Package | Usage | Obligatoire |
|---------|-------|-------------|
| `unidecode` | Deaccentuation (C0) | Oui |
| `rapidfuzz` | Fuzzy matching (C3) | Recommande |
| `numpy` | Features ML (C4) | Pour C4 |
| `scikit-learn` | TF-IDF, meta-classifieur | Pour C3/C4 |
| `lightgbm` | Modele ensemble | Pour C4 |
| `xgboost` | Modele ensemble | Pour C4 |
| `sentence-transformers` | Embeddings semantiques | Pour C3 |
| `anthropic` / `openai` | LLM matching | Pour C5 |

Le systeme fonctionne en mode degrade : si une dependance optionnelle est absente, la couche correspondante est desactivee et le pipeline continue avec les couches disponibles.

## Metriques cibles

| Metrique | Cible |
|----------|-------|
| Taux de matching automatique | >= 95% |
| Precision (pas de faux positifs) | >= 99.5% |
| Temps moyen par paiement | < 10ms (C1-C2), < 100ms (C3-C4) |
| File de revue humaine | < 5% des paiements |

## Configuration

Tous les seuils et parametres sont configurables via `ReconciliationConfig` :

```python
from reconciliation.config import ReconciliationConfig, C2Config

config = ReconciliationConfig()

# Ajuster la tolerance SWIFT
config.c2.swift_fee_max = 50.0

# Modifier le seuil de confiance pour le matching automatique
config.orchestrator.auto_match_confidence_threshold = 0.85

# Ajouter des abreviations metier
config.c0.abbreviation_map["VERST"] = "VERSEMENT"
```
