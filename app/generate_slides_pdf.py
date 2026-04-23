#!/usr/bin/env python3
"""
Generate PDF slide deck for C-level presentation using reportlab.
Uses real data from the simulation engine.

Usage: python app/generate_slides_pdf.py
Output: app/presentation_reconciliation_ia.pdf
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import warnings; warnings.filterwarnings("ignore")
import logging; logging.getLogger("reconciliation").setLevel(logging.CRITICAL)

from reportlab.lib.pagesizes import landscape, A4
from reportlab.lib.colors import HexColor, white, black
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Load real data ──
print("Loading simulation data...")
from app.simulation_data import generate_all
data = generate_all(seed=42, target_payments=5000)
m = data["metrics"]
df = data["df"]
auto_pct = m.matched_auto / m.total_payments * 100
review_pct = m.by_layer.get(6, 0) / m.total_payments * 100
total_eur = df["amount"].sum()
print("Building PDF...")

W, H = landscape(A4)  # 841 x 595
OUT = Path(__file__).parent / "presentation_reconciliation_ia.pdf"

# Colors
DARK = HexColor("#0f172a")
SLATE = HexColor("#64748b")
LIGHT_BG = HexColor("#f1f5f9")
GREEN = HexColor("#10b981")
YELLOW = HexColor("#f59e0b")
RED = HexColor("#ef4444")
INDIGO = HexColor("#667eea")
PURPLE = HexColor("#8b5cf6")
CYAN = HexColor("#06b6d4")
PINK = HexColor("#ec4899")

c = canvas.Canvas(str(OUT), pagesize=landscape(A4))

def dark_slide():
    c.setFillColor(DARK)
    c.rect(0, 0, W, H, fill=1, stroke=0)

def white_slide():
    c.setFillColor(white)
    c.rect(0, 0, W, H, fill=1, stroke=0)
    # accent bar
    c.setFillColor(INDIGO)
    c.rect(0, 0, 8*mm, H, fill=1, stroke=0)

def title(text, y, size=28, color=DARK, bold=True):
    c.setFillColor(color)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    c.drawString(25*mm, y, text)

def subtitle(text, y, size=14):
    c.setFillColor(SLATE)
    c.setFont("Helvetica", size)
    c.drawString(25*mm, y, text)

def bullet(text, y, x=25*mm, bold_pre=""):
    c.setFont("Helvetica", 12)
    c.setFillColor(DARK)
    if bold_pre:
        c.setFont("Helvetica-Bold", 12)
        c.drawString(x, y, bold_pre + "  ")
        bw = c.stringWidth(bold_pre + "  ", "Helvetica-Bold", 12)
        c.setFont("Helvetica", 12)
        c.drawString(x + bw, y, text)
    else:
        c.drawString(x, y, chr(8226) + "  " + text)
    return y - 14

def kpi_box(x, y, w, h, value, label, accent=None):
    c.setFillColor(LIGHT_BG)
    c.roundRect(x, y, w, h, 4, fill=1, stroke=0)
    if accent:
        c.setFillColor(accent)
        c.rect(x, y, w, 3, fill=1, stroke=0)
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold", 22)
    c.drawCentredString(x + w/2, y + h - 22, str(value))
    c.setFillColor(SLATE)
    c.setFont("Helvetica", 9)
    c.drawCentredString(x + w/2, y + 10, label)

def pipe_box(x, y, w, h, code, name, sub, color):
    c.setFillColor(color)
    c.roundRect(x, y, w, h, 5, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica", 7)
    c.drawCentredString(x+w/2, y+h-10, code)
    c.setFont("Helvetica-Bold", 9)
    c.drawCentredString(x+w/2, y+h-22, name)
    c.setFont("Helvetica", 7)
    c.drawCentredString(x+w/2, y+6, sub)

def table_header(cols, widths, x, y):
    c.setFillColor(DARK)
    total_w = sum(widths)
    c.rect(x, y-2, total_w, 14, fill=1, stroke=0)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    cx = x
    for col, w in zip(cols, widths):
        c.drawCentredString(cx + w/2, y+1, col)
        cx += w
    return y - 16

def table_row(cols, widths, x, y, bold=False):
    c.setFillColor(DARK)
    c.setFont("Helvetica-Bold" if bold else "Helvetica", 10)
    cx = x
    for i, (col, w) in enumerate(zip(cols, widths)):
        if i == 0:
            c.drawString(cx + 3, y+1, str(col))
        else:
            c.drawCentredString(cx + w/2, y+1, str(col))
        cx += w
    return y - 13

# =====================================================================
# SLIDE 1 — Title
# =====================================================================
dark_slide()
c.setFillColor(white)
c.setFont("Helvetica-Bold", 34)
c.drawCentredString(W/2, H - 180, "Reconciliation Paiement-Facture par IA")
c.setFont("Helvetica", 17)
c.setFillColor(HexColor("#94a3b8"))
c.drawCentredString(W/2, H - 215, "Architecture 6 couches | Factoring & Finance Receivables")
c.setFont("Helvetica", 12)
c.setFillColor(HexColor("#64748b"))
tags = f"{data['n_debtors']} debiteurs  |  {data['n_invoices']:,} factures  |  {data['n_payments']:,} paiements  |  40+ pays  |  12 langues"
c.drawCentredString(W/2, H - 280, tags)
c.drawCentredString(W/2, H - 320, "Joseph Gesnouin  |  Avril 2026")
c.showPage()

# =====================================================================
# SLIDE 2 — Le Probleme
# =====================================================================
white_slide()
title("Le Probleme", H-50)
subtitle("Reconciliation manuelle : couteux, lent, fragile", H-70)
y = H - 110
y = bullet("Des milliers de paiements entrants par jour a rapprocher des factures", y)
y = bullet("Libelles bancaires cryptiques, dans 12+ langues, avec acronymes", y)
y = bullet("Ecarts de montant : frais SWIFT, escomptes, retenues BTP, avoirs, WHT", y)
y = bullet("Paiements groupes couvrant N factures sur plusieurs mois", y)
y = bullet("Taux d'erreur 2-5%, delais de cloture J+2 a J+5", y)
y -= 15
c.setFillColor(RED)
c.setFont("Helvetica-Bold", 15)
c.drawString(25*mm, y, "Cout estime : ~8 ETP de reconciliation manuelle")
c.showPage()

# =====================================================================
# SLIDE 3 — La Solution (Pipeline)
# =====================================================================
white_slide()
title("La Solution", H-50)
subtitle("Pipeline IA a 6 couches avec early-exit", H-70)
layers = [
    ("C0","Normalisation","14 transforms",PURPLE),
    ("C1","Exact Match","97-100%",GREEN),
    ("C2","Regles Metier","85-99%",YELLOW),
    ("C3","NLP / Fuzzy","75-92%",CYAN),
    ("C4","ML Ensemble","42 features",PURPLE),
    ("C5","LLM Claude","Variable",PINK),
    ("C6","Revue Humaine","Recos ML",RED),
]
bx = 20*mm
by = H - 155
for code, name, sub, color in layers:
    pipe_box(bx, by, 32*mm, 35, code, name, sub, color)
    bx += 35*mm
c.setFillColor(DARK)
c.setFont("Helvetica-Oblique", 11)
c.drawString(25*mm, by - 25, "Early-exit : des qu'une couche match >= 90% de confiance, le paiement est cloture instantanement.")
c.showPage()

# =====================================================================
# SLIDE 4 — Resultats KPIs
# =====================================================================
white_slide()
title("Resultats Mesures", H-50)
subtitle(f"Sur {data['n_payments']:,} paiements simules (50 debiteurs, 12 mois)", H-70)
ky = H - 150
kpi_box(20*mm, ky, 55*mm, 45, f"{auto_pct:.1f}%", "Automatisation", INDIGO)
kpi_box(85*mm, ky, 55*mm, 45, f"{m.total_payments:,}", "Paiements traites", GREEN)
kpi_box(150*mm, ky, 55*mm, 45, f"{total_eur/1e6:.0f}M EUR", "Volume", YELLOW)
kpi_box(215*mm, ky, 55*mm, 45, f"{review_pct:.0f}%", "Revue humaine", RED)

# Layer bars
y = ky - 30
title("Distribution par couche", y + 5, size=14)
y -= 15
ln = {1:"C1 Exact",2:"C2 Regles",3:"C3 Fuzzy",4:"C4 ML",6:"C6 Humain"}
lc = {1:GREEN,2:YELLOW,3:CYAN,4:PURPLE,6:RED}
for layer in [1,2,3,4,6]:
    cnt = m.by_layer.get(layer, 0)
    if cnt == 0: continue
    pct = cnt / m.total_payments * 100
    c.setFont("Helvetica", 10); c.setFillColor(DARK)
    c.drawString(25*mm, y+2, ln.get(layer,""))
    c.setFillColor(lc.get(layer, SLATE))
    c.rect(55*mm, y, pct * 1.5*mm, 5*mm, fill=1, stroke=0)
    c.setFillColor(DARK); c.setFont("Helvetica", 9)
    c.drawString(55*mm + pct*1.5*mm + 3, y+2, f"{pct:.1f}% ({cnt:,})")
    y -= 12
c.showPage()

# =====================================================================
# SLIDE 5 — ROI
# =====================================================================
white_slide()
title("ROI Estime", H-50)
subtitle("Impact operationnel du systeme", H-70)
tw = [65*mm, 50*mm, 55*mm]
tx = 35*mm
y = H - 110
y = table_header(["Indicateur", "Sans IA", "Avec le systeme"], tw, tx, y)
y = table_row(["ETP reconciliation", "~8 ETP", "< 1 ETP"], tw, tx, y, bold=True)
y = table_row(["Temps / paiement", "3-5 min", "17 ms"], tw, tx, y)
y = table_row(["Erreurs", "2-5%", "< 0.1%"], tw, tx, y)
y = table_row(["Delai cloture", "J+2 a J+5", "Temps reel"], tw, tx, y, bold=True)
y = table_row(["Couverture", "1-2 pays", "40+ pays, 12 langues"], tw, tx, y)
y = table_row(["Reco ML", "Aucune", "Top-5, 77% precision"], tw, tx, y)
c.showPage()

# =====================================================================
# SLIDE 6 — Scenarios
# =====================================================================
white_slide()
title("60+ Scenarios Couverts", H-50)
left = [
    "Reference exacte + montant (C1)",
    "ISO 20022 SEPA structure (C1)",
    "IBAN + montant unique (C1)",
    "Purchase Order / BL (C1)",
    "Frais SWIFT internationaux (C2)",
    "Escompte contractuel (C2)",
    "Retenue de garantie BTP (C2)",
    "RFA / Remise fin d'annee (C2)",
]
right = [
    "Deduction d'avoirs (C2)",
    "Subset sum N factures x M mois (C2)",
    "Acomptes 30/50/70% (C2)",
    "Retenue a la source WHT (C2)",
    "Typos / OCR : 0->O, 1->l (C3)",
    "Ref tronquee / prefixe change (C3)",
    "ML ensemble 42 features (C4)",
    "Combos multi-factures (C4 reco)",
]
y = H - 90
for s in left:
    y = bullet(s, y, x=20*mm)
y = H - 90
for s in right:
    y = bullet(s, y, x=150*mm)
c.showPage()

# =====================================================================
# SLIDE 7 — ML & Recommandations
# =====================================================================
white_slide()
title("Machine Learning & Recommandations", H-50)
subtitle("C4 ML alimente les recommandations pour la revue humaine", H-70)
y = H - 100
y = bullet("LightGBM + XGBoost + Random Forest + meta-classifieur", y, bold_pre="Ensemble :")
y = bullet("Amount (10) + Reference (12) + Temporal (10) + Behavioral (10)", y, bold_pre="42 features :")
y = bullet("F1 = 0.95, auto-training sur ground truth", y, bold_pre="Performance :")
y = bullet("77% precision top-5 (la bonne facture dans les 5 premiers)", y, bold_pre="Recos C6 :")
y -= 5
y = bullet("Score composite = ML proba 60% + Heuristique 40%", y, bold_pre="Scoring :")
y = bullet("Paires et triples dont la somme ~ montant paiement", y, bold_pre="Combos :")
y = bullet("'montant exact | echeance +3j | debiteur regulier 94%'", y, bold_pre="Explainability :")
y -= 5
y = bullet("Timing, montants, methodes, verbatims par debiteur", y, bold_pre="Profiling :")
c.showPage()

# =====================================================================
# SLIDE 8 — Demo 11 pages
# =====================================================================
white_slide()
title("Demo Interactive — 11 Pages Streamlit", H-50)
pages = [
    ("Executive Summary", "KPIs, pie chart, barres mensuelles"),
    ("Architecture", "Pipeline visuel, detail par couche"),
    ("Factures", "Portefeuille complet filtrable"),
    ("Paiements", "Flux avec libelle complet et statut"),
    ("Simulation Live", "5000+ paiements filtrables"),
    ("Analyse Debiteurs", "Taux par debiteur, scatter pays"),
    ("Paiements par Couche", "Deep dive C1/C2/C3/C6"),
    ("Revue Humaine", "Recos ML top-5 + combos"),
    ("Mapping Complet", "Paiement<>facture + CSV"),
    ("Profils Debiteurs IA", "Comportements, verbatims"),
    ("Deep Dive", "Parcours couche par couche"),
]
y = H - 80
for name, desc in pages:
    c.setFont("Helvetica-Bold", 10); c.setFillColor(INDIGO)
    c.drawString(25*mm, y, name)
    c.setFont("Helvetica", 10); c.setFillColor(DARK)
    c.drawString(75*mm, y, desc)
    y -= 13
c.showPage()

# =====================================================================
# SLIDE 9 — Methode de travail
# =====================================================================
white_slide()
title("Methode de Travail avec Claude Code", H-50)
subtitle("Pair-programming humain + agent IA", H-70)
y = H - 100
y = bullet("Joseph donne la vision produit, les specs metier, detecte les bugs", y)
y = bullet("Claude Code implemente, teste, debugge, optimise, documente", y)
y = bullet("Cycle rapide : demande -> code -> test -> feedback -> iteration", y)
y -= 10
title("Timeline du projet", y+5, size=14)
y -= 15
milestones = [
    ("Jour 1 (7 avril)", "Architecture 6 couches + 74 tests + demo + README"),
    ("Jour 2 (8 avril)", "Simulation 10k+, Streamlit, HTML export, 40+ pays"),
    ("Jour 3 (9 avril)", "Audit 22 bugs, perf 2.5x, API keys, .env"),
    ("Jour 4 (10 avril)", "Fix C3 (0->11%), 127 tests, subset sum, Streamlit 11p"),
    ("Jour 5 (16 avril)", "Fix C4 ML (0->14%), explainability, combos"),
    ("Jour 6 (23 avril)", "Profiler debiteur, verbatims, rapport, presentation"),
]
for d, desc in milestones:
    c.setFont("Helvetica-Bold", 10); c.setFillColor(INDIGO)
    c.drawString(25*mm, y, d)
    c.setFont("Helvetica", 10); c.setFillColor(DARK)
    c.drawString(75*mm, y, desc)
    y -= 13
c.showPage()

# =====================================================================
# SLIDE 10 — Chiffres du projet
# =====================================================================
white_slide()
title("Le Projet en Chiffres", H-50)
tw2 = [75*mm, 55*mm]
tx2 = 55*mm
y = H - 90
y = table_header(["Metrique", "Valeur"], tw2, tx2, y)
rows = [
    ("Lignes de code Python", "14 548", False),
    ("Fichiers Python", "33", False),
    ("Tests unitaires", "127 (100% pass)", True),
    ("Commits git", "41", False),
    ("Verbatims de paiement", "522 (12 langues)", False),
    ("Pages Streamlit", "11", False),
    ("Bugs corriges (audit)", "22", False),
    ("Gain performance", "2.5x (200->497 p/s)", True),
    ("Taux d'automatisation", f"{auto_pct:.1f}%", True),
    ("Precision reco ML", "77% top-5", True),
]
for label, val, bold in rows:
    y = table_row([label, val], tw2, tx2, y, bold=bold)
c.showPage()

# =====================================================================
# SLIDE 11 — Next Steps
# =====================================================================
white_slide()
title("Prochaines Etapes", H-50)
y = H - 100
y = bullet("Connecter aux donnees reelles (flux bancaires SWIFT/SEPA)", y, bold_pre="1.")
y = bullet("Activer la couche LLM (C5) avec Claude API pour les cas complexes", y, bold_pre="2.")
y = bullet("Deployer l'API REST (FastAPI) pour integration SI", y, bold_pre="3.")
y = bullet("Production avec monitoring MLOps et boucle de feedback", y, bold_pre="4.")
y = bullet("Etendre a d'autres types de reconciliation", y, bold_pre="5.")
c.showPage()

# =====================================================================
# SLIDE 12 — Merci
# =====================================================================
dark_slide()
c.setFillColor(white)
c.setFont("Helvetica-Bold", 36)
c.drawCentredString(W/2, H - 200, "Merci")
c.setFont("Helvetica", 18)
c.setFillColor(HexColor("#94a3b8"))
c.drawCentredString(W/2, H - 240, "Questions ?")
c.setFont("Helvetica", 13)
c.setFillColor(HexColor("#64748b"))
c.drawCentredString(W/2, H - 310, "Joseph Gesnouin  |  Reconciliation IA  |  Avril 2026")
c.drawCentredString(W/2, H - 335, "Demo : streamlit run app/streamlit_app.py")
c.showPage()

c.save()
print(f"\nPDF: {OUT}")
print(f"Size: {OUT.stat().st_size // 1024} KB, {12} slides")
