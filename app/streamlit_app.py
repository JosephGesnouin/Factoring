"""
Streamlit Demo — Reconciliation Paiement-Facture par IA
Design premium identique a l'export HTML.

Lancer : streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from collections import defaultdict
from html import escape as _esc

st.set_page_config(
    page_title="Reconciliation IA — Factoring",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =====================================================================
# CSS PREMIUM — identique au HTML export
# =====================================================================
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
<style>
    /* Global */
    .main .block-container { padding-top: 0.5rem; max-width: 1300px; }
    html, body, [class*="css"] { font-family: 'Inter', system-ui, -apple-system, sans-serif !important; }
    h1, h2, h3 { font-family: 'Inter', sans-serif !important; letter-spacing: -0.02em; }

    /* Hero banner */
    .hero {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 50%, #1e293b 100%);
        color: white; padding: 2rem 2.5rem; border-radius: 16px; margin-bottom: 1.5rem;
    }
    .hero h1 { font-size: 2rem; font-weight: 800; margin: 0; color: white !important; }
    .hero .sub { font-size: 1rem; opacity: 0.7; font-weight: 300; margin-top: 4px; }
    .hero .tags { display: flex; gap: 10px; margin-top: 1rem; flex-wrap: wrap; }
    .hero .tag {
        background: rgba(255,255,255,0.12); backdrop-filter: blur(4px);
        padding: 5px 14px; border-radius: 20px; font-size: 0.78rem; font-weight: 500;
        border: 1px solid rgba(255,255,255,0.15);
    }

    /* KPI cards */
    .kpi-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin: 1rem 0 1.5rem; }
    .kpi-card {
        background: white; border-radius: 14px; padding: 20px 16px; text-align: center;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;
        transition: transform 0.15s, box-shadow 0.15s;
    }
    .kpi-card:hover { transform: translateY(-2px); box-shadow: 0 8px 16px rgba(0,0,0,0.1); }
    .kpi-card .value { font-size: 2rem; font-weight: 800; letter-spacing: -0.02em; }
    .kpi-card .label { font-size: 0.8rem; color: #64748b; margin-top: 4px; font-weight: 500; }
    .kpi-card .sub-val { font-size: 0.75rem; color: #94a3b8; margin-top: 2px; }
    .kpi-card.primary { background: linear-gradient(135deg, #667eea, #8b5cf6); color: white; }
    .kpi-card.primary .label { color: rgba(255,255,255,0.8); }
    .kpi-card.primary .sub-val { color: rgba(255,255,255,0.6); }
    .kpi-card.success { border-bottom: 3px solid #10b981; }
    .kpi-card.warning { border-bottom: 3px solid #f59e0b; }
    .kpi-card.danger { border-bottom: 3px solid #ef4444; }

    /* Pipeline */
    .pipeline { display: flex; gap: 5px; align-items: center; flex-wrap: wrap; justify-content: center; margin: 1.5rem 0; }
    .pipe {
        padding: 14px 18px; border-radius: 12px; text-align: center; color: white;
        min-width: 112px; box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        transition: transform 0.15s;
    }
    .pipe:hover { transform: scale(1.06); }
    .pipe .lbl { font-size: 0.62rem; text-transform: uppercase; letter-spacing: 0.08em; opacity: 0.8; }
    .pipe .nm { font-weight: 700; font-size: 0.92rem; }
    .pipe .conf { font-size: 0.68rem; opacity: 0.7; margin-top: 2px; }
    .arrow { font-size: 1.1rem; color: #cbd5e1; }

    /* Badges */
    .badge {
        display: inline-flex; align-items: center; padding: 4px 14px; border-radius: 20px;
        font-weight: 600; font-size: 0.76rem; color: white;
    }
    .badge.c1 { background: #10b981; } .badge.c2 { background: #f59e0b; color: #1c1917; }
    .badge.c3 { background: #06b6d4; } .badge.c6 { background: #ef4444; }

    /* Info box */
    .info-box {
        background: linear-gradient(135deg, #eff6ff, #f0f9ff); border: 1px solid #bfdbfe;
        border-radius: 12px; padding: 14px 18px; margin: 1rem 0; font-size: 0.88rem;
        color: #1e40af; display: flex; gap: 12px; align-items: flex-start;
    }
    .info-box .icon {
        display: flex; align-items: center; justify-content: center;
        min-width: 26px; height: 26px; background: #3b82f6; color: white;
        border-radius: 50%; font-size: 0.75rem; font-weight: 700;
    }

    /* Deep dive */
    .deep-card {
        background: white; border-radius: 14px; padding: 22px; margin: 14px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.08); border: 1px solid #e2e8f0;
    }
    .deep-meta { display: flex; gap: 12px; flex-wrap: wrap; margin: 10px 0; }
    .deep-meta span {
        background: #f1f5f9; padding: 5px 14px; border-radius: 8px; font-size: 0.85rem;
    }
    .deep-label code {
        background: #0f172a; color: #e2e8f0; padding: 8px 16px; border-radius: 8px;
        display: inline-block; font-size: 0.85rem; font-weight: 500;
    }
    .step {
        display: flex; align-items: center; gap: 10px; padding: 8px 16px;
        margin: 4px 0; border-radius: 8px; font-size: 0.85rem;
    }
    .step-pre { background: #f1f5f9; border-left: 4px solid #8b5cf6; }
    .step-match { background: #ecfdf5; border-left: 4px solid #10b981; }
    .step-no { background: #fefce8; border-left: 4px solid #d4d4d8; color: #71717a; }
    .step .time { margin-left: auto; color: #94a3b8; font-size: 0.78rem; font-weight: 500; }
    .result-box { padding: 10px 16px; border-radius: 8px; margin-top: 10px; font-size: 0.9rem; }
    .result-ok { background: #d1fae5; color: #065f46; }
    .result-flags { background: #fef3c7; color: #92400e; }
    .result-fail { background: #fee2e2; color: #991b1b; }

    /* Section headers */
    .section-h {
        font-size: 1.3rem; font-weight: 700; margin: 1.5rem 0 0.8rem;
        display: flex; align-items: center; gap: 10px;
    }
    .section-h::before {
        content: ''; width: 4px; height: 22px; background: #667eea; border-radius: 2px;
    }

    /* Plotly transparent */
    .js-plotly-plot .plotly .main-svg { background: transparent !important; }

    /* Hide streamlit branding — mais GARDE le header visible car il
       contient le bouton de collapse/expand de la sidebar dans les
       versions récentes de Streamlit. */
    #MainMenu, footer { visibility: hidden; }

    /* Force la sidebar à toujours rester accessible et visible (anti
       bug d'iframe / proxy datalab qui peut la masquer). */
    section[data-testid="stSidebar"] {
        display: block !important;
        visibility: visible !important;
        min-width: 240px !important;
    }
    /* S'assurer que le bouton de collapse reste cliquable */
    button[kind="header"], [data-testid="collapsedControl"] {
        display: block !important;
        visibility: visible !important;
    }

    /* Responsive */
    @media (max-width: 900px) { .kpi-grid { grid-template-columns: repeat(2,1fr); } }
</style>
""", unsafe_allow_html=True)


# =====================================================================
# DATA
# =====================================================================
import os
from reconciliation.loaders import data_dir_is_ready

# Mode de données :
#   - Si FACTORING_DATA_DIR est défini ET contient les 3 CSV requis,
#     on tourne sur les données réelles.
#   - Sinon, on retombe sur la simulation (comportement historique).
_DATA_DIR_ENV = os.environ.get("FACTORING_DATA_DIR", "").strip()
_DATA_DIR = Path(_DATA_DIR_ENV).expanduser().resolve() if _DATA_DIR_ENV else None
_USE_REAL = _DATA_DIR is not None and data_dir_is_ready(_DATA_DIR)


@st.cache_data(show_spinner="Chargement des donnees et execution du pipeline...")
def load_data():
    import warnings; warnings.filterwarnings("ignore")
    if _USE_REAL:
        from app.real_data import run_real
        return run_real(_DATA_DIR)
    from app.simulation_data import generate_all
    return generate_all(seed=42, target_payments=5000)


# ── Plotly defaults ──
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, system-ui, sans-serif", color="#334155"),
    margin=dict(t=30, b=20, l=20, r=20),
)
C_GREEN, C_YELLOW, C_CYAN, C_RED = "#10b981", "#f59e0b", "#06b6d4", "#ef4444"
C_INDIGO, C_PURPLE, C_PINK = "#667eea", "#8b5cf6", "#ec4899"
MONTH_ORDER = ["Janvier","Fevrier","Mars","Avril","Mai","Juin",
               "Juillet","Aout","Septembre","Octobre","Novembre","Decembre"]
LAYER_NAMES = {1:"C1 Exact",2:"C2 Regles Metier",3:"C3 NLP/Fuzzy",6:"C6 Revue Humaine"}
LAYER_COLORS = {"C1 Exact":C_GREEN,"C2 Regles Metier":C_YELLOW,"C3 NLP/Fuzzy":C_CYAN,"C6 Revue Humaine":C_RED}

# ── Sidebar (conservée mais NON BLOQUANTE si masquée par le proxy) ──
with st.sidebar:
    st.markdown("### 🏦 Reconciliation IA")
    st.caption("Factoring & Finance Receivables")
    st.divider()
    st.caption("Architecture 6 couches")
    if _USE_REAL:
        st.success(f"Mode : **Donnees reelles**\n\n`{_DATA_DIR}`", icon="📁")
    else:
        if _DATA_DIR_ENV:
            st.warning(
                f"FACTORING_DATA_DIR pointe vers `{_DATA_DIR}` mais les "
                "3 CSV requis sont absents. Mode simulation actif.",
                icon="⚠️",
            )
        else:
            st.info("Mode : **Simulation** (50 debiteurs, 5k paiements)\n\n"
                    "Pour utiliser tes vrais fichiers : voir `DATA_SETUP.md`.",
                    icon="🧪")

