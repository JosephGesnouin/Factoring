# Challenge de l'approche — Réflexion stratégique

> Document de réflexion honnête sur les **forces et faiblesses structurelles**
> du pipeline 6 couches. Écrit après confrontation aux données réelles.
> À relire avant chaque itération majeure.

---

## 1. Ce qu'on a appris en confrontant aux vraies données

| Promesse marketing  | Réalité observée               | Cause                                                                 |
|---------------------|--------------------------------|-----------------------------------------------------------------------|
| 90 %+ d'automatisation | 1 % au premier run         | IBAN dans `identifiers_3` au lieu de `IBAN` → C1-R004 désactivée     |
| Précision 99,5 %   | Non mesurable                  | Pas de vérité terrain en production (ground_truth uniquement en simu) |
| Robuste aux libellés multilingues | Patterns regex FR-centric | Manque de couverture DE/IT/ES/NL/PL                                  |
| Détection doublons | Loggue 4 700 alertes en quelques minutes | CSV avec deux extractions concaténées                          |

**Leçon n°1** : le pipeline est *configurable*, pas *autonome*. Il dépend
fortement de la qualité des CSV en entrée et du mapping de colonnes. Sa
performance affichée en simulation **ne se transpose pas** mécaniquement.

**Leçon n°2** : C1 (déterministe) est le bras armé du système. Si C1 ne
peut pas fonctionner (mauvais mapping IBAN, libellés cryptiques), C2-C5
ne compensent que partiellement.

---

## 2. Forces réelles de l'approche

- **Modularité couche par couche** : on peut désactiver C5 (LLM) sans
  toucher au reste, ajouter une règle C2 sans risquer C1. Chaque couche
  a un test dédié.
- **Précision déterministe sur C1-C2** : zéro faux positif quand les
  règles passent. C'est rare en ML et ça compte pour de l'audit.
- **Latence basse** : <10 ms par paiement en C1/C2. Permet du temps-réel.
- **Observabilité** : `ctx.processing_log`, `metrics.by_layer`,
  `metrics.by_method` permettent de débugger chaque décision.
- **Dégradation gracieuse** : pas de dépendance ML obligatoire — C0/C1/C2
  fonctionnent avec `unidecode` seul.

---

## 3. Faiblesses structurelles (les vraies)

### 3.1 Dépendance forte aux données d'entrée
Le système suppose un **schéma propre** (colonnes nommées, types
homogènes, IBAN normalisés). En production :
- les IBAN sont rangés dans une colonne « bonus » (`identifiers_3`)
- les CSV sont concaténés sans dédoublonnage
- les `debtor_number` peuvent être en code legacy

→ Sans page **Diagnostic Données** robuste, le pipeline tourne en
sourdine sur des données pourries.

### 3.2 Pas de boucle d'apprentissage active sans humain
C4 (ML) doit être entraîné sur des paiements *résolus*. En l'absence de
boucle de feedback C6 → MLOps déjà déclenchée, **C4 est silencieusement
skip** dans 100 % des nouveaux déploiements. L'orchestrateur loggue
`"C4 model not trained"` et passe à C5.

→ La promesse "ensemble ML 42 features" n'est tenue qu'après plusieurs
mois de feedback humain accumulé. C'est rarement explicité.

### 3.3 Hypothèse implicite 1 paiement → N factures
Le subset sum (C2) gère bien le cas N factures → 1 paiement. Mais le cas
**inverse** (1 facture → M acomptes) est mal couvert : le ratio acompte
30/40/50/70 % marche en simulation, mais en pratique les acomptes sont
des montants ronds (`5 000 €`, `10 000 €`) sans ratio standard. Beaucoup
finissent en C6.

### 3.4 Pas de profil temporel
Si un débiteur paie **toujours le 15 du mois**, on devrait booster les
factures dont la date d'échéance est proche du 15. Ce signal n'est pas
exploité (`debtor_profiler` apprend la régularité mais pas le jour
préféré).

### 3.5 Pas d'inférence par graphe
Si on observe 5 paiements le même jour, du même débiteur, sur 5 factures
du même montant total, c'est presque sûrement un *batch* du même
émetteur. Le système traite chaque paiement isolément (C2 fait du
subset-sum dans une fenêtre, mais pas de propagation d'évidence entre
paiements voisins).

