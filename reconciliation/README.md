# reconciliation/ — Coeur du systeme de reconciliation

Ce dossier contient l'implementation complete du pipeline de reconciliation
paiement-facture en 6 couches. Chaque fichier correspond a une couche ou
un composant transversal du systeme.

## Architecture des fichiers

```
reconciliation/
  models.py              # Modeles de donnees partages
  config.py              # Configuration centralisee
  c0_preprocessing.py    # Couche 0 : Normalisation
  c1_exact_matching.py   # Couche 1 : Matching deterministe
  c2_business_rules.py   # Couche 2 : Regles metier
  c3_nlp_fuzzy.py        # Couche 3 : NLP & Fuzzy
  c4_ml.py               # Couche 4 : Machine Learning
  c5_llm.py              # Couche 5 : LLM generative
  c6_human_review.py     # Couche 6 : Revue humaine
  orchestrator.py        # Pipeline end-to-end
  mlops.py               # MLOps & monitoring
```

---

## models.py — Modeles de donnees

Definit toutes les structures de donnees partagees entre les couches :

| Classe | Description |
|--------|-------------|
| `Payment` | Paiement entrant avec montant, date, libelle, IBAN, signaux extraits |
| `Invoice` | Facture ouverte avec reference, montant TTC/HT, debiteur, echeance |
| `Debtor` | Profil du debiteur (comportement, taux, risque, historique) |
| `CreditNote` | Avoir / note de credit |
| `MatchResult` | Resultat d'un rapprochement (factures matchees, confiance, methode, flags) |
| `PaymentSignals` | Signaux extraits en C0 (references, montants, periodes, mots-cles) |
| `ISO20022Fields` | Champs structures d'un virement SEPA (ROC, RFB, E2EId, TxId) |
| `ReconciliationContext` | Contexte complet d'un paiement traversant le pipeline |
| `MatchMethod` | Enum de toutes les methodes de matching (C1_EXACT_REF, C2_TOLERANCE, etc.) |
| `LabelClass` | Classification du libelle (SINGLE_REF, MULTI_REF, CRYPTIC, EMPTY...) |

---

## config.py — Configuration centralisee

Toutes les constantes et seuils sont regroupes dans des dataclasses configurables :

| Classe | Parametres principaux |
|--------|-----------------------|
| `C0Config` | Carte d'abreviations, prefixes bancaires a supprimer, padding numerique |
| `C1Config` | Fenetre temporelle (180j), seuil IBAN unique (120j) |
| `C2Config` | Tolerances SWIFT (35EUR), SEPA OUR (15EUR), arrondi (1EUR), % acomptes |
| `C3Config` | Seuil fuzzy (0.75), ngram range TF-IDF, seuil NER |
| `C4Config` | Seuil confiance ML (0.85), poids ensemble, intervalle retraining |
| `C5Config` | Provider, api_key, model, temperature, budget mensuel (USD), kill switch |
| `C6Config` | Taille max file, poids priorite, SLA (24h) |
| `OrchestratorConfig` | Seuil auto-match (0.90), timeouts par couche |

---

## c0_preprocessing.py — Couche 0 : Normalisation universelle

Appliquee a 100% des paiements. 14 transformations deterministes et idempotentes :

**Classe principale : `PaymentPreprocessor`**

1. **Normalisation du libelle** (N001-N014) :
   - N001 Uppercase, N002 Deaccentuation, N003 Strip ponctuation
   - N004 Normalisation separateurs, N005 Parsing montants (EUR/US)
   - N006 Deduplication espaces, N007 Expansion abreviations metier
   - N008 Normalisation IBAN, N009 Parsing dates multi-format
   - N010 Normalisation devises, N011 Suppression prefixes bancaires
   - N012 Detection langue (FR/EN/DE/NL/ES/IT)
   - N013 Tokenisation n-grams, N014 Padding numerique

2. **Enrichissement contextuel** (C0.2) :
   - Resolution IBAN → debiteur via table de mapping
   - Chargement du profil debiteur (historique, avoirs, escomptes)

3. **Extraction de signaux** (C0.3) :
   - References brutes (regex greedy, 9 patterns)
   - Montants mentionnes dans le libelle
   - Periodes temporelles (mois, trimestres)
   - Mots-cles metier (acompte, avoir, escompte, retenue...)
   - Classification du libelle (SINGLE_REF, MULTI_REF, CRYPTIC, EMPTY...)
   - Score de qualite du libelle (0.0 a 1.0)
   - Fingerprint SHA-256 pour deduplication

---

## c1_exact_matching.py — Couche 1 : Matching deterministe