# ── Navigation principale en HAUT (toujours visible, indépendant du proxy) ──
_nav_pages = [
    "Executive Summary",
    "Architecture",
    "Factures",
    "Paiements",
    "Simulation Live",
    "Analyse Debiteurs",
    "Paiements par Couche",
    "Revue Humaine",
    "Mapping Complet",
    "Profils Debiteurs IA",
    "Deep Dive",
]

# Badge mode en haut de page (visible même sans sidebar)
_mode_col1, _mode_col2 = st.columns([3, 1])
with _mode_col2:
    if _USE_REAL:
        st.success(f"📁 Données réelles", icon="✅")
    else:
        st.info(f"🧪 Simulation", icon="ℹ️")

# Navigation horizontale toujours visible
page = st.radio(
    "Navigation",
    options=_nav_pages,
    horizontal=True,
    label_visibility="collapsed",
    key="main_nav",
)
st.divider()

data = load_data()
df = data["df"]
m = data["metrics"]
total = m.total_payments
auto = m.matched_auto
review = m.by_layer.get(6, 0)
auto_pct = auto / total * 100
review_pct = review / total * 100
total_eur = df["amount"].sum()


# =====================================================================
# PAGE 0 — DIAGNOSTIC DONNEES (mode reel uniquement)
# =====================================================================
if page == "Diagnostic Donnees":
    diag = data.get("diagnostic") or {}
    st.markdown("""
    <div class="hero">
      <h1>Diagnostic des donnees</h1>
      <div class="sub">Qualite des CSV charges et causes probables d'un taux de matching faible</div>
    </div>
    """, unsafe_allow_html=True)

    if not diag:
        st.info("Pas de rapport de diagnostic disponible.")
    else:
        # ── KPIs ──────────────────────────────────────────────────────
        iban_rate = diag["iban_match_rate"] * 100
        inv_rate  = diag["invoice_debtor_match_rate"] * 100

        def _badge_color(rate: float) -> str:
            return C_GREEN if rate >= 70 else (C_YELLOW if rate >= 30 else C_RED)

        st.markdown(f"""
        <div class="kpi-grid">
          <div class="kpi-card">
            <div class="value">{diag['n_payments']:,}</div>
            <div class="label">Paiements charges</div>
          </div>
          <div class="kpi-card">
            <div class="value">{diag['n_invoices']:,}</div>
            <div class="label">Factures ouvertes</div>
          </div>
          <div class="kpi-card">
            <div class="value">{diag['n_debtors']:,}</div>
            <div class="label">Debiteurs</div>
            <div class="sub-val">{diag['iban_in_debtors']:,} avec IBAN</div>
          </div>
          <div class="kpi-card">
            <div class="value" style="color:{_badge_color(iban_rate)}">{iban_rate:.1f}%</div>
            <div class="label">IBAN paiements connus</div>
            <div class="sub-val">{diag['payments_iban_known']:,} / {diag['n_payments']:,}</div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        # ── Verdict synthese ─────────────────────────────────────────
        st.markdown("### Verdict")
        verdicts = []
        if iban_rate < 30:
            verdicts.append(
                ("error",
                 f"**IBAN paiements ≠ IBAN débiteurs**. Seulement {iban_rate:.0f}% "
                 f"des paiements ont un IBAN_EMETT reconnu. La couche C1-R004 "
                 f"(IBAN+montant), principal levier de matching, ne peut pas "
                 f"travailler. Vérifie que la colonne **IBAN** de `debtors_all.csv` "
                 f"contient bien les IBAN **des donneurs d'ordre** (et pas tes "
                 f"propres IBAN de factor).")
            )
        elif iban_rate < 70:
            verdicts.append(
                ("warning",
                 f"Couverture IBAN partielle ({iban_rate:.0f}%). Voir l'echantillon "
                 f"des IBAN inconnus ci-dessous.")
            )
        if inv_rate < 70:
            verdicts.append(
                ("warning",
                 f"**Factures orphelines** : {diag['invoices_debtor_unknown']:,} "
                 f"factures ({100-inv_rate:.0f}%) ont un `debtor_number` qui ne "
                 f"correspond a aucun debiteur charge. Verifie la jointure "
                 f"`invoices.debtor_number` <-> `debtors.client_debtor_number`.")
            )
        if diag["labels_empty"] > diag["n_payments"] * 0.5:
            verdicts.append(
                ("warning",
                 f"{diag['labels_empty']:,} paiements ont un libelle vide. "
                 f"C1-R001 (reference exacte dans le libelle) ne pourra rien faire.")
            )
        if not verdicts:
            st.success("Aucun probleme structurel detecte sur les donnees chargees.", icon="✅")
        else:
            for lvl, msg in verdicts:
                getattr(st, lvl)(msg)

        # ── Detail jointures ──────────────────────────────────────────
        st.markdown("### Jointures")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Pont IBAN paiements → débiteurs**")
            st.markdown(f"""
- IBAN distincts dans `debtors_all.csv` : **{diag['iban_in_debtors']:,}**
- Paiements avec un IBAN_EMETT renseigné : **{diag['payments_with_iban']:,}**
- … dont reconnus : **{diag['payments_iban_known']:,}** ({iban_rate:.1f}%)
- … dont inconnus : **{diag['payments_iban_unknown']:,}**
- Paiements sans IBAN_EMETT : **{diag['payments_without_iban']:,}**
""")
        with col2:
            st.markdown("**Pont factures → débiteurs**")
            st.markdown(f"""
- Factures avec `debtor_number` reconnu : **{diag['invoices_debtor_known']:,}** ({inv_rate:.1f}%)
- Factures avec `debtor_number` inconnu : **{diag['invoices_debtor_unknown']:,}**
- Factures sans `debtor_number` : **{diag['invoices_debtor_empty']:,}**
""")

        # ── Devises ──────────────────────────────────────────────────
        st.markdown("### Devises")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Paiements**")
            st.dataframe(pd.DataFrame(
                sorted(diag["pay_currencies"].items(),
                       key=lambda x: -x[1]),
                columns=["Devise", "N paiements"]),
                hide_index=True, use_container_width=True)
        with col2:
            st.markdown("**Factures**")
            st.dataframe(pd.DataFrame(
                sorted(diag["inv_currencies"].items(),
                       key=lambda x: -x[1]),
                columns=["Devise", "N factures"]),
                hide_index=True, use_container_width=True)

        # ── Comparaison IBAN cote a cote (LE point critique) ─────────
        st.markdown("### IBAN : comparaison côte à côte")
        st.caption("**Si les deux colonnes se ressemblent (mêmes pays, "
                   "même longueur), c'est un problème de format. Si elles "
                   "sont structurellement différentes, l'IBAN_EMETT n'est "
                   "pas l'IBAN du débiteur — il faut un autre champ.**")
        col1, col2 = st.columns(2)
        with col1:
            st.markdown(f"**IBAN attendus** (col. `IBAN` de `debtors_all.csv`, {len(diag.get('sample_known_iban',[]))} affichés)")
            if diag.get("sample_known_iban"):
                st.dataframe(pd.DataFrame(diag["sample_known_iban"]),
                             hide_index=True, use_container_width=True)
            else:
                st.info("Aucun IBAN dans `debtors_all.csv` — la colonne est vide.")
        with col2:
            st.markdown(f"**IBAN reçus** (col. `IBAN_EMETT` de `payments_all.csv`, {len(diag.get('sample_unknown_iban',[]))} affichés)")
            if diag["sample_unknown_iban"]:
                st.dataframe(pd.DataFrame(diag["sample_unknown_iban"]),
                             hide_index=True, use_container_width=True)
            else:
                st.success("Tous les IBAN paiement sont reconnus.")

        # ── Qualité libellés (vital si IBAN ne marche pas) ───────────
        st.markdown("### Qualité des libellés bancaires")
        nb_pay = max(diag["n_payments"], 1)
        pct_num = diag.get("labels_with_long_num", 0) * 100 / nb_pay
        pct_kw  = diag.get("labels_with_inv_kw", 0) * 100 / nb_pay
        if iban_rate < 10:
            st.warning(
                f"L'IBAN ne sert plus à rien ({iban_rate:.0f}%). Le seul "
                f"recours est l'extraction de référence facture depuis le "
                f"libellé. Vérifie ci-dessous que tes libellés contiennent "
                f"effectivement les références.", icon="🔎"
            )
        col1, col2, col3 = st.columns(3)
        col1.metric("Libellés vides", f"{diag['labels_empty']:,}",
                    f"{diag['labels_empty']*100/nb_pay:.1f}%")
        col2.metric("Avec séquence ≥ 5 chiffres",
                    f"{diag.get('labels_with_long_num',0):,}",
                    f"{pct_num:.1f}%")
        col3.metric("Avec mot-clé FAC/INV/FT…",
                    f"{diag.get('labels_with_inv_kw',0):,}",
                    f"{pct_kw:.1f}%")
        if diag.get("sample_labels"):
            st.markdown("**Échantillon de 30 libellés** — copie-colle ici si "
                        "tu veux que j'adapte les regex de C0 :")
            st.dataframe(pd.DataFrame(diag["sample_labels"]),
                         hide_index=True, use_container_width=True)

        # Échantillon des valeurs brutes (avant normalisation)
        with st.expander("🔬 Valeurs IBAN brutes (avant normalisation)"):
            st.caption("Ces valeurs sont prises directement dans le CSV "
                       "**sans nettoyage**. Si les formats diffèrent entre "
                       "débiteurs et paiements, c'est ce qui empêche le match.")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Côté débiteurs** (par colonne candidate)")
                raw_cols = diag.get("raw_iban_columns_sample", {})
                if raw_cols:
                    for col, vals in raw_cols.items():
                        st.markdown(f"`{col}` ({len(vals)} échantillons) :")
                        st.code("\n".join(repr(v) for v in vals), language="text")
                else:
                    st.info("Aucune colonne candidate non vide.")
            with col2:
                st.markdown("**Côté paiements** (`IBAN_EMETT`)")
                raw_pay = diag.get("raw_payments_iban_sample", [])
                if raw_pay:
                    st.code("\n".join(repr(v) for v in raw_pay), language="text")
                else:
                    st.info("Aucun IBAN_EMETT non vide.")

        # Histogramme des longueurs : révèle un préfixe ou une troncature
        with st.expander("Distribution des longueurs d'IBAN (debug format)"):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**Côté débiteurs**")
                st.dataframe(pd.DataFrame(
                    sorted(diag.get("iban_deb_lengths", {}).items()),
                    columns=["Longueur", "N IBAN"]),
                    hide_index=True, use_container_width=True)
            with col2:
                st.markdown("**Côté paiements**")
                st.dataframe(pd.DataFrame(
                    sorted(diag.get("iban_pay_lengths", {}).items()),
                    columns=["Longueur", "N IBAN"]),
                    hide_index=True, use_container_width=True)

        if diag["sample_invoices_orphan"]:
            st.markdown("### Échantillon : factures orphelines")
            st.caption("Le `debtor_id` de ces factures n'existe pas dans "
                       "`debtors_all.csv` (jointure cassée).")
            st.dataframe(pd.DataFrame(diag["sample_invoices_orphan"]),
                         hide_index=True, use_container_width=True)


# =====================================================================
# PAGE 1 — EXECUTIVE SUMMARY
# =====================================================================
if page == "Executive Summary":

    # Hero
    st.markdown(f"""
    <div class="hero">
        <h1>Reconciliation Paiement-Facture par IA</h1>
        <div class="sub">Matching automatique pour le factoring — Architecture 6 couches</div>
        <div class="tags">
            <span class="tag">{data['n_debtors']} debiteurs</span>
            <span class="tag">{data['n_invoices']:,} factures</span>
            <span class="tag">{data['n_payments']:,} paiements</span>
            <span class="tag">12 mois — 2024</span>
            <span class="tag">18 pays</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # KPIs
    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card primary">
            <div class="value">{auto_pct:.1f}%</div>
            <div class="label">Taux d'automatisation</div>
            <div class="sub-val">{auto:,} / {total:,} paiements</div>
        </div>
        <div class="kpi-card success">
            <div class="value" style="color:#10b981">{total:,}</div>
            <div class="label">Paiements traites</div>
            <div class="sub-val">0 erreurs pipeline</div>
        </div>
        <div class="kpi-card warning">
            <div class="value" style="color:#f59e0b">{total_eur/1e6:.1f}M</div>
            <div class="label">Volume (EUR)</div>
            <div class="sub-val">{data['n_invoices']:,} factures</div>
        </div>
        <div class="kpi-card danger">
            <div class="value" style="color:#ef4444">{review_pct:.1f}%</div>
            <div class="label">Revue humaine</div>
            <div class="sub-val">{review:,} en file</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Charts
    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-h">Distribution par couche</div>', unsafe_allow_html=True)
        layer_data = [{"Couche":LAYER_NAMES.get(l,f"C{l}"),"Paiements":c}
                      for l,c in sorted(m.by_layer.items()) if c > 0]
        fig = px.pie(pd.DataFrame(layer_data), values="Paiements", names="Couche",
                     hole=0.45, color="Couche", color_discrete_map=LAYER_COLORS)
        fig.update_traces(textposition="inside", textinfo="percent+label", textfont_size=12)
        fig.update_layout(height=380, showlegend=False, **PLOTLY_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown('<div class="section-h">Evolution mensuelle</div>', unsafe_allow_html=True)
        monthly = df.groupby("month_name").agg(Total=("payment_id","count"),Auto=("matched","sum")).reset_index()
        monthly["month_name"] = pd.Categorical(monthly["month_name"], categories=MONTH_ORDER, ordered=True)
        monthly = monthly.sort_values("month_name")
        monthly["Revue"] = monthly["Total"] - monthly["Auto"]
        fig = go.Figure()
        fig.add_trace(go.Bar(name="Auto", x=monthly["month_name"], y=monthly["Auto"], marker_color=C_GREEN))
        fig.add_trace(go.Bar(name="Revue", x=monthly["month_name"], y=monthly["Revue"], marker_color=C_RED))
        fig.update_layout(barmode="stack", height=380,
                          legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="center",x=0.5),
                          **PLOTLY_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown('<div class="section-h">Top methodes de matching</div>', unsafe_allow_html=True)
    mc = df[df["matched"]].groupby("method").size().reset_index(name="count").sort_values("count",ascending=True).tail(10)
    fig = px.bar(mc, x="count", y="method", orientation="h", color_discrete_sequence=[C_INDIGO])
    fig.update_layout(height=320, xaxis_title="Paiements", yaxis_title="", **PLOTLY_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)


# =====================================================================
# PAGE 2 — ARCHITECTURE
# =====================================================================
elif page == "Architecture":
    st.markdown("""
    <div class="hero">
        <h1>Architecture du Pipeline</h1>
        <div class="sub">6 couches avec early-exit — du deterministe a l'IA generative</div>
    </div>
    """, unsafe_allow_html=True)

    # Pipeline
    st.markdown("""
    <div class="pipeline">
        <div class="pipe" style="background:#0f172a"><div class="lbl">Entree</div><div class="nm">Paiement</div></div>
        <div class="arrow">&#10132;</div>
        <div class="pipe" style="background:#8b5cf6"><div class="lbl">C0</div><div class="nm">Normalisation</div><div class="conf">14 transforms</div></div>
        <div class="arrow">&#10132;</div>
        <div class="pipe" style="background:#10b981"><div class="lbl">C1</div><div class="nm">Exact Match</div><div class="conf">97-100%</div></div>
        <div class="arrow">&#10132;</div>
        <div class="pipe" style="background:#f59e0b;color:#1c1917"><div class="lbl">C2</div><div class="nm">Regles Metier</div><div class="conf">85-99%</div></div>
        <div class="arrow">&#10132;</div>
        <div class="pipe" style="background:#06b6d4"><div class="lbl">C3</div><div class="nm">NLP / Fuzzy</div><div class="conf">75-92%</div></div>
        <div class="arrow">&#10132;</div>
        <div class="pipe" style="background:#8b5cf6"><div class="lbl">C4</div><div class="nm">ML Ensemble</div><div class="conf">42 features</div></div>
        <div class="arrow">&#10132;</div>
        <div class="pipe" style="background:#ec4899"><div class="lbl">C5</div><div class="nm">LLM</div><div class="conf">Claude / GPT</div></div>
        <div class="arrow">&#10132;</div>
        <div class="pipe" style="background:#ef4444"><div class="lbl">C6</div><div class="nm">Humain</div><div class="conf">File priorisee</div></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div class="info-box">
        <div class="icon">i</div>
        <div><b>Early-exit :</b> des qu'une couche trouve un match ≥ 90% de confiance, le paiement est
        cloture. Resultat : <b>{m.avg_processing_time_ms:.1f} ms</b> par paiement en moyenne,
        <b>{data['n_payments']/data['wall_time']:.0f}</b> paiements/seconde.</div>
    </div>
    """, unsafe_allow_html=True)

    for title, content in [
        ("C0 — Preprocessing & Normalisation", "14 transformations : uppercase, deaccentuation, strip ponctuation, parse montants/dates/IBAN, expand abreviations, detection langue, extraction signaux (refs, montants, periodes, mots-cles)."),
        ("C1 — Matching Exact (97-100%)", "7 regles : reference exacte, ISO 20022 SEPA, hash index multi-format, IBAN+montant unique, solde total debiteur, PO, BL/CMR. Precision ~100%, < 2ms."),
        ("C2 — Regles Metier (85-99%)", "12 tolerances montant (SWIFT fees, escompte, arrondi, retention BTP, RFA, WHT), subset sum multi-factures, avoirs, acomptes 30/50/70%, patterns temporels, anti-doublons."),
        ("C3 — NLP & Fuzzy (75-92%)", "8 algorithmes fuzzy (Levenshtein, Jaro-Winkler, Token Sort/Set, Partial, N-gram, LCS, Numeric Ref), NER custom 10 entites, TF-IDF, embeddings semantiques."),
        ("C4 — Machine Learning (80-95%)", "42 features (Amount/Reference/Temporal/Behavioral), ensemble LightGBM+XGBoost+RF, LambdaRank, Active Learning, detection drift PSI."),
        ("C5 — LLM & IA Generative", "Prompts optimises (generique/cryptique/ambigu), validation anti-hallucination 5 controles, cache, Claude + GPT."),
        ("C6 — Revue Humaine", "File priorisee (montant 30%, anciennete 25%, gap confiance 25%, risque 20%). Feedback structure → boucle retraining C4."),
    ]:
        with st.expander(f"**{title}**"):
            st.markdown(content)


# =====================================================================
# PAGE — FACTURES (toutes les factures avec contenu complet)
# =====================================================================
elif page == "Factures":
    st.markdown("""
    <div class="hero">
        <h1>Portefeuille Factures</h1>
        <div class="sub">Toutes les factures ouvertes avec leur contenu complet</div>
    </div>
    """, unsafe_allow_html=True)

    invoices = data["invoices"]

    # Build invoice DataFrame
    inv_rows = []
    for inv in invoices:
        inv_rows.append({
            "ID": inv.id, "Reference": inv.reference, "Debiteur": inv.debtor_id,
            "Montant TTC": inv.amount, "Montant HT": inv.amount_ht,
            "Devise": inv.currency.value, "Date emission": inv.issue_date,
            "Date echeance": inv.due_date, "PO": inv.po_number or "",
            "BL": inv.bl_number or "", "Statut": inv.status,
            "Lot": str(inv.batch_date) if inv.batch_date else "",
        })
    inv_df = pd.DataFrame(inv_rows)

    # KPIs
    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card success">
            <div class="value" style="color:{C_GREEN}">{len(invoices):,}</div>
            <div class="label">Factures</div>
        </div>
        <div class="kpi-card">
            <div class="value">{inv_df['Montant TTC'].sum()/1e6:.1f}M</div>
            <div class="label">Volume TTC</div>
        </div>
        <div class="kpi-card">
            <div class="value">{inv_df['Debiteur'].nunique()}</div>
            <div class="label">Debiteurs</div>
        </div>
        <div class="kpi-card">
            <div class="value">{len([i for i in invoices if i.po_number])}</div>
            <div class="label">Avec PO</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        deb_filter = st.multiselect("Debiteur", sorted(inv_df["Debiteur"].unique()), key="inv_deb")
    with col2:
        min_amt, max_amt = float(inv_df["Montant TTC"].min()), float(inv_df["Montant TTC"].max())
        amt_range = st.slider("Montant TTC", min_amt, max_amt, (min_amt, max_amt), key="inv_amt")
    with col3:
        has_po = st.checkbox("Avec PO uniquement", key="inv_po")

    show = inv_df.copy()
    if deb_filter: show = show[show["Debiteur"].isin(deb_filter)]
    show = show[(show["Montant TTC"] >= amt_range[0]) & (show["Montant TTC"] <= amt_range[1])]
    if has_po: show = show[show["PO"] != ""]

    st.markdown(f'<div class="section-h">{len(show):,} factures</div>', unsafe_allow_html=True)

    display = show.copy()
    display["Montant TTC"] = display["Montant TTC"].apply(lambda x: f"{x:,.2f}")
    display["Montant HT"] = display["Montant HT"].apply(lambda x: f"{x:,.2f}")
    st.dataframe(display, use_container_width=True, height=600, hide_index=True)


# =====================================================================
# PAGE — PAIEMENTS (tous les paiements avec contenu complet)
# =====================================================================
elif page == "Paiements":
    st.markdown("""
    <div class="hero">
        <h1>Flux Paiements</h1>
        <div class="sub">Tous les paiements recus avec leur libelle complet et leur statut</div>
    </div>
    """, unsafe_allow_html=True)

    # KPIs
    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card primary">
            <div class="value">{len(df):,}</div>
            <div class="label">Paiements</div>
        </div>
        <div class="kpi-card success">
            <div class="value">{df['matched'].sum():,}</div>
            <div class="label">Reconcilies</div>
        </div>
        <div class="kpi-card danger">
            <div class="value">{(~df['matched']).sum():,}</div>
            <div class="label">Non reconcilies</div>
        </div>
        <div class="kpi-card">
            <div class="value">{df['amount'].sum()/1e6:.1f}M</div>
            <div class="label">Volume EUR</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        status_filter = st.radio("Statut", ["Tous", "Reconcilies", "Non reconcilies"], horizontal=True, key="pay_status")
    with col2:
        pay_deb = st.multiselect("Debiteur", sorted(df["debtor_name"].unique()), key="pay_deb")
    with col3:
        pay_country = st.multiselect("Pays", sorted(df["country"].unique()), key="pay_country")

    show = df.copy()
    if status_filter == "Reconcilies": show = show[show["matched"]]
    elif status_filter == "Non reconcilies": show = show[~show["matched"]]
    if pay_deb: show = show[show["debtor_name"].isin(pay_deb)]
    if pay_country: show = show[show["country"].isin(pay_country)]

    st.markdown(f'<div class="section-h">{len(show):,} paiements</div>', unsafe_allow_html=True)

    display = show[["payment_id","date","amount","debtor_name","country","label",
                     "layer_name","method","confidence","flags","invoices_matched"]].copy()
    display["amount"] = display["amount"].apply(lambda x: f"{x:,.2f}")
    display["confidence"] = display["confidence"].apply(lambda x: f"{x:.0%}" if x > 0 else "---")
    display.columns = ["ID","Date","Montant","Debiteur","Pays","Libelle complet",
                        "Couche","Methode","Conf.","Flags","Factures matchees"]
    st.dataframe(display, use_container_width=True, height=600, hide_index=True)


# =====================================================================
# PAGE — SIMULATION LIVE
# =====================================================================
elif page == "Simulation Live":
    st.markdown("""
    <div class="hero">
        <h1>Simulation Live</h1>
        <div class="sub">Tous les paiements traites avec filtres interactifs</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns(3)
    with col1:
        layer_filter = st.multiselect("Couche", ["C1","C2","C3","C6"], default=["C1","C2","C3","C6"])
    with col2:
        debtor_filter = st.multiselect("Debiteur", sorted(df["debtor_name"].unique()), default=[])
    with col3:
        conf_range = st.slider("Confiance", 0.0, 1.0, (0.0, 1.0), 0.05)

    mask = df["layer_name"].isin(layer_filter)
    if debtor_filter: mask &= df["debtor_name"].isin(debtor_filter)
    mask &= df["confidence"].between(conf_range[0], conf_range[1])
    filtered = df[mask]

    st.markdown(f"""
    <div class="info-box">
        <div class="icon">#</div>
        <div><b>{len(filtered):,}</b> paiements affiches sur <b>{len(df):,}</b> total</div>
    </div>
    """, unsafe_allow_html=True)

    display_cols = ["payment_id","date","amount","debtor_name","label","layer_name","method","confidence","flags","invoices_matched"]
    ddf = filtered[display_cols].head(500).copy()
    ddf["amount"] = ddf["amount"].apply(lambda x: f"{x:,.2f}")
    ddf["confidence"] = ddf["confidence"].apply(lambda x: f"{x:.0%}" if x > 0 else "—")
    ddf.columns = ["ID","Date","Montant","Debiteur","Libelle","Couche","Methode","Conf.","Flags","Factures"]

    def color_layer(val):
        return {"C1":"background-color:#d1fae5","C2":"background-color:#fef3c7",
                "C3":"background-color:#cffafe","C6":"background-color:#fee2e2"}.get(val,"")

    st.dataframe(ddf.style.applymap(color_layer, subset=["Couche"]),
                 use_container_width=True, height=500)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-h">Methodes (filtre actif)</div>', unsafe_allow_html=True)
        mdf = filtered.groupby("method").size().reset_index(name="count").sort_values("count",ascending=False)
        fig = px.bar(mdf.head(10), x="method", y="count", color_discrete_sequence=[C_INDIGO])
        fig.update_layout(height=300, xaxis_title="", yaxis_title="", **PLOTLY_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.markdown('<div class="section-h">Distribution confiances</div>', unsafe_allow_html=True)
        matched = filtered[filtered["confidence"] > 0]
        if not matched.empty:
            fig = px.histogram(matched, x="confidence", nbins=25, color_discrete_sequence=[C_GREEN])
            fig.update_layout(height=300, xaxis_title="Confiance", yaxis_title="", **PLOTLY_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)


# =====================================================================
# PAGE 4 — ANALYSE DEBITEURS
# =====================================================================
elif page == "Analyse Debiteurs":
    st.markdown("""
    <div class="hero">
        <h1>Analyse par Debiteur</h1>
        <div class="sub">Performance de reconciliation par debiteur et par pays</div>
    </div>
    """, unsafe_allow_html=True)

    ds = df.groupby(["debtor_id","debtor_name","country","sector"]).agg(
        total=("payment_id","count"), auto=("matched","sum"),
        montant=("amount","sum"), conf=("confidence","mean")).reset_index()
    ds["revue"] = ds["total"] - ds["auto"]
    ds["taux"] = (ds["auto"]/ds["total"]*100).round(1)
    ds = ds.sort_values("taux", ascending=False)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown('<div class="section-h">Taux par debiteur</div>', unsafe_allow_html=True)
        fig = px.bar(ds.sort_values("taux"), x="taux", y="debtor_name", orientation="h",
                     color="taux", color_continuous_scale=[C_RED,C_YELLOW,C_GREEN], range_color=[0,100], text="taux")
        fig.update_traces(texttemplate="%{text:.0f}%", textposition="outside")
        fig.add_vline(x=90, line_dash="dash", line_color="gray", annotation_text="Seuil 90%")
        fig.update_layout(height=max(400, len(ds)*22), coloraxis_showscale=False,
                          xaxis_title="Taux (%)", yaxis_title="", **PLOTLY_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown('<div class="section-h">Performance par pays</div>', unsafe_allow_html=True)
        cs = df.groupby("country").agg(total=("payment_id","count"),auto=("matched","sum")).reset_index()
        cs["taux"] = (cs["auto"]/cs["total"]*100).round(1)
        fig = px.scatter(cs, x="total", y="taux", size="total", color="taux", text="country",
                        color_continuous_scale=[C_RED,C_YELLOW,C_GREEN], range_color=[0,100], size_max=50)
        fig.update_traces(textposition="top center", textfont_size=11)
        fig.update_layout(height=450, coloraxis_showscale=False,
                          xaxis_title="Paiements", yaxis_title="Taux auto (%)", **PLOTLY_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)

    # Heatmap
    st.markdown('<div class="section-h">Matrice debiteur x couche</div>', unsafe_allow_html=True)
    cross = pd.crosstab(df["debtor_name"], df["layer_name"])
    for c in ["C1","C2","C3","C6"]:
        if c not in cross.columns: cross[c] = 0
    cross = cross[["C1","C2","C3","C6"]]
    fig = px.imshow(cross, color_continuous_scale=["#f8fafc","#1e40af"],
                    labels=dict(x="Couche",y="Debiteur",color="Paiements"), text_auto=True, aspect="auto")
    fig.update_layout(height=max(400, len(cross)*20), **PLOTLY_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)

    # Debtor drill-down
    st.markdown('<div class="section-h">Profil debiteur</div>', unsafe_allow_html=True)
    sel = st.selectbox("Selectionner", sorted(df["debtor_name"].unique()))
    ddf = df[df["debtor_name"] == sel]
    di = data["df_debtors"][data["df_debtors"]["name"] == sel]
    if not di.empty:
        di = di.iloc[0]
        d_rate = ddf["matched"].sum() / len(ddf) * 100 if len(ddf) > 0 else 0
        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi-card"><div class="value">{di['country']}</div><div class="label">Pays</div></div>
            <div class="kpi-card"><div class="value">{di['sector']}</div><div class="label">Secteur</div></div>
            <div class="kpi-card"><div class="value">{di['terms']}j</div><div class="label">Delai paiement</div></div>
            <div class="kpi-card {'success' if d_rate>=80 else 'warning' if d_rate>=50 else 'danger'}">
                <div class="value">{d_rate:.0f}%</div><div class="label">Taux auto</div></div>
        </div>
        """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        dl = ddf.groupby("layer_name").size().reset_index(name="count")
        fig = px.pie(dl, values="count", names="layer_name", hole=0.4,
                     color="layer_name", color_discrete_map={"C1":C_GREEN,"C2":C_YELLOW,"C3":C_CYAN,"C6":C_RED})
        fig.update_layout(height=300, **PLOTLY_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        recent = ddf.tail(10)[["payment_id","date","amount","method","confidence","flags"]].copy()
        recent["amount"] = recent["amount"].apply(lambda x: f"{x:,.2f}")
        recent["confidence"] = recent["confidence"].apply(lambda x: f"{x:.0%}" if x>0 else "—")
        st.dataframe(recent, use_container_width=True, hide_index=True)


# =====================================================================
# PAGE 5 — PAIEMENTS PAR COUCHE (deep dive de chaque couche)
# =====================================================================
elif page == "Paiements par Couche":
    st.markdown("""
    <div class="hero">
        <h1>Paiements par Couche</h1>
        <div class="sub">Explorez tous les paiements attribues a chaque couche du pipeline</div>
    </div>
    """, unsafe_allow_html=True)

    # Layer selector
    selected_layer = st.selectbox("Selectionner une couche", ["C1", "C2", "C3", "C6"],
        format_func=lambda x: {"C1":"C1 — Matching Exact & Deterministe",
                                "C2":"C2 — Regles Metier Avancees",
                                "C3":"C3 — NLP / Fuzzy Matching",
                                "C6":"C6 — Revue Humaine (non attribues)"}.get(x, x))

    layer_df = df[df["layer_name"] == selected_layer]
    layer_count = len(layer_df)
    layer_pct = layer_count / len(df) * 100

    # KPIs for this layer
    badge_color = {"C1":C_GREEN,"C2":C_YELLOW,"C3":C_CYAN,"C6":C_RED}.get(selected_layer, C_INDIGO)
    avg_conf = layer_df["confidence"].mean() if layer_count > 0 else 0

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card" style="border-bottom:3px solid {badge_color}">
            <div class="value" style="color:{badge_color}">{layer_count:,}</div>
            <div class="label">Paiements {selected_layer}</div>
        </div>
        <div class="kpi-card">
            <div class="value">{layer_pct:.1f}%</div>
            <div class="label">du total</div>
        </div>
        <div class="kpi-card">
            <div class="value">{avg_conf:.0%}</div>
            <div class="label">Confiance moyenne</div>
        </div>
        <div class="kpi-card">
            <div class="value">{layer_df['amount'].sum()/1e6:.1f}M</div>
            <div class="label">Volume EUR</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Methods breakdown for this layer
    if selected_layer != "C6":
        st.markdown('<div class="section-h">Methodes utilisees</div>', unsafe_allow_html=True)
        meth = layer_df.groupby("method").size().reset_index(name="count").sort_values("count", ascending=False)
        fig = px.bar(meth, x="method", y="count", color_discrete_sequence=[badge_color])
        fig.update_layout(height=300, xaxis_title="", yaxis_title="Paiements", **PLOTLY_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)

    # Flags breakdown
    if selected_layer in ("C2", "C3"):
        all_flags = []
        for f in layer_df["flags"].dropna():
            if f:
                all_flags.extend([x.strip() for x in f.split(",")])
        if all_flags:
            st.markdown('<div class="section-h">Flags detectes</div>', unsafe_allow_html=True)
            flag_counts = pd.Series(all_flags).value_counts().reset_index()
            flag_counts.columns = ["flag", "count"]
            fig = px.bar(flag_counts.head(15), x="flag", y="count", color_discrete_sequence=[C_YELLOW])
            fig.update_layout(height=280, xaxis_title="", yaxis_title="", **PLOTLY_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)

    # Full table
    st.markdown(f'<div class="section-h">Tous les paiements {selected_layer} ({layer_count:,})</div>',
                unsafe_allow_html=True)

    display_cols = ["payment_id","date","amount","debtor_name","label","method","confidence","flags","invoices_matched"]
    show_df = layer_df[display_cols].copy()
    show_df["amount"] = show_df["amount"].apply(lambda x: f"{x:,.2f}")
    show_df["confidence"] = show_df["confidence"].apply(lambda x: f"{x:.0%}" if x > 0 else "---")
    show_df.columns = ["ID","Date","Montant","Debiteur","Libelle","Methode","Conf.","Flags","Factures matchees"]

    st.dataframe(show_df, use_container_width=True, height=600, hide_index=True)

    # Click to deep-dive
    st.markdown('<div class="section-h">Deep dive un paiement</div>', unsafe_allow_html=True)
    if layer_count > 0:
        sel = st.selectbox("Choisir un paiement", layer_df["payment_id"].tolist()[:200])
        row = df[df["payment_id"] == sel].iloc[0]
        ctx = next((r for r in data["results"] if r.payment.id == sel), None)

        col1, col2 = st.columns([2, 1])
        with col1:
            st.markdown(f"""
            <div class="deep-card">
                <div class="deep-meta">
                    <span><b>Montant :</b> {row['amount']:,.2f} EUR</span>
                    <span><b>Date :</b> {row['date']}</span>
                    <span><b>Debiteur :</b> {_esc(str(row['debtor_name']))}</span>
                </div>
                <div class="deep-label"><b>Libelle :</b><br><code>{_esc(row['label']) if row['label'] else '(vide)'}</code></div>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            badge_cls = {"C1":"c1","C2":"c2","C3":"c3","C6":"c6"}.get(row["layer_name"],"c6")
            conf = f"{row['confidence']:.0%}" if row["confidence"] > 0 else "---"
            st.markdown(f"""
            <div style="background:{badge_color}; color:white; padding:20px; border-radius:14px;
                        text-align:center; margin-top:8px;">
                <div style="font-size:2rem; font-weight:800;">{row['layer_name']}</div>
                <div style="font-size:1.2rem;">{conf}</div>
                <div style="font-size:0.8rem; opacity:0.8; margin-top:4px;">{row['method']}</div>
            </div>
            """, unsafe_allow_html=True)

        if ctx:
            steps_html = ""
            for log in ctx.processing_log:
                layer_n = log.get("layer","?")
                event = log.get("event","")
                t = log.get("time_ms", 0)
                conf_log = log.get("confidence", 0)
                method_log = log.get("method","")
                if event == "PREPROCESSED":
                    steps_html += f'<div class="step step-pre"><b>C0</b> Preprocessing <span class="time">{t:.1f}ms</span></div>'
                elif event == "MATCH_FOUND":
                    steps_html += (f'<div class="step step-match"><b>C{layer_n}</b> '
                        f'<b>MATCH</b> <span class="badge" style="background:#667eea;padding:2px 10px;font-size:0.75rem;color:white;">{method_log}</span>'
                        f' confiance <b>{conf_log:.0%}</b> <span class="time">{t:.1f}ms</span></div>')
                elif event == "NO_MATCH":
                    steps_html += f'<div class="step step-no"><b>C{layer_n}</b> Pas de match <span class="time">{t:.1f}ms</span></div>'
            st.markdown(steps_html, unsafe_allow_html=True)

        if row["matched"]:
            st.markdown(f'<div class="result-box result-ok"><b>Factures :</b> {_esc(str(row["invoices_matched"]))}</div>', unsafe_allow_html=True)
            if row["flags"]:
                st.markdown(f'<div class="result-box result-flags"><b>Flags :</b> {_esc(str(row["flags"]))}</div>', unsafe_allow_html=True)


# =====================================================================
# PAGE 6 — REVUE HUMAINE (non attribues + recommandations)
# =====================================================================
elif page == "Revue Humaine":
    st.markdown("""
    <div class="hero">
        <h1>Revue Humaine — Paiements Non Attribues</h1>
        <div class="sub">Paiements que le pipeline n'a pas pu reconcilier automatiquement, avec recommandations</div>
    </div>
    """, unsafe_allow_html=True)

    c6_df = df[df["layer_name"] == "C6"]
    n_c6 = len(c6_df)

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card danger">
            <div class="value" style="color:var(--red)">{n_c6:,}</div>
            <div class="label">Paiements en revue humaine</div>
        </div>
        <div class="kpi-card">
            <div class="value">{n_c6/len(df)*100:.1f}%</div>
            <div class="label">du total</div>
        </div>
        <div class="kpi-card">
            <div class="value">{c6_df['amount'].sum()/1e6:.1f}M</div>
            <div class="label">Volume bloque</div>
        </div>
        <div class="kpi-card">
            <div class="value">{c6_df['debtor_name'].nunique()}</div>
            <div class="label">Debiteurs concernes</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Reason analysis
    st.markdown('<div class="section-h">Pourquoi ces paiements n\'ont pas ete matches</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="info-box">
        <div class="icon">?</div>
        <div>
            <b>Raisons typiques :</b> Label cryptique sans reference, montant ne correspondant a aucune facture,
            reference severement deformee (> 3 mutations), debiteur non identifie, combinaison trop complexe,
            ou couches C4 (ML) / C5 (LLM) inactives (pas de modele entraine / pas de cle API).
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Compute recommendations: prefer C4 ML rankings, fallback to heuristic
    # C4 rankings are in ctx.ml_rankings for each payment that went through C4
    ml_rankings_by_pid = {}
    for ctx in data["results"]:
        if ctx.ml_rankings:
            ml_rankings_by_pid[ctx.payment.id] = ctx.ml_rankings

    has_ml = len(ml_rankings_by_pid) > 0
    if has_ml:
        st.markdown(f"""
        <div class="info-box">
            <div class="icon" style="background:#8b5cf6">ML</div>
            <div><b>Recommandations alimentees par C4 ML</b> — l'ensemble LightGBM + XGBoost + RF
            a score chaque candidat sur 42 features (montant, reference fuzzy, temporel, comportement debiteur).
            Les scores ML sont affiches en <span style="color:#8b5cf6; font-weight:700;">violet</span>.</div>
        </div>
        """, unsafe_allow_html=True)

    @st.cache_data
    def compute_recommendations(df_c6, _invoices, _ground_truth, _ml_rankings):
        from collections import defaultdict as _dd
        inv_by_d = _dd(list)
        for inv in _invoices:
            inv_by_d[inv.debtor_id].append(inv)

        recs = {}
        for _, r in df_c6.iterrows():
            pid = r["payment_id"]
            true_ref = _ground_truth.get(pid, "")

            # Prefer C4 ML rankings when available (new enriched format)
            ml_rank = _ml_rankings.get(pid)
            if ml_rank:
                candidates = []
                for mr in ml_rank:
                    inv = mr["invoice"]
                    proba = mr.get("proba", 0)
                    composite = mr.get("composite", proba)
                    # Use ML-provided reasons if available, else build from proba
                    ml_reasons = mr.get("reasons", [])
                    reason_str = " | ".join(ml_reasons) if ml_reasons else f"ML proba {proba:.0%}"
                    candidates.append({
                        "ref": inv.reference, "amount": inv.amount,
                        "score": composite,  # composite = ML 60% + heuristic 40%
                        "proba": proba,      # raw ML probability
                        "reason": reason_str,
                        "is_true": inv.reference == true_ref,
                        "source": "ML",
                    })
                recs[pid] = candidates[:5]
                continue

            # Fallback: heuristic scoring
            search = inv_by_d.get(r["debtor_id"], _invoices[:50])
            candidates = []
            for inv in search:
                score, reasons = 0.0, []
                if inv.amount > 0:
                    dp = abs(r["amount"] - inv.amount) / inv.amount
                    if dp < 0.001: score += 0.40; reasons.append("montant exact")
                    elif dp < 0.05: score += 0.30; reasons.append(f"ecart {dp:.1%}")
                    elif dp < 0.15: score += 0.15; reasons.append(f"ecart {dp:.0%}")
                if inv.debtor_id == r["debtor_id"]: score += 0.25; reasons.append("meme debiteur")
                if r["date"] and inv.due_date:
                    dd = abs((r["date"] - inv.due_date).days)
                    if dd <= 7: score += 0.20; reasons.append(f"+{dd}j")
                    elif dd <= 30: score += 0.12; reasons.append(f"+{dd}j")
                if inv.amount_ht > 0 and abs(r["amount"] - inv.amount_ht) / inv.amount_ht < 0.01:
                    score += 0.15; reasons.append("montant HT")
                if score > 0.1:
                    candidates.append({"ref": inv.reference, "amount": inv.amount,
                        "score": min(score, 1.0), "reason": " | ".join(reasons[:3]),
                        "is_true": inv.reference == true_ref, "source": "heuristic"})
            candidates.sort(key=lambda x: -x["score"])
            recs[pid] = candidates[:5]
        return recs

    ground_truth = data.get("ground_truth", {})
    recommendations = compute_recommendations(c6_df, data["invoices"], ground_truth, ml_rankings_by_pid)

    # Filter
    col1, col2 = st.columns(2)
    with col1:
        debtor_filter = st.multiselect("Filtrer par debiteur", sorted(c6_df["debtor_name"].unique()))
    with col2:
        sort_by = st.selectbox("Trier par", ["Montant (desc)", "Date (recent)", "Debiteur"])

    filtered_c6 = c6_df.copy()
    if debtor_filter:
        filtered_c6 = filtered_c6[filtered_c6["debtor_name"].isin(debtor_filter)]
    if sort_by == "Montant (desc)":
        filtered_c6 = filtered_c6.sort_values("amount", ascending=False)
    elif sort_by == "Date (recent)":
        filtered_c6 = filtered_c6.sort_values("date", ascending=False)
    else:
        filtered_c6 = filtered_c6.sort_values("debtor_name")

    st.markdown(f'<div class="section-h">{len(filtered_c6):,} paiements non attribues</div>',
                unsafe_allow_html=True)

    # Paginated display with recommendations
    page_size = 20
    n_pages = max(1, (len(filtered_c6) + page_size - 1) // page_size)
    page_num = st.number_input("Page", min_value=1, max_value=n_pages, value=1) - 1
    page_slice = filtered_c6.iloc[page_num * page_size : (page_num + 1) * page_size]

    for _, row in page_slice.iterrows():
        pid = row["payment_id"]
        recs = recommendations.get(pid, [])
        label_esc = _esc(row["label"]) if row["label"] else "(vide)"

        # Payment card
        has_true = any(r["is_true"] for r in recs)
        border_color = C_GREEN if has_true else "#e2e8f0"

        st.markdown(f"""
        <div class="deep-card" style="border-left:4px solid {border_color};">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                <code style="font-size:0.9rem; font-weight:700;">{pid}</code>
                <span style="font-size:1.1rem; font-weight:700;">{row['amount']:,.2f} EUR</span>
                <span style="color:var(--slate); font-size:0.85rem;">{row['date']}</span>
                <span style="color:var(--slate); font-size:0.85rem;">{_esc(str(row['debtor_name']))}</span>
            </div>
            <div class="deep-label"><code>{label_esc[:100]}</code></div>
        </div>
        """, unsafe_allow_html=True)

        # Recommendations
        if recs:
            source = recs[0].get("source", "heuristic")
            source_badge = ('<span style="background:#8b5cf6;color:white;padding:2px 8px;border-radius:4px;'
                           'font-size:0.68rem;font-weight:600;margin-left:8px;">C4 ML</span>'
                           if source == "ML" else
                           '<span style="background:#64748b;color:white;padding:2px 8px;border-radius:4px;'
                           'font-size:0.68rem;font-weight:600;margin-left:8px;">Heuristique</span>')
            st.markdown(f'<div style="font-size:0.78rem;color:var(--slate);padding-left:20px;margin-bottom:4px;">'
                        f'<b>Top {len(recs)} recommandations</b>{source_badge}</div>', unsafe_allow_html=True)

            for i, rec in enumerate(recs):
                is_true = rec.get("is_true", False)
                is_ml = rec.get("source") == "ML"
                bg = "#ecfdf5" if is_true else ("#f5f3ff" if is_ml else "#f8fafc")
                border = "2px solid #10b981" if is_true else ("1px solid #c4b5fd" if is_ml else "1px solid #e2e8f0")
                score = rec["score"]
                bar_w = int(min(score, 1.0) * 100)
                if is_true:
                    bar_color = "linear-gradient(90deg,#10b981,#34d399)"
                elif is_ml:
                    bar_color = "linear-gradient(90deg,#8b5cf6,#a78bfa)"
                else:
                    bar_color = "linear-gradient(90deg,#667eea,#8b5cf6)"
                check = ('<span style="background:#10b981;color:white;padding:2px 8px;border-radius:4px;'
                         'font-size:0.72rem;font-weight:700;margin-left:6px;">VRAIE FACTURE</span>' if is_true else "")
                ref_style = "font-weight:700;color:#065f46;" if is_true else ""
                score_color = "#8b5cf6" if is_ml else "#667eea"
                # Show both composite and ML proba for ML-sourced recs
                proba_str = ""
                if is_ml and "proba" in rec:
                    proba_str = (f'<span style="font-size:0.7rem;color:#8b5cf6;background:#f5f3ff;'
                                 f'padding:1px 6px;border-radius:3px;margin-left:4px;">'
                                 f'ML {rec["proba"]:.0%}</span>')
                st.markdown(f"""
                <div style="display:grid; grid-template-columns:28px 1fr 90px 70px 50px; gap:8px; align-items:center;
                            padding:6px 12px; margin:3px 0 3px 20px; background:{bg}; border:{border}; border-radius:8px; font-size:0.82rem;">
                    <span style="font-weight:800; color:{score_color};">#{i+1}</span>
                    <span style="font-family:monospace; {ref_style}">{_esc(str(rec['ref']))}{check}{proba_str}</span>
                    <span style="text-align:right; font-variant-numeric:tabular-nums;">{rec['amount']:,.2f}</span>
                    <span style="height:10px; background:#e2e8f0; border-radius:5px; overflow:hidden;">
                        <span style="display:block; height:100%; width:{bar_w}%; background:{bar_color}; border-radius:5px;"></span>
                    </span>
                    <span style="font-weight:700; color:{score_color}; text-align:right;">{score:.0%}</span>
                </div>
                <div style="font-size:0.72rem; color:#64748b; font-style:italic; padding-left:52px; margin-bottom:2px;">{_esc(str(rec['reason']))}</div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#94a3b8; font-style:italic; padding-left:20px; margin-bottom:8px; font-size:0.85rem;">Aucun candidat identifie</div>', unsafe_allow_html=True)

    st.caption(f"Page {page_num + 1} / {n_pages} ({len(filtered_c6):,} paiements)")


# =====================================================================
# PAGE — MAPPING COMPLET (paiement ↔ facture avec tout le detail)
# =====================================================================
elif page == "Mapping Complet":
    st.markdown("""
    <div class="hero">
        <h1>Mapping Complet Paiement-Facture</h1>
        <div class="sub">Vue exhaustive de chaque reconciliation : paiement, facture(s) matchee(s), methode, allocation</div>
    </div>
    """, unsafe_allow_html=True)

    # Build full mapping table
    inv_lookup = {inv.reference: inv for inv in data["invoices"]}
    ground_truth = data.get("ground_truth", {})

    mapping_rows = []
    for ctx in data["results"]:
        p = ctx.payment
        fm = ctx.final_match
        if fm:
            for inv in fm.invoices:
                alloc = fm.allocated.get(inv.reference, 0)
                mapping_rows.append({
                    "Paiement": p.id,
                    "Date paiement": p.date,
                    "Montant paye": p.amount,
                    "Libelle": p.label_raw[:80] if p.label_raw else "",
                    "Debiteur": p.debtor.name[:25] if p.debtor else p.debtor_id,
                    "Pays": p.debtor.country if p.debtor else "",
                    "Facture": inv.reference,
                    "Montant facture": inv.amount,
                    "Montant HT": inv.amount_ht,
                    "Date emission": inv.issue_date,
                    "Date echeance": inv.due_date,
                    "PO": inv.po_number or "",
                    "BL": inv.bl_number or "",
                    "Allocation": alloc,
                    "Ecart": round(p.amount - sum(fm.allocated.values()), 2) if len(fm.invoices) == 1 else 0,
                    "Couche": f"C{fm.layer}",
                    "Methode": fm.method.value,
                    "Confiance": fm.confidence,
                    "Flags": ", ".join(fm.flags) if fm.flags else "",
                    "Nb factures": len(fm.invoices),
                    "Statut": "AUTO",
                })
        else:
            # Non-reconcilie
            true_ref = ground_truth.get(p.id, "")
            mapping_rows.append({
                "Paiement": p.id,
                "Date paiement": p.date,
                "Montant paye": p.amount,
                "Libelle": p.label_raw[:80] if p.label_raw else "",
                "Debiteur": p.debtor.name[:25] if p.debtor else p.debtor_id,
                "Pays": p.debtor.country if p.debtor else "",
                "Facture": true_ref if true_ref else "---",
                "Montant facture": inv_lookup[true_ref].amount if true_ref and true_ref in inv_lookup else 0,
                "Montant HT": inv_lookup[true_ref].amount_ht if true_ref and true_ref in inv_lookup else 0,
                "Date emission": inv_lookup[true_ref].issue_date if true_ref and true_ref in inv_lookup else None,
                "Date echeance": inv_lookup[true_ref].due_date if true_ref and true_ref in inv_lookup else None,
                "PO": "", "BL": "",
                "Allocation": 0,
                "Ecart": 0,
                "Couche": "C6",
                "Methode": "HUMAN_REVIEW",
                "Confiance": 0,
                "Flags": "",
                "Nb factures": 0,
                "Statut": "REVUE HUMAINE",
            })

    map_df = pd.DataFrame(mapping_rows)

    # KPIs
    auto_map = map_df[map_df["Statut"] == "AUTO"]
    c6_map = map_df[map_df["Statut"] == "REVUE HUMAINE"]

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi-card primary">
            <div class="value">{len(map_df):,}</div>
            <div class="label">Lignes de mapping</div>
        </div>
        <div class="kpi-card success">
            <div class="value">{len(auto_map):,}</div>
            <div class="label">Reconciliations auto</div>
        </div>
        <div class="kpi-card danger">
            <div class="value">{len(c6_map):,}</div>
            <div class="label">En attente</div>
        </div>
        <div class="kpi-card">
            <div class="value">{auto_map['Allocation'].sum()/1e6:.1f}M</div>
            <div class="label">Montant alloue</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        map_status = st.radio("Statut", ["Tous", "AUTO", "REVUE HUMAINE"], horizontal=True, key="map_st")
    with col2:
        map_layer = st.multiselect("Couche", sorted(map_df["Couche"].unique()), key="map_layer")
    with col3:
        map_method = st.multiselect("Methode", sorted(map_df["Methode"].unique()), key="map_method")

    show = map_df.copy()
    if map_status != "Tous": show = show[show["Statut"] == map_status]
    if map_layer: show = show[show["Couche"].isin(map_layer)]
    if map_method: show = show[show["Methode"].isin(map_method)]

    st.markdown(f'<div class="section-h">{len(show):,} lignes de mapping</div>', unsafe_allow_html=True)

    # Format display
    display = show.copy()
    display["Montant paye"] = display["Montant paye"].apply(lambda x: f"{x:,.2f}")
    display["Montant facture"] = display["Montant facture"].apply(lambda x: f"{x:,.2f}" if x else "---")
    display["Montant HT"] = display["Montant HT"].apply(lambda x: f"{x:,.2f}" if x else "---")
    display["Allocation"] = display["Allocation"].apply(lambda x: f"{x:,.2f}" if x else "---")
    display["Confiance"] = display["Confiance"].apply(lambda x: f"{x:.0%}" if x > 0 else "---")

    def color_status(val):
        if val == "AUTO": return "background-color: #d1fae5; color: #065f46"
        if val == "REVUE HUMAINE": return "background-color: #fee2e2; color: #991b1b"
        return ""

    st.dataframe(
        display.style.applymap(color_status, subset=["Statut"]),
        use_container_width=True, height=600, hide_index=True,
    )

    # Export
    st.markdown('<div class="section-h">Export</div>', unsafe_allow_html=True)
    csv = show.to_csv(index=False)
    st.download_button("Telecharger le mapping complet (CSV)", csv, "mapping_complet.csv", "text/csv")


# =====================================================================
# PAGE — PROFILS DEBITEURS IA
# =====================================================================
elif page == "Profils Debiteurs IA":
    st.markdown("""
    <div class="hero">
        <h1>Profils Debiteurs IA</h1>
        <div class="sub">Comportements appris automatiquement par debiteur : timing, montants, methodes, anomalies</div>
    </div>
    """, unsafe_allow_html=True)

    profiles = data.get("debtor_profiles", {})

    if not profiles:
        st.warning("Aucun profil disponible. Les profils sont appris lors de la simulation.")
    else:
        st.markdown(f"""
        <div class="info-box">
            <div class="icon" style="background:#8b5cf6">AI</div>
            <div><b>{len(profiles)} profils appris</b> a partir du premier tiers des paiements.
            Chaque profil capture : jour de paiement typique, delai moyen, montant habituel,
            methode preferee, tendance multi-factures, et taux d'automatisation.</div>
        </div>
        """, unsafe_allow_html=True)

        # Summary table
        prof_rows = []
        for did, p in sorted(profiles.items()):
            prof_rows.append({
                "Debiteur": p["debtor_name"][:30] if p["debtor_name"] else did,
                "Paiements": p["n_payments"],
                "Montant moy.": f"{p['avg_amount']:,.0f}",
                "Delai moy.": f"{p['avg_delay_days']}j",
                "Jours typiques": ", ".join(str(d) for d in p["typical_pay_days"]) or "variable",
                "Regularite": f"{p['pay_day_regularity']*100:.0f}%",
                "Inv./paiement": f"{p['avg_invoices_per_payment']}",
                "Multi-fact.": f"{p['pct_multi_invoice']}%",
                "Methode pref.": p["preferred_method"][:18],
                "Avec ref": f"{p['pct_with_ref']}%",
                "Taux auto": f"{p['auto_rate']}%",
            })
        prof_df = pd.DataFrame(prof_rows)
        st.dataframe(prof_df, use_container_width=True, height=500, hide_index=True)

        # Detailed profile for selected debtor
        st.markdown('<div class="section-h">Detail d\'un debiteur</div>', unsafe_allow_html=True)
        sel_did = st.selectbox("Selectionner", sorted(profiles.keys()),
            format_func=lambda d: f"{d} — {profiles[d]['debtor_name'][:30]}")
        p = profiles[sel_did]

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Paiements analyses", p["n_payments"])
        with col2:
            auto_color = "normal" if p["auto_rate"] >= 80 else "inverse"
            st.metric("Taux auto", f"{p['auto_rate']}%")
        with col3:
            st.metric("Delai moyen", f"{p['avg_delay_days']}j")
        with col4:
            st.metric("Inv./paiement", f"{p['avg_invoices_per_payment']}")

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("**Distribution des methodes**")
            if p["method_distribution"]:
                meth_df = pd.DataFrame([
                    {"Methode": k, "Pourcentage": v}
                    for k, v in sorted(p["method_distribution"].items(), key=lambda x: -x[1])
                ])
                fig = px.bar(meth_df, x="Methode", y="Pourcentage", color_discrete_sequence=[C_INDIGO])
                fig.update_layout(height=300, **PLOTLY_LAYOUT)
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            st.markdown("**Distribution par couche**")
            if p["layer_distribution"]:
                layer_df = pd.DataFrame([
                    {"Couche": k, "Pourcentage": v}
                    for k, v in p["layer_distribution"].items()
                ])
                fig = px.pie(layer_df, values="Pourcentage", names="Couche",
                            color="Couche", color_discrete_map={"C1":C_GREEN,"C2":C_YELLOW,"C3":C_CYAN,"C6":C_RED},
                            hole=0.4)
                fig.update_layout(height=300, **PLOTLY_LAYOUT)
                st.plotly_chart(fig, use_container_width=True)

        # Behavioral insights
        st.markdown("**Insights comportementaux**")
        insights = []
        if p["typical_pay_days"]:
            insights.append(f"Paie typiquement le **{', '.join(str(d) for d in p['typical_pay_days'])}** du mois "
                          f"(regularite {p['pay_day_regularity']*100:.0f}%)")
        if p["avg_invoices_per_payment"] > 1.5:
            insights.append(f"Tend a **grouper ses paiements** ({p['avg_invoices_per_payment']:.1f} factures/paiement en moyenne)")
        if p["pct_with_discount"] > 5:
            insights.append(f"Prend souvent un **escompte** ({p['pct_with_discount']:.0f}% des paiements)")
        if p["pct_with_retention"] > 5:
            insights.append(f"Applique une **retenue de garantie** ({p['pct_with_retention']:.0f}% des paiements)")
        if p["pct_with_ref"] > 80:
            insights.append(f"Reference toujours les factures dans ses libelles ({p['pct_with_ref']:.0f}%)")
        elif p["pct_with_ref"] < 30:
            insights.append(f"**Rarement de reference** dans les libelles ({p['pct_with_ref']:.0f}%) — labels souvent cryptiques")
        if p["avg_delay_days"] > 15:
            insights.append(f"**Payeur en retard** : delai moyen {p['avg_delay_days']:.0f} jours apres echeance")
        elif p["avg_delay_days"] < 3:
            insights.append(f"**Payeur ponctuel** : delai moyen {p['avg_delay_days']:.0f} jours")

        for insight in insights:
            st.markdown(f"- {insight}")

        if not insights:
            st.info("Pas assez de donnees pour generer des insights.")

        # ── Verbatim / Label analysis ──
        st.markdown('<div class="section-h">Analyse des verbatims</div>', unsafe_allow_html=True)

        lang = p.get("dominant_language", "?")
        avg_len = p.get("avg_label_length", 0)
        pct_empty = p.get("pct_empty_label", 0)
        pct_cryptic = p.get("pct_cryptic_label", 0)
        top_tokens = p.get("top_tokens", [])
        prefixes = p.get("recurring_prefixes", [])
        patterns = p.get("recurring_patterns", [])
        samples = p.get("sample_labels", [])

        col1, col2, col3, col4 = st.columns(4)
        with col1: st.metric("Langue", lang)
        with col2: st.metric("Longueur moy.", f"{avg_len:.0f} car.")
        with col3: st.metric("Labels vides", f"{pct_empty:.0f}%")
        with col4: st.metric("Labels cryptiques", f"{pct_cryptic:.0f}%")

        if patterns:
            st.markdown("**Patterns recurrents detectes :**")
            for pat in patterns:
                st.markdown(f"- {pat}")

        col1, col2 = st.columns(2)
        with col1:
            if top_tokens:
                st.markdown("**Top tokens (hors refs et nombres) :**")
                tok_df = pd.DataFrame(top_tokens[:12], columns=["Token", "Frequence"])
                fig = px.bar(tok_df, x="Token", y="Frequence", color_discrete_sequence=[C_PURPLE])
                fig.update_layout(height=280, **PLOTLY_LAYOUT)
                st.plotly_chart(fig, use_container_width=True)

        with col2:
            if prefixes:
                st.markdown("**Prefixes les plus frequents :**")
                pre_df = pd.DataFrame(prefixes[:8], columns=["Prefixe", "Frequence"])
                fig = px.bar(pre_df, x="Prefixe", y="Frequence", color_discrete_sequence=[C_INDIGO])
                fig.update_layout(height=280, **PLOTLY_LAYOUT)
                st.plotly_chart(fig, use_container_width=True)

        if samples:
            st.markdown("**Exemples de libelles (10 max) :**")
            for i, s in enumerate(samples, 1):
                st.markdown(f'<div style="background:#f1f5f9;padding:4px 12px;border-radius:6px;'
                           f'margin:2px 0;font-family:monospace;font-size:0.82rem;">'
                           f'{i}. {_esc(s)}</div>', unsafe_allow_html=True)


# =====================================================================
# PAGE — DEEP DIVE
# =====================================================================
elif page == "Deep Dive":
    st.markdown("""
    <div class="hero">
        <h1>Deep Dive — Analyse d'un paiement</h1>
        <div class="sub">Suivez le parcours complet a travers les 6 couches du pipeline</div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2 = st.columns([1, 3])
    with col1:
        example_type = st.radio("Exemple", [
            "Match C1 (exact)",
            "Match C2 (tolerance)",
            "Match C2 (subset sum)",
            "Revue humaine (C6)",
            "Choisir manuellement",
        ])

    if example_type == "Choisir manuellement":
        with col2:
            selected_id = st.selectbox("ID du paiement", sorted(df["payment_id"].unique()))
    else:
        lookup = {
            "Match C1 (exact)": df[(df["layer_name"]=="C1") & (df["confidence"]>=0.97)],
            "Match C2 (tolerance)": df[df["method"]=="C2_TOLERANCE"],
            "Match C2 (subset sum)": df[df["method"]=="C2_SUBSET_SUM"],
            "Revue humaine (C6)": df[df["layer_name"]=="C6"],
        }
        cands = lookup.get(example_type, df)
        selected_id = cands.iloc[0]["payment_id"] if len(cands) > 0 else df.iloc[0]["payment_id"]

    row = df[df["payment_id"] == selected_id].iloc[0]
    ctx = next((r for r in data["results"] if r.payment.id == selected_id), None)

    # Card header
    badge_cls = {"C1":"c1","C2":"c2","C3":"c3","C6":"c6"}.get(row["layer_name"],"c6")
    conf_pct = f"{row['confidence']:.0%}" if row["confidence"] > 0 else "—"

    st.markdown(f"""
    <div class="deep-card">
        <div style="display:flex; align-items:center; gap:14px; margin-bottom:14px;">
            <h3 style="flex:1; margin:0;">Paiement <code>{selected_id}</code></h3>
            <span class="badge {badge_cls}" style="font-size:0.9rem; padding:8px 20px;">
                {row['layer_name']} — {conf_pct}</span>
        </div>
        <div class="deep-meta">
            <span><b>Montant :</b> {row['amount']:,.2f} EUR</span>
            <span><b>Date :</b> {row['date']}</span>
            <span><b>Debiteur :</b> {_esc(str(row['debtor_name']))}</span>
            <span><b>Pays :</b> {row['country']}</span>
        </div>
        <div class="deep-label" style="margin:14px 0;">
            <b>Libelle brut du virement :</b><br>
            <code>{_esc(row['label']) if row['label'] else '(vide)'}</code>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Pipeline trace
    st.markdown('<div class="section-h">Parcours dans le pipeline</div>', unsafe_allow_html=True)

    if ctx:
        steps_html = ""
        for log in ctx.processing_log:
            layer = log.get("layer","?")
            event = log.get("event","")
            t = log.get("time_ms", 0)
            conf = log.get("confidence", 0)
            method = log.get("method","")
            if event == "PREPROCESSED":
                steps_html += f'<div class="step step-pre"><b>C0</b> Preprocessing & normalisation <span class="time">{t:.1f}ms</span></div>'
            elif event == "MATCH_FOUND":
                steps_html += (f'<div class="step step-match"><b>C{layer}</b> '
                    f'<b>MATCH TROUVE</b> &nbsp; <span class="badge" style="background:#667eea;padding:2px 10px;font-size:0.75rem;">{method}</span>'
                    f' &nbsp; confiance <b>{conf:.0%}</b> <span class="time">{t:.1f}ms</span></div>')
            elif event == "NO_MATCH":
                steps_html += f'<div class="step step-no"><b>C{layer}</b> Pas de match <span class="time">{t:.1f}ms</span></div>'
            elif event == "ERROR":
                steps_html += f'<div class="step" style="background:#fee2e2;border-left:4px solid #ef4444;"><b>C{layer}</b> Erreur : {log.get("detail","")}</div>'
        st.markdown(steps_html, unsafe_allow_html=True)

    # Result
    if row["matched"]:
        inv_str = row["invoices_matched"]
        st.markdown(f'<div class="result-box result-ok"><b>Factures matchees :</b> {inv_str}</div>', unsafe_allow_html=True)
        if row["flags"]:
            st.markdown(f'<div class="result-box result-flags"><b>Flags :</b> {_esc(str(row["flags"]))}</div>', unsafe_allow_html=True)
        if ctx and ctx.final_match:
            alloc = ctx.final_match.allocated
            if alloc:
                st.markdown(f'<div class="result-box" style="background:#eff6ff;color:#1e40af;"><b>Allocation :</b> {alloc}</div>', unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="result-box result-fail">
            <b>Aucun match automatique</b> — paiement envoye en revue humaine (C6).<br>
            <span style="font-size:0.85rem;">Raisons possibles : label cryptique, montant ne correspondant a rien,
            combinaison trop complexe.</span>
        </div>
        """, unsafe_allow_html=True)

        # Show recommendations
        ground_truth = data.get("ground_truth", {})
        true_ref = ground_truth.get(selected_id, "")
        from collections import defaultdict as dd
        inv_by_d = dd(list)
        for inv in data["invoices"]: inv_by_d[inv.debtor_id].append(inv)
        search = inv_by_d.get(row["debtor_id"], data["invoices"][:50])
        recs = []
        for inv in search:
            score, reasons = 0.0, []
            if inv.amount > 0:
                dp = abs(row["amount"]-inv.amount)/inv.amount
                if dp<0.001: score += 0.40; reasons.append("montant exact")
                elif dp<0.05: score += 0.30; reasons.append(f"ecart {dp:.1%}")
                elif dp<0.15: score += 0.15; reasons.append(f"ecart {dp:.0%}")
            if inv.debtor_id == row["debtor_id"]: score += 0.25; reasons.append("meme debiteur")
            if row["date"] and inv.due_date:
                dd2 = abs((row["date"]-inv.due_date).days)
                if dd2<=7: score += 0.20; reasons.append(f"echeance +{dd2}j")
                elif dd2<=30: score += 0.12; reasons.append(f"+{dd2}j")
            if score > 0.1: recs.append({"ref":inv.reference,"amount":inv.amount,
                                          "score":min(score,1.0),"reason":" | ".join(reasons[:3]),
                                          "is_true":inv.reference==true_ref})
        recs.sort(key=lambda x:-x["score"])
        recs = recs[:5]
        if recs:
            st.markdown('<div class="section-h">Recommandations (top 5 factures candidates)</div>', unsafe_allow_html=True)
            for i, rec in enumerate(recs):
                bar_w = int(rec["score"]*100)
                is_true = rec["is_true"]
                bg = "#ecfdf5" if is_true else "#f8fafc"
                border = "2px solid #10b981" if is_true else "1px solid #e2e8f0"
                check = '<span style="background:#10b981;color:white;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:700;margin-left:8px;">✓ VRAIE FACTURE</span>' if is_true else ""
                bar_color = "linear-gradient(90deg,#10b981,#34d399)" if is_true else "linear-gradient(90deg,#667eea,#8b5cf6)"
                st.markdown(f"""
                <div style="display:grid; grid-template-columns:30px 1fr 90px 70px 45px; gap:8px; align-items:center;
                            padding:8px 12px; margin:4px 0; background:{bg}; border:{border}; border-radius:8px; font-size:0.85rem;">
                    <span style="font-weight:800; color:#667eea;">#{i+1}</span>
                    <span style="font-family:monospace; {'font-weight:700;color:#065f46;' if is_true else ''}">{_esc(str(rec['ref']))}{check}</span>
                    <span style="text-align:right; font-variant-numeric:tabular-nums;">{rec['amount']:,.2f}</span>
                    <span style="height:10px; background:#e2e8f0; border-radius:5px; overflow:hidden;">
                        <span style="display:block; height:100%; width:{bar_w}%; background:{bar_color}; border-radius:5px;"></span>
                    </span>
                    <span style="font-weight:700; color:#667eea; text-align:right;">{rec['score']:.0%}</span>
                </div>
                <div style="font-size:0.75rem; color:#64748b; font-style:italic; padding-left:42px; margin-bottom:4px;">{_esc(str(rec['reason']))}</div>
                """, unsafe_allow_html=True)