### 3.6 Pas de mesure de précision en production
On a `auto_rate` (combien sont auto-matchés). On n'a pas le **taux de
faux positifs** : combien de matches "automatiques" sont rejetés par
l'humain au contrôle a posteriori ? Sans ce signal, la métrique de
99,5 % de précision est invérifiable hors simulation.

### 3.7 Champ `mandate_id_RUM` ignoré
La colonne `mandate_id_RUM` dans `debtors_all.csv` est un identifiant
SEPA prélèvement extrêmement fort (1-to-1 avec un débiteur). Elle n'est
pas chargée par le loader.

### 3.8 Caches Streamlit invisibles
`@st.cache_data` peut servir un ancien résultat de simulation après
qu'on a basculé en données réelles. Pas de busting automatique sur
changement de mode. Le user doit penser à "Clear cache".

---

## 4. Angles morts technologiques

### 4.1 Embeddings sémantiques désactivés
`sentence-transformers` est commenté dans `requirements.txt`. Or des
embeddings cross-lingues (e.g. `paraphrase-multilingual-MiniLM-L12-v2`)
résoudraient 80 % des cas C3 fuzzy avec une qualité supérieure aux
8 algos pondérés.

### 4.2 LLM uniquement en fin de pipeline
C5 ne tourne **que** quand C1-C4 ont échoué. Mais un LLM est aussi bon
pour **valider** un match faiblement confiant de C2/C3. Pas d'usage
"second opinion" implémenté.

### 4.3 Pas de retrieval-augmented matching
On pourrait indexer toutes les factures ouvertes dans un vecteur store
(Faiss/Chroma) et faire une recherche sémantique pour chaque libellé
bancaire. C'est sans doute plus performant que le hash index pour les
libellés très bruités.

### 4.4 Pas d'extraction LLM des references
Le LLM est utilisé pour matcher, pas pour extraire. Un appel LLM
"extrais la référence facture de ce libellé en JSON" résoudrait des cas
où aucune regex ne tient.

---

## 5. Approches alternatives qu'on n'a pas évaluées