**Precision cible : 100% — zero faux positif.**
Temps d'execution cible : < 10ms par paiement.

**Classe principale : `ExactMatcher`**

7 regles executees en ordre de priorite :

| Regle | Description | Confiance |
|-------|-------------|-----------|
| R002 | **ISO 20022** : reference structuree SEPA (/ROC/, /RFB/, E2EId, TxId, /BV/) | 93-100% |
| R001 | **Ref exacte + montant** : ref extraite = ref facture, montant exact ou HT | 97-100% |
| R003 | **Hash index** : lookup O(1) via index multi-format (prefixes, zeros, annees) | 98% |
| R004 | **IBAN + montant** : debiteur identifie + montant unique/total/batch/mois | 94-98% |
| R005 | **Solde total** : paiement = somme de toutes les factures ouvertes (net avoirs) | 95-96% |
| R006 | **Purchase Order** : reference PO extraite, mapping PO → factures | 88-96% |
| R007 | **Bon de Livraison** : reference BL/CMR/DAE, mapping BL → factures | 92-97% |

**Classe utilitaire : `InvoiceHashIndex`**
- Index de hachage MD5 multi-format
- Genere toutes les variantes d'une reference (avec/sans prefixe, padding, annee)
- Lookup O(1) quelle que soit la taille du portefeuille

---

## c2_business_rules.py — Couche 2 : Regles metier avancees

**Encode la connaissance metier du factoring. 100% deterministe et auditable.**

**Classe principale : `BusinessRuleMatcher`**

