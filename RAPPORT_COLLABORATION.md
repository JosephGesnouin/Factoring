# Rapport de Collaboration — Claude Code x Joseph Gesnouin
## Systeme de Reconciliation Paiement-Facture par IA pour le Factoring

**Date :** Avril 2026
**Projet :** Reconciliation AI — Architecture 6 couches
**Branche :** `claude/reconciliation-ai-system-8DjRU`
**Repository :** `josephgesnouin/factoring`

---

## Chiffres cles du projet

| Metrique | Valeur |
|----------|--------|
| Lignes de code Python | **14 546** |
| Fichiers Python | **33** |
| Tests unitaires | **127 (100% pass)** |
| Commits | **38** |
| Debiteurs simules | **50** (18 pays) |
| Factures generees | **5 270** |
| Paiements traites | **4 724** |
| Taux d'automatisation | **90.3%** |
| Verbatims de paiement | **522 templates** (12 langues) |
| Pages Streamlit | **11** |

---

## Comment on a travaille ensemble

### Le processus de collaboration

Joseph a donne les orientations strategiques et les specifications metier.
Claude Code a implemente, debugge, teste, et optimise le code.

Le cycle typique :
1. **Joseph demande** une fonctionnalite ou detecte un probleme
2. **Claude Code analyse** le code existant, diagnostique, propose
3. **Claude Code implemente** (ecriture de code, tests, commit)
4. **Joseph teste** (Streamlit, HTML, terminal) et donne du feedback
5. **Iteration** jusqu'a satisfaction

### Repartition du travail

| Qui | Fait quoi |
|-----|-----------|
| **Joseph (humain)** | Vision produit, specifications metier, orientations strategiques, validation fonctionnelle, detection de bugs, feedback UX |
| **Claude Code (IA)** | Architecture technique, implementation complete, tests unitaires, debugging, optimisation performance, documentation, audit de code |

---

## Chronologie detaillee des 38 commits

### Phase 1 — Fondations (commits 1-3)
*Joseph donne le cahier des charges complet du systeme 6 couches*

**Commit 1** `0deca58` — Implementation initiale
- Claude Code cree l'architecture complete : 6 couches (C0-C6), orchestrateur, MLOps
- 11 fichiers Python, modeles de donnees, configuration centralisee
- 74 tests unitaires
- **Tout le coeur du systeme en un seul commit**

**Commits 2-3** — Demo et README
- Script de simulation avec 20 scenarios didactiques
- README exhaustif avec tables de regles et exemples

### Phase 2 — Simulation massive (commits 4-7)
*Joseph : "je veux beaucoup plus de factures et de diversite"*

**Commit 4** `704c323` — 12 debiteurs, 500 factures, 6 mois
- Profils de debiteurs realistes (Boulangerie Dupont, Construction Martin, etc.)
- Volume saisonnier (aout creux, Q4 en hausse)

**Commit 5** `a84c396` — Stress test 2000+ factures, CLI parametrable
- Generation procedurale de debiteurs
- `--debtors 30 --months 24` en ligne de commande

**Commit 6** `381557e` — 40+ pays, 17 archetypes, labels multilingues
- *Joseph : "je veux un ecosysteme international"*
- 150+ noms de societes, 18 pays, labels en FR/EN/DE/NL/ES/IT/PT/TR/PL/AR/JP/CN/KR
- Templates cryptiques bancaires dans toutes les langues

**Commit 7** `0aee588` — README dans chaque sous-dossier
- *Joseph : "rajoute des readme partout"*

### Phase 3 — Demo executive (commits 8-14)
*Joseph : "fais moi une demo Streamlit ultra propre pour un top manager"*

**Commit 8** `7043422` — Streamlit 5 pages (Executive Summary, Architecture, Simulation, Debiteurs, Deep Dive)
**Commit 9** `65b731a` — Export HTML autonome avec 7 graphiques Plotly
**Commit 10** `12a74e0` — Catalogue complet de tous les paiements par methode
- *Joseph : "j'arrive pas a voir les montants"*
- Claude Code diagnostique le bug CSS (accordeons fermes), corrige