### 5.1 Matching probabiliste global (Hungarian assignment)
Au lieu de traiter chaque paiement isolément, formuler la
réconciliation comme un **problème d'affectation** : minimiser le coût
total de jointure entre N paiements et M factures, où chaque arête a un
coût (1 - confiance). Algo polynomial O((N+M)³). Capture les
dépendances globales (si un paiement X est affecté à la facture A, il
ne peut pas l'être à B).

### 5.2 Graph Neural Network
Encoder paiements + factures + débiteurs comme un graphe hétérogène,
apprendre les bonnes affectations par message passing. Adapté aux cas
N↔M, mais nécessite un dataset annoté conséquent.

### 5.3 Bandit / RL pour la stratégie d'orchestration
Aujourd'hui l'ordre C1→C2→C3→C4→C5 est figé. Un bandit pourrait
apprendre quelle couche essayer en premier pour chaque profil de
paiement (ex. libellé court + montant rond → essayer C2 d'abord ; libellé
long + bruit → C5).

### 5.4 Active learning ciblé
Aujourd'hui les paiements C6 (revue humaine) sont priorisés par montant.
Un meilleur critère : prioriser les paiements **les plus informatifs**
pour le modèle (haute incertitude, proches de la frontière de décision).
Réduit le coût d'annotation pour atteindre une perf donnée.

### 5.5 Différentiation par segment
Le système est mono-modèle. Mais un débiteur grand-compte (millions/an,
process structuré) n'a pas le même comportement qu'une PME (chèques,
acomptes erratiques). Segmenter et entraîner des sous-modèles ?

---

## 6. Métriques manquantes — ce qu'on devrait afficher

| Métrique                       | Pourquoi                                         | Aujourd'hui |
|--------------------------------|--------------------------------------------------|-------------|
| Faux positifs C1/C2/C3 (auto)  | Vérifier la promesse de 99,5 % de précision     | ❌          |
| Taux d'annulation post-match   | Match auto défait par l'humain                  | ❌          |
| Latence p99 / p999             | SLA temps réel                                  | ❌ (seul avg)|
| PSI par feature C4             | Drift granulaire vs global                      | ❌          |
| Coût total / paiement          | h humain + tokens LLM                           | ❌          |
| Coverage IBAN / mandat / réf   | Hygiène données en continu                      | ✅ (page diag)|
| Time-to-resolution C6          | Combien de temps une revue humaine prend        | ❌          |
| Auto-rate par segment débiteur | Petites entreprises vs grandes                  | ❌          |

---

## 7. Risques cachés

1. **Sur-confiance dans C1** : les règles déterministes peuvent matcher
   à 98-100 % de confiance des cas faux. Ex. : 2 factures du même
   débiteur avec le même montant, l'IBAN du payeur matche → C1 attribue
   à la première trouvée. Mauvaise facture, 98 % de confiance.

2. **Cumul d'erreurs C0 → C1** : si C0 extrait mal une référence, C1
   l'utilise comme si c'était propre. Pas de re-validation.

3. **Dépendance aux clés API** : C5 sans clé → fallback silencieux à C6.
   Aucun monitoring de "combien de fois on aurait pu appeler C5 et on a
   pas pu". Une clé qui expire passe inaperçue.

4. **Mise en cache trop agressive** : `@st.cache_data` ne re-calcule pas
   tant que les arguments ne changent pas. Si on modifie un CSV en
   place (même nom, même chemin), le cache sert l'ancien résultat.

5. **Doublons "métier" vs doublons "techniques"** : on confond les deux.
   Un client peut **légitimement** payer 2 fois le même montant au
   même débiteur le même jour (commande A + commande B). Le détecteur
   exact_duplicate les fusionne.

---

## 8. Recommandations priorisées

### Niveau 1 — Fixer ce qu'on sait casser
1. Charger `mandate_id_RUM` côté débiteurs comme clé d'enrichissement
   alternative à l'IBAN.
2. Ajouter un signal qualité **par couche** (pas juste global).
3. Mesurer le coût-précision de C1 strict vs C1+C2 vs C1+C2+C3.

### Niveau 2 — Capturer plus de signal
1. **Faire** le mining offline des libellés non-matchés pour découvrir
   des patterns récurrents non couverts par les regex actuelles
   (`pattern_miner.py`).
2. Activer `sentence-transformers` (déjà câblé en C3, juste désactivé).
3. Charger le téléphone et l'email du débiteur — ils peuvent apparaître
   dans le libellé bancaire.

### Niveau 3 — Repenser l'orchestration
1. Mettre C5 en "second opinion" sur les matches C2/C3 à confiance
   moyenne (0.80-0.92), pas seulement en fallback.
2. Évaluer le matching global (Hungarian) sur un batch quotidien :
   compare ses choix à ceux du pipeline séquentiel.

### Niveau 4 — Construire les boucles manquantes
1. Logger en base les **rejets humains** post-match auto pour mesurer la
   précision réelle.
2. Calculer la **précision rolling 30 j** par couche et par méthode.
3. Mettre en place un **canary** : 1 % du flux traité aussi par une
   version expérimentale du pipeline, comparer offline.

---

## 9. Ce qu'on devrait écrire avant le prochain commit

| Doc                                | Pour                                                  |
|------------------------------------|-------------------------------------------------------|
| `EVALUATION.md`                    | Comment mesurer la qualité **en production**, avec et sans ground truth (proxy via rejets humains, A/B sur un échantillon). |
| `DATA_QUALITY.md`                  | Liste exhaustive des hypothèses sur les CSV avec un test associé (en `tests/test_real_data_assumptions.py`). |
| `BENCHMARK.md`                     | Comparaison documentée vs : (a) règles seules, (b) ML seul, (c) LLM seul, (d) pipeline complet. Sur le même dataset. |

---

## 10. La question qui dérange

> **Si on remplaçait tout le pipeline par "un LLM bien prompté + un
> retrieval sur les factures ouvertes", quelle serait la différence ?**

À tester sérieusement avant la prochaine itération. Ce serait :
- moins de code, moins de bugs, moins de docs ;
- plus cher (coût LLM par paiement) ;
- moins auditable (rules explicites vs prompt) ;
- probablement aussi précis sur les cas non triviaux.

La réponse n'est pas binaire. Mais c'est la baseline qu'on n'a pas
mesurée. Sans ce benchmark, on ne sait pas si notre architecture
6 couches *justifie* son coût d'entretien.
