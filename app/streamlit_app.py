"""
Streamlit Demo — Reconciliation Paiement-Facture par IA
Presentation executive pour top management.

Lancer : streamlit run app/streamlit_app.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(
    page_title="Reconciliation IA — Factoring",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ──
st.markdown("""
<style>
    .main .block-container { padding-top: 1rem; max-width: 1200px; }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.2rem; border-radius: 12px; color: white; text-align: center;
    }
    .metric-card h2 { font-size: 2.2rem; margin: 0; font-weight: 700; }
    .metric-card p { font-size: 0.9rem; margin: 0.2rem 0 0 0; opacity: 0.85; }
    .layer-badge {
        display: inline-block; padding: 4px 12px; border-radius: 20px;
        font-weight: 600; font-size: 0.8rem; color: white;
    }
    .layer-c1 { background: #10b981; }
    .layer-c2 { background: #f59e0b; }
    .layer-c3 { background: #06b6d4; }
    .layer-c6 { background: #ef4444; }
    div[data-testid="stMetric"] {
        background: #f8fafc; border-radius: 8px; padding: 12px;
        border: 1px solid #e2e8f0;
    }
</style>
""", unsafe_allow_html=True)


@st.cache_data(show_spinner="Generation des donnees et simulation...")
def load_data():
    from app.simulation_data import generate_all
    return generate_all(seed=42)


# ── Sidebar ──
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/bank-building.png", width=60)
    st.title("Reconciliation IA")
    st.caption("Factoring & Finance Receivables")
    st.divider()
    page = st.radio("Navigation", [
        "Executive Summary",
        "Architecture du Systeme",
        "Simulation Live",
        "Analyse par Debiteur",
        "Deep Dive Paiement",
    ], label_visibility="collapsed")
    st.divider()
    st.caption("Architecture 6 couches\n\n74 tests | 12 debiteurs | 12 mois")


data = load_data()
df = data["df"]
metrics = data["metrics"]


# =====================================================================
# PAGE 1 — EXECUTIVE SUMMARY
# =====================================================================
if page == "Executive Summary":
    st.title("Executive Summary")
    st.markdown("**Tableau de bord de la reconciliation automatique paiement-facture**")
    st.markdown("---")

    # KPI cards
    auto_rate = metrics.matched_auto / metrics.total_payments * 100
    review_rate = metrics.by_layer.get(6, 0) / metrics.total_payments * 100
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric("Paiements traites", f"{metrics.total_payments:,}", help="Total sur 12 mois")
    with c2:
        st.metric("Taux d'automatisation", f"{auto_rate:.1f}%",
                   delta=f"{metrics.matched_auto} auto-matches")
    with c3:
        st.metric("Revue humaine", f"{review_rate:.1f}%",
                   delta=f"{metrics.by_layer.get(6, 0)} paiements", delta_color="inverse")
    with c4:
        st.metric("Temps moyen", f"{metrics.avg_processing_time_ms:.1f} ms",
                   help="Temps de traitement par paiement")

    st.markdown("")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Factures ouvertes", f"{data['n_invoices']:,}")
    with c2:
        total_eur = df["amount"].sum()
        st.metric("Volume traite", f"{total_eur/1e6:.1f} M EUR")
    with c3:
        st.metric("Debiteurs actifs", f"{data['n_debtors']}")
    with c4:
        st.metric("Zero erreur", f"{metrics.errors}", delta="Pipeline stable", delta_color="off")

    st.markdown("---")

    # Two charts side by side
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Distribution par couche")
        layer_data = []
        layer_names = {1: "C1 Exact", 2: "C2 Regles Metier", 3: "C3 NLP/Fuzzy", 6: "C6 Revue Humaine"}
        layer_colors = {1: "#10b981", 2: "#f59e0b", 3: "#06b6d4", 6: "#ef4444"}
        for layer, count in sorted(metrics.by_layer.items()):
            if count > 0:
                layer_data.append({
                    "Couche": layer_names.get(layer, f"C{layer}"),
                    "Paiements": count,
                    "color": layer_colors.get(layer, "#94a3b8"),
                })
        ldf = pd.DataFrame(layer_data)
        fig = px.pie(ldf, values="Paiements", names="Couche",
                     color="Couche",
                     color_discrete_map={r["Couche"]: r["color"] for r in layer_data},
                     hole=0.45)
        fig.update_layout(height=350, margin=dict(t=20, b=20, l=20, r=20))
        fig.update_traces(textposition="inside", textinfo="percent+label")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Evolution mensuelle")
        monthly = df.groupby("month_name").agg(
            Total=("payment_id", "count"),
            Auto=("matched", "sum"),
        ).reset_index()
        # Fix month ordering
        month_order = ["Janvier","Fevrier","Mars","Avril","Mai","Juin",
                       "Juillet","Aout","Septembre","Octobre","Novembre","Decembre"]
        monthly["month_name"] = pd.Categorical(monthly["month_name"], categories=month_order, ordered=True)
        monthly = monthly.sort_values("month_name")
        monthly["Revue"] = monthly["Total"] - monthly["Auto"]

        fig = go.Figure()
        fig.add_trace(go.Bar(name="Auto-match", x=monthly["month_name"], y=monthly["Auto"],
                             marker_color="#10b981"))
        fig.add_trace(go.Bar(name="Revue humaine", x=monthly["month_name"], y=monthly["Revue"],
                             marker_color="#ef4444"))
        fig.update_layout(barmode="stack", height=350, margin=dict(t=20, b=20),
                          legend=dict(orientation="h", yanchor="bottom", y=1.02))
        st.plotly_chart(fig, use_container_width=True)

    # Top methods
    st.subheader("Top methodes de matching")
    method_counts = df[df["matched"]].groupby("method").size().reset_index(name="count")
    method_counts = method_counts.sort_values("count", ascending=True).tail(10)
    fig = px.bar(method_counts, x="count", y="method", orientation="h",
                 color_discrete_sequence=["#667eea"])
    fig.update_layout(height=300, margin=dict(l=20, r=20, t=10, b=10),
                      xaxis_title="Nombre de paiements", yaxis_title="")
    st.plotly_chart(fig, use_container_width=True)


# =====================================================================
# PAGE 2 — ARCHITECTURE DU SYSTEME
# =====================================================================
elif page == "Architecture du Systeme":
    st.title("Architecture du Systeme")
    st.markdown("**Pipeline de reconciliation en 6 couches avec early-exit**")
    st.markdown("---")

    # Pipeline visualization
    st.markdown("""
    <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap; justify-content:center; margin:20px 0;">
        <div style="background:#1e293b; color:white; padding:12px 20px; border-radius:10px; text-align:center; min-width:120px;">
            <div style="font-size:0.7rem; opacity:0.7;">ENTREE</div>
            <div style="font-size:1.1rem; font-weight:700;">Paiement</div>
        </div>
        <div style="font-size:1.5rem;">→</div>
        <div style="background:#6366f1; color:white; padding:12px 16px; border-radius:10px; text-align:center;">
            <div style="font-size:0.7rem; opacity:0.8;">C0</div>
            <div style="font-weight:600;">Normalisation</div>
            <div style="font-size:0.7rem;">14 transforms</div>
        </div>
        <div style="font-size:1.5rem;">→</div>
        <div style="background:#10b981; color:white; padding:12px 16px; border-radius:10px; text-align:center;">
            <div style="font-size:0.7rem; opacity:0.8;">C1</div>
            <div style="font-weight:600;">Exact Match</div>
            <div style="font-size:0.7rem;">97-100%</div>
        </div>
        <div style="font-size:1.5rem;">→</div>
        <div style="background:#f59e0b; color:white; padding:12px 16px; border-radius:10px; text-align:center;">
            <div style="font-size:0.7rem; opacity:0.8;">C2</div>
            <div style="font-weight:600;">Regles Metier</div>
            <div style="font-size:0.7rem;">85-99%</div>
        </div>
        <div style="font-size:1.5rem;">→</div>
        <div style="background:#06b6d4; color:white; padding:12px 16px; border-radius:10px; text-align:center;">
            <div style="font-size:0.7rem; opacity:0.8;">C3</div>
            <div style="font-weight:600;">NLP / Fuzzy</div>
            <div style="font-size:0.7rem;">75-92%</div>
        </div>
        <div style="font-size:1.5rem;">→</div>
        <div style="background:#8b5cf6; color:white; padding:12px 16px; border-radius:10px; text-align:center;">
            <div style="font-size:0.7rem; opacity:0.8;">C4</div>
            <div style="font-weight:600;">ML Ensemble</div>
            <div style="font-size:0.7rem;">80-95%</div>
        </div>
        <div style="font-size:1.5rem;">→</div>
        <div style="background:#ec4899; color:white; padding:12px 16px; border-radius:10px; text-align:center;">
            <div style="font-size:0.7rem; opacity:0.8;">C5</div>
            <div style="font-weight:600;">LLM / IA Gen.</div>
            <div style="font-size:0.7rem;">Variable</div>
        </div>
        <div style="font-size:1.5rem;">→</div>
        <div style="background:#ef4444; color:white; padding:12px 16px; border-radius:10px; text-align:center;">
            <div style="font-size:0.7rem; opacity:0.8;">C6</div>
            <div style="font-weight:600;">Revue Humaine</div>
            <div style="font-size:0.7rem;">File priorisee</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.info("**Principe d'early-exit** : des qu'une couche trouve un match avec une confiance >= 90%, "
            "le paiement est cloture et les couches suivantes ne sont pas executees. "
            "Cela maximise la vitesse (< 2ms pour les cas C1).")

    st.markdown("---")

    # Layer details in expanders
    st.subheader("Detail de chaque couche")

    with st.expander("**C0 — Preprocessing & Normalisation** (applique a 100% des paiements)", expanded=False):
        st.markdown("""
        14 transformations deterministes et idempotentes :

        | # | Transformation | Exemple |
        |---|---------------|---------|
        | N001 | Uppercase | `fac-2024-001` → `FAC-2024-001` |
        | N002 | Deaccentuation | `Règlmnt` → `REGLMNT` |
        | N003 | Strip ponctuation | `FAC.001!` → `FAC001` |
        | N005 | Parse montants | `15.000,50` → `15000.50` |
        | N007 | Expand abreviations | `REGLT` → `REGLEMENT` |
        | N008 | Normalise IBAN | `fr76 1234` → `FR761234...` |
        | N009 | Parse dates | `01/10/24` → `2024-10-01` |
        | N011 | Strip prefixes bancaires | `VIRT RECU DE...` → `...` |
        | N012 | Detection langue | `Payment invoices` → `EN` |

        Plus : enrichissement debiteur via IBAN, extraction de signaux (refs, montants, periodes, mots-cles).
        """)

    with st.expander("**C1 — Matching Exact & Deterministe** (confiance 97-100%)", expanded=False):
        st.markdown("""
        7 regles avec precision ~100%, zero faux positif :

        | Regle | Description | Confiance |
        |-------|-------------|-----------|
        | R001 | Reference exacte + montant exact (TTC ou HT) | 97-100% |
        | R002 | Reference ISO 20022 SEPA (/ROC/, /RFB/, EndToEndId) | 93-100% |
        | R003 | Hash index multi-format (variantes de references) | 98% |
        | R004 | IBAN connu + montant unique / total / batch | 94-98% |
        | R005 | Solde total du debiteur (net des avoirs) | 95-96% |
        | R006 | Matching via Purchase Order (PO) | 88-96% |
        | R007 | Matching via Bon de Livraison (BL/CMR) | 92-97% |
        """)

    with st.expander("**C2 — Regles Metier Avancees** (confiance 85-99%)", expanded=False):
        st.markdown("""
        **12 regles de tolerance montant :**
        Frais SWIFT (-35 EUR), SEPA OUR (-15 EUR), escompte contractuel, arrondi (+-1 EUR),
        retenue de garantie BTP (3/5/10%), deduction d'avoirs, RFA, retenue a la source (WHT),
        acomptes standards (30/50/70%).

        **Subset Sum multi-factures :** 3 strategies (greedy, exact, two-sum).

        **Patterns temporels :** paiement par periode ("FACTURES OCTOBRE 2024").

        **Anti-doublons :** fingerprint, meme jour/montant/debiteur.
        """)

    with st.expander("**C3 — NLP, Fuzzy Matching & Embeddings** (confiance 75-92%)", expanded=False):
        st.markdown("""
        **8 algorithmes fuzzy** avec score composite pondere :
        Levenshtein, Jaro-Winkler, Token Sort/Set, Partial Ratio, N-gram Jaccard,
        LCS, Numeric Ref Similarity.

        **NER custom** : 10 types d'entites (INVOICE_REF, AMOUNT, DATE, PERIOD...).

        **TF-IDF** : n-grams caracteres pour similarite cosinus.

        **Embeddings semantiques** : sentence-transformers multilingue.
        """)

    with st.expander("**C4 — Machine Learning Supervise** (confiance 80-95%)", expanded=False):
        st.markdown("""
        **42 features** en 4 groupes : Amount (10), Reference (12), Temporal (10), Behavioral (10).

        **Ensemble** : LightGBM + XGBoost + Random Forest + meta-classifieur logistique.

        **LambdaRank** pour le ranking 1-to-N. **Active Learning** (6 strategies).

        **Drift detection** via PSI (Population Stability Index).
        """)

    with st.expander("**C5 — LLM & IA Generative**", expanded=False):
        st.markdown("""
        3 prompts optimises (generique, cryptique, ambigu).

        **Validation anti-hallucination** : 5 controles automatiques sur chaque reponse.

        Supporte Claude (Anthropic) et GPT (OpenAI). Cache intelligent.
        """)

    with st.expander("**C6 — Revue Humaine Intelligente**", expanded=False):
        st.markdown("""
        File de revue priorisee par :
        - **Montant** (30%) : gros montants d'abord
        - **Anciennete** (25%) : plus vieux d'abord
        - **Gap confiance** (25%) : proches du seuil = faciles
        - **Risque debiteur** (20%)

        Feedback structure (APPROVE, REJECT, CORRECT, SPLIT) → boucle d'apprentissage vers C4.
        """)


# =====================================================================
# PAGE 3 — SIMULATION LIVE
# =====================================================================
elif page == "Simulation Live":
    st.title("Simulation Live")
    st.markdown("**Visualisation du traitement de chaque paiement a travers le pipeline**")
    st.markdown("---")

    # Filters
    col1, col2, col3 = st.columns(3)
    with col1:
        layer_filter = st.multiselect("Filtrer par couche",
            ["C1", "C2", "C3", "C6"], default=["C1", "C2", "C3", "C6"])
    with col2:
        debtor_filter = st.multiselect("Filtrer par debiteur",
            sorted(df["debtor_name"].unique()), default=[])
    with col3:
        conf_range = st.slider("Confiance min-max", 0.0, 1.0, (0.0, 1.0), 0.05)

    # Apply filters
    mask = df["layer_name"].isin(layer_filter)
    if debtor_filter:
        mask &= df["debtor_name"].isin(debtor_filter)
    mask &= df["confidence"].between(conf_range[0], conf_range[1])
    filtered = df[mask]

    st.markdown(f"**{len(filtered)}** paiements affiches sur **{len(df)}** total")
    st.markdown("")

    # Color map for layers
    def color_layer(val):
        colors = {"C1": "background-color: #d1fae5", "C2": "background-color: #fef3c7",
                  "C3": "background-color: #cffafe", "C6": "background-color: #fee2e2"}
        return colors.get(val, "")

    # Display table
    display_cols = ["payment_id", "date", "amount", "debtor_name", "label",
                    "layer_name", "method", "confidence", "flags", "invoices_matched"]
    display_df = filtered[display_cols].copy()
    display_df["amount"] = display_df["amount"].apply(lambda x: f"{x:,.2f}")
    display_df["confidence"] = display_df["confidence"].apply(lambda x: f"{x:.0%}" if x > 0 else "—")
    display_df.columns = ["ID", "Date", "Montant", "Debiteur", "Libelle",
                          "Couche", "Methode", "Confiance", "Flags", "Factures"]

    st.dataframe(
        display_df.style.applymap(color_layer, subset=["Couche"]),
        use_container_width=True,
        height=500,
    )

    # Stats for filtered set
    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Repartition des methodes (filtre actif)")
        method_df = filtered.groupby("method").size().reset_index(name="count")
        method_df = method_df.sort_values("count", ascending=False)
        fig = px.bar(method_df.head(10), x="method", y="count",
                     color_discrete_sequence=["#667eea"])
        fig.update_layout(height=300, margin=dict(t=10, b=10),
                          xaxis_title="", yaxis_title="Paiements")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Distribution des confiances")
        matched = filtered[filtered["confidence"] > 0]
        if not matched.empty:
            fig = px.histogram(matched, x="confidence", nbins=20,
                              color_discrete_sequence=["#10b981"])
            fig.update_layout(height=300, margin=dict(t=10, b=10),
                              xaxis_title="Score de confiance", yaxis_title="Nombre")
            st.plotly_chart(fig, use_container_width=True)


# =====================================================================
# PAGE 4 — ANALYSE PAR DEBITEUR
# =====================================================================
elif page == "Analyse par Debiteur":
    st.title("Analyse par Debiteur")
    st.markdown("**Performance de reconciliation par debiteur et par pays**")
    st.markdown("---")

    # Debtor summary table
    debtor_stats = df.groupby(["debtor_id", "debtor_name", "country", "sector"]).agg(
        total=("payment_id", "count"),
        auto=("matched", "sum"),
        montant=("amount", "sum"),
        conf_moy=("confidence", "mean"),
    ).reset_index()
    debtor_stats["revue"] = debtor_stats["total"] - debtor_stats["auto"]
    debtor_stats["taux"] = (debtor_stats["auto"] / debtor_stats["total"] * 100).round(1)
    debtor_stats = debtor_stats.sort_values("taux", ascending=False)

    # Color the rate
    def color_rate(val):
        try:
            v = float(val)
        except (ValueError, TypeError):
            return ""
        if v >= 80: return "background-color: #d1fae5; color: #065f46"
        if v >= 50: return "background-color: #fef3c7; color: #92400e"
        return "background-color: #fee2e2; color: #991b1b"

    st.subheader("Tableau de bord par debiteur")
    show = debtor_stats[["debtor_name","country","sector","total","auto","revue","taux","montant","conf_moy"]].copy()
    show["montant"] = show["montant"].apply(lambda x: f"{x:,.0f}")
    show["conf_moy"] = show["conf_moy"].apply(lambda x: f"{x:.0%}")
    show.columns = ["Debiteur","Pays","Secteur","Total","Auto","Revue","Taux %","Montant EUR","Confiance moy."]

    st.dataframe(
        show.style.applymap(color_rate, subset=["Taux %"]),
        use_container_width=True, height=450,
    )

    st.markdown("---")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Taux d'automatisation par debiteur")
        fig = px.bar(debtor_stats.sort_values("taux"), x="taux", y="debtor_name",
                     orientation="h", color="taux",
                     color_continuous_scale=["#ef4444", "#f59e0b", "#10b981"],
                     range_color=[0, 100])
        fig.update_layout(height=450, margin=dict(l=20, r=20, t=10, b=10),
                          xaxis_title="Taux d'automatisation (%)", yaxis_title="",
                          coloraxis_showscale=False)
        fig.add_vline(x=90, line_dash="dash", line_color="gray",
                      annotation_text="Seuil 90%", annotation_position="top")
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Repartition par pays")
        country_stats = df.groupby("country").agg(
            total=("payment_id", "count"),
            auto=("matched", "sum"),
        ).reset_index()
        country_stats["taux"] = (country_stats["auto"] / country_stats["total"] * 100).round(1)

        fig = px.scatter(country_stats, x="total", y="taux", size="total",
                        color="taux", text="country",
                        color_continuous_scale=["#ef4444", "#f59e0b", "#10b981"],
                        range_color=[0, 100])
        fig.update_traces(textposition="top center")
        fig.update_layout(height=450, margin=dict(t=10, b=10),
                          xaxis_title="Nombre de paiements", yaxis_title="Taux auto (%)",
                          coloraxis_showscale=False)
        st.plotly_chart(fig, use_container_width=True)

    # Debtor profile cards
    st.markdown("---")
    st.subheader("Profils debiteurs")

    selected_debtor = st.selectbox("Selectionner un debiteur",
        sorted(df["debtor_name"].unique()))

    d_df = df[df["debtor_name"] == selected_debtor]
    d_info = data["df_debtors"][data["df_debtors"]["name"] == selected_debtor].iloc[0]

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("Pays", d_info["country"])
    with col2: st.metric("Secteur", d_info["sector"])
    with col3: st.metric("Delai paiement", f"{d_info['terms']}j")
    with col4:
        d_rate = d_df["matched"].sum() / len(d_df) * 100 if len(d_df) > 0 else 0
        st.metric("Taux auto", f"{d_rate:.0f}%")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Distribution des couches pour ce debiteur**")
        d_layers = d_df.groupby("layer_name").size().reset_index(name="count")
        fig = px.pie(d_layers, values="count", names="layer_name",
                     color="layer_name",
                     color_discrete_map={"C1":"#10b981","C2":"#f59e0b","C3":"#06b6d4","C6":"#ef4444"},
                     hole=0.4)
        fig.update_layout(height=300, margin=dict(t=10, b=10))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown("**Derniers paiements**")
        recent = d_df.tail(10)[["payment_id","date","amount","method","confidence","flags"]].copy()
        recent["amount"] = recent["amount"].apply(lambda x: f"{x:,.2f}")
        recent["confidence"] = recent["confidence"].apply(lambda x: f"{x:.0%}" if x > 0 else "—")
        st.dataframe(recent, use_container_width=True, hide_index=True)


# =====================================================================
# PAGE 5 — DEEP DIVE PAIEMENT
# =====================================================================
elif page == "Deep Dive Paiement":
    st.title("Deep Dive — Analyse d'un paiement")
    st.markdown("**Suivez le parcours d'un paiement a travers les 6 couches du pipeline**")
    st.markdown("---")

    # Payment selector
    col1, col2 = st.columns([1, 3])
    with col1:
        # Show interesting examples
        example_type = st.radio("Type d'exemple", [
            "Match C1 (exact)",
            "Match C2 (tolerance)",
            "Match C2 (subset sum)",
            "Revue humaine (C6)",
            "Choisir manuellement",
        ])

    if example_type == "Choisir manuellement":
        selected_id = st.selectbox("ID du paiement", sorted(df["payment_id"].unique()))
    else:
        if example_type == "Match C1 (exact)":
            candidates = df[(df["layer_name"] == "C1") & (df["confidence"] >= 0.97)]
        elif example_type == "Match C2 (tolerance)":
            candidates = df[(df["layer_name"] == "C2") & (df["method"] == "C2_TOLERANCE")]
        elif example_type == "Match C2 (subset sum)":
            candidates = df[(df["method"] == "C2_SUBSET_SUM")]
        else:
            candidates = df[df["layer_name"] == "C6"]

        if len(candidates) > 0:
            selected_id = candidates.iloc[0]["payment_id"]
        else:
            selected_id = df.iloc[0]["payment_id"]

    # Get the row
    row = df[df["payment_id"] == selected_id].iloc[0]
    ctx = None
    for r in data["results"]:
        if r.payment.id == selected_id:
            ctx = r
            break

    with col2:
        st.markdown(f"### Paiement `{selected_id}`")

    st.markdown("---")

    # Payment details card
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Montant", f"{row['amount']:,.2f} EUR")
    with col2:
        st.metric("Date", str(row["date"]))
    with col3:
        st.metric("Debiteur", row["debtor_name"][:25])
    with col4:
        layer_colors_html = {"C1": "#10b981", "C2": "#f59e0b", "C3": "#06b6d4", "C6": "#ef4444"}
        color = layer_colors_html.get(row["layer_name"], "#94a3b8")
        st.markdown(f"""
        <div style="background:{color}; color:white; padding:12px; border-radius:10px;
                    text-align:center; font-weight:700; font-size:1.3rem; margin-top:8px;">
            {row['layer_name']} — {row['confidence']:.0%}
        </div>
        """, unsafe_allow_html=True)

    st.markdown("")

    # Label analysis
    st.markdown("#### Libelle du paiement")
    st.code(row["label"] if row["label"] else "(vide)", language=None)

    # Pipeline journey
    st.markdown("#### Parcours dans le pipeline")

    if ctx:
        for log_entry in ctx.processing_log:
            layer = log_entry.get("layer", "?")
            event = log_entry.get("event", "")
            time_ms = log_entry.get("time_ms", 0)
            conf = log_entry.get("confidence", 0)
            method = log_entry.get("method", "")

            if event == "PREPROCESSED":
                st.markdown(f"""
                <div style="display:flex; align-items:center; gap:10px; padding:8px 16px;
                            background:#f1f5f9; border-left:4px solid #6366f1; border-radius:4px; margin:4px 0;">
                    <span style="font-weight:700; color:#6366f1;">C0</span>
                    <span>Preprocessing & normalisation</span>
                    <span style="margin-left:auto; color:#94a3b8; font-size:0.8rem;">{time_ms:.1f}ms</span>
                </div>
                """, unsafe_allow_html=True)
            elif event == "MATCH_FOUND":
                color = {"C1_":"#10b981","C2_":"#f59e0b","C3_":"#06b6d4"}.get(method[:3], "#8b5cf6")
                st.markdown(f"""
                <div style="display:flex; align-items:center; gap:10px; padding:10px 16px;
                            background:#f0fdf4; border-left:4px solid {color}; border-radius:4px; margin:4px 0;">
                    <span style="font-weight:700; color:{color};">C{layer}</span>
                    <span style="font-weight:600;">MATCH TROUVE</span>
                    <span style="background:{color}; color:white; padding:2px 10px; border-radius:12px;
                                 font-size:0.8rem;">{method}</span>
                    <span style="font-weight:700;">{conf:.0%}</span>
                    <span style="margin-left:auto; color:#94a3b8; font-size:0.8rem;">{time_ms:.1f}ms</span>
                </div>
                """, unsafe_allow_html=True)
            elif event == "NO_MATCH":
                st.markdown(f"""
                <div style="display:flex; align-items:center; gap:10px; padding:8px 16px;
                            background:#fefce8; border-left:4px solid #d4d4d8; border-radius:4px; margin:4px 0;">
                    <span style="font-weight:700; color:#a1a1aa;">C{layer}</span>
                    <span style="color:#71717a;">Pas de match</span>
                    <span style="margin-left:auto; color:#94a3b8; font-size:0.8rem;">{time_ms:.1f}ms</span>
                </div>
                """, unsafe_allow_html=True)
            elif event == "ERROR":
                st.markdown(f"""
                <div style="display:flex; align-items:center; gap:10px; padding:8px 16px;
                            background:#fef2f2; border-left:4px solid #ef4444; border-radius:4px; margin:4px 0;">
                    <span style="font-weight:700; color:#ef4444;">C{layer}</span>
                    <span style="color:#dc2626;">Erreur : {log_entry.get('detail','')}</span>
                </div>
                """, unsafe_allow_html=True)

    # Result details
    if row["matched"]:
        st.markdown("---")
        st.markdown("#### Resultat du matching")
        col1, col2 = st.columns(2)
        with col1:
            st.success(f"**Methode** : {row['method']}")
            st.success(f"**Confiance** : {row['confidence']:.0%}")
            if row["flags"]:
                st.warning(f"**Flags** : {row['flags']}")
        with col2:
            st.info(f"**Factures matchees** : {row['invoices_matched']}")
            if ctx and ctx.final_match:
                st.info(f"**Allocation** : {ctx.final_match.allocated}")
    else:
        st.markdown("---")
        st.error("**Aucun match automatique** — ce paiement a ete envoye en revue humaine (C6).")
        st.markdown("Couches tentees : " + row["layers_attempted"])
        st.markdown("""
        **Raisons possibles :**
        - Label cryptique sans reference identifiable
        - Montant ne correspondant a aucune facture ouverte
        - Debiteur non identifie via IBAN
        - Combinaison de factures trop complexe
        """)
