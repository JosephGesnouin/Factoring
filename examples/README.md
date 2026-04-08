# examples/ — Simulations et demonstrations

3 scripts de simulation de complexite croissante pour tester le systeme
de reconciliation avec des donnees realistes.

## Lancer les simulations

```bash
# Demo simple : 20 scenarios didactiques
python -m examples.demo_simulation

# Simulation moyenne : 12 debiteurs, 500 factures, 6 mois
python -m examples.demo_large_simulation

# Stress test massif : 20+ debiteurs, 2000+ factures, 12 mois, 40+ pays
python -m examples.demo_stress_test
python -m examples.demo_stress_test --debtors 30 --months 24
```

---

## demo_simulation.py — Demo didactique

**But :** Montrer chaque scenario de matching un par un avec explications.

- 19 factures ouvertes, 20 paiements
- 1 debiteur type par scenario
- Affichage detaille de chaque etape (libelle, montant, methode, confiance, flags)
- Ideal pour comprendre le fonctionnement de chaque regle

**Scenarios couverts :**
1. Reference exacte + montant exact (C1)
2. ISO 20022 SEPA structure (C1)
3. Matching IBAN + montant unique (C1)
4. Reference PO / bon de commande (C1)
5. Solde total debiteur (C1)
6. Frais SWIFT internationaux (C2)
7. Escompte contractuel 2% (C2)
8. Retenue de garantie BTP 5% (C2)
9. Arrondi comptable ±1 EUR (C2)
10. Deduction d'avoir (C2)
11. Multi-factures / subset sum (C2)
12. Acompte 30% (C2)
13. Reference avec typo (C3)
14. Label completement cryptique (C6)
... et plus

---

## demo_large_simulation.py — Simulation 6 mois

**But :** Tester sur un volume realiste avec des debiteurs aux comportements varies.

### Donnees generees
- **12 debiteurs** nommes avec profils detailles :
  - Boulangerie Dupont (payeur modele, toujours la ref)
  - Construction Martin (BTP, retenue 5%, paieur en retard)
  - Schmidt Import GmbH (ISO 20022, erreur HT occasionnelle)
  - Groupe Leclerc Distribution (escompte 2%, RFA 3%, avoirs)
  - Transport Rossi Srl (refs BL, solde total)
  - Maroc Export SARL (frais SWIFT, retenue source 20%)
  - Pharma Nordic AB (subset sum, labels cryptiques)
  - AutoParts Polska (refs PO systematiques)
  - Tech Solutions Ltd (acomptes 30/70%)
  - Tunisie Textiles SA (WHT 15%, labels vides)
  - Iberia Foods SL (typos dans les refs)
  - Groupe Energie SA (paiements par periode)
- **~500 factures** sur 6 mois (juillet-decembre 2024)
- **~400 paiements** avec volume saisonnier
- **8 avoirs** pour les debiteurs avec deductions

### Volume saisonnier
- Aout : -50% (vacances)
- Octobre : baseline
- Decembre : +40% (fin d'annee)

### Sortie
- Barre de progression en temps reel
- Distribution par couche (C1/C2/C6)
- Distribution par methode de matching
- Resultats par debiteur (taux d'automatisation)
- Timeline mensuelle
- Echantillon detaille de 20 paiements
- File de revue humaine avec top 15 prioritaires

---

## demo_stress_test.py — Stress test international

**But :** Tester la robustesse et la performance a grande echelle avec diversite maximale.

### Donnees generees proceduralement
- **20-50+ debiteurs** (parametrable via `--debtors N`)
- **2000+ factures** sur 12 mois (parametrable via `--months N`)
- **1500+ paiements** avec scenarios ponderees
- **Reproductible** via `--seed N`

### Diversite geographique (40+ pays)
```
SEPA  : FR DE IT ES BE NL PT SE PL CZ HU RO AT FI DK IE LU SK SI LT LV EE HR BG GR CY MT
Non-SEPA : MA TN TR US BR CH GB DZ EG SN CI CM IN CN JP KR AE SA MX CO CL AU ZA NG IL
```

### 17 archetypes de comportement
| Archetype | Comportement type |
|-----------|-------------------|
| `exemplaire` | Toujours la ref, paiement exact, payeur modele |
| `iso20022` | Virements SEPA structures, champs /ROC/ /RFB/ |
| `btp_retention` | Retenue de garantie, acomptes, paieur en retard |
| `distribution` | Escompte, RFA, avoirs, paiements groupes |
| `international_fees` | Frais SWIFT, retenue a la source |
| `multi_facture` | Paiements groupes (subset sum), labels cryptiques |
| `po_bl` | References PO et BL systematiques |
| `installments` | Acomptes 30/50/70% puis solde |
| `fuzzy_typos` | Typos dans les references (swap, drop, 0→O) |
| `temporel` | Paiements par periode ("FACTURES OCTOBRE 2024") |
| `chaotique` | Labels inutilisables, montants aleatoires |
| `grand_compte` | Mix ISO20022, escompte, avoirs, volumes importants |
| `pme_rigoureux` | Ref toujours exacte, petits volumes |
| `africain_mix` | SWIFT + WHT + labels cryptiques |
| `asiatique` | SWIFT + labels en ideogrammes + cryptique |
| `americain` | ACH/WIRE, acomptes, labels EN |
| `scandinave` | ISO 20022, SEPA structure, rigoureux |

### Libelles multilingues (100+ templates)
Les libelles de paiement sont generes dans la langue du pays du debiteur :
- **FR** : REGLEMENT, PAIEMENT, VIR SEPA, REGL FACTURE...
- **EN** : WIRE TRANSFER, REMITTANCE, ACH PAYMENT, SETTLEMENT...
- **DE** : ÜBERWEISUNG, RECHNUNGSBEGLEICHUNG, SEPA-ÜBERWEISUNG...
- **NL** : BETALING FACTUUR, SPOEDBETALING, CREDITOVERSCHRIJVING...
- **ES** : TRANSFERENCIA RECIBIDA, PAGO FACTURA, LIQUIDACION...
- **IT** : BONIFICO RICEVUTO, PAGAMENTO FATTURA, ACCREDITO...
- **PT** : TRANSFERÊNCIA RECEBIDA, PAGAMENTO FATURA...
- **TR** : HAVALE GELEN, EFT ALINDI, FATURA ODEMESI...
- **PL** : PRZELEW PRZYCHODZACY, ZAPŁATA FAKTURY...
- **AR** : TAHWIL, TASDID FATOURA, SADDAD...
- **JP/CN/KR** : 送金受領, 收到汇款, 입금확인...

Les labels cryptiques (90+ templates) couvrent aussi toutes les langues :
tresorie interne, codes bancaires, references opaques, termes comptables locaux.

### Types de typos generes
5 mutations realistes pour le fuzzy matching :
- **swap** : inversion de 2 caracteres adjacents
- **drop** : suppression d'un caractere
- **replace_0_O** : confusion 0 / O
- **extra_digit** : ajout d'un chiffre parasite
- **wrong_digit** : remplacement d'un chiffre par un autre

### Sortie
- Resume des donnees (par mois, par pays)
- Barre de progression
- Taux d'automatisation global
- Distribution par couche et par methode
- Top 20 debiteurs avec taux individuel
- Timeline trimestrielle
- File de revue humaine (top 10 prioritaires)
- Debit en paiements/seconde

### Performance
- ~500 paiements/seconde sur un poste standard
- Pre-filtrage par debiteur pour eviter le O(n^2) en fuzzy matching
- Cache des imports optionnels non disponibles (sklearn, LLM)
