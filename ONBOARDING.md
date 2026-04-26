# Guide de prise en main — Reconciliation IA (Factoring)

> Document de référence pour tout nouveau développeur rejoignant le projet.
> Lis-le dans l'ordre, ou utilise le sommaire pour aller au point qui te bloque.

---

## Sommaire

1. [Avant-propos](#1-avant-propos)
2. [Le projet en 60 secondes](#2-le-projet-en-60-secondes)
3. [Vocabulaire métier essentiel](#3-vocabulaire-métier-essentiel)
4. [Setup local en 10 minutes](#4-setup-local-en-10-minutes)
5. [Carte du dépôt](#5-carte-du-dépôt)
6. [Le voyage d'un paiement](#6-le-voyage-dun-paiement)
7. [Les 6 couches en détail](#7-les-6-couches-en-détail)
8. [Modèles de données](#8-modèles-de-données)
9. [Configuration centralisée](#9-configuration-centralisée)
10. [Workflow développeur](#10-workflow-développeur)
11. [Recettes pratiques](#11-recettes-pratiques)
12. [App Streamlit](#12-app-streamlit)
13. [Démos & stress tests](#13-démos--stress-tests)
14. [Tests](#14-tests)
15. [MLOps & boucle de feedback](#15-mlops--boucle-de-feedback)
16. [LLM (C5) en sécurité](#16-llm-c5-en-sécurité)
17. [Dégradation gracieuse des dépendances](#17-dégradation-gracieuse-des-dépendances)
18. [Dépannage / FAQ](#18-dépannage--faq)
19. [Conventions de code](#19-conventions-de-code)
20. [Glossaire](#20-glossaire)
21. [Pour aller plus loin](#21-pour-aller-plus-loin)

---

## 1. Avant-propos

**Pour qui ?** Un développeur Python qui rejoint le projet et n'a *aucun* bagage factoring ni connaissance préalable du dépôt.

**Objectif** : qu'au bout de 30 minutes tu puisses :
- lancer la suite de tests,
- exécuter une démo et lire le résultat,
- localiser le code responsable d'une décision de matching,
- savoir où ajouter une règle métier ou un test.

**Comment lire ce document ?**
- **Lecture rapide (10 min)** : sections 2, 4, 5, 6.
- **Lecture complète (45 min)** : tout, dans l'ordre.
- **Référence** : sections 11 (recettes), 18 (FAQ), 20 (glossaire) à ouvrir au fil de l'eau.

Les références au code sont au format `chemin/fichier.py:ligne` pour cliquer directement (utile si ton éditeur le supporte).

---

## 2. Le projet en 60 secondes

### Le problème métier

Dans une activité d'**affacturage** (factoring), un paiement bancaire arrive sur le compte du *factor*. Il faut le rapprocher des factures qu'il couvre. Le défi :

- libellés bancaires cryptiques, multilingues (12 langues), tronqués, abrégés ;
- montants qui ne correspondent pas exactement (frais SWIFT, escompte, retenue BTP, avoir, RFA, conversion devise, retenue à la source…) ;
- un paiement peut couvrir N factures, ou une facture peut être réglée en M paiements (acomptes) ;
- des doublons, des erreurs, des paiements ambigus.

Fait à la main : 3-5 minutes par paiement. Plusieurs milliers/jour. Coûteux, lent, source d'erreurs.

### La solution

Un **pipeline en 6 couches** qui traite chaque paiement en cascade, du plus déterministe au plus probabiliste, avec **early-exit** dès qu'une couche atteint un score de confiance suffisant :

```
Paiement entrant
   │
   ├─ C0  Préprocessing & normalisation (100 % des paiements)
   ├─ C1  Matching exact, 7 règles déterministes        (30-40 %)
   ├─ C2  Règles métier factoring (tolérances, subset)   (+20-25 %)
   ├─ C3  NLP & fuzzy matching (8 algos)                 (+12-18 %)
   ├─ C4  ML ensemble (LightGBM + XGBoost + RF)          (+8-12 %)
   ├─ C5  LLM (Claude / GPT) pour cas ambigus            (résiduel)
   └─ C6  Revue humaine + feedback loop                  (< 5 %)
```

### Métriques cibles

| Indicateur                            | Cible            |
|---------------------------------------|------------------|
| Taux de matching automatique          | ≥ 95 %           |
| Précision (zéro faux positif C1/C2)   | ≥ 99,5 %         |
| Temps moyen / paiement (C1-C2)        | < 10 ms          |
| Temps moyen / paiement (C3-C4)        | < 100 ms         |
| File de revue humaine                 | < 5 % des paiements |

**Stack** : Python ≥ 3.10, dataclasses, scikit-learn, LightGBM, XGBoost, rapidfuzz, anthropic / openai (optionnels), Streamlit + Plotly (UI démo), pytest.

---

## 3. Vocabulaire métier essentiel

Si tu ne viens pas de la finance, lis cette section avant tout. La majorité des règles du code ne se comprennent qu'avec ce vocabulaire.

| Terme                  | Définition courte                                                                                              |
|------------------------|-----------------------------------------------------------------------------------------------------------------|
| **Factor**             | Société qui rachète les créances. C'est *nous* dans ce système.                                                |
| **Cédant** (*adherent*)| Le client du factor : l'entreprise qui lui cède ses factures.                                                  |
| **Débiteur**           | L'entreprise qui *doit* payer la facture. C'est lui qui envoie le paiement.                                    |
| **Créance / facture**  | Document à payer, identifié par une `reference` (ex. `FAC-2024-001`).                                         |
| **Avoir** (*credit note*) | Note de crédit qui réduit le montant à payer (retour produit, geste commercial…).                          |
| **Acompte**            | Paiement partiel avant échéance (souvent 30 / 40 / 50 / 70 %).                                                 |
| **Solde**              | Reste dû sur un compte débiteur (somme des factures ouvertes − avoirs).                                        |
| **Échéance** (*due date*) | Date limite de paiement.                                                                                    |
| **Escompte**           | Réduction si paiement anticipé (ex. 2 % si payé sous 10 jours).                                                |
| **Retenue de garantie**| Pourcentage retenu jusqu'à la fin du contrat (BTP : 5-10 %).                                                   |
| **RFA**                | Remise de Fin d'Année — ristourne déduite a posteriori.                                                        |
| **WHT** (*withholding tax*) | Retenue à la source sur des paiements internationaux (taux par pays).                                     |
| **SWIFT**              | Réseau de virements internationaux. Frais typiques : -25 à -35 € côté receveur.                                |
| **SEPA**               | Réseau européen. Frais : -5 à -15 € en mode "OUR".                                                             |
| **ISO 20022**          | Format structuré des messages SEPA. Champs clés : `/ROC/` (créditeur), `/RFB/` (bénéficiaire), `EndToEndId`.   |
| **IBAN**               | Identifiant de compte bancaire international. Sert de clé de rapprochement débiteur → paiement.                |
| **PO** (Purchase Order)| Bon de commande. Parfois utilisé en référence dans le libellé.                                                 |
| **BL / CMR / DAE**     | Bon de livraison / lettre de voiture / document accompagnement export.                                          |
| **Subset sum**         | Trouver le sous-ensemble de factures dont la somme = montant payé (un paiement → N factures).                  |
| **Libellé bancaire**   | Texte libre dans le virement. Souvent cryptique (`VIRT FAC2024 28 SWIFT REGLT`).                              |
| **Drift (PSI)**        | *Population Stability Index* : mesure de dérive statistique. PSI > 0,2 → ré-entraîner le modèle.               |

---

## 4. Setup local en 10 minutes

### Prérequis

- **Python** ≥ 3.10 (testé 3.10, 3.11, 3.12)
- **pip** ≥ 23.0
- (optionnel) **virtualenv** ou `venv`

### Installation

```bash
# 1) Cloner le dépôt
git clone <url-du-repo>
cd Factoring

# 2) Créer un environnement virtuel
python -m venv .venv
source .venv/bin/activate   # Linux/macOS
# .venv\Scripts\activate    # Windows

# 3) Installer toutes les dépendances
pip install -r requirements.txt
```

> **Installation minimale** (uniquement C0-C2) : `pip install unidecode numpy`. Suffisant pour comprendre la base, mais C3/C4/C5 seront désactivés.

### Configuration `.env` (optionnel — pour la couche LLM)

```bash
cp .env.example .env
# Édite .env pour renseigner LLM_API_KEY si tu veux activer C5
# Sinon, mets LLM_ENABLED=false : le pipeline fonctionne sans.
```

> **Important** : `.env` est dans `.gitignore`. Ne **jamais** committer une clé API.

### Vérification

```bash
# 1) Lancer la suite de tests (≈ 5 secondes)
python -m pytest tests/ -v

# 2) Lancer la démo didactique (20 scénarios commentés)
python -m examples.demo_simulation
```

Tu devrais voir 74 tests passer, puis 20 paiements traités en console avec leur méthode et leur niveau de confiance.

### (Bonus) Lancer l'app Streamlit

```bash
streamlit run app/streamlit_app.py
```

Ouvre `http://localhost:8501` — dashboard 11 pages avec KPIs, deep-dive par paiement, profils débiteurs.

---

## 5. Carte du dépôt

```
Factoring/
├── reconciliation/             ← Le cœur du système (à connaître)
│   ├── models.py               Dataclasses partagées (Payment, Invoice, MatchResult…)
│   ├── config.py               ReconciliationConfig (toutes les constantes ajustables)
│   ├── c0_preprocessing.py     C0 : normalisation, extraction de signaux
│   ├── c1_exact_matching.py    C1 : 7 règles déterministes + index hash
│   ├── c2_business_rules.py    C2 : tolérances, subset sum, doublons, acomptes
│   ├── c3_nlp_fuzzy.py         C3 : 8 algos fuzzy + NER + TF-IDF
│   ├── c4_ml.py                C4 : ensemble ML (LightGBM + XGB + RF) + LambdaRank
│   ├── c5_llm.py               C5 : Claude/GPT avec validation anti-hallucination
│   ├── c6_human_review.py      C6 : file de revue priorisée + capture feedback
│   ├── orchestrator.py         Pipeline end-to-end (C0 → … → C6, early-exit)
│   ├── debtor_profiler.py      Apprentissage comportemental par débiteur
│   ├── mlops.py                Boucle de feedback : retraining auto de C4
│   └── utils.py                Helpers (IBAN, dates, hash, montants)
│
├── app/                        ← Démo Streamlit + exports HTML/PDF
│   ├── streamlit_app.py        Dashboard 11 pages (entry point UI)
│   ├── simulation_data.py      Génération de données réalistes (50 débiteurs, 6 mois)
│   ├── export_html.py          Export HTML autonome (~500 KB, 7 charts Plotly)
│   ├── generate_chief_of_staff_pdf.py    Brief exécutif 1 page
│   ├── generate_retex_pdf.py             Retour d'expérience technique
│   └── generate_slides_pdf.py            Deck de présentation
│
├── examples/                   ← Démos en CLI
│   ├── demo_simulation.py            20 scénarios didactiques (1-2 min)
│   ├── demo_large_simulation.py      12 débiteurs, 500 factures, 6 mois
│   ├── demo_stress_test.py           20-50 débiteurs, 2000+ factures, 40+ pays
│   └── llm_api_key_usage.py          Exemple de configuration LLM
│
├── tests/                      ← 74 tests (pytest)
│   ├── test_c0_preprocessing.py      29 tests (normalisation, signaux, IBAN…)
│   ├── test_c1_exact_matching.py     12 tests (7 règles, hash index)
│   ├── test_c2_business_rules.py     11 tests (tolérances, subset, doublons)
│   ├── test_c3_nlp_fuzzy.py          16 tests (algos fuzzy, NER)
│   ├── test_orchestrator.py          7 tests (pipeline end-to-end)
│   ├── test_fixes.py                 régressions de bugs corrigés
│   └── test_multi_invoice.py         scénarios N factures ↔ 1 paiement
│
├── data/
│   ├── generate_verbatims.py   Génération de 522 templates multilingues mutés
│   └── verbatims.json          Templates pré-calculés (12 langues, 16 mutations)
│
├── config/                     Réservé pour de la config production (YAML/JSON)
│
├── .env.example                Variables d'environnement (LLM)
├── pyproject.toml              Métadonnées du paquet, extras (`ml`, `nlp`, `llm`)
├── requirements.txt            Toutes les dépendances en un fichier
├── README.md                   Présentation du projet (orientée pitch)
├── RAPPORT_COLLABORATION.md    Rétrospective détaillée et résultats
└── ONBOARDING.md               ← Tu es ici
```

**Heuristique de navigation** :
- *Tu veux comprendre comment ça marche ?* → `reconciliation/orchestrator.py`
- *Tu veux ajouter une règle métier ?* → `reconciliation/c2_business_rules.py`
- *Tu veux ajuster un seuil ?* → `reconciliation/config.py`
- *Tu veux essayer ?* → `examples/demo_simulation.py`
- *Tu veux voir une UI ?* → `app/streamlit_app.py`

---

## 6. Le voyage d'un paiement

Suivre un paiement à travers le pipeline est la meilleure façon de comprendre le système. Point d'entrée : `reconciliation/orchestrator.py:111` — méthode `process_payment`.

### Séquence

```
1. Payment arrive (id, amount, label_raw, iban_source, date)
        │
2. C0  PaymentPreprocessor.process(payment)                  reconciliation/c0_preprocessing.py
        ├─ Normalise (uppercase, désaccentue, strip ponct.)
        ├─ Parse montants, IBAN, dates, devises
        ├─ Détecte la langue
        ├─ Extrait les signaux : refs, montants, périodes, mots-clés
        ├─ Classifie le label : SINGLE_REF / MULTI_REF / CRYPTIC / EMPTY…
        └─ Enrichit avec le profil débiteur (lookup IBAN → debtor)
        │
3. Détection doublon (DuplicateIndex, O(1))                  reconciliation/c2_business_rules.py
        │
4. C1  ExactMatcher.match(payment, open_invoices)            reconciliation/c1_exact_matching.py
        ├─ R001 référence exacte + montant exact
        ├─ R002 ISO 20022 (/ROC/, /RFB/, EndToEndId, /INV/)
        ├─ R003 hash index (variantes de réfs)
        ├─ R004 IBAN + montant unique
        ├─ R005 solde total débiteur (avec/sans avoirs)
        ├─ R006 matching via PO
        └─ R007 matching via BL/CMR/DAE
        │
   Si confidence ≥ 0.90 → STOP (early-exit), retourne le MatchResult
        │
5. C2  BusinessRuleMatcher.match(...)                        reconciliation/c2_business_rules.py
        ├─ 12 tolérances (SWIFT, SEPA, escompte, BTP, avoir, RFA, WHT…)
        ├─ Subset sum multi-factures
        ├─ Patterns temporels ("règlement octobre 2024")
        └─ Acomptes (30/40/50/70 %)
        │
   Si confidence ≥ 0.90 → STOP
        │
6. C3  NLPFuzzyMatcher.match(...)                            reconciliation/c3_nlp_fuzzy.py
        ├─ Pré-filtre numérique
        ├─ 8 algos fuzzy → score composite pondéré
        ├─ NER (10 entités)
        └─ TF-IDF n-grams
        │
   Si confidence ≥ max(0.90 - 0.10, 0.80) = 0.80 → STOP
   (Seuil C3 abaissé : les scores fuzzy sont structurellement plus bas.)
        │
7. C4  MLMatcher.match(...) (si entraîné)                    reconciliation/c4_ml.py
        ├─ Compute 42 features (montant, ref, temporel, comportemental)
        ├─ Ensemble : LightGBM + XGBoost + RandomForest → meta-classifieur
        └─ Toujours produit un top-5 ranking pour C6 (ml_rankings)
        │
   Si confidence ≥ c4.confidence_threshold (0.85) → STOP
        │
8. C5  LLMMatcher.match(...) (si LLM_ENABLED)                reconciliation/c5_llm.py
        ├─ Sélectionne le prompt (générique / cryptique / ambigu)
        ├─ Appelle Claude ou GPT
        ├─ Valide (5 contrôles anti-hallucination)
        └─ Cache + budget mensuel
        │
   Si confidence ≥ 0.90 → STOP
        │
9. C6  HumanReviewQueue.enqueue(ctx)                         reconciliation/c6_human_review.py
        └─ File priorisée (montant 30 % + ancienneté 25 % + gap 25 % + risque 20 %)
        │
   Le feedback humain alimente MLOps → ré-entraînement de C4.
```

### Sortie

Chaque paiement produit un `ReconciliationContext` (`reconciliation/models.py:209`) qui contient :

- `final_match: MatchResult | None` — la décision retenue (ou `None` si C6) ;
- `candidate_matches: list[MatchResult]` — toutes les hypothèses produites ;
- `ml_rankings: list[dict]` — top-5 ML pour aider la revue humaine ;
- `layers_attempted: list[int]` — couches traversées ;
- `processing_log: list[dict]` — événements horodatés (utile pour debug).

### Mode batch

`process_batch(payments, open_invoices, rebuild_every=100)` (`orchestrator.py:205`) traite une liste, et **reconstruit les index C1/C3 toutes les 100 décisions** pour ne pas re-proposer les factures déjà consommées. C'est important pour les gros volumes.

---

## 7. Les 6 couches en détail

Pour chaque couche : rôle, fichier, classe principale, ce qu'elle prend en entrée, ce qu'elle produit, et où ajouter du nouveau.

### C0 — Préprocessing

| | |
|---|---|
| **Fichier** | `reconciliation/c0_preprocessing.py` |
| **Classe** | `PaymentPreprocessor` |
| **Config** | `C0Config` (`config.py`) |
| **Couverture** | 100 % des paiements |

**Rôle** : transformer un paiement brut en paiement enrichi exploitable.

**14 transformations** : uppercase, désaccentuation, strip ponctuation, normalisation séparateurs, parse montants (`15.000,50 EUR` → `15000.50`), dédoublonnage espaces, expansion des abréviations (`REGLT` → `REGLEMENT`), normalisation IBAN, dates ISO, devises, strip préfixes bancaires, détection langue, n-grams caractères, padding numérique.

**Entrée** : `Payment(label_raw="...", amount=..., iban_source="...")`
**Sortie** : enrichit `payment.label_normalized`, `payment.signals` (`PaymentSignals`), `payment.iso20022`, `payment.debtor`.

**Points d'extension** :
- ajouter une abréviation : `C0Config.abbreviation_map` ;
- ajouter un préfixe bancaire à stripper : `C0Config.bank_prefixes_to_strip`.

---

### C1 — Matching exact (déterministe)

| | |
|---|---|
| **Fichier** | `reconciliation/c1_exact_matching.py` |
| **Classes** | `ExactMatcher`, `InvoiceHashIndex` |
| **Config** | `C1Config` |
| **Confiance** | 93-100 % — précision quasi parfaite |
| **Latence** | < 10 ms (lookup O(1)) |

**7 règles** :

| ID    | Règle                                                  | Confiance |
|-------|--------------------------------------------------------|-----------|
| R001  | Référence exacte + montant exact                       | 97-100 %  |
| R002  | Référence ISO 20022 (/ROC/, /RFB/, EndToEndId, /INV/)  | 93-100 %  |
| R003  | Hash index multi-format (variantes : avec/sans tirets) | 98 %      |
| R004  | IBAN + montant unique sur la fenêtre temporelle        | 94-98 %   |
| R005  | Solde total débiteur (avec/sans avoirs)                | 95-96 %   |
| R006  | Matching via Purchase Order                            | 88-96 %   |
| R007  | Matching via BL/CMR/DAE                                | 92-97 %   |

**Index** : `InvoiceHashIndex` indexe les factures sur plusieurs clés (référence brute, normalisée, sans tirets, padding numérique) → lookup O(1).

**Méthode clé** : `ExactMatcher.build_index(invoices)` doit être appelée *avant* `match()`. C'est ce que fait `Orchestrator.setup()`.

---

### C2 — Règles métier

| | |
|---|---|
| **Fichier** | `reconciliation/c2_business_rules.py` |
| **Classes** | `BusinessRuleMatcher`, `DuplicateIndex` |
| **Config** | `C2Config` |
| **Confiance** | 85-99 % |
| **Latence** | 1-5 ms |

**Catégories** :

1. **Tolérances montant (12 règles)** — listées dans `README.md` (R-M001 à R-M012). Chaque règle teste si l'écart entre le montant payé et le montant attendu de la facture s'explique par une raison métier.
2. **Subset sum** — un paiement = somme de N factures. Stratégies : greedy, brute-force (≤ 15 factures), two-sum.
3. **Patterns temporels** — détection de `RÈGLEMENT OCTOBRE 2024` → toutes les factures du mois.
4. **Doublons** — index `DuplicateIndex` (`O(1)`), 8 contrôles : fingerprint, montant + jour, montant proche…
5. **Acomptes** — détection `ACOMPTE` + ratios standards 30/40/50/70 %.

**Points d'extension** :
- nouvelle tolérance → ajouter une méthode `_check_<rule>` et l'enregistrer dans la liste de règles ;
- nouveau pourcentage d'acompte → `C2Config.standard_installment_pcts`.

---

### C3 — NLP & fuzzy matching

| | |
|---|---|
| **Fichier** | `reconciliation/c3_nlp_fuzzy.py` |
| **Classe** | `NLPFuzzyMatcher` |
| **Config** | `C3Config` |
| **Confiance** | 75-92 % |
| **Latence** | 10-50 ms |

**Score composite pondéré** (8 algorithmes) :

| Algorithme              | Poids | Force                              |
|-------------------------|-------|------------------------------------|
| Levenshtein normalisé   | 15 %  | Distance d'édition classique       |
| Jaro-Winkler            | 15 %  | Typos en début de chaîne           |
| Token Sort Ratio        | 10 %  | Mots dans le désordre              |
| Token Set Ratio         | 10 %  | Mots manquants ou en trop          |
| Partial Ratio           | 15 %  | Sous-chaînes partielles            |
| N-gram Jaccard          | 10 %  | Overlap de trigrammes              |
| LCS Ratio               | 10 %  | Plus longue sous-séquence commune  |
| Numeric Ref Similarity  | 15 %  | Similarité des parties numériques  |

Plus : NER custom (10 types d'entités), TF-IDF char n-grams. Embeddings sentence-transformers **désactivés par défaut**.

**Seuil dynamique** : C3 utilise `auto_match_confidence_threshold - 0.10` (plancher 0.80) car les scores fuzzy sont structurellement plus bas que C1/C2 (`orchestrator.py:157`).

---

### C4 — Machine learning

| | |
|---|---|
| **Fichier** | `reconciliation/c4_ml.py` |
| **Classe** | `MLMatcher` |
| **Config** | `C4Config` |
| **Confiance** | 80-95 % |
| **Latence** | 20-100 ms |

**42 features en 4 groupes** :

| Groupe | N | Exemples |
|--------|---|----------|
| G1 Amount     | 10 | `amount_diff_pct`, `amount_match_exact`, log ratios, mention dans le label |
| G2 Reference  | 12 | `ref_composite_score`, `label_quality`, présence, n-grams |
| G3 Temporal   | 10 | `days_from_due`, `days_from_issue`, `same_month`, jour de la semaine |
| G4 Behavioral | 10 | `debtor_regularity`, `risk_score`, déviation du pattern de paiement |

**Modèles** : LightGBM + XGBoost + RandomForest → meta-classifieur logistique. **LambdaRank** pour le ranking 1-to-N. **Active learning** (6 stratégies). **Drift detection** via PSI.

> ⚠️ **Piège classique** : par défaut `MLMatcher` n'est **pas** entraîné. L'orchestrateur skippe alors C4 silencieusement. Dans les logs : `"C4 model not trained"` (`orchestrator.py:177`). Pour entraîner : `MLMatcher.train(training_data)`.

**`ml_rankings` toujours calculé** quand C4 est entraîné, même si C4 ne donne pas un match — pour aider la revue humaine en C6.

---

### C5 — LLM (Claude / GPT)

| | |
|---|---|
| **Fichier** | `reconciliation/c5_llm.py` |
| **Classe** | `LLMMatcher` |
| **Config** | `C5Config` (+ `.env`) |
| **Confiance** | 88-98 % |
| **Latence** | 1-3 s |

**3 prompts optimisés** : générique / cryptique / ambigu.
**5 contrôles anti-hallucination** : références existent vraiment, montants raisonnables, total ≤ paiement, confiance plafonnée à 0.99, raisonnement fourni.
**Cache** : par hash MD5 du prompt (économie de coûts).
**Budget** : plafond mensuel en USD (`LLM_MONTHLY_BUDGET`), refus d'appel au-delà.
**Kill switch** : `LLM_ENABLED=false` désactive complètement la couche.

**Providers supportés** : `anthropic` (défaut) ou `openai`. Modèles configurables via `LLM_MODEL`.

---

### C6 — Revue humaine

| | |
|---|---|
| **Fichier** | `reconciliation/c6_human_review.py` |
| **Classe** | `HumanReviewQueue` |
| **Config** | `C6Config` |
| **Volume cible** | < 5 % des paiements |

**Priorisation** : score = montant × 30 % + ancienneté × 25 % + gap de confiance × 25 % + risque débiteur × 20 %.

**Décisions possibles** : `APPROVE`, `REJECT`, `CORRECT`, `SPLIT`, `DEFER`, `ESCALATE`.

**Capture du feedback** : structurée (`ReviewFeedback`), pour alimenter la boucle MLOps qui ré-entraîne C4.

**Contexte fourni au reviewer** : payment normalisé, top-5 candidats ML scorés, profil débiteur, timeline.

---

## 8. Modèles de données

Tout est dans `reconciliation/models.py` — dataclasses sans dépendance externe.

### Entrée du pipeline

```python
@dataclass
class Payment:                              # models.py:146
    id: str
    amount: float
    currency: Currency = Currency.EUR
    date: date | None = None
    label_raw: str = ""                     # libellé bancaire brut
    label_normalized: str = ""              # rempli par C0
    iban_source: str = ""                   # IBAN du compte émetteur
    bic_source: str = ""
    debtor_id: str | None = None
    debtor: Debtor | None = None            # injecté par C0 via lookup IBAN
    signals: PaymentSignals = ...           # rempli par C0
    iso20022: ISO20022Fields = ...          # rempli par C0
    metadata: dict[str, Any] = ...
```

```python
@dataclass
class Invoice:                              # models.py:69
    id: str
    reference: str
    debtor_id: str
    amount: float                           # TTC
    amount_ht: float                        # HT
    currency: Currency = Currency.EUR
    issue_date: date | None
    due_date: date | None
    po_number: str | None                   # pour C1-R006
    bl_number: str | None                   # pour C1-R007
    status: str = "open"
```

```python
@dataclass
class Debtor:                               # models.py:100
    id: str
    name: str
    iban: str | None
    country: str | None
    payment_terms: int = 30
    discount_rate: float = 0.0              # escompte contractuel
    retention_rate: float = 0.0              # retenue de garantie
    rfa_rate: float = 0.0
    avg_payment_delay: float = 0.0
    payment_regularity_score: float = 0.5    # 0=erratique, 1=très régulier
    risk_score: float = 0.5
```

### Sortie du pipeline

```python
@dataclass
class MatchResult:                          # models.py:184
    payment_id: str
    invoices: list[Invoice]                  # factures matchées
    method: MatchMethod                      # ex. C1_EXACT_REF, C2_TOLERANCE…
    confidence: float                        # 0.0 - 1.0
    allocated: dict[str, float]              # invoice_id → montant alloué
    flags: list[str]                         # diagnostics
    credit_notes_applied: list[CreditNote]
    explanation: str                         # texte humain
    layer: int                               # 1-6
    rule_id: str                             # ex. "R001", "R-M003"

    @property
    def is_auto(self) -> bool: return self.confidence >= 0.90
```

```python
@dataclass
class ReconciliationContext:                # models.py:209
    payment: Payment
    open_invoices: list[Invoice]
    candidate_matches: list[MatchResult]     # toutes les hypothèses
    final_match: MatchResult | None          # la décision retenue
    ml_rankings: list[dict]                  # top-5 C4 (toujours calculé si C4 trained)
    layers_attempted: list[int]              # ex. [0, 1, 2, 3]
    processing_log: list[dict]               # événements pour debug
```

### Énumérations utiles

- **`MatchMethod`** (`models.py:15`) — identifie quelle règle/couche a produit le match. Préfixé par la couche : `C1_EXACT_REF`, `C2_TOLERANCE`, `C3_FUZZY`, `C4_ENSEMBLE`, `C5_LLM`, `C6_HUMAN`.
- **`LabelClass`** (`models.py:50`) — qualité/type du libellé : `SINGLE_REF`, `MULTI_REF`, `PERIOD_ONLY`, `AMOUNT_ONLY`, `EMPTY`, `CRYPTIC`, `MIXED`.
- **`Currency`** — `EUR`, `USD`, `GBP`, `CHF`.

### Types auxiliaires

- `PaymentSignals` (`models.py:122`) — résultat de l'extraction par C0 : `raw_refs`, `label_amounts`, `label_periods`, `keywords`, `label_class`, `label_quality`, `fingerprint`.
- `ISO20022Fields` (`models.py:134`) — `roc_ref`, `rfb_ref`, `inv_number`, `end_to_end_id`, `tx_id`, `bv_ref`.
- `CreditNote` (`models.py:87`) — avoirs, peuvent être consommés par C2.
- `DuplicateAlert` (`models.py:226`) — alerte de doublon (`EXACT_DUPLICATE`, `NEAR_DUPLICATE`, `SAME_DAY_SAME_AMOUNT`).

---

## 9. Configuration centralisée

Tous les seuils, tolérances, paramètres ajustables sont dans **un seul endroit** : `reconciliation/config.py`. Architecture en cascade :

```python
@dataclass
class ReconciliationConfig:                 # config.py:165
    c0: C0Config                            # normalisation, abréviations
    c1: C1Config                            # fenêtres temporelles, seuils PO
    c2: C2Config                            # tolérances montant, subset sum
    c3: C3Config                            # poids fuzzy, seuils
    c4: C4Config                            # seuils ML, retraining
    c5: C5Config                            # provider, budget, prompts
    c6: C6Config                            # poids de priorisation
    orchestrator: OrchestratorConfig        # seuils globaux
```

### Seuils-clés à connaître

| Variable | Valeur défaut | Effet |
|----------|---------------|-------|
| `orchestrator.auto_match_confidence_threshold`     | 0.90 | Seuil global d'early-exit (sauf C3 et C4 qui ont leur propre logique). |
| `orchestrator.escalation_confidence_threshold`     | 0.50 | En dessous, on n'essaie même pas de proposer ce match. |
| `c4.confidence_threshold`                          | 0.85 | Seuil spécifique au ML (scores calibrés différemment). |
| **C3 effectif** (calculé)                          | 0.80 | `max(auto_match - 0.10, 0.80)` — `orchestrator.py:157`. |
| `c2.swift_fee_max`                                 | 35.0 | Tolérance frais SWIFT (€). |
| `c2.sepa_our_fee_max`                              | 15.0 | Tolérance frais SEPA OUR (€). |
| `c2.rounding_tolerance`                            | 1.0  | Arrondi comptable (€). |
| `c2.subset_sum_max_invoices`                       | 15   | Limite combinatoire. |
| `c2.subset_sum_timeout_ms`                         | 500  | Garde-fou de timeout. |

### Override sans toucher au code

```python
from reconciliation.config import ReconciliationConfig

config = ReconciliationConfig()
config.c2.swift_fee_max = 50.0                              # plus tolérant
config.orchestrator.auto_match_confidence_threshold = 0.85  # plus permissif
config.c0.abbreviation_map["VERST"] = "VERSEMENT"           # nouveau métier

orch = ReconciliationOrchestrator(config)
```

### Variables d'environnement (LLM uniquement)

Cf. `.env.example`. Les autres paramètres sont en code (volontairement, pour audit).

| Variable                | Rôle                                        |
|-------------------------|---------------------------------------------|
| `LLM_PROVIDER`          | `anthropic` / `openai` / `disabled`         |
| `LLM_MODEL`             | ex. `claude-sonnet-4-5`, `gpt-4o`           |
| `LLM_API_KEY`           | clé unifiée (prend le pas sur les autres)   |
| `ANTHROPIC_API_KEY`     | fallback Anthropic                          |
| `OPENAI_API_KEY`        | fallback OpenAI                             |
| `LLM_ENABLED`           | `true` / `false` — kill switch              |
| `LLM_MONTHLY_BUDGET`    | plafond mensuel USD                         |
| `LLM_BASE_URL`          | proxy / Azure / self-hosted                 |
| `LLM_MAX_TOKENS`        | défaut 1024                                 |
| `LLM_TEMPERATURE`       | défaut 0.0 (déterministe)                   |

---

## 10. Workflow développeur

### Branches

- `main` — branche stable.
- `claude/...` — branches de travail Claude Code (préfixe imposé par la session).
- Convention : une branche = un sujet. Pas de feature géante.

### Cycle de dev quotidien

```bash
# 1) Mettre à jour
git fetch origin
git pull origin main

# 2) Travailler sur ta branche
git checkout -b feature/ma-nouvelle-regle

# 3) Lancer les tests souvent
python -m pytest tests/ -v

# 4) Vérifier la couverture sur ton fichier
python -m pytest tests/test_c2_business_rules.py --cov=reconciliation.c2_business_rules --cov-report=term-missing

# 5) Smoke test démo
python -m examples.demo_simulation
```

### Commits

- Messages descriptifs en anglais ou français, courts (≤ 72 car. première ligne).
- Préfixes utiles : `fix:`, `feat:`, `refactor:`, `test:`, `docs:`, `chore:`.
- Un commit = un changement cohérent.

### Tests : où regarder

- `tests/test_<module>.py` reflète `reconciliation/<module>.py` 1-to-1.
- Fixtures fréquentes : `make_invoice()`, `make_payment()` dans `test_orchestrator.py:17`.
- Pour un test d'intégration end-to-end : copier le pattern de `TestOrchestratorPipeline.test_c1_exact_match`.

### Logging & debug

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Puis dans ton code :
ctx = orch.process_payment(payment, invoices)
for event in ctx.processing_log:
    print(event)             # chaque étape, chaque couche, chaque skip
print(ctx.layers_attempted)  # ex. [0, 1, 2, 3]
print(ctx.candidate_matches) # toutes les hypothèses non-retenues
```

---

## 11. Recettes pratiques

Les manipulations les plus fréquentes, pas-à-pas.

### 11.1 Ajouter une nouvelle règle de tolérance C2

**Cas** : tu veux gérer une nouvelle déduction métier (ex. *frais de relance −10 €*).

1. **Définir le paramètre** dans `reconciliation/config.py` :
   ```python
   @dataclass
   class C2Config:
       ...
       collection_fee_max: float = 10.0   # nouveau
   ```

2. **Implémenter la règle** dans `reconciliation/c2_business_rules.py` :
   ```python
   def _check_collection_fee(self, payment, invoice) -> MatchResult | None:
       diff = invoice.amount - payment.amount
       if 0 < diff <= self._cfg.collection_fee_max:
           return MatchResult(
               payment_id=payment.id,
               invoices=[invoice],
               method=MatchMethod.C2_TOLERANCE,
               confidence=0.94,
               allocated={invoice.id: payment.amount},
               rule_id="R-M013",
               layer=2,
               explanation=f"Frais de relance déduits ({diff:.2f}€)",
           )
       return None
   ```

3. **Enregistrer la règle** dans la liste de tolérances de `BusinessRuleMatcher.match()`.

4. **Écrire un test** dans `tests/test_c2_business_rules.py` :
   ```python
   def test_collection_fee_tolerance(self):
       inv = make_invoice("FAC001", 1000.0)
       pay = make_payment(990.0, refs=[])
       result = matcher.match(pay, [inv])
       assert result.rule_id == "R-M013"
       assert result.confidence >= 0.90
   ```

5. **Lancer** `python -m pytest tests/test_c2_business_rules.py -v`.

### 11.2 Ajuster un seuil sans modifier le code

```python
config = ReconciliationConfig()
config.c2.swift_fee_max = 50.0
orch = ReconciliationOrchestrator(config)
```

### 11.3 Débugger un paiement qui n'est pas matché

```python
# Active le log détaillé
import logging
logging.basicConfig(level=logging.DEBUG)

ctx = orch.process_payment(payment, invoices)

# 1) Quelles couches ont été essayées ?
print(ctx.layers_attempted)

# 2) Quels candidats ont été produits ?
for m in ctx.candidate_matches:
    print(f"{m.method.value:25s} conf={m.confidence:.2f} rule={m.rule_id}")

# 3) Que s'est-il passé étape par étape ?
for ev in ctx.processing_log:
    print(ev)

# 4) Ranking ML (utile même sans match) ?
for r in ctx.ml_rankings:
    print(f"  {r['rank']}. {r['invoice'].reference} proba={r['proba']:.3f}")
```

### 11.4 Activer / désactiver C5 (LLM)

```bash
# Désactiver
echo "LLM_ENABLED=false" >> .env

# Activer avec Claude
echo "LLM_PROVIDER=anthropic"        >> .env
echo "LLM_MODEL=claude-sonnet-4-5"   >> .env
echo "LLM_API_KEY=sk-ant-..."        >> .env
echo "LLM_ENABLED=true"              >> .env
echo "LLM_MONTHLY_BUDGET=100.0"      >> .env
```

### 11.5 Tester un libellé bancaire isolé

```python
from reconciliation.c0_preprocessing import PaymentPreprocessor
from reconciliation.config import C0Config
from reconciliation.models import Payment

prep = PaymentPreprocessor(C0Config())
p = Payment(id="X", amount=10000, label_raw="VIRT REGLT FAC.2024/101 -28 SWIFT")
prep.process(p)

print(p.label_normalized)
print(p.signals.raw_refs)
print(p.signals.label_amounts)
print(p.signals.label_class)
```

### 11.6 Ajouter un scénario à la démo

Édite `examples/demo_simulation.py`, ajoute un dict dans la liste `SCENARIOS`, ajoute la facture/paiement correspondants, relance `python -m examples.demo_simulation`. Pas besoin de modifier l'orchestrateur.

### 11.7 Entraîner C4 sur tes propres données

```python
from reconciliation.c4_ml import MLMatcher
from reconciliation.config import C4Config

ml = MLMatcher(C4Config())
ml.train(training_data)        # liste de (Payment, Invoice, label_match: bool)
# À partir d'ici, l'orchestrateur invoquera C4 normalement.
```

> Sans cette étape, C4 est silencieusement skippé (cf. `orchestrator.py:165-178`).

---

## 12. App Streamlit

### Lancer

```bash
pip install streamlit plotly pandas      # si pas déjà installé
streamlit run app/streamlit_app.py
# → http://localhost:8501
```

### Architecture

- `app/streamlit_app.py` — entry point, 11 pages, CSS premium custom (Inter, hero banners, KPI cards).
- `app/simulation_data.py` — backend de génération : 50 débiteurs, 5 270 factures, 4 724 paiements sur 6 mois, 40+ pays, 12 langues. Sert le même dataset à toutes les pages.
- Données mises en cache via `@st.cache_data` (relance lente uniquement au premier load).

### Les 11 pages

| Page | Contenu |
|------|---------|
| Executive Summary       | 8 KPIs, pie distribution par couche, évolution mensuelle |
| System Architecture     | Pipeline interactif avec drilldown par couche |
| Live Simulation         | Tableau filtrable des 4 724 paiements |
| Debtor Analysis         | Profilage, taux d'automatisation par débiteur |
| Deep Dive Payment       | Trace complète d'un paiement à travers les 6 couches |
| Debtor Behavior Profiles| Patterns, langues, méthodes |
| Recommendations Engine  | Top combos suggérés pour la revue humaine |
| Layer Breakdown         | Statistiques détaillées par couche |
| Method Distribution     | Histogramme des `MatchMethod` |
| Showcase Scenarios      | Cas d'école pour démo client |
| About / Tech            | Stack, dépendances, roadmap |

### Exports autonomes

- **HTML** (~500 KB, 7 charts Plotly, aucune dépendance JS externe) :
  ```bash
  python -m app.export_html        # produit demo_reconciliation.html
  ```
- **PDF Chief of Staff** (1 page exécutive) :
  ```bash
  python -m app.generate_chief_of_staff_pdf
  ```
- **PDF retex** (rétro technique détaillée) :
  ```bash
  python -m app.generate_retex_pdf
  ```
- **PDF slides** (deck de présentation) :
  ```bash
  python -m app.generate_slides_pdf
  ```

---

## 13. Démos & stress tests

Quatre scripts dans `examples/`, complexité croissante :

### `demo_simulation.py` — 20 scénarios didactiques

```bash
python -m examples.demo_simulation
```

20 paiements couvrant **toutes les règles** C1-C6 avec un commentaire pour chaque (`PAY-01` = C1 réf exacte, `PAY-07` = C2 frais SWIFT, `PAY-15` = C3 typo, `PAY-20` = C6…). C'est ton premier port d'attache pour comprendre le système.

### `demo_large_simulation.py` — 6 mois réalistes

```bash
python -m examples.demo_large_simulation
```

12 débiteurs, ~500 factures, 6 mois d'historique avec saisonnalité. Permet de voir les métriques agrégées (taux d'auto, distribution par couche).

### `demo_stress_test.py` — montée en charge

```bash
python -m examples.demo_stress_test
python -m examples.demo_stress_test --debtors 30 --months 24
python -m examples.demo_stress_test --debtors 50 --months 36 --invoices 5000
```

Paramétrable. 20-50+ débiteurs, 2 000+ factures, 40+ pays, 12 langues. Mesure le throughput (`payments/sec`) et la dégradation à grande échelle.

### `llm_api_key_usage.py`

Exemple de configuration LLM avec tracking des coûts. Lance-le après avoir mis ta clé dans `.env` :

```bash
python -m examples.llm_api_key_usage
```

---

## 14. Tests

### Lancer

```bash
# Tous (74 tests, ~5s)
python -m pytest tests/ -v

# Un fichier
python -m pytest tests/test_c2_business_rules.py -v

# Un test précis
python -m pytest tests/test_c2_business_rules.py::TestAmountTolerance::test_swift_fees -v

# Avec couverture
python -m pytest tests/ --cov=reconciliation --cov-report=term-missing

# Couverture HTML pour exploration
python -m pytest tests/ --cov=reconciliation --cov-report=html
open htmlcov/index.html
```

### Structure

| Fichier                          | Tests | Cible                          |
|----------------------------------|-------|--------------------------------|
| `test_c0_preprocessing.py`       | 29    | Normalisation, signaux, IBAN   |
| `test_c1_exact_matching.py`      | 12    | 7 règles, hash index           |
| `test_c2_business_rules.py`      | 11    | Tolérances, subset, doublons   |
| `test_c3_nlp_fuzzy.py`           | 16    | Algos fuzzy, NER               |
| `test_orchestrator.py`           | 7     | Pipeline end-to-end            |
| `test_fixes.py`                  | —     | Régressions                    |
| `test_multi_invoice.py`          | —     | Scénarios N factures           |

### Conventions

- Classes `TestXxx`, méthodes `test_xxx`.
- Fixtures partagées : `make_invoice()`, `make_payment()` (`test_orchestrator.py:17, 25`).
- Un test = une assertion claire (méthode + confiance min, ou layer attendu).

### Pattern de test typique

```python
def test_swift_fees_tolerance(self):
    inv = make_invoice("FAC001", 10000.0)
    pay = make_payment(9972.50, refs=[])           # -27.50 € de frais
    matcher = BusinessRuleMatcher(C2Config())

    result = matcher.match(pay, [inv])

    assert result is not None
    assert result.method == MatchMethod.C2_TOLERANCE
    assert result.confidence >= 0.90
    assert result.allocated[inv.id] == 9972.50
```

---

## 15. MLOps & boucle de feedback

Module : `reconciliation/mlops.py`.

### La boucle

```
C6 (revue humaine) → ReviewFeedback   ──► accumulé en mémoire/DB
                                            │
                                            ▼
                                  ┌─ trigger 1 : 7 jours ─────┐
                                  ├─ trigger 2 : 100 samples ─┤
                                  └─ trigger 3 : PSI > 0.20 ──┘
                                            │
                                            ▼
                                   MLMatcher.train(...)
                                  (LightGBM + XGB + RF + meta)
                                            │
                                            ▼
                              C4 mis à jour, intégré au pipeline
```

### Les 3 déclencheurs de retraining

1. **Cadence** : tous les 7 jours par défaut.
2. **Volume** : dès que 100 nouveaux feedbacks C6 sont disponibles.
3. **Drift** : Population Stability Index entre la distribution train et la distribution courante. PSI > 0,2 → retraining immédiat.

### Métriques monitorées (13)

Volume traité, taux d'automatisation, précision par couche, latence p50/p95, taux d'erreur, ratio C6, âge du modèle, PSI par feature, distribution des `MatchMethod`, taux de succès LLM, coût LLM mensuel, taille de la file C6, SLA respect.

### Source de vérité pour le retraining

- `MatchResult` C1 (confidence ≥ 0.97) → labels positifs sûrs.
- Décisions `APPROVE` / `CORRECT` de C6 → labels human-confirmed.
- Décisions `REJECT` → labels négatifs.

---

## 16. LLM (C5) en sécurité

C5 est la couche la plus puissante mais aussi la plus à risque (coût, fuite de données, hallucinations). Quelques règles d'hygiène :

### Règles strictes

1. **Ne jamais committer `.env`**. Il est listé dans `.gitignore`. Si tu modifies une config sensible, double-vérifie avec `git status`.
2. **Toujours définir un budget mensuel** (`LLM_MONTHLY_BUDGET`). Au-delà, les appels sont refusés.
3. **Kill switch en cas d'incident** : `LLM_ENABLED=false` désactive complètement la couche, sans modification de code.
4. **Ne pas envoyer de PII** : les libellés bancaires peuvent contenir des noms. Le code C5 minimise déjà mais reste vigilant si tu modifies un prompt.
5. **Cache activé** : par hash MD5 du prompt. Évite les requêtes redondantes coûteuses.

### Validation anti-hallucination (5 contrôles)

C5 rejette une réponse si :
- une référence proposée par le modèle n'existe **pas** dans `open_invoices` ;
- le total alloué dépasse le montant payé ;
- la confiance proposée est > 0.99 (impossible pour un LLM, signe d'over-confident) ;
- aucun raisonnement n'est fourni ;
- le format de réponse JSON ne valide pas le schéma attendu.

### Choix du modèle

| Modèle Anthropic       | Pour quel cas                                         |
|------------------------|--------------------------------------------------------|
| `claude-haiku-4-5`     | Volumes, latence faible, cas plutôt simples           |
| `claude-sonnet-4-5`    | **Défaut recommandé** — bon ratio précision / coût    |
| `claude-opus-4-5`      | Cas extrêmement ambigus, audit, faibles volumes       |

Côté OpenAI : `gpt-4o`, `gpt-4-turbo` ou `gpt-3.5-turbo` selon le cas.

---

## 17. Dégradation gracieuse des dépendances

Le pipeline est conçu pour fonctionner **même si certaines dépendances optionnelles sont absentes**. La couche concernée est alors *skippée* avec un log, sans crasher.

| Dépendance manquante         | Couche désactivée | Conséquence                              |
|------------------------------|-------------------|------------------------------------------|
| `unidecode`                  | C0 (partiel)      | ❌ Erreur — c'est obligatoire             |
| `rapidfuzz`                  | C3                | Plus de fuzzy matching                   |
| `scikit-learn`               | C3 + C4           | Pas de TF-IDF ni d'ensemble ML           |
| `lightgbm`                   | C4                | Ensemble dégradé                         |
| `xgboost`                    | C4                | Ensemble dégradé                         |
| `sentence-transformers`      | C3 (avancé)       | Aucun impact (désactivé par défaut)      |
| `anthropic` ou `openai`      | C5                | LLM désactivé, fallback C6               |
| `streamlit` / `plotly`       | App               | UI démo indisponible (CLI fonctionne)    |
| Clé API LLM absente          | C5                | LLM désactivé, fallback C6               |

**Politique** : C0-C2 doivent **toujours** fonctionner (cœur métier). C3-C5 sont des accélérateurs.

---

## 18. Dépannage / FAQ

### "Mes tests passent mais la démo Streamlit explose"
Probablement `streamlit` ou `plotly` non installés : `pip install streamlit plotly pandas`.

### "ImportError: rapidfuzz"
```bash
pip install rapidfuzz
```
Ou plus large : `pip install -r requirements.txt`.

### "C4 n'est jamais appelé dans mes logs"
Par défaut, `MLMatcher` n'est pas entraîné. L'orchestrateur le détecte (`is_trained=False`) et passe à C5. Pour utiliser C4 :
```python
ml = orch._ml_matcher
ml.train(your_training_data)
```

### "C5 ne fait jamais d'appel"
Vérifie :
1. `.env` créé et chargé (`cp .env.example .env`).
2. `LLM_ENABLED=true`.
3. `LLM_API_KEY` ou `ANTHROPIC_API_KEY` renseignée.
4. Budget non dépassé : remettre `LLM_MONTHLY_BUDGET` à une valeur > 0.

### "Le pipeline retourne `final_match=None` alors que je vois la facture"
- Le score n'a pas atteint le seuil. Imprime `ctx.candidate_matches` pour voir les hypothèses.
- Vérifie `ctx.layers_attempted` : si C3 manque, c'est probablement `rapidfuzz` non installé.
- Le cas est peut-être légitime → C6 (file de revue).

### "Les batches sont lents"
Utilise `process_batch(payments, invoices, rebuild_every=100)` au lieu d'une boucle manuelle. Les index C1/C3 sont rebuild automatiquement.

### "Les factures déjà matchées sont re-proposées"
Tu utilises `process_payment` en boucle sans retirer les factures consommées. Soit utilise `process_batch`, soit retire manuellement après chaque match :
```python
matched = {inv.id for inv in ctx.final_match.invoices}
open_invoices = [inv for inv in open_invoices if inv.id not in matched]
```

### "PSI très élevé après mise en prod"
Distribution de production différente de l'entraînement. Déclenche un retraining :
```python
from reconciliation.mlops import MLOpsManager
mlops.trigger_retraining(reason="psi_drift")
```

### "Comment voir le détail d'un match en JSON ?"
```python
import dataclasses, json
print(json.dumps(dataclasses.asdict(ctx.final_match), default=str, indent=2))
```

---

## 19. Conventions de code

Adopte ces règles pour rester cohérent avec l'existant.

### Style général

- **Type hints obligatoires** sur toute signature publique. Le projet est entièrement typé.
- **`from __future__ import annotations`** en tête de chaque module pour autoriser les annotations forward.
- **Dataclasses** pour modèles et configuration. Pas de classe artificielle qui ne porte que des données.
- **Enum** (`MatchMethod`, `LabelClass`, `Currency`) pour les valeurs discrètes — jamais de strings magiques.
- **Pas d'abstraction prématurée** : trois lignes similaires valent mieux qu'une factory inutile.

### Commentaires

- Par défaut **pas de commentaire**. Les noms parlent.
- N'écris un commentaire que pour le **pourquoi** non-évident : invariant caché, contournement d'un bug spécifique, contrainte métier surprenante.
- Pas de docstring multi-paragraphes. Une ligne maximum.

### Erreurs & validation

- Valider aux **frontières** : entrée utilisateur, API externes. Pas d'`isinstance` défensif partout.
- Faire confiance au code interne et aux garanties du framework.
- Les couches gèrent leurs erreurs en isolation (cf. `orchestrator.py:194` — un crash dans une couche ne tue pas le pipeline).

### Performance

- C1-C2 doivent rester **< 10 ms**. Si ta règle dépasse, profile-la.
- C3-C4 ont droit à 100 ms.
- Privilégie les structures O(1) : `InvoiceHashIndex`, `DuplicateIndex`. Pas de scan linéaire.
- Pour les calculs ML, vectorise avec NumPy plutôt que des boucles Python.

### Logging

- Module : `logger = logging.getLogger(__name__)`.
- Niveaux : `DEBUG` pour la trace fine, `INFO` pour les événements pipeline, `WARNING` pour les anomalies métier, `ERROR` pour les erreurs techniques.
- `processing_log` (`ReconciliationContext`) capture les événements structurés pour la traçabilité.

---

## 20. Glossaire

Ordre alphabétique. Liens vers la section 3 pour les termes métier.

| Terme | Sens dans le projet |
|-------|----------------------|
| **Acompte**             | Paiement partiel d'une facture (30/40/50/70 % typiques). Détecté en C2. |
| **Allocation**          | Répartition d'un montant payé sur une ou plusieurs factures. Champ `MatchResult.allocated`. |
| **Avoir**               | Note de crédit (`CreditNote`) qui réduit le montant à payer. Géré en C2. |
| **BL / CMR / DAE**      | Documents de livraison/transport. Référencés par C1-R007. |
| **Cédant**              | Entreprise qui cède ses factures au factor (notre client). |
| **Confidence**          | Score 0.0-1.0 de fiabilité d'un match. Seuil d'auto-match : 0.90 (sauf C3 / C4). |
| **Débiteur**            | Entité qui doit payer la facture. `Debtor` dataclass. |
| **Drift**               | Dérive statistique. Mesurée par PSI. PSI > 0.2 → retraining. |
| **Early-exit**          | Stratégie de l'orchestrateur : on s'arrête à la première couche qui dépasse le seuil. |
| **Escompte**            | Réduction pour paiement anticipé. C2-R-M003. |
| **Factor**              | Société qui rachète les créances. C'est nous. |
| **Fingerprint**         | Hash SHA-256 d'un paiement pour détection de doublon (`Payment.fingerprint`). |
| **Hash index**          | `InvoiceHashIndex` — lookup O(1) sur clés normalisées de référence. |
| **IBAN**                | Identifiant de compte bancaire international. Clé d'enrichissement débiteur. |
| **ISO 20022**           | Format structuré des messages SEPA. Champs `/ROC/`, `/RFB/`, `EndToEndId`, `/INV/`. |
| **LambdaRank**          | Algorithme de ranking utilisé en C4 pour 1-to-N. |
| **Layer**               | Une des 6 couches du pipeline. Numérotée 0-6 (C0 préprocessing inclus). |
| **MatchMethod**         | Enum identifiant l'algorithme/règle qui a produit un match. |
| **MatchResult**         | Décision de matching : factures, méthode, confiance, allocation. |
| **MLOps**               | Pipeline de retraining automatique de C4 sur le feedback C6. |
| **NER**                 | Named Entity Recognition. C3 extrait 10 types d'entités du libellé. |
| **PSI**                 | Population Stability Index. Mesure de dérive entre deux distributions. |
| **PO**                  | Purchase Order — bon de commande. Utilisé par C1-R006. |
| **Reconciliation**      | Le rapprochement paiement ↔ facture(s). |
| **Retenue de garantie** | Pourcentage retenu (BTP : 5-10 %). C2-R-M005. |
| **RFA**                 | Remise de Fin d'Année. C2-R-M009. |
| **Score composite**     | Moyenne pondérée des 8 algos fuzzy en C3. |
| **SEPA**                | Réseau européen de virements. Frais OUR : -5 à -15 €. |
| **Subset sum**          | Trouver le sous-ensemble de factures dont la somme = montant payé. C2. |
| **SWIFT**               | Réseau international. Frais : -25 à -35 €. C2-R-M001. |
| **TF-IDF**              | Term Frequency-Inverse Document Frequency. C3 utilise des char n-grams TF-IDF. |
| **WHT**                 | Withholding Tax — retenue à la source internationale. C2-R-M010. |

---

## 21. Pour aller plus loin

Une fois ce guide assimilé, voici l'ordre recommandé de lecture pour approfondir :

### Documentation complémentaire dans le repo

| Document                                  | Quand le lire                                        |
|-------------------------------------------|------------------------------------------------------|
| `README.md`                               | Vue marketing + démarrage rapide                     |
| `RAPPORT_COLLABORATION.md`                | Rétrospective détaillée du build et résultats        |
| `reconciliation/README.md`                | Catalogue technique fichier par fichier              |
| `app/README.md`                           | Détail des 11 pages Streamlit                        |
| `examples/README.md`                      | Détail de chaque démo                                |
| `tests/README.md`                         | Détail des suites de tests                           |
| `app/dossier_chief_of_staff.pdf`          | Résumé exécutif 1 page                               |
| `app/retex_claude_code.pdf`               | Retour d'expérience technique                        |
| `app/presentation_reconciliation_ia.pdf`  | Deck de présentation                                 |

### Parcours d'apprentissage suggéré

1. **Jour 1** : sections 1-6 de ce document + `python -m examples.demo_simulation`.
2. **Jour 2** : section 7 (les 6 couches) + lire `reconciliation/orchestrator.py` ligne par ligne.
3. **Jour 3** : `reconciliation/c1_exact_matching.py` + tests associés.
4. **Jour 4** : `reconciliation/c2_business_rules.py` (le plus dense) + tests.
5. **Jour 5** : C3 + C4 + démo Streamlit.
6. **Semaine 2** : ajouter ta première règle métier (recette 11.1).

### Aide

- **Bug ou incohérence dans ce document ?** Ouvre une PR. Ce document est censé évoluer avec le code.
- **Question métier ?** Regarde d'abord le glossaire (section 20), puis `RAPPORT_COLLABORATION.md`.
- **Question technique ?** Les `README.md` par dossier sont précis et à jour.

Bienvenue dans le projet.
