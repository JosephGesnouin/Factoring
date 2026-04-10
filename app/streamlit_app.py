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

    /* Hide streamlit branding */
    #MainMenu, footer, header { visibility: hidden; }

    /* Responsive */
    @media (max-width: 900px) { .kpi-grid { grid-template-columns: repeat(2,1fr); } }
</style>
""", unsafe_allow_html=True)


# =====================================================================
# DATA
# =====================================================================
@st.cache_data(show_spinner="Generation des donnees et simulation (10 000+ paiements)...")
def load_data():
    from app.simulation_data import generate_all
    return generate_all(seed=42, target_payments=10000)


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

# ── Sidebar ──
with st.sidebar:
    st.markdown("### 🏦 Reconciliation IA")
    st.caption("Factoring & Finance Receivables")
    st.divider()
    page = st.radio("Navigation", [
        "Executive Summary",
        "Architecture",
        "Simulation Live",
        "Analyse Debiteurs",
        "Paiements par Couche",
        "Revue Humaine",
        "Deep Dive",
    ], label_visibility="collapsed")
    st.divider()
    st.caption("Architecture 6 couches")
    st.caption("50 debiteurs | 10k+ paiements")

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
# PAGE 3 — SIMULATION LIVE
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
                    <span><b>Debiteur :</b> {row['debtor_name']}</span>
                </div>
                <div class="deep-label"><b>Libelle :</b><br><code>{row['label'] if row['label'] else '(vide)'}</code></div>
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
            st.markdown(f'<div class="result-box result-ok"><b>Factures :</b> {row["invoices_matched"]}</div>', unsafe_allow_html=True)
            if row["flags"]:
                st.markdown(f'<div class="result-box result-flags"><b>Flags :</b> {row["flags"]}</div>', unsafe_allow_html=True)


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

    # Compute recommendations for all C6 payments
    @st.cache_data
    def compute_recommendations(df_c6, _invoices, _ground_truth):
        from collections import defaultdict as _dd
        inv_by_d = _dd(list)
        for inv in _invoices:
            inv_by_d[inv.debtor_id].append(inv)

        recs = {}
        for _, r in df_c6.iterrows():
            pid = r["payment_id"]
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
                true_ref = _ground_truth.get(pid, "")
                if score > 0.1:
                    candidates.append({"ref": inv.reference, "amount": inv.amount,
                        "score": min(score, 1.0), "reason": " | ".join(reasons[:3]),
                        "is_true": inv.reference == true_ref})
            candidates.sort(key=lambda x: -x["score"])
            recs[pid] = candidates[:5]
        return recs

    ground_truth = data.get("ground_truth", {})
    recommendations = compute_recommendations(c6_df, data["invoices"], ground_truth)

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
        label_esc = row["label"] if row["label"] else "(vide)"

        # Payment card
        has_true = any(r["is_true"] for r in recs)
        border_color = C_GREEN if has_true else "#e2e8f0"

        st.markdown(f"""
        <div class="deep-card" style="border-left:4px solid {border_color};">
            <div style="display:flex; align-items:center; gap:12px; margin-bottom:8px;">
                <code style="font-size:0.9rem; font-weight:700;">{pid}</code>
                <span style="font-size:1.1rem; font-weight:700;">{row['amount']:,.2f} EUR</span>
                <span style="color:var(--slate); font-size:0.85rem;">{row['date']}</span>
                <span style="color:var(--slate); font-size:0.85rem;">{row['debtor_name']}</span>
            </div>
            <div class="deep-label"><code>{label_esc[:100]}</code></div>
        </div>
        """, unsafe_allow_html=True)

        # Recommendations
        if recs:
            for i, rec in enumerate(recs):
                is_true = rec.get("is_true", False)
                bg = "#ecfdf5" if is_true else "#f8fafc"
                border = "2px solid #10b981" if is_true else "1px solid #e2e8f0"
                bar_w = int(rec["score"] * 100)
                bar_color = "linear-gradient(90deg,#10b981,#34d399)" if is_true else "linear-gradient(90deg,#667eea,#8b5cf6)"
                check = '<span style="background:#10b981;color:white;padding:2px 8px;border-radius:4px;font-size:0.72rem;font-weight:700;margin-left:6px;">VRAIE FACTURE</span>' if is_true else ""
                ref_style = "font-weight:700;color:#065f46;" if is_true else ""
                st.markdown(f"""
                <div style="display:grid; grid-template-columns:28px 1fr 90px 70px 42px; gap:8px; align-items:center;
                            padding:6px 12px; margin:3px 0 3px 20px; background:{bg}; border:{border}; border-radius:8px; font-size:0.82rem;">
                    <span style="font-weight:800; color:#667eea;">#{i+1}</span>
                    <span style="font-family:monospace; {ref_style}">{rec['ref']}{check}</span>
                    <span style="text-align:right; font-variant-numeric:tabular-nums;">{rec['amount']:,.2f}</span>
                    <span style="height:10px; background:#e2e8f0; border-radius:5px; overflow:hidden;">
                        <span style="display:block; height:100%; width:{bar_w}%; background:{bar_color}; border-radius:5px;"></span>
                    </span>
                    <span style="font-weight:700; color:#667eea; text-align:right;">{rec['score']:.0%}</span>
                </div>
                <div style="font-size:0.72rem; color:#64748b; font-style:italic; padding-left:52px; margin-bottom:2px;">{rec['reason']}</div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#94a3b8; font-style:italic; padding-left:20px; margin-bottom:8px; font-size:0.85rem;">Aucun candidat identifie</div>', unsafe_allow_html=True)

    st.caption(f"Page {page_num + 1} / {n_pages} ({len(filtered_c6):,} paiements)")


# =====================================================================
# PAGE 7 — DEEP DIVE
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
            <span><b>Debiteur :</b> {row['debtor_name']}</span>
            <span><b>Pays :</b> {row['country']}</span>
        </div>
        <div class="deep-label" style="margin:14px 0;">
            <b>Libelle brut du virement :</b><br>
            <code>{row['label'] if row['label'] else '(vide)'}</code>
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
            st.markdown(f'<div class="result-box result-flags"><b>Flags :</b> {row["flags"]}</div>', unsafe_allow_html=True)
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
                    <span style="font-family:monospace; {'font-weight:700;color:#065f46;' if is_true else ''}">{rec['ref']}{check}</span>
                    <span style="text-align:right; font-variant-numeric:tabular-nums;">{rec['amount']:,.2f}</span>
                    <span style="height:10px; background:#e2e8f0; border-radius:5px; overflow:hidden;">
                        <span style="display:block; height:100%; width:{bar_w}%; background:{bar_color}; border-radius:5px;"></span>
                    </span>
                    <span style="font-weight:700; color:#667eea; text-align:right;">{rec['score']:.0%}</span>
                </div>
                <div style="font-size:0.75rem; color:#64748b; font-style:italic; padding-left:42px; margin-bottom:4px;">{rec['reason']}</div>
                """, unsafe_allow_html=True)