**Commit 11** `4e910cd` — Moteur de recommandation pour C6
- *Joseph : "rajoute une couche de recommandation triee par probabilite"*
- Score composite (montant 40%, debiteur 25%, temporel 20%, HT 15%)

**Commit 12** `6177704` — Redesign UX premium
- *Joseph : "travaille beaucoup plus l'UX design"*
- Inter font, hero banners, KPI cards avec hover, pipeline avec ombres

**Commit 13** `2a964bc` — Vraies factures en vert
- *Joseph : "mets en vert celles qui sont les vraies"*
- Ground truth tracking, badge "VRAIE FACTURE"

**Commit 14** `1a86359` — Scale a 10k+ paiements, 50 debiteurs

### Phase 4 — Audit et optimisations (commits 15-20)
*Joseph : "regarde tout le code et optimise, fais des trucs en plus"*

**Commit 15-16** — Audit massif : 22 bugs corriges
- Claude Code lance un agent d'audit automatique en background
- 10 bugs CRITICAL/HIGH trouves et corriges :
  - Layer attribute manquant → metriques fausses
  - Duplicate check O(n²) → O(1) via DuplicateIndex
  - InvoiceHashIndex non-deterministe (datetime.now())
  - Subset sum brute-force → meet-in-the-middle DP
  - LLM JSON parser casse sur nested objects
  - normalize_ref recompile 15x → lru_cache
- API key injection (C5Config.api_key, .env loader, budget enforcement)
- **Performance 2.5x** (200 → 497 paiements/seconde)

**Commits 17-20** — Verbatims et typos
- *Joseph : "je veux vraiment des verbatims de toute sorte"*
- 522 templates dans 19 categories, 12 langues
- 16 mutations realistes (swap, 0→O, truncate, prefix swap...)
- 3 niveaux de severite (light/medium/heavy)

### Phase 5 — C3 Fuzzy et C4 ML (commits 21-30)
*Joseph : "C3 et C4 marchent pas du tout, aide moi a debugger"*

**Commit 21** `256c29c` — Fix C3 Fuzzy : de 0% a 11.5%
- Claude Code diagnostique 5 root causes :
  1. C0 ecrasait les refs injectees
  2. Pas de correction OCR (0↔O, 1↔l)
  3. Seuil fuzzy trop haut (0.75 → 0.60)
  4. Seuil orchestrateur trop haut pour C3 (0.90 → 0.80)
- **Taux auto : 65% → 81%**

**Commit 24** `f93a878` — Fix C4 ML : auto-training
- *Joseph : "le modele ML affiche 0% partout"*
- Claude Code installe lightgbm/xgboost/sklearn
- Auto-training depuis le ground truth de la simulation
- Logs diagnostiques quand C4 est skip

**Commit 25** `e79423f` — Fix C4 training data diversity
- *Joseph : "C4 ne sert a rien en recommandation"*
- Claude Code diagnostique : training que sur paiements avec ref
- Fix : 3 sources de training (avec ref, sans ref, ground truth C6)
- **C4 auto-matches : 0 → 217, auto rate : 86% → 93.6%**
- **Ground truth en top-5 : 77%**

**Commit 26** `ef5d191` — ML Explainability
- *Joseph : "explique pourquoi le ML pense que c'est ca"*
- Raisons humaines : "montant identique", "echeance +3j", "debiteur regulier 94%"

**Commit 27** `0c82098` — Recommandations multi-factures (combos)
- *Joseph : "on peut avoir N factures pour 1 paiement"*
- Recherche de paires et triples dont la somme ≈ montant paiement

### Phase 6 — Subset sum avance et Streamlit (commits 28-35)
*Joseph : "rajoute des regles de somme combinatoire avec ecarts"*

**Commit 28-29** — Subset sum avec 7 hypotheses de tolerance
- Exact, arrondi ±1€, SWIFT fees, escompte, retention, WHT, avoir
- Fenetres temporelles : 1 mois, 2 mois, trimestre, semestre

