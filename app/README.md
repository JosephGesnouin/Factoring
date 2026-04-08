# app/ — Demo Streamlit Interactive

Application de demonstration interactive pour presenter le systeme
de reconciliation IA a un top management.

## Lancer l'application

```bash
pip install streamlit plotly pandas
streamlit run app/streamlit_app.py
```

## Pages

### 1. Executive Summary
- 8 KPIs executifs (paiements, taux auto, revue, temps, volume EUR...)
- Pie chart distribution par couche (C1/C2/C3/C6)
- Barres empilees evolution mensuelle (auto vs revue)
- Top methodes de matching

### 2. Architecture du Systeme
- Pipeline visuel interactif des 6 couches
- Explication du principe d'early-exit
- Accordeons detailles pour chaque couche avec regles et algorithmes

### 3. Simulation Live
- Table filtrable de tous les paiements traites
- Filtres par couche, debiteur, plage de confiance
- Code couleur par couche (vert C1, jaune C2, cyan C3, rouge C6)
- Distribution des methodes et histogramme des confiances

### 4. Analyse par Debiteur
- Tableau de bord par debiteur (taux, montant, confiance moyenne)
- Barres horizontales taux d'automatisation par debiteur
- Scatter plot pays (volume vs taux)
- Profil detaille d'un debiteur selectionne
- Pie chart couches + derniers paiements

### 5. Deep Dive Paiement
- Selection par type (C1/C2/subset/C6) ou manuellement
- Carte du paiement (montant, date, debiteur, couche)
- Affichage du libelle brut
- **Parcours complet dans le pipeline** : chaque couche avec timing et resultat
- Detail du matching (methode, confiance, flags, factures, allocation)
- Diagnostic des echecs (pourquoi C6)

## Fichiers

- `streamlit_app.py` — Application principale (5 pages)
- `simulation_data.py` — Backend de donnees (generation + simulation)
