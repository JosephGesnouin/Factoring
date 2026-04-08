#!/usr/bin/env python3
"""
Export HTML autonome de la demo Reconciliation IA.
Genere un fichier HTML interactif avec tous les graphiques Plotly.

Usage: python app/export_html.py
Resultat: app/demo_reconciliation.html
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logging
logging.getLogger("reconciliation").setLevel(logging.CRITICAL)

from app.simulation_data import generate_all
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
from collections import defaultdict

print("Generating data...")
data = generate_all(seed=42)
df = data["df"]
m = data["metrics"]
total = m.total_payments
auto = m.matched_auto
review = m.by_layer.get(6, 0)
auto_pct = auto / total * 100
review_pct = review / total * 100

print(f"  {data['n_invoices']} invoices, {data['n_payments']} payments")
print(f"  Auto: {auto_pct:.1f}%, Review: {review_pct:.1f}%")

# ── Colors ──
C_GREEN = "#10b981"
C_YELLOW = "#f59e0b"
C_CYAN = "#06b6d4"
C_RED = "#ef4444"
C_PURPLE = "#8b5cf6"
C_PINK = "#ec4899"
C_INDIGO = "#667eea"
C_SLATE = "#64748b"
LAYER_COLORS = {"C1 Exact": C_GREEN, "C2 Regles Metier": C_YELLOW,
                "C3 NLP/Fuzzy": C_CYAN, "C6 Revue Humaine": C_RED}

MONTH_ORDER = ["Janvier","Fevrier","Mars","Avril","Mai","Juin",
               "Juillet","Aout","Septembre","Octobre","Novembre","Decembre"]

# ============================================================
# CHARTS
# ============================================================
print("Building charts...")

# 1. Pie chart - Layer distribution
layer_names = {1: "C1 Exact", 2: "C2 Regles Metier", 3: "C3 NLP/Fuzzy", 6: "C6 Revue Humaine"}
layer_data = []
for layer, count in sorted(m.by_layer.items()):
    if count > 0:
        name = layer_names.get(layer, f"C{layer}")
        layer_data.append({"Couche": name, "Paiements": count})
ldf = pd.DataFrame(layer_data)
fig_pie = px.pie(ldf, values="Paiements", names="Couche", hole=0.45,
                 color="Couche", color_discrete_map=LAYER_COLORS)
fig_pie.update_traces(textposition="inside", textinfo="percent+label",
                      textfont_size=13)
fig_pie.update_layout(height=380, margin=dict(t=40, b=20), showlegend=False,
                      title_text="Distribution par couche", title_x=0.5)

# 2. Monthly stacked bar
monthly = df.groupby("month_name").agg(
    Total=("payment_id", "count"), Auto=("matched", "sum")).reset_index()
monthly["month_name"] = pd.Categorical(monthly["month_name"], categories=MONTH_ORDER, ordered=True)
monthly = monthly.sort_values("month_name")
monthly["Revue"] = monthly["Total"] - monthly["Auto"]

fig_monthly = go.Figure()
fig_monthly.add_trace(go.Bar(name="Auto-match", x=monthly["month_name"], y=monthly["Auto"],
                             marker_color=C_GREEN))
fig_monthly.add_trace(go.Bar(name="Revue humaine", x=monthly["month_name"], y=monthly["Revue"],
                             marker_color=C_RED))
fig_monthly.update_layout(barmode="stack", height=380, margin=dict(t=40, b=20),
                          title_text="Evolution mensuelle", title_x=0.5,
                          legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="center", x=0.5))

# 3. Top methods
method_counts = df[df["matched"]].groupby("method").size().reset_index(name="count")
method_counts = method_counts.sort_values("count", ascending=True).tail(10)
fig_methods = px.bar(method_counts, x="count", y="method", orientation="h",
                     color_discrete_sequence=[C_INDIGO])
fig_methods.update_layout(height=350, margin=dict(l=20, r=20, t=40, b=10),
                          title_text="Top methodes de matching", title_x=0.5,
                          xaxis_title="Paiements", yaxis_title="")

# 4. Debtor auto rate
debtor_stats = df.groupby(["debtor_name", "country"]).agg(
    total=("payment_id", "count"), auto=("matched", "sum"),
    montant=("amount", "sum"), conf=("confidence", "mean")).reset_index()
debtor_stats["taux"] = (debtor_stats["auto"] / debtor_stats["total"] * 100).round(1)
debtor_stats = debtor_stats.sort_values("taux")

fig_debtor = px.bar(debtor_stats, x="taux", y="debtor_name", orientation="h",
                    color="taux", color_continuous_scale=["#ef4444","#f59e0b","#10b981"],
                    range_color=[0, 100], text="taux")
fig_debtor.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
fig_debtor.add_vline(x=90, line_dash="dash", line_color="gray",
                     annotation_text="Seuil 90%")
fig_debtor.update_layout(height=500, margin=dict(l=20, r=60, t=40, b=10),
                         title_text="Taux d'automatisation par debiteur", title_x=0.5,
                         xaxis_title="Taux (%)", yaxis_title="",
                         coloraxis_showscale=False)

# 5. Country scatter
country_stats = df.groupby("country").agg(
    total=("payment_id", "count"), auto=("matched", "sum")).reset_index()
country_stats["taux"] = (country_stats["auto"] / country_stats["total"] * 100).round(1)
fig_country = px.scatter(country_stats, x="total", y="taux", size="total",
                        color="taux", text="country",
                        color_continuous_scale=["#ef4444","#f59e0b","#10b981"],
                        range_color=[0, 100], size_max=50)
fig_country.update_traces(textposition="top center", textfont_size=12)
fig_country.update_layout(height=400, margin=dict(t=40, b=20),
                          title_text="Performance par pays", title_x=0.5,
                          xaxis_title="Nombre de paiements", yaxis_title="Taux auto (%)",
                          coloraxis_showscale=False)

# 6. Confidence histogram
matched = df[df["confidence"] > 0]
fig_conf = px.histogram(matched, x="confidence", nbins=25, color_discrete_sequence=[C_GREEN])
fig_conf.update_layout(height=350, margin=dict(t=40, b=20),
                       title_text="Distribution des scores de confiance", title_x=0.5,
                       xaxis_title="Confiance", yaxis_title="Nombre de paiements")

# 7. Layer by debtor heatmap
cross = pd.crosstab(df["debtor_name"], df["layer_name"])
for col in ["C1", "C2", "C3", "C6"]:
    if col not in cross.columns:
        cross[col] = 0
cross = cross[["C1","C2","C3","C6"]]
fig_heat = px.imshow(cross, color_continuous_scale=["#f8fafc","#1e40af"],
                     labels=dict(x="Couche", y="Debiteur", color="Paiements"),
                     text_auto=True, aspect="auto")
fig_heat.update_layout(height=500, margin=dict(t=40, b=20),
                       title_text="Matrice debiteur x couche", title_x=0.5)

# 8. Deep dive examples — one per method type
examples = []
for label_filter, title in [
    ("C1", "Exemple C1 — Match exact"),
    ("C2", "Exemple C2 — Regle metier"),
    ("C6", "Exemple C6 — Revue humaine"),
]:
    candidates = df[df["layer_name"] == label_filter]
    if len(candidates) > 0:
        row = candidates.iloc[0]
        ctx = None
        for r in data["results"]:
            if r.payment.id == row["payment_id"]:
                ctx = r
                break
        examples.append({"row": row, "ctx": ctx, "title": title})

# ── Explanations by method ──
METHOD_EXPLANATIONS = {
    "C1_IBAN_AMOUNT": (
        "Match IBAN + Montant Unique",
        "Le debiteur est identifie par son IBAN. Il n'existe qu'une seule facture ouverte "
        "de ce montant exact pour ce debiteur → le rapprochement est certain sans meme "
        "avoir besoin de reference dans le libelle."
    ),
    "C1_EXACT_REF": (
        "Reference Exacte + Montant",
        "Le libelle contient une reference de facture qui correspond exactement a une facture "
        "ouverte. Le montant est aussi exact. C'est le cas le plus simple et le plus fiable."
    ),
    "C1_EXACT_REF_HT": (
        "Reference Exacte + Montant HT (erreur TVA)",
        "La reference est correcte, mais le debiteur a paye le montant HT au lieu du TTC. "
        "Erreur frequente quand le debiteur confond la base taxable et le montant final."
    ),
    "C1_ISO20022": (
        "Reference Structuree ISO 20022 (SEPA)",
        "Le virement SEPA contient des champs structures (/ROC/, EndToEndId) qui portent "
        "directement la reference facture. Priorite absolue — pas besoin d'analyser le libelle."
    ),
    "C1_FULL_BALANCE": (
        "Solde Total Debiteur",
        "Le montant du paiement correspond exactement a la somme de TOUTES les factures "
        "ouvertes du debiteur. Cas frequent en fin de mois ou apres une relance globale."
    ),
    "C1_FULL_BALANCE_NET_CREDITS": (
        "Solde Total Net (avoirs deduits)",
        "Comme le solde total, mais le debiteur a deduit les avoirs en cours. "
        "Montant = total factures - total avoirs."
    ),
    "C1_PO_MATCH": (
        "Match via Bon de Commande (PO)",
        "Le debiteur reference son numero de commande (PO) au lieu du numero de facture. "
        "La table PO → Facture permet le rapprochement indirect."
    ),
    "C1_BL_MATCH": (
        "Match via Bon de Livraison (BL)",
        "Le debiteur reference le numero de livraison (BL/CMR). "
        "Courant dans le transport et la distribution."
    ),
    "C1_HASH_INDEX": (
        "Hash Index Multi-Format",
        "La reference extraite ne correspond pas exactement au format stocke, mais "
        "l'index de hachage multi-format (avec variantes de prefixes et padding) trouve la correspondance."
    ),
    "C2_TOLERANCE": (
        "Tolerance Montant (Regles Metier)",
        "Le montant differe legerement de la facture. La regle identifie la raison : "
        "frais SWIFT (-35 EUR max), escompte contractuel, arrondi (+-1 EUR), "
        "retenue de garantie BTP, retenue a la source (WHT), etc."
    ),
    "C2_SUBSET_SUM": (
        "Multi-Factures (Subset Sum)",
        "Le paiement correspond a la somme exacte de PLUSIEURS factures. "
        "Trois algorithmes combines : greedy, exact (brute-force), et two-sum (paires)."
    ),
    "C2_CREDIT_NOTE": (
        "Deduction d'Avoir",
        "Le debiteur a deduit un avoir (note de credit) du montant de la facture. "
        "Ex: facture 10 000 EUR - avoir 500 EUR = paiement 9 500 EUR."
    ),
    "C2_TEMPORAL": (
        "Pattern Temporel",
        "Le libelle mentionne une periode ('FACTURES OCTOBRE 2024') et le montant "
        "correspond a la somme des factures emises pendant cette periode."
    ),
    "C2_INSTALLMENT": (
        "Acompte / Paiement Partiel",
        "Le paiement correspond a un pourcentage standard (30%, 50%, 70%) d'une facture. "
        "Detecte via mots-cles (ACOMPTE, ADVANCE) et ratio paiement/facture."
    ),
    "HUMAN_REVIEW": (
        "Revue Humaine Requise",
        "Aucune couche automatique n'a pu trouver un rapprochement fiable. "
        "Raisons possibles : label cryptique, montant ne correspondant a rien, "
        "debiteur non identifie, combinaison trop complexe."
    ),
}

# ── Compute recommendations for HUMAN_REVIEW payments ──
print("Computing recommendations for unmatched payments...")
inv_by_debtor = defaultdict(list)
for inv in data["invoices"]:
    inv_by_debtor[inv.debtor_id].append(inv)

ground_truth = data.get("ground_truth", {})  # payment_id -> true invoice ref
recommendations = {}  # payment_id -> list of {ref, amount, score, reason, is_true}

human_review_df = df[df["method"] == "HUMAN_REVIEW"]
for _, r in human_review_df.iterrows():
    pay_id = r["payment_id"]
    pay_amount = r["amount"]
    pay_date = r["date"]
    debtor_id = r["debtor_id"]

    candidates = []
    search_invoices = inv_by_debtor.get(debtor_id, data["invoices"][:50])

    for inv in search_invoices:
        score = 0.0
        reasons = []

        # Amount proximity (0-0.40)
        if inv.amount > 0:
            diff_pct = abs(pay_amount - inv.amount) / inv.amount
            if diff_pct < 0.001:
                score += 0.40; reasons.append("montant exact")
            elif diff_pct < 0.05:
                score += 0.30; reasons.append(f"ecart {diff_pct:.1%}")
            elif diff_pct < 0.15:
                score += 0.15; reasons.append(f"ecart {diff_pct:.0%}")
            elif diff_pct < 0.30:
                score += 0.05

        # Debtor match (0-0.25)
        if inv.debtor_id == debtor_id:
            score += 0.25; reasons.append("meme debiteur")

        # Temporal proximity (0-0.20)
        if pay_date and inv.due_date:
            day_diff = abs((pay_date - inv.due_date).days)
            if day_diff <= 7:
                score += 0.20; reasons.append(f"echeance +{day_diff}j")
            elif day_diff <= 30:
                score += 0.12; reasons.append(f"echeance +{day_diff}j")
            elif day_diff <= 60:
                score += 0.05

        # Amount HT match (0-0.15)
        if inv.amount_ht > 0 and abs(pay_amount - inv.amount_ht) / inv.amount_ht < 0.01:
            score += 0.15; reasons.append("montant HT")

        if score > 0.10:
            true_ref = ground_truth.get(pay_id, "")
            candidates.append({
                "ref": inv.reference,
                "amount": inv.amount,
                "score": min(score, 1.0),
                "reason": " | ".join(reasons[:3]),
                "is_true": inv.reference == true_ref,
            })

    candidates.sort(key=lambda x: -x["score"])
    recommendations[pay_id] = candidates[:5]

print(f"  Recommendations computed for {len(recommendations)} payments")

# Build FULL catalogue grouped by method
print("Building full catalogue...")
catalogue_html = ""

# Group payments by method
grouped = df.groupby("method")
method_order = df.groupby("method").size().sort_values(ascending=False).index.tolist()

for method_name in method_order:
    group = grouped.get_group(method_name)
    expl_title, expl_text = METHOD_EXPLANATIONS.get(method_name, (method_name, ""))
    badge_cls = "c1" if "C1_" in method_name else "c2" if "C2_" in method_name else "c3" if "C3_" in method_name else "c6"
    count = len(group)

    catalogue_html += f"""
    <div class="method-group open">
      <div class="method-header" onclick="this.parentElement.classList.toggle('open')">
        <span class="badge {badge_cls}">{method_name}</span>
        <span class="method-title">{expl_title}</span>
        <span class="method-count">{count} paiement{'s' if count>1 else ''}</span>
        <span class="chevron">▼</span>
      </div>
      <div class="method-body">
        <div class="method-explanation">{expl_text}</div>
        <table class="cat-table">
          <tr>
            <th style="min-width:80px">ID</th>
            <th style="min-width:90px">Date</th>
            <th style="min-width:100px">Montant EUR</th>
            <th style="min-width:140px">Debiteur</th>
            <th style="min-width:250px">Libelle du paiement</th>
            <th style="min-width:60px">Conf.</th>
            <th style="min-width:120px">Flags</th>
            <th style="min-width:180px">Facture(s) matchee(s)</th>
          </tr>"""

    # For HUMAN_REVIEW, add recommendation column
    is_human_review = (method_name == "HUMAN_REVIEW")
    if is_human_review:
        catalogue_html = catalogue_html.rstrip("</tr>")
        catalogue_html += """<th style="min-width:320px">Top 5 recommandations (tri par score)</th>
          </tr>"""

    MAX_PER_METHOD = 50
    shown = 0
    for _, r in group.iterrows():
        shown += 1
        if shown > MAX_PER_METHOD:
            if shown == MAX_PER_METHOD + 1:
                remaining = count - MAX_PER_METHOD
                catalogue_html += f"""<tr><td colspan="{'9' if is_human_review else '8'}"
                    style="text-align:center; padding:12px; color:var(--slate); font-style:italic;">
                    ... et {remaining} paiements supplementaires (non affiches pour lisibilite)</td></tr>"""
            continue
        conf_str = f"{r['confidence']:.0%}" if r["confidence"] > 0 else "—"
        label_esc = (r["label"] if r["label"] else "(vide)").replace("<","&lt;").replace(">","&gt;")
        inv_str = r["invoices_matched"] if r["invoices_matched"] else "—"
        flags_str = r["flags"] if r["flags"] else ""

        catalogue_html += f"""
          <tr>
            <td><code>{r['payment_id']}</code></td>
            <td>{r['date']}</td>
            <td class="num">{r['amount']:,.2f}</td>
            <td>{r['debtor_name'][:22]}</td>
            <td class="label-cell" title="{label_esc}">{label_esc[:50]}</td>
            <td class="num">{conf_str}</td>
            <td class="flags-cell">{flags_str}</td>
            <td class="inv-cell">{inv_str}</td>"""

        if is_human_review:
            recs = recommendations.get(r["payment_id"], [])
            true_ref = ground_truth.get(r["payment_id"], "")
            if recs:
                rec_html = '<div class="reco-list">'
                for rank, rec in enumerate(recs[:5], 1):
                    bar_w = int(rec["score"] * 100)
                    is_correct = rec.get("is_true", False)
                    item_cls = "reco-item reco-correct" if is_correct else "reco-item"
                    check = ' <span class="reco-check">&#10003; VRAIE FACTURE</span>' if is_correct else ""
                    bar_cls = "reco-fill reco-fill-correct" if is_correct else "reco-fill"
                    rec_html += (
                        f'<div class="{item_cls}">'
                        f'<span class="reco-rank">#{rank}</span>'
                        f'<span class="reco-ref">{rec["ref"]}</span>'
                        f'<span class="reco-amt">{rec["amount"]:,.2f}</span>'
                        f'<span class="reco-bar"><span class="{bar_cls}" style="width:{bar_w}%"></span></span>'
                        f'<span class="reco-score">{rec["score"]:.0%}</span>'
                        f'<span class="reco-reason">{rec["reason"]}{check}</span>'
                        f'</div>'
                    )
                rec_html += '</div>'
                catalogue_html += f'<td class="reco-cell">{rec_html}</td>'
            else:
                catalogue_html += '<td class="reco-cell" style="color:#94a3b8">Aucun candidat</td>'

        catalogue_html += "</tr>"

    catalogue_html += """
        </table>
      </div>
    </div>"""


# ============================================================
# HTML GENERATION — Premium UX Design
# ============================================================
print("Generating HTML (premium design)...")

def fig_to_div(fig, div_id):
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id)

# Update all plotly figures for consistent premium look
for fig in [fig_pie, fig_monthly, fig_methods, fig_debtor, fig_country, fig_conf, fig_heat]:
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, system-ui, sans-serif", color="#334155"),
    )

pie_html = fig_to_div(fig_pie, "pie")
monthly_html = fig_to_div(fig_monthly, "monthly")
methods_html = fig_to_div(fig_methods, "methods")
debtor_html = fig_to_div(fig_debtor, "debtor")
country_html = fig_to_div(fig_country, "country")
conf_html = fig_to_div(fig_conf, "conf")
heat_html = fig_to_div(fig_heat, "heat")

# Deep dive HTML
deep_html = ""
for ex in examples:
    row = ex["row"]
    ctx = ex["ctx"]
    steps_html = ""
    if ctx:
        for log in ctx.processing_log:
            layer = log.get("layer","?")
            event = log.get("event","")
            t = log.get("time_ms",0)
            conf = log.get("confidence",0)
            method = log.get("method","")
            if event == "PREPROCESSED":
                steps_html += f'<div class="step step-pre"><b>C0</b> Preprocessing <span class="time">{t:.1f}ms</span></div>'
            elif event == "MATCH_FOUND":
                steps_html += f'<div class="step step-match"><b>C{layer}</b> <b>MATCH</b> <span class="badge-sm">{method}</span> {conf:.0%} <span class="time">{t:.1f}ms</span></div>'
            elif event == "NO_MATCH":
                steps_html += f'<div class="step step-no"><b>C{layer}</b> Pas de match <span class="time">{t:.1f}ms</span></div>'

    badge_cls = {"C1":"c1","C2":"c2","C3":"c3","C6":"c6"}.get(row["layer_name"],"c6")
    conf_pct = f"{row['confidence']:.0%}" if row["confidence"] > 0 else "—"
    invoices_str = row["invoices_matched"] if row["invoices_matched"] else "Aucune (revue humaine)"

    deep_html += f"""
    <div class="deep">
        <div style="display:flex; align-items:center; gap:12px; margin-bottom:12px;">
            <h3 style="flex:1; margin:0;">{ex['title']}</h3>
            <span class="badge {badge_cls}" style="font-size:0.85rem; padding:6px 16px;">
                {row['layer_name']} &mdash; {conf_pct}</span>
        </div>
        <div class="deep-meta">
            <span><b>ID:</b> {row['payment_id']}</span>
            <span><b>Montant:</b> {row['amount']:,.2f} EUR</span>
            <span><b>Date:</b> {row['date']}</span>
            <span><b>Debiteur:</b> {row['debtor_name']}</span>
        </div>
        <div class="deep-label"><b>Libelle brut :</b><br><code>{row['label'] if row['label'] else '(vide)'}</code></div>
        <div style="margin:12px 0;"><b>Parcours dans le pipeline :</b></div>
        {steps_html}
        <div style="margin-top:12px; padding:10px 16px; background:var(--green-light); border-radius:8px;">
            <b>Factures matchees :</b> {invoices_str}</div>
        {f'<div style="margin-top:8px; padding:8px 16px; background:var(--yellow-light); border-radius:8px;"><b>Flags :</b> {row["flags"]}</div>' if row["flags"] else ""}
    </div>"""

# Debtor table
debtor_table = ""
for _, r in debtor_stats.sort_values("taux", ascending=False).iterrows():
    rate_cls = "rate-high" if r["taux"] >= 80 else "rate-mid" if r["taux"] >= 50 else "rate-low"
    debtor_table += f"""<tr>
        <td>{r['debtor_name'][:30]}</td><td>{r['country']}</td>
        <td class="num">{r['total']}</td><td class="num">{r['auto']:.0f}</td>
        <td class="num">{r['total']-r['auto']:.0f}</td>
        <td class="{rate_cls}">{r['taux']:.1f}%</td>
        <td class="num">{r['montant']:,.0f}</td>
    </tr>"""

# ============================================================
# ASSEMBLE FINAL HTML
# ============================================================
total_eur = df["amount"].sum()

html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reconciliation IA — Factoring</title>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --green:#10b981; --green-light:#d1fae5; --green-dark:#065f46;
    --yellow:#f59e0b; --yellow-light:#fef3c7; --yellow-dark:#92400e;
    --cyan:#06b6d4; --red:#ef4444; --red-light:#fee2e2; --red-dark:#991b1b;
    --purple:#8b5cf6; --pink:#ec4899; --indigo:#667eea;
    --slate:#64748b; --slate-100:#f1f5f9; --slate-200:#e2e8f0; --slate-800:#1e293b;
    --radius:14px; --shadow:0 1px 3px rgba(0,0,0,0.08), 0 1px 2px rgba(0,0,0,0.04);
    --shadow-lg:0 10px 15px -3px rgba(0,0,0,0.1), 0 4px 6px rgba(0,0,0,0.05);
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Inter',system-ui,-apple-system,sans-serif; background:#f0f4f8;
          color:var(--slate-800); line-height:1.65; -webkit-font-smoothing:antialiased; }}
  .container {{ max-width:1280px; margin:0 auto; padding:0 24px; }}
  h2 {{ font-size:1.4rem; font-weight:700; margin:3rem 0 1.2rem; color:var(--slate-800);
        display:flex; align-items:center; gap:10px; }}
  h2::before {{ content:''; width:4px; height:24px; background:var(--indigo); border-radius:2px; }}
  h3 {{ font-size:1.05rem; font-weight:600; }}

  /* ─── NAV ─── */
  .nav {{ background:white; border-bottom:1px solid var(--slate-200); position:sticky; top:0; z-index:100;
          box-shadow:var(--shadow); }}
  .nav-inner {{ display:flex; align-items:center; gap:24px; padding:12px 0; overflow-x:auto; }}
  .nav-brand {{ font-weight:800; font-size:1.1rem; color:var(--indigo); white-space:nowrap; }}
  .nav a {{ color:var(--slate); font-size:0.85rem; font-weight:500; text-decoration:none;
            padding:6px 14px; border-radius:8px; white-space:nowrap; transition:all 0.15s; }}
  .nav a:hover {{ background:var(--slate-100); color:var(--slate-800); }}

  /* ─── HERO ─── */
  .hero {{ background:linear-gradient(135deg,#0f172a 0%,#1e3a5f 50%,#1e293b 100%);
           color:white; padding:3.5rem 0 3rem; margin-bottom:2.5rem; }}
  .hero h1 {{ font-size:2.5rem; font-weight:800; letter-spacing:-0.03em; }}
  .hero .sub {{ font-size:1.1rem; opacity:0.75; margin-top:0.5rem; font-weight:300; }}
  .hero .tags {{ display:flex; gap:12px; margin-top:1.2rem; flex-wrap:wrap; }}
  .hero .tag {{ background:rgba(255,255,255,0.12); backdrop-filter:blur(4px);
                padding:6px 16px; border-radius:20px; font-size:0.82rem; font-weight:500;
                border:1px solid rgba(255,255,255,0.15); }}

  /* ─── KPI CARDS ─── */
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:18px; margin-bottom:2.5rem; }}
  .kpi {{ background:white; border-radius:var(--radius); padding:24px; text-align:center;
          box-shadow:var(--shadow); border:1px solid var(--slate-200); transition:transform 0.15s; }}
  .kpi:hover {{ transform:translateY(-2px); box-shadow:var(--shadow-lg); }}
  .kpi .value {{ font-size:2.2rem; font-weight:800; letter-spacing:-0.02em; }}
  .kpi .label {{ font-size:0.82rem; color:var(--slate); margin-top:6px; font-weight:500; }}
  .kpi .sub-val {{ font-size:0.78rem; color:var(--slate); margin-top:2px; }}
  .kpi.primary {{ background:linear-gradient(135deg,var(--indigo),var(--purple)); color:white; }}
  .kpi.primary .label {{ color:rgba(255,255,255,0.80); }}
  .kpi.success {{ border-bottom:3px solid var(--green); }}
  .kpi.warning {{ border-bottom:3px solid var(--yellow); }}
  .kpi.danger {{ border-bottom:3px solid var(--red); }}

  /* ─── CARDS & CHARTS ─── */
  .card {{ background:white; border-radius:var(--radius); padding:20px;
           box-shadow:var(--shadow); border:1px solid var(--slate-200); }}
  .grid-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin:1rem 0; }}

  /* ─── BADGES ─── */
  .badge {{ display:inline-flex; align-items:center; padding:4px 14px; border-radius:20px;
            font-weight:600; font-size:0.76rem; color:white; letter-spacing:0.02em; }}
  .badge.c1 {{ background:var(--green); }} .badge.c2 {{ background:var(--yellow); color:#1c1917; }}
  .badge.c3 {{ background:var(--cyan); }} .badge.c6 {{ background:var(--red); }}
  .badge-sm {{ display:inline-block; padding:2px 10px; border-radius:12px;
               font-size:0.72rem; color:white; background:var(--indigo); font-weight:600; }}

  /* ─── PIPELINE ─── */
  .pipeline {{ display:flex; gap:4px; align-items:center; flex-wrap:wrap;
               justify-content:center; margin:2rem 0; }}
  .pipe {{ padding:16px 20px; border-radius:12px; text-align:center; color:white;
           min-width:115px; transition:transform 0.15s; box-shadow:0 2px 8px rgba(0,0,0,0.15); }}
  .pipe:hover {{ transform:scale(1.05); }}
  .pipe .lbl {{ font-size:0.65rem; text-transform:uppercase; letter-spacing:0.08em; opacity:0.8; }}
  .pipe .nm {{ font-weight:700; font-size:0.95rem; }}
  .pipe .conf {{ font-size:0.7rem; opacity:0.7; margin-top:2px; }}
  .arrow {{ font-size:1.2rem; color:#cbd5e1; }}

  /* ─── TABLES ─── */
  table {{ width:100%; border-collapse:separate; border-spacing:0; font-size:0.82rem; }}
  thead th {{ background:var(--slate-100); padding:12px 10px; text-align:left; font-weight:600;
              font-size:0.75rem; text-transform:uppercase; letter-spacing:0.04em;
              color:var(--slate); border-bottom:2px solid var(--slate-200); position:sticky; top:0; z-index:2; }}
  td {{ padding:10px; border-bottom:1px solid #f1f5f9; }}
  tbody tr {{ transition:background 0.1s; }}
  tbody tr:hover {{ background:#fefce8; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; font-weight:500; }}
  .mono {{ font-family:'SF Mono',SFMono-Regular,Consolas,'Liberation Mono',Menlo,monospace;
           font-size:0.75rem; color:#475569; }}
  .rate-high {{ color:var(--green-dark); font-weight:700; background:var(--green-light);
                padding:3px 10px; border-radius:6px; text-align:center; }}
  .rate-mid  {{ color:var(--yellow-dark); font-weight:700; background:var(--yellow-light);
                padding:3px 10px; border-radius:6px; text-align:center; }}
  .rate-low  {{ color:var(--red-dark); font-weight:700; background:var(--red-light);
                padding:3px 10px; border-radius:6px; text-align:center; }}
  .tbl-wrap {{ overflow-x:auto; border-radius:var(--radius); border:1px solid var(--slate-200);
               background:white; }}

  /* ─── DEEP DIVE ─── */
  .deep {{ background:white; border-radius:var(--radius); padding:24px; margin:16px 0;
           box-shadow:var(--shadow); border:1px solid var(--slate-200); }}
  .deep-meta {{ display:flex; gap:16px; flex-wrap:wrap; margin:10px 0; font-size:0.88rem; }}
  .deep-meta span {{ background:var(--slate-100); padding:4px 12px; border-radius:8px; }}
  .deep-label {{ margin:12px 0; }}
  .deep-label code {{ background:#0f172a; color:#e2e8f0; padding:8px 16px; border-radius:8px;
                      display:inline-block; font-size:0.85rem; font-weight:500; }}
  .step {{ display:flex; align-items:center; gap:10px; padding:8px 16px; margin:4px 0;
           border-radius:8px; font-size:0.85rem; }}
  .step-pre {{ background:var(--slate-100); border-left:4px solid var(--purple); }}
  .step-match {{ background:#ecfdf5; border-left:4px solid var(--green); }}
  .step-no {{ background:#fefce8; border-left:4px solid #d4d4d8; color:#71717a; }}
  .time {{ margin-left:auto; color:#94a3b8; font-size:0.78rem; font-weight:500; }}

  /* ─── INFO BOX ─── */
  .info {{ background:linear-gradient(135deg,#eff6ff,#f0f9ff); border:1px solid #bfdbfe;
           border-radius:12px; padding:16px 20px; margin:1.2rem 0; font-size:0.9rem; color:#1e40af;
           display:flex; gap:12px; align-items:flex-start; }}
  .info::before {{ content:'i'; display:flex; align-items:center; justify-content:center;
                   min-width:24px; height:24px; background:#3b82f6; color:white;
                   border-radius:50%; font-size:0.75rem; font-weight:700; }}

  /* ─── ACCORDION ─── */
  .method-group {{ background:white; border-radius:var(--radius); margin:12px 0;
                   border:1px solid var(--slate-200); overflow:hidden; box-shadow:var(--shadow); }}
  .method-header {{ display:flex; align-items:center; gap:14px; padding:16px 20px;
                    cursor:pointer; user-select:none; transition:background 0.1s; }}
  .method-header:hover {{ background:var(--slate-100); }}
  .method-title {{ font-weight:600; font-size:1rem; flex:1; }}
  .method-count {{ background:var(--slate-100); padding:3px 12px; border-radius:20px;
                   font-size:0.8rem; font-weight:600; color:var(--slate); }}
  .chevron {{ color:var(--slate); transition:transform 0.2s; font-size:0.8rem; }}
  .method-group.open .chevron {{ transform:rotate(180deg); }}
  .method-body {{ display:none; padding:0 20px 20px; }}
  .method-group.open .method-body {{ display:block; }}
  .method-explanation {{ background:linear-gradient(135deg,#eff6ff,#f0f9ff);
                         border-left:4px solid var(--indigo); padding:14px 18px;
                         border-radius:0 10px 10px 0; margin-bottom:16px;
                         font-size:0.9rem; color:#1e40af; line-height:1.6; }}
  .cat-table {{ width:100%; border-collapse:separate; border-spacing:0; font-size:0.8rem; }}
  .cat-table thead th {{ background:var(--slate-100); padding:10px 8px; text-align:left;
                         font-weight:600; font-size:0.72rem; text-transform:uppercase;
                         letter-spacing:0.04em; color:var(--slate);
                         border-bottom:2px solid var(--slate-200); position:sticky; top:0; z-index:2; }}
  .cat-table td {{ padding:8px; border-bottom:1px solid #f8fafc; vertical-align:top; }}
  .cat-table tbody tr {{ transition:background 0.1s; }}
  .cat-table tbody tr:hover {{ background:#fffbeb; }}
  .cat-table .label-cell {{ font-family:'SF Mono',Consolas,monospace; font-size:0.74rem;
                            color:#475569; max-width:320px; word-break:break-all; line-height:1.4; }}
  .cat-table .inv-cell {{ font-family:monospace; font-size:0.74rem; color:var(--green-dark);
                          font-weight:600; max-width:220px; word-break:break-all; }}
  .cat-table .flags-cell {{ font-size:0.72rem; font-weight:600; }}
  .cat-table .flags-cell {{ color:var(--yellow-dark); background:var(--yellow-light);
                            padding:2px 8px; border-radius:4px; white-space:nowrap; }}

  /* ─── RECOMMENDATION ─── */
  .reco-cell {{ padding:6px !important; }}
  .reco-list {{ display:flex; flex-direction:column; gap:4px; }}
  .reco-item {{ display:grid; grid-template-columns:24px 1fr 78px 55px 38px;
                gap:6px; align-items:center; font-size:0.73rem; padding:5px 8px;
                background:var(--slate-100); border-radius:6px; border:1px solid var(--slate-200); }}
  .reco-item:first-child {{ background:#f0f9ff; border-color:#93c5fd; }}
  .reco-item.reco-correct {{ background:#ecfdf5 !important; border:2px solid var(--green) !important;
                             box-shadow:0 0 0 1px rgba(16,185,129,0.2); }}
  .reco-correct .reco-ref {{ color:var(--green-dark) !important; font-weight:700; }}
  .reco-correct .reco-score {{ color:var(--green-dark) !important; }}
  .reco-check {{ display:inline-block; background:var(--green); color:white; font-size:0.62rem;
                 padding:1px 7px; border-radius:4px; font-weight:700; margin-left:6px;
                 font-style:normal; letter-spacing:0.03em; }}
  .reco-fill-correct {{ background:linear-gradient(90deg, var(--green), #34d399) !important; }}
  .reco-rank {{ font-weight:800; color:var(--indigo); font-size:0.8rem; }}
  .reco-ref {{ font-family:monospace; font-size:0.7rem; color:var(--slate-800);
               overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .reco-amt {{ text-align:right; font-variant-numeric:tabular-nums; color:#475569; font-weight:500; }}
  .reco-bar {{ height:10px; background:var(--slate-200); border-radius:5px; overflow:hidden; }}
  .reco-fill {{ display:block; height:100%; border-radius:5px;
                background:linear-gradient(90deg,var(--green),var(--indigo)); }}
  .reco-score {{ font-weight:700; color:var(--indigo); text-align:right; }}
  .reco-reason {{ grid-column:2/-1; color:var(--slate); font-size:0.68rem; padding-left:2px;
                  font-style:italic; }}

  /* ─── BUTTONS ─── */
  .btn {{ display:inline-flex; align-items:center; gap:6px; padding:8px 18px; border:1px solid var(--slate-200);
          border-radius:8px; cursor:pointer; font-size:0.85rem; font-weight:500; background:white;
          color:var(--slate-800); transition:all 0.15s; font-family:inherit; }}
  .btn:hover {{ background:var(--slate-100); box-shadow:var(--shadow); }}
  .btn-group {{ display:flex; gap:8px; margin-bottom:1.2rem; }}

  /* ─── FOOTER ─── */
  .footer {{ margin-top:4rem; padding:2.5rem 0; border-top:2px solid var(--slate-200);
             text-align:center; color:var(--slate); }}

  @media(max-width:900px) {{ .kpis {{ grid-template-columns:repeat(2,1fr); }}
    .grid-2 {{ grid-template-columns:1fr; }} .pipeline {{ gap:2px; }}
    .pipe {{ min-width:80px; padding:10px; }} .hero h1 {{ font-size:1.6rem; }} }}
</style>
</head>
<body>

<!-- NAV -->
<div class="nav">
<div class="container nav-inner">
  <span class="nav-brand">Reconciliation IA</span>
  <a href="#kpis">Dashboard</a>
  <a href="#pipeline">Architecture</a>
  <a href="#charts">Resultats</a>
  <a href="#debtors">Debiteurs</a>
  <a href="#deep">Deep Dive</a>
  <a href="#catalogue">Catalogue</a>
</div>
</div>

<!-- HERO -->
<div class="hero">
<div class="container">
  <h1>Reconciliation Paiement-Facture</h1>
  <div class="sub">Systeme de matching automatique par intelligence artificielle pour le factoring</div>
  <div class="tags">
    <span class="tag">Architecture 6 couches</span>
    <span class="tag">{data['n_debtors']} debiteurs</span>
    <span class="tag">{data['n_invoices']} factures</span>
    <span class="tag">{data['n_payments']} paiements</span>
    <span class="tag">12 mois — 2024</span>
    <span class="tag">74 tests unitaires</span>
  </div>
</div>
</div>

<div class="container">

<!-- KPIs -->
<div id="kpis" class="kpis">
  <div class="kpi primary">
    <div class="value">{auto_pct:.1f}%</div>
    <div class="label">Taux d'automatisation</div>
    <div class="sub-val">{auto} / {total} paiements</div>
  </div>
  <div class="kpi success">
    <div class="value" style="color:var(--green)">{total:,}</div>
    <div class="label">Paiements traites</div>
    <div class="sub-val">0 erreurs pipeline</div>
  </div>
  <div class="kpi warning">
    <div class="value" style="color:var(--yellow)">{total_eur/1e6:.1f}M EUR</div>
    <div class="label">Volume total</div>
    <div class="sub-val">{data['n_invoices']} factures ouvertes</div>
  </div>
  <div class="kpi danger">
    <div class="value" style="color:var(--red)">{review_pct:.1f}%</div>
    <div class="label">Revue humaine</div>
    <div class="sub-val">{review} paiements en file</div>
  </div>
</div>

<!-- PIPELINE -->
<h2 id="pipeline">Architecture du Pipeline</h2>
<div class="pipeline">
  <div class="pipe" style="background:#0f172a"><div class="lbl">Entree</div><div class="nm">Paiement</div></div>
  <div class="arrow">&#10132;</div>
  <div class="pipe" style="background:var(--purple)"><div class="lbl">C0</div><div class="nm">Normalisation</div><div class="conf">14 transforms</div></div>
  <div class="arrow">&#10132;</div>
  <div class="pipe" style="background:var(--green)"><div class="lbl">C1</div><div class="nm">Exact Match</div><div class="conf">97-100%</div></div>
  <div class="arrow">&#10132;</div>
  <div class="pipe" style="background:var(--yellow);color:#1c1917"><div class="lbl">C2</div><div class="nm">Regles Metier</div><div class="conf">85-99%</div></div>
  <div class="arrow">&#10132;</div>
  <div class="pipe" style="background:var(--cyan)"><div class="lbl">C3</div><div class="nm">NLP / Fuzzy</div><div class="conf">75-92%</div></div>
  <div class="arrow">&#10132;</div>
  <div class="pipe" style="background:var(--purple)"><div class="lbl">C4</div><div class="nm">ML Ensemble</div><div class="conf">42 features</div></div>
  <div class="arrow">&#10132;</div>
  <div class="pipe" style="background:var(--pink)"><div class="lbl">C5</div><div class="nm">LLM / IA Gen.</div><div class="conf">Claude / GPT</div></div>
  <div class="arrow">&#10132;</div>
  <div class="pipe" style="background:var(--red)"><div class="lbl">C6</div><div class="nm">Revue Humaine</div><div class="conf">File priorisee</div></div>
</div>
<div class="info">
  <div><b>Principe d'early-exit :</b> des qu'une couche trouve un match avec confiance &#8805; 90%,
  le paiement est cloture instantanement. Les couches suivantes ne sont pas executees.
  Resultat : temps moyen de <b>{m.avg_processing_time_ms:.1f} ms</b> par paiement.</div>
</div>

<!-- CHARTS -->
<h2 id="charts">Resultats de la Simulation</h2>
<div class="grid-2">
  <div class="card">{pie_html}</div>
  <div class="card">{monthly_html}</div>
</div>
<div class="grid-2">
  <div class="card">{methods_html}</div>
  <div class="card">{conf_html}</div>
</div>

<!-- DEBTORS -->
<h2 id="debtors">Analyse par Debiteur</h2>
<div class="card" style="margin-bottom:20px">{debtor_html}</div>
<div class="grid-2">
  <div class="card">{country_html}</div>
  <div class="card">{heat_html}</div>
</div>

<div class="tbl-wrap" style="margin-top:20px; max-height:420px; overflow-y:auto;">
<table>
<thead><tr><th>Debiteur</th><th>Pays</th><th>Total</th><th>Auto</th><th>Revue</th><th>Taux</th><th>Montant EUR</th></tr></thead>
<tbody>{debtor_table}</tbody>
</table>
</div>

<!-- DEEP DIVE -->
<h2 id="deep">Deep Dive — Parcours dans le pipeline</h2>
<p style="color:var(--slate); margin-bottom:1rem; font-size:0.9rem;">
  Chaque paiement traverse les couches C0 &#8594; C6. Voici 3 exemples representatifs
  montrant le parcours complet avec les timings.</p>
{deep_html}

<!-- CATALOGUE -->
<h2 id="catalogue">Catalogue Complet — {total} paiements</h2>
<p style="color:var(--slate); margin-bottom:0.8rem; font-size:0.9rem;">
  Tous les paiements groupes par methode de matching. Pour les paiements <b>Revue Humaine</b>,
  la colonne <b style="color:var(--indigo)">Recommandations</b> affiche les 5 meilleures factures candidates
  triees par score de proximite (montant, debiteur, echeance).
</p>
<div class="btn-group">
  <button class="btn" onclick="document.querySelectorAll('.method-group').forEach(e=>e.classList.add('open'))">
    &#9660; Tout ouvrir</button>
  <button class="btn" onclick="document.querySelectorAll('.method-group').forEach(e=>e.classList.remove('open'))">
    &#9650; Tout fermer</button>
</div>
{catalogue_html}

<!-- FOOTER -->
<div class="footer">
  <p style="font-weight:700; font-size:1rem; margin-bottom:4px;">Reconciliation IA Paiement-Facture</p>
  <p>Architecture 6 couches &bull; Factoring & Finance Receivables</p>
  <p>{data['n_invoices']} factures &bull; {data['n_payments']} paiements &bull;
     {data['n_debtors']} debiteurs &bull; 74 tests</p>
</div>

</div>
</body>
</html>"""

# Write
out = Path(__file__).parent / "demo_reconciliation.html"
out.write_text(html, encoding="utf-8")
print(f"\nExported to: {out}")
print(f"Size: {out.stat().st_size / 1024:.0f} KB")