### Tolerances montant (12 regles R-M001 a R-M012)
- Frais SWIFT internationaux (jusqu'a -35 EUR pour pays hors SEPA)
- Frais SEPA OUR (jusqu'a -15 EUR)
- Escompte contractuel (taux dans le profil debiteur)
- Arrondi comptable (+/- 1 EUR)
- Retenue de garantie BTP (3%, 5%, 10%)
- Deduction d'avoirs (exacts ou partiels)
- Penalite de retard
- RFA - Remise Fin d'Annee
- Retenue a la source (WHT) par pays (MA 20%, TN 15%, TR 18%...)
- Acomptes standards (30%, 40%, 50%, 70%)

### Multi-factures (Subset Sum)
3 strategies combinees :
- **Greedy** : plus gros d'abord
- **Exact** : brute-force pour N <= 12
- **Two-sum** : paires via table de hachage

### Patterns temporels
- Detection d'habitudes de paiement (jour fixe + delai moyen)
- Rapprochement par periode mentionnee dans le libelle ("FACTURES OCTOBRE 2024")

### Anti-doublons (8 controles)
- Fingerprint identique (doublon exact)
- Meme jour + meme montant + meme debiteur
- Montant proche + meme semaine + meme debiteur

### Acomptes N-to-1
- Detection de paiements partiels via mots-cles (ACOMPTE, ADVANCE, PARTIAL)
- Verification ratio paiement/facture contre pourcentages standards

---

## c3_nlp_fuzzy.py — Couche 3 : NLP, Fuzzy matching & Embeddings

**Pour les cas ou C1/C2 echouent : references mal ecrites, labels ambigus.**

**Classe principale : `NLPFuzzyMatcher`**

### C3.1 — Fuzzy matching (8 algorithmes)
Score composite pondere de :
1. Levenshtein normalise (15%)
2. Jaro-Winkler (15%)
3. Token Sort Ratio (10%)
4. Token Set Ratio / Jaccard (10%)
5. Partial Ratio (15%)
6. N-gram Jaccard caracteres (10%)
7. LCS Ratio (10%)
8. Numeric Ref Similarity (15%) — compare uniquement les parties numeriques

Pre-filtrage rapide par similarite numerique, puis score complet sur les top-10 candidats.

### C3.2 — NER custom
10 types d'entites extraites par regex :
INVOICE_REF, PO_REF, BL_REF, AMOUNT, DATE, PERIOD, DEBTOR_CODE, IBAN, CREDIT_NOTE, CONTRACT

### C3.3 — Embeddings semantiques
Classe `EmbeddingMatcher` utilisant sentence-transformers (paraphrase-multilingual-MiniLM-L12-v2).
Similarite cosinus pour rapprochement semantique.

### C3.4 — Regles NLP combinees
Score multi-signal combinant NER + fuzzy + montant + debiteur.

### C3.5 — TF-IDF caracteres
Classe `TFIDFMatcher` avec n-grams caracteres (2-4) pour similarite cosinus.

---

## c4_ml.py — Couche 4 : Machine Learning supervise

**Classe principale : `MLMatcher`**

### 42 features (4 groupes)
- **G1 Amount (10)** : diff, ratio, log, match exact/HT, arrondi, montant dans label
- **G2 Reference (12)** : scores fuzzy composites, qualite label, ref dans label, n-grams
- **G3 Temporal (10)** : jours depuis emission, jours vs echeance, meme mois, jour semaine
- **G4 Behavioral (10)** : debiteur connu, regularite, retard moyen, risque, mots-cles

### Ensemble (`EnsembleModel`)
- LightGBM (200 arbres, lr=0.05)
- XGBoost (200 arbres, lr=0.05)
- Random Forest (150 arbres)
- Meta-classifieur : regression logistique sur les 3 probas

### LambdaRank (`LambdaRankModel`)
Pour le ranking 1-to-N : quand un paiement a plusieurs candidats, les classe par pertinence.

### Active Learning (`ActiveLearner`)
6 strategies de selection des echantillons les plus informatifs :
uncertainty, margin, entropy, committee, diversity, hybrid

### Drift Detection
Population Stability Index (PSI) par feature pour detecter les derives des donnees.
PSI > 0.2 → retraining automatique.

---

## c5_llm.py — Couche 5 : LLM & IA generative

**Pour les cas complexes, ambigus ou cryptiques que les regles ne resolvent pas.**

**Classe principale : `LLMMatcher`**

### Prompts optimises
| Prompt | Usage |
|--------|-------|
| `PROMPT_GENERIC` | Cas standard avec contexte complet |
| `PROMPT_CRYPTIC` | Labels vides ou cryptiques, analyse du pattern |
| `PROMPT_AMBIGUOUS` | Plusieurs candidats possibles, desambiguation |

### Validation anti-hallucination (`ResponseValidator`)
5 controles sur chaque reponse LLM :
1. Toutes les references citees doivent exister dans le portefeuille
2. Les montants alloues doivent etre positifs et raisonnables
3. Le total alloue ne doit pas depasser le montant du paiement
4. La confiance ne doit pas depasser 0.99 (signe d'hallucination)
5. Un raisonnement doit etre fourni

### Client LLM (`LLMClient`)
- Supporte Claude (Anthropic) et GPT (OpenAI)
- Cache par hash MD5 du prompt
- Metriques de cout et tokens

---

## c6_human_review.py — Couche 6 : Revue humaine intelligente

**File de revue priorisee pour les cas non resolus automatiquement.**

**Classe principale : `HumanReviewQueue`**

### Algorithme de priorisation (C6.1)
Score = ponderation de 4 criteres :
- **Montant** (30%) : les gros montants d'abord
- **Anciennete** (25%) : les plus vieux d'abord
- **Gap de confiance** (25%) : les plus proches du seuil (faciles a resoudre)
- **Risque debiteur** (20%) : debiteurs a risque d'abord

### Feedback structure (`ReviewFeedback`)
6 decisions possibles : APPROVE, REJECT, CORRECT, SPLIT, DEFER, ESCALATE
Capture : refs correctes, allocation, raison, temps passe, tags

### Donnees de revue (C6.2)
Prepare toutes les informations pour l'interface :
- Paiement complet (montant, date, label, signaux)
- Liste des candidats avec scores et explications
- Factures ouvertes du debiteur
- Couches tentees et logs de traitement

---

## orchestrator.py — Pipeline end-to-end

**Classe principale : `ReconciliationOrchestrator`**

Orchestre le passage d'un paiement a travers les 6 couches avec :
- **Early-exit** : des qu'un match depasse le seuil de confiance (defaut 0.90)
- **Tracking des metriques** : distribution par couche et par methode
- **Gestion d'erreurs** : chaque couche est isolee, une erreur n'arrete pas le pipeline
- **Traitement batch** : retire les factures matchees du portefeuille ouvert entre chaque paiement
- **Detection de doublons** : avant toute tentative de matching

`PipelineMetrics` : taux d'automatisation, distribution, temps moyen, erreurs.

---

## mlops.py — Pipeline d'amelioration continue

**Classe principale : `MLOpsPipeline`**

### Retraining automatique
Declenchement sur 3 criteres :
- Planifie (tous les 7 jours)
- Seuil de feedback (100 echantillons accumules)
- Derive detectee (PSI > 0.2)

### 13 metriques de monitoring
Volume (paiements/heure, taux auto, temps moyen), Qualite (precision, recall, F1, taux FP),
Business (SLA, backlog, temps revue), Modele (PSI drift, staleness)

### Boucle de feedback
C6 → collecte feedback → accumulation → retraining C4 → amelioration continue
