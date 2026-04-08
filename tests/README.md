# tests/ — Tests unitaires

74 tests couvrant toutes les couches du systeme de reconciliation.

## Lancer les tests

```bash
# Tous les tests
python -m pytest tests/ -v

# Un fichier specifique
python -m pytest tests/test_c1_exact_matching.py -v

# Un test specifique
python -m pytest tests/test_c2_business_rules.py::TestAmountTolerance::test_swift_fees -v

# Avec couverture
python -m pytest tests/ --cov=reconciliation --cov-report=term-missing
```

## Dependances requises

```bash
pip install pytest unidecode rapidfuzz numpy
```

## Structure des tests

### test_c0_preprocessing.py (29 tests)

Tests de la couche 0 — normalisation et extraction de signaux.

| Classe | Tests | Description |
|--------|-------|-------------|
| `TestLabelNormalization` | 7 | Uppercase, deaccentuation, strip ponctuation, espaces, abreviations, prefixes bancaires, label vide |
| `TestAmountNormalization` | 4 | Format europeen (15.000,50), americain (15,000.50), comma simple, vide |
| `TestIBANNormalization` | 2 | Normalisation IBAN avec espaces, vide |
| `TestDateNormalization` | 4 | DD/MM/YYYY, DD/MM/YY, ISO YYYY-MM-DD, invalide |
| `TestCurrencyNormalization` | 3 | Symbole euro, USD, devise inconnue → EUR par defaut |
| `TestLanguageDetection` | 2 | Detection FR et EN |
| `TestSignalExtraction` | 4 | Extraction refs, classification EMPTY, score qualite, mots-cles |
| `TestFullPreprocessing` | 2 | Pipeline complet, enrichissement debiteur via IBAN |

### test_c1_exact_matching.py (12 tests)

Tests de la couche 1 — matching deterministe.

| Classe | Tests | Description |
|--------|-------|-------------|
| `TestR001ExactRef` | 5 | Ref exacte single (R001-A), match HT (R001-C), multi-ref (R001-D), mauvais montant, mauvais debiteur |
| `TestR002ISO20022` | 2 | Reference /ROC/ SEPA, EndToEndId |
| `TestR004IBANAmount` | 2 | Montant unique (R004-A), solde total (R004-B) |
| `TestR005FullBalance` | 1 | Solde net avec deduction avoirs |
| `TestR006PO` | 1 | Matching via numero de commande (PO) |
| `TestHashIndex` | 2 | Lookup par variantes de format, ref manquante |

### test_c2_business_rules.py (11 tests)

Tests de la couche 2 — regles metier.

| Classe | Tests | Description |
|--------|-------|-------------|
| `TestAmountTolerance` | 4 | Arrondi ±1EUR, frais SWIFT (-28EUR), escompte 2%, retenue BTP 5% |
| `TestCreditNotes` | 1 | Deduction d'avoir exact (facture 10000 - avoir 500 = 9500) |
| `TestSubsetSum` | 2 | Two-sum (2 factures), greedy (5 factures) |
| `TestDuplicateDetection` | 2 | Doublon exact (fingerprint), meme jour + meme montant |
| `TestInstallments` | 1 | Acompte 30% avec mot-cle "ACOMPTE" |

### test_c3_nlp_fuzzy.py (16 tests)

Tests de la couche 3 — NLP et fuzzy matching.

| Classe | Tests | Description |
|--------|-------|-------------|
| `TestFuzzyAlgorithms` | 9 | Levenshtein (identique, similaire, different), Jaro-Winkler, Token Set, N-gram, Numeric Ref (identique, leading zeros), score composite |
| `TestNER` | 5 | Extraction invoice ref, amount, date, credit note, texte vide |
| `TestNLPFuzzyMatcher` | 2 | Match fuzzy (ref off-by-one), pas de match (ref completement differente) |

### test_orchestrator.py (7 tests)

Tests du pipeline end-to-end.

| Classe | Tests | Description |
|--------|-------|-------------|
| `TestOrchestratorPipeline` | 5 | Match C1 exact, match C2 tolerance, fallback revue humaine, batch processing, metriques |
| `TestOrchestratorEdgeCases` | 2 | Portefeuille vide, preprocessing applique |

## Convention de tests

- Les helpers `make_invoice()` et `make_payment()` simplifient la creation de donnees de test
- Chaque test verifie : le resultat non-null, la methode de matching, le score de confiance, les flags
- Les tests sont independants et executables individuellement
- Pas de dependance a des services externes (LLM, base de donnees)
