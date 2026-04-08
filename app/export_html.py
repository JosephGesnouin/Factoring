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

recommendations = {}  # payment_id -> list of {ref, amount, score, reason}

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
            candidates.append({
                "ref": inv.reference,
                "amount": inv.amount,
                "score": min(score, 1.0),
                "reason": " | ".join(reasons[:3]),
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

    for _, r in group.iterrows():
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
            if recs:
                rec_html = '<div class="reco-list">'
                for rank, rec in enumerate(recs[:5], 1):
                    bar_w = int(rec["score"] * 100)
                    rec_html += (
                        f'<div class="reco-item">'
                        f'<span class="reco-rank">#{rank}</span>'
                        f'<span class="reco-ref">{rec["ref"]}</span>'
                        f'<span class="reco-amt">{rec["amount"]:,.2f}</span>'
                        f'<span class="reco-bar"><span class="reco-fill" style="width:{bar_w}%"></span></span>'
                        f'<span class="reco-score">{rec["score"]:.0%}</span>'
                        f'<span class="reco-reason">{rec["reason"]}</span>'
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
# HTML GENERATION
# ============================================================
print("Generating HTML...")

# Convert plotly figures to HTML divs
def fig_to_div(fig, div_id):
    return fig.to_html(full_html=False, include_plotlyjs=False, div_id=div_id)

pie_html = fig_to_div(fig_pie, "pie")
monthly_html = fig_to_div(fig_monthly, "monthly")
methods_html = fig_to_div(fig_methods, "methods")
debtor_html = fig_to_div(fig_debtor, "debtor")
country_html = fig_to_div(fig_country, "country")
conf_html = fig_to_div(fig_conf, "conf")
heat_html = fig_to_div(fig_heat, "heat")

# Build payment table (top 50)
display = df.head(80).copy()
table_rows = ""
for _, r in display.iterrows():
    layer_class = {"C1":"c1","C2":"c2","C3":"c3","C6":"c6"}.get(r["layer_name"],"c6")
    conf_str = f"{r['confidence']:.0%}" if r["confidence"] > 0 else "—"
    table_rows += f"""<tr>
        <td>{r['payment_id']}</td><td>{r['date']}</td>
        <td class="num">{r['amount']:,.2f}</td>
        <td>{r['debtor_name'][:25]}</td>
        <td class="label-cell">{r['label'][:35]}</td>
        <td><span class="badge {layer_class}">{r['layer_name']}</span></td>
        <td>{r['method'][:20]}</td>
        <td class="num">{conf_str}</td>
        <td>{r['flags'][:20]}</td>
    </tr>"""

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
    <div class="deep-card">
        <h3>{ex['title']}</h3>
        <div class="deep-meta">
            <span><b>ID:</b> {row['payment_id']}</span>
            <span><b>Montant:</b> {row['amount']:,.2f} EUR</span>
            <span><b>Date:</b> {row['date']}</span>
            <span><b>Debiteur:</b> {row['debtor_name']}</span>
            <span class="badge {badge_cls}">{row['layer_name']} — {conf_pct}</span>
        </div>
        <div class="deep-label"><b>Libelle:</b> <code>{row['label'] if row['label'] else '(vide)'}</code></div>
        <div class="deep-steps"><b>Parcours pipeline :</b>{steps_html}</div>
        <div class="deep-result"><b>Factures:</b> {invoices_str}</div>
        {f'<div class="deep-flags"><b>Flags:</b> {row["flags"]}</div>' if row["flags"] else ""}
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

# Assemble
total_eur = df["amount"].sum()

html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Reconciliation IA — Demo Executive</title>
<script src="https://cdn.plot.ly/plotly-2.35.0.min.js"></script>
<style>
  :root {{ --green:#10b981; --yellow:#f59e0b; --cyan:#06b6d4; --red:#ef4444;
           --purple:#8b5cf6; --indigo:#667eea; --slate:#64748b; }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:'Segoe UI',system-ui,-apple-system,sans-serif; background:#f8fafc; color:#1e293b; line-height:1.6; }}
  .container {{ max-width:1200px; margin:0 auto; padding:20px; }}
  h1 {{ font-size:2rem; margin-bottom:0.3rem; }}
  h2 {{ font-size:1.5rem; margin:2.5rem 0 1rem; padding-bottom:0.5rem; border-bottom:2px solid #e2e8f0; }}
  h3 {{ font-size:1.15rem; margin-bottom:0.5rem; }}

  /* Header */
  .header {{ background:linear-gradient(135deg,#1e293b 0%,#334155 100%); color:white;
             padding:2.5rem 0; margin-bottom:2rem; }}
  .header h1 {{ font-size:2.2rem; }}
  .header p {{ opacity:0.8; font-size:1.05rem; }}
  .header .subtitle {{ display:flex; gap:2rem; margin-top:0.5rem; font-size:0.9rem; opacity:0.65; }}

  /* KPI cards */
  .kpis {{ display:grid; grid-template-columns:repeat(4,1fr); gap:16px; margin-bottom:2rem; }}
  .kpi {{ background:white; border-radius:12px; padding:20px; text-align:center;
          box-shadow:0 1px 3px rgba(0,0,0,0.1); border:1px solid #e2e8f0; }}
  .kpi .value {{ font-size:2rem; font-weight:700; }}
  .kpi .label {{ font-size:0.85rem; color:var(--slate); margin-top:4px; }}
  .kpi.highlight {{ background:linear-gradient(135deg,var(--indigo),var(--purple)); color:white; }}
  .kpi.highlight .label {{ color:rgba(255,255,255,0.8); }}

  /* Charts grid */
  .charts-2 {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin:1rem 0; }}
  .chart-box {{ background:white; border-radius:12px; padding:16px;
                box-shadow:0 1px 3px rgba(0,0,0,0.08); border:1px solid #e2e8f0; }}

  /* Badges */
  .badge {{ display:inline-block; padding:3px 12px; border-radius:20px; font-weight:600;
            font-size:0.78rem; color:white; }}
  .badge.c1 {{ background:var(--green); }} .badge.c2 {{ background:var(--yellow); }}
  .badge.c3 {{ background:var(--cyan); }}  .badge.c6 {{ background:var(--red); }}
  .badge-sm {{ display:inline-block; padding:1px 8px; border-radius:12px;
               font-size:0.72rem; color:white; background:var(--indigo); }}

  /* Pipeline */
  .pipeline {{ display:flex; gap:6px; align-items:center; flex-wrap:wrap;
               justify-content:center; margin:1.5rem 0; }}
  .pipe-box {{ padding:14px 18px; border-radius:10px; text-align:center; color:white; min-width:110px; }}
  .pipe-box .layer {{ font-size:0.7rem; opacity:0.8; }} .pipe-box .name {{ font-weight:700; }}
  .pipe-box .sub {{ font-size:0.72rem; opacity:0.75; }}
  .pipe-arrow {{ font-size:1.4rem; color:#94a3b8; }}

  /* Tables */
  table {{ width:100%; border-collapse:collapse; font-size:0.82rem; }}
  th {{ background:#f1f5f9; padding:10px 8px; text-align:left; font-weight:600;
       border-bottom:2px solid #e2e8f0; position:sticky; top:0; }}
  td {{ padding:8px; border-bottom:1px solid #f1f5f9; }}
  tr:hover {{ background:#f8fafc; }}
  .num {{ text-align:right; font-variant-numeric:tabular-nums; }}
  .label-cell {{ font-family:monospace; font-size:0.75rem; color:var(--slate); max-width:250px;
                 overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .rate-high {{ color:#065f46; font-weight:700; background:#d1fae5; text-align:center; border-radius:4px; }}
  .rate-mid  {{ color:#92400e; font-weight:700; background:#fef3c7; text-align:center; border-radius:4px; }}
  .rate-low  {{ color:#991b1b; font-weight:700; background:#fee2e2; text-align:center; border-radius:4px; }}
  .table-scroll {{ max-height:500px; overflow-y:auto; border-radius:8px; border:1px solid #e2e8f0; }}

  /* Deep dive */
  .deep-card {{ background:white; border-radius:12px; padding:20px; margin:16px 0;
                box-shadow:0 1px 3px rgba(0,0,0,0.08); border:1px solid #e2e8f0; }}
  .deep-meta {{ display:flex; gap:16px; flex-wrap:wrap; margin:8px 0; font-size:0.88rem; }}
  .deep-label {{ margin:10px 0; }} .deep-label code {{ background:#f1f5f9; padding:4px 10px;
    border-radius:4px; font-size:0.85rem; }}
  .deep-steps {{ margin:10px 0; }}
  .step {{ display:flex; align-items:center; gap:10px; padding:6px 14px; margin:3px 0;
           border-radius:4px; font-size:0.85rem; }}
  .step-pre {{ background:#f1f5f9; border-left:4px solid var(--purple); }}
  .step-match {{ background:#f0fdf4; border-left:4px solid var(--green); }}
  .step-no {{ background:#fefce8; border-left:4px solid #d4d4d8; color:#71717a; }}
  .time {{ margin-left:auto; color:#94a3b8; font-size:0.78rem; }}
  .deep-result {{ margin-top:8px; font-size:0.9rem; }}
  .deep-flags {{ margin-top:4px; font-size:0.85rem; color:var(--yellow); }}

  /* Info box */
  .info {{ background:#eff6ff; border:1px solid #bfdbfe; border-radius:8px;
           padding:12px 16px; margin:1rem 0; font-size:0.9rem; color:#1e40af; }}

  /* Section divider */
  .section {{ margin-top:3rem; }}

  /* Catalogue accordion */
  .method-group {{ background:white; border-radius:10px; margin:10px 0;
                   border:1px solid #e2e8f0; overflow:hidden; }}
  .method-header {{ display:flex; align-items:center; gap:12px; padding:14px 18px;
                    cursor:pointer; user-select:none; }}
  .method-header:hover {{ background:#f8fafc; }}
  .method-title {{ font-weight:600; font-size:1rem; flex:1; }}
  .method-count {{ color:var(--slate); font-size:0.85rem; }}
  .chevron {{ color:var(--slate); transition:transform 0.2s; }}
  .method-group.open .chevron {{ transform:rotate(180deg); }}
  .method-body {{ display:none; padding:0 18px 18px; }}
  .method-group.open .method-body {{ display:block; }}
  .method-explanation {{ background:#eff6ff; border-left:4px solid var(--indigo);
                         padding:10px 14px; border-radius:0 6px 6px 0;
                         margin-bottom:12px; font-size:0.9rem; color:#1e40af; }}
  .cat-table {{ width:100%; border-collapse:collapse; font-size:0.8rem; }}
  .cat-table th {{ background:#f1f5f9; padding:8px 6px; text-align:left;
                   font-weight:600; font-size:0.75rem; border-bottom:2px solid #e2e8f0;
                   position:sticky; top:0; }}
  .cat-table td {{ padding:6px; border-bottom:1px solid #f1f5f9; vertical-align:top; }}
  .cat-table tr:hover {{ background:#fefce8; }}
  .cat-table .label-cell {{ font-family:'Courier New',monospace; font-size:0.75rem;
                            color:#475569; max-width:300px; word-break:break-all; }}
  .cat-table .inv-cell {{ font-family:monospace; font-size:0.73rem; color:var(--green);
                          max-width:200px; word-break:break-all; }}
  .cat-table .flags-cell {{ font-size:0.73rem; color:var(--yellow); font-weight:600; }}

  /* Recommendation cells */
  .reco-cell {{ padding:4px !important; }}
  .reco-list {{ display:flex; flex-direction:column; gap:3px; }}
  .reco-item {{ display:grid; grid-template-columns:22px 130px 80px 60px 36px 1fr;
                gap:4px; align-items:center; font-size:0.72rem; padding:2px 4px;
                background:#f8fafc; border-radius:3px; }}
  .reco-rank {{ font-weight:700; color:var(--indigo); }}
  .reco-ref {{ font-family:monospace; font-size:0.7rem; color:#334155; overflow:hidden;
               text-overflow:ellipsis; white-space:nowrap; }}
  .reco-amt {{ text-align:right; font-variant-numeric:tabular-nums; color:#475569; }}
  .reco-bar {{ height:8px; background:#e2e8f0; border-radius:4px; overflow:hidden; }}
  .reco-fill {{ display:block; height:100%; background:linear-gradient(90deg,var(--green),var(--indigo));
                border-radius:4px; }}
  .reco-score {{ font-weight:700; color:var(--indigo); text-align:right; }}
  .reco-reason {{ color:var(--slate); font-size:0.68rem; overflow:hidden;
                  text-overflow:ellipsis; white-space:nowrap; }}

  @media(max-width:768px) {{ .kpis {{ grid-template-columns:repeat(2,1fr); }}
    .charts-2 {{ grid-template-columns:1fr; }} }}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
<div class="container">
  <h1>Reconciliation Paiement-Facture par IA</h1>
  <p>Systeme intelligent de matching automatique pour le factoring — Architecture 6 couches</p>
  <div class="subtitle">
    <span>{data['n_debtors']} debiteurs</span>
    <span>{data['n_invoices']} factures</span>
    <span>{data['n_payments']} paiements</span>
    <span>12 mois (2024)</span>
    <span>74 tests</span>
  </div>
</div>
</div>

<div class="container">

<!-- KPIs -->
<div class="kpis">
  <div class="kpi highlight">
    <div class="value">{auto_pct:.1f}%</div>
    <div class="label">Taux d'automatisation</div>
  </div>
  <div class="kpi">
    <div class="value">{total:,}</div>
    <div class="label">Paiements traites</div>
  </div>
  <div class="kpi">
    <div class="value">{total_eur/1e6:.1f}M</div>
    <div class="label">Volume (EUR)</div>
  </div>
  <div class="kpi">
    <div class="value">{m.avg_processing_time_ms:.1f}ms</div>
    <div class="label">Temps moyen/paiement</div>
  </div>
</div>

<!-- PIPELINE -->
<h2>Architecture du Pipeline</h2>
<div class="pipeline">
  <div class="pipe-box" style="background:#1e293b"><div class="layer">ENTREE</div><div class="name">Paiement</div></div>
  <div class="pipe-arrow">→</div>
  <div class="pipe-box" style="background:var(--purple)"><div class="layer">C0</div><div class="name">Normalisation</div><div class="sub">14 transforms</div></div>
  <div class="pipe-arrow">→</div>
  <div class="pipe-box" style="background:var(--green)"><div class="layer">C1</div><div class="name">Exact Match</div><div class="sub">97-100%</div></div>
  <div class="pipe-arrow">→</div>
  <div class="pipe-box" style="background:var(--yellow)"><div class="layer">C2</div><div class="name">Regles Metier</div><div class="sub">85-99%</div></div>
  <div class="pipe-arrow">→</div>
  <div class="pipe-box" style="background:var(--cyan)"><div class="layer">C3</div><div class="name">NLP / Fuzzy</div><div class="sub">75-92%</div></div>
  <div class="pipe-arrow">→</div>
  <div class="pipe-box" style="background:#8b5cf6"><div class="layer">C4</div><div class="name">ML Ensemble</div><div class="sub">80-95%</div></div>
  <div class="pipe-arrow">→</div>
  <div class="pipe-box" style="background:#ec4899"><div class="layer">C5</div><div class="name">LLM / IA Gen.</div><div class="sub">Variable</div></div>
  <div class="pipe-arrow">→</div>
  <div class="pipe-box" style="background:var(--red)"><div class="layer">C6</div><div class="name">Revue Humaine</div><div class="sub">File priorisee</div></div>
</div>
<div class="info">
  <b>Principe d'early-exit :</b> des qu'une couche trouve un match avec confiance ≥ 90%,
  le paiement est cloture instantanement. Les couches suivantes ne sont pas executees.
  C1 traite ~46% des paiements en moins de 2ms.
</div>

<!-- CHARTS -->
<h2>Resultats de la Simulation</h2>
<div class="charts-2">
  <div class="chart-box">{pie_html}</div>
  <div class="chart-box">{monthly_html}</div>
</div>

<div class="charts-2">
  <div class="chart-box">{methods_html}</div>
  <div class="chart-box">{conf_html}</div>
</div>

<!-- DEBTOR ANALYSIS -->
<h2 class="section">Analyse par Debiteur</h2>
<div class="chart-box">
  {debtor_html}
</div>

<div class="charts-2" style="margin-top:20px">
  <div class="chart-box">{country_html}</div>
  <div class="chart-box">{heat_html}</div>
</div>

<h3 style="margin-top:1.5rem">Tableau detaille</h3>
<div class="table-scroll" style="max-height:400px">
<table>
<tr><th>Debiteur</th><th>Pays</th><th>Total</th><th>Auto</th><th>Revue</th><th>Taux</th><th>Montant EUR</th></tr>
{debtor_table}
</table>
</div>

<!-- DEEP DIVE — 3 exemples -->
<h2 class="section">Deep Dive — 3 exemples representatifs</h2>
<p style="color:var(--slate); margin-bottom:1rem">Parcours complet de paiements a travers le pipeline couche par couche.</p>
{deep_html}

<!-- CATALOGUE COMPLET -->
<h2 class="section">Catalogue Complet — Tous les {total} paiements par methode</h2>
<p style="color:var(--slate); margin-bottom:0.5rem">
  Chaque section explique la logique de matching. Pour les paiements <b>Revue Humaine</b>,
  une colonne <b>recommandation</b> affiche les 5 meilleures factures candidates triees par score de proximite.
</p>
<div style="margin-bottom:1rem">
  <button onclick="document.querySelectorAll('.method-group').forEach(e=>e.classList.add('open'))"
          style="padding:6px 16px; border:1px solid #e2e8f0; border-radius:6px; cursor:pointer; font-size:0.85rem; background:white;">
    Tout ouvrir</button>
  <button onclick="document.querySelectorAll('.method-group').forEach(e=>e.classList.remove('open'))"
          style="padding:6px 16px; border:1px solid #e2e8f0; border-radius:6px; cursor:pointer; font-size:0.85rem; background:white; margin-left:6px;">
    Tout fermer</button>
</div>
{catalogue_html}

<!-- FOOTER -->
<div style="margin-top:3rem; padding:2rem 0; border-top:1px solid #e2e8f0; text-align:center; color:var(--slate); font-size:0.85rem;">
  <p><b>Reconciliation IA Paiement-Facture</b> — Architecture 6 couches</p>
  <p>Factoring & Finance Receivables | {data['n_invoices']} factures | {data['n_payments']} paiements | 74 tests</p>
</div>

</div>
</body>
</html>"""

# Write
out = Path(__file__).parent / "demo_reconciliation.html"
out.write_text(html, encoding="utf-8")
print(f"\nExported to: {out}")
print(f"Size: {out.stat().st_size / 1024:.0f} KB")
