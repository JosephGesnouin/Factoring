# config/ — Configuration applicative

Ce dossier est reserve pour les fichiers de configuration applicative
(fichiers YAML, JSON, .env, etc.) qui seraient utilises en production.

## Configuration actuelle

La configuration du systeme est geree par code dans `reconciliation/config.py`
via des dataclasses Python. Cela permet :

- Typage statique et valeurs par defaut
- Documentation inline des parametres
- Validation a l'instanciation
- Pas de parsing de fichiers a l'execution

## Parametres principaux

```python
from reconciliation.config import ReconciliationConfig

config = ReconciliationConfig()

# --- Seuils de la couche C2 ---
config.c2.swift_fee_max       # 35.0 EUR — tolerance max frais SWIFT
config.c2.sepa_our_fee_max    # 15.0 EUR — tolerance max frais SEPA OUR
config.c2.rounding_tolerance  # 1.0 EUR — tolerance arrondi comptable
config.c2.fx_tolerance_pct    # 0.01 — tolerance conversion devise (1%)
config.c2.subset_sum_max_invoices  # 15 — max factures pour subset sum

# --- Seuils de la couche C3 ---
config.c3.fuzzy_min_score                 # 0.75 — seuil min fuzzy matching
config.c3.embedding_similarity_threshold  # 0.80 — seuil embeddings

# --- Seuils de la couche C4 ---
config.c4.confidence_threshold  # 0.85 — seuil confiance ML
config.c4.drift_psi_threshold   # 0.2 — seuil PSI pour retraining

# --- Orchestrateur ---
config.orchestrator.auto_match_confidence_threshold  # 0.90 — seuil auto-match
config.orchestrator.escalation_confidence_threshold  # 0.50 — seuil escalade
```

## Extension future

Pour une mise en production, ce dossier accueillerait :

```
config/
  production.yaml       # Parametres de production
  staging.yaml          # Parametres de recette
  development.yaml      # Parametres de dev
  debtors/              # Profils debiteurs specifiques
  rules/                # Regles metier customisees par client
```