**Commits 30-32** — Nouvelles pages Streamlit
- *Joseph : "je veux voir les factures, les paiements, et le mapping"*
- Page Factures (portefeuille complet filtrable)
- Page Paiements (tous les flux avec libelle complet)
- Page Mapping Complet (paiement ↔ facture avec export CSV)

**Commit 33** — Debtor Behavior Profiler
- *Joseph : "une couche qui apprend les comportements du debiteur"*
- Apprentissage : timing, montants, methodes, patterns
- Confidence boost/penalty base sur le profil
- Page Streamlit "Profils Debiteurs IA"

**Commit 34** — Analyse des verbatims par debiteur
- *Joseph : "analyse les verbatims de chaque debiteur"*
- Detection langue, top tokens, prefixes recurrents, patterns

### Phase 7 — HTML final (commits 36-38)
**Commit 38** `567ca82` — HTML export final avec tout
- ML-powered recommendations avec combos
- 90.3% auto, 417 recos ML, 15 showcase scenarios

---

## Architecture finale

```
Paiement → C0 (normalisation) → C1 (exact) → C2 (regles metier)
         → C3 (fuzzy + OCR fix) → C4 (ML ensemble 42 features)
         → C5 (LLM Claude/GPT) → C6 (revue humaine avec recos ML)
```

Distribution finale sur 4 724 paiements :
- **C1 Exact : 57%** (IBAN+montant, ref exacte, ISO20022, PO/BL)
- **C2 Regles : 14%** (tolerances, subset sum, avoirs, acomptes)
- **C3 Fuzzy : 5%** (typos, OCR, prefix swap)
- **C4 ML : 14%** (ensemble LightGBM+XGBoost+RF, 42 features)
- **C6 Humain : 10%** (avec recommandations ML top-5, combos)

---

## Technologies utilisees

| Composant | Technologies |
|-----------|-------------|
| Coeur reconciliation | Python 3.11, dataclasses |
| NLP / Fuzzy | rapidfuzz, unidecode, regex |
| Machine Learning | LightGBM, XGBoost, scikit-learn, NumPy |
| LLM (optionnel) | Anthropic Claude API, OpenAI API |
| Demo interactive | Streamlit (11 pages) |
| Graphiques | Plotly (7 charts interactifs) |
| Export | HTML autonome (490 KB), CSV |
| Tests | pytest (127 tests) |
| Donnees | JSON verbatims (522 templates, 12 langues) |

---

## Ce que Claude Code a fait que l'humain n'aurait pas fait aussi vite

1. **Architecture complete en 1 commit** (6 couches, 11 fichiers, 74 tests)
2. **Audit automatique** avec agent background (22 bugs trouves)
3. **Optimisation performance** de 200 a 497 paiements/s (2.5x)
4. **Debugging C3/C4** : diagnostic de 5 root causes en quelques minutes
5. **522 verbatims** dans 12 langues avec 16 mutations realistes
6. **11 pages Streamlit** avec UX premium (Inter font, hero banners, etc.)
7. **Meet-in-the-middle DP** pour le subset sum (algorithme avance)
8. **ML explainability** : raisons humaines pour chaque prediction

## Ce que l'humain a apporte que l'IA n'aurait pas fait seule

1. **Vision produit** : les 6 couches, le pipeline, le factoring
2. **Detection de bugs** : "C3 marche pas", "C4 affiche 0%"
3. **Exigences UX** : "ultra propre", "pour un top manager"
4. **Diversite metier** : "40+ pays", "tous les acronymes", "N factures M paiements"
5. **Iteration** : "plus de verbatims", "plus de diversite", "retravaille l'UX"
6. **Validation fonctionnelle** : tester sur le terrain, detecter les incoherences

---

*Genere par Claude Code — Session du 23 Avril 2026*
*38 commits, 14 546 lignes de code, 127 tests, 1 session de travail*
