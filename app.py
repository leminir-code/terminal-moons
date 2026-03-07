# ============================================================
# app.py — Terminal Moons Pro (Version Intégrée & Corrigée)
# Ichimoku + Fibonacci + Bracket Order TWS
# ============================================================

import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime

# ── Connexion TWS via tunnel Cloudflare ─────────────────────
import requests as _req

TUNNEL_URL = "https://acceptable-ordinance-linda-specialized.trycloudflare.com"
SECRET     = "moons2026"

def executer_plan_moons(ticker_str, qty, entry_px, stop_px, tp_px, mode="ACHAT (Long)"):
    try:
        r = _req.post(
            f"{TUNNEL_URL}/trade",
            json={
                "secret": SECRET,
                "ticker": ticker_str,
                "qty":    qty,
                "entry":  entry_px,
                "stop":   stop_px,
                "tp":     tp_px,
                "mode":   mode
            },
            timeout=15
        )
        return r.json().get("succes", False)
    except Exception as e:
        return False

# ── Configuration page ───────────────────────────────────────
st.set_page_config(
    page_title="Terminal Moons Pro",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ── CSS Bloomberg Style ──────────────────────────────────────
st.markdown("""
<style>
    .stApp { background-color: #1e1e1e !important; color: #e0e0e0; }
    section[data-testid="stSidebar"] { background-color: #252525 !important; border-right: 1px solid #444; }
    section[data-testid="stSidebar"] * { color: #d0d0d0 !important; }
    [data-testid="stMetric"] { background: #2a2a2a !important; border: 1px solid #444; border-top: 3px solid #f5a623; border-radius: 4px; padding: 12px 16px; }
    [data-testid="stMetricLabel"] { color: #999 !important; font-size: 11px !important; text-transform: uppercase; letter-spacing: 1px; }
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 22px !important; font-weight: 700; }
    h1, h2, h3 { color: #ffffff !important; }
    h1 { border-bottom: 2px solid #f5a623; padding-bottom: 8px; }
    thead tr th { background-color: #333 !important; color: #f5a623 !important; font-size: 11px; text-transform: uppercase; }
    tbody tr:nth-child(even) { background-color: #2a2a2a !important; }
    td { color: #e0e0e0 !important; font-size: 13px; }
    .stButton > button[kind="primary"] { background: linear-gradient(135deg, #f5a623, #e8941a) !important; color: #1a1a1a !important; font-weight: 900 !important; border: none !important; border-radius: 4px !important; text-transform: uppercase; letter-spacing: 1px; }
    .stButton > button[kind="primary"]:hover { background: linear-gradient(135deg, #ffd166, #f5a623) !important; box-shadow: 0 4px 12px rgba(245,166,35,0.4) !important; }
    .stButton > button:not([kind="primary"]) { background: #333 !important; color: #aaa !important; border: 1px solid #555 !important; border-radius: 4px !important; }
    .status-box { padding: 10px 16px; border-radius: 3px; font-weight: bold; margin: 4px 0; font-size: 13px; }
    .alert-danger { background: #2a1515; border-left: 4px solid #e53935; color: #ef9a9a; }
    .alert-ok { background: #152a1a; border-left: 4px solid #43a047; color: #a5d6a7; }
    .alert-warn { background: #2a2010; border-left: 4px solid #f5a623; color: #ffe082; }
    .stTextInput input, .stNumberInput input { background: #333 !important; border: 1px solid #555 !important; color: #fff !important; border-radius: 3px !important; }
    hr { border-color: #444 !important; }
    .stTabs [data-baseweb="tab-list"] { background: #2a2a2a !important; border-bottom: 2px solid #f5a623; }
    .stTabs [data-baseweb="tab"] { color: #aaa !important; font-weight: 600; }
    .stTabs [aria-selected="true"] { color: #f5a623 !important; }
    [data-testid="stExpander"] { background: #2a2a2a !important; border: 1px solid #444; border-radius: 4px; }
    ::-webkit-scrollbar { width: 6px; }
    ::-webkit-scrollbar-track { background: #1e1e1e; }
    ::-webkit-scrollbar-thumb { background: #555; border-radius: 3px; }
    ::-webkit-scrollbar-thumb:hover { background: #f5a623; }
</style>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    st.divider()

    ticker = st.text_input("🔍 Symbole", value="NVDA").upper().strip()
    capital = st.number_input("💰 Capital ($)", value=10000, min_value=1000, step=500)
    mode = st.radio(
        "📊 Direction du Trade",
        ["ACHAT (Long)", "VENTE (Short)"],
        help="Long = vous pariez à la hausse | Short = vous pariez à la baisse"
    )
    risk_pc = st.slider(
        "⚠️ Risque par trade (%)", 0.5, 15.0, 5.0, 0.5,
        help="% du capital risqué sur ce trade. 5% recommandé pour débutants."
    ) / 100
    lookback_max = st.slider(
        "📅 Fenêtre Swing (jours)", 15, 120, 91,
        help="Nombre de jours pour chercher les points pivots Fibonacci"
    )

    st.divider()
    st.markdown("**🔌 Connexion TWS**")
    tws_port = st.number_input("Port TWS", value=7497, step=1)
    st.caption("Paper trading: 7497 | Live: 7496")
    st.caption("⚠️ TWS doit être ouvert avec l'API activée")


# ════════════════════════════════════════════════════════════
# FONCTIONS TECHNIQUES
# ════════════════════════════════════════════════════════════

@st.cache_data(ttl=900)
def load_data(ticker: str):
    """Télécharge les données journalières (1an) et 15 min (60 jours)."""
    df_d  = yf.download(ticker, period="1y",  interval="1d",  auto_adjust=True, progress=False)
    df_15 = yf.download(ticker, period="60d", interval="15m", auto_adjust=True, progress=False)
    if isinstance(df_d.columns,  pd.MultiIndex): df_d.columns  = df_d.columns.get_level_values(0)
    if isinstance(df_15.columns, pd.MultiIndex): df_15.columns = df_15.columns.get_level_values(0)
    return df_d, df_15


def get_ichimoku(data: pd.DataFrame):
    h9,  l9  = data['High'].rolling(9).max(),  data['Low'].rolling(9).min()
    h26, l26 = data['High'].rolling(26).max(), data['Low'].rolling(26).min()
    h52, l52 = data['High'].rolling(52).max(), data['Low'].rolling(52).min()
    tenkan = (h9  + l9)  / 2
    kijun  = (h26 + l26) / 2
    sa     = ((tenkan + kijun) / 2).shift(26)
    sb     = ((h52 + l52) / 2).shift(26)
    chikou = data['Close'].shift(-26)
    return tenkan, kijun, sa, sb, chikou


def get_ichimoku_score(data: pd.DataFrame, mode_trade: str):
    if len(data) < 52:
        return 0, None, None, None, None

    tenkan, kijun, sa, sb, _ = get_ichimoku(data)
    px = data['Close'].iloc[-1]
    sa_last = sa.iloc[-1]
    sb_last = sb.iloc[-1]

    if pd.isna(sa_last) or pd.isna(sb_last):
        return 0, sa, sb, tenkan, kijun

    chikou_bull = px > data['Close'].shift(26).iloc[-1]
    chikou_bear = px < data['Close'].shift(26).iloc[-1]

    if mode_trade == "ACHAT (Long)":
        conds = [
            px > max(sa_last, sb_last),
            sa_last > sb_last,
            tenkan.iloc[-1] > kijun.iloc[-1],
            chikou_bull
        ]
    else:
        conds = [
            px < min(sa_last, sb_last),
            sa_last < sb_last,
            tenkan.iloc[-1] < kijun.iloc[-1],
            chikou_bear
        ]

    return sum(conds), sa, sb, tenkan, kijun


def find_dynamic_swings(data: pd.DataFrame, mode_trade: str, atr_val: float):
    col = 'High' if mode_trade == "ACHAT (Long)" else 'Low'
    price_avg = data['Close'].mean()
    dynamic_dist = max(3, int((atr_val / price_avg) * 500))
    swings = []

    df_temp = data.copy().sort_values(
        by=col,
        ascending=(mode_trade == "VENTE (Short)")
    )

    for idx, row in df_temp.iterrows():
        idx_naive = idx.replace(tzinfo=None) if hasattr(idx, 'tzinfo') else idx
        too_close = False
        for s in swings:
            s_dt = pd.to_datetime(s['Date'])
            s_dt = s_dt.replace(tzinfo=None) if hasattr(s_dt, 'tzinfo') else s_dt
            if abs((idx_naive - s_dt).days) < dynamic_dist:
                too_close = True
                break
        if not too_close:
            swings.append({
                'Date': idx.strftime('%Y-%m-%d'),
                'Prix': round(row[col], 2)
            })
        if len(swings) >= 2:
            break

    return pd.DataFrame(swings), dynamic_dist


def valider_plan(mode_trade, entry, stop, tp, px_actuel, score, qty):
    checks = []

    # Check 1 : Score Ichimoku
    if score >= 3:
        checks.append(("✅", "Score Ichimoku", f"{score}/4 — Signal fort", "ok"))
    elif score == 2:
        checks.append(("⚠️", "Score Ichimoku", f"{score}/4 — Signal modéré", "warn"))
    else:
        checks.append(("❌", "Score Ichimoku", f"{score}/4 — Signal faible", "danger"))

    # Check 2 : Prix dans la zone d'entrée (±2%)
    dist_entry = abs(px_actuel - entry) / entry
    if dist_entry <= 0.02:
        checks.append(("✅", "Zone d'entrée", f"Prix actuel {px_actuel:.2f}$ proche de {entry:.2f}$ ({dist_entry*100:.1f}%)", "ok"))
    elif dist_entry <= 0.05:
        checks.append(("⚠️", "Zone d'entrée", f"Prix {px_actuel:.2f}$ à {dist_entry*100:.1f}% de l'entrée", "warn"))
    else:
        checks.append(("❌", "Zone d'entrée", f"Prix trop éloigné de l'entrée ({dist_entry*100:.1f}%)", "danger"))

    # Check 3 : Ratio R:R
    risk   = abs(entry - stop)
    reward = abs(tp - entry)
    rr = reward / risk if risk > 0 else 0
    if rr >= 2.0:
        checks.append(("✅", "Ratio R:R", f"1:{rr:.2f} — Excellent", "ok"))
    elif rr >= 1.5:
        checks.append(("⚠️", "Ratio R:R", f"1:{rr:.2f} — Acceptable", "warn"))
    else:
        checks.append(("❌", "Ratio R:R", f"1:{rr:.2f} — Insuffisant (min 1:1.5)", "danger"))

    # Check 4 : Cohérence des niveaux
    if mode_trade == "ACHAT (Long)" and stop < entry < tp:
        checks.append(("✅", "Cohérence niveaux", f"SL {stop:.2f} < Entry {entry:.2f} < TP {tp:.2f}", "ok"))
    elif mode_trade == "VENTE (Short)" and stop > entry > tp:
        checks.append(("✅", "Cohérence niveaux", f"SL {stop:.2f} > Entry {entry:.2f} > TP {tp:.2f}", "ok"))
    else:
        checks.append(("❌", "Cohérence niveaux", "Niveaux de prix incohérents — vérifier la direction", "danger"))

    # Check 5 : Quantité non nulle
    if qty > 0:
        checks.append(("✅", "Quantité", f"{qty} actions — Capital exposé calculable", "ok"))
    else:
        checks.append(("❌", "Quantité", "Quantité = 0 — Risque par action trop faible ou capital insuffisant", "danger"))

    return checks


# ════════════════════════════════════════════════════════════
# LOGIQUE PRINCIPALE
# ════════════════════════════════════════════════════════════
st.title("🏦 Terminal Moons Pro")
st.caption("Analyse Ichimoku × Fibonacci × Exécution TWS Interactive Brokers")

try:
    # ── Chargement données ───────────────────────────────────
    with st.spinner(f"Chargement des données pour {ticker}..."):
        # FIX #4 : bouton de rechargement forcé pour contourner le cache en cas d'erreur
        if st.sidebar.button("🔄 Forcer le rechargement des données"):
            st.cache_data.clear()
            st.rerun()
        df_d, df_15 = load_data(ticker)

    # ── FIX #9 : validation ticker ──────────────────────────
    if df_d.empty or len(df_d) < 52:
        st.error(
            f"❌ Données insuffisantes ou symbole invalide pour **{ticker}**.\n\n"
            "**Formats acceptés :** Symboles NYSE/NASDAQ uniquement (ex: NVDA, AAPL, MSFT).\n"
            "Les symboles étrangers (AAPL.PA), crypto (BTC-USD) ou indices (^SPX) ne sont pas supportés."
        )
        st.stop()
    if df_15.empty or len(df_15) < 50:
        st.warning(f"⚠️ Données 15 min limitées pour {ticker}. L'analyse reste possible mais moins précise.")

    # ── FIX #7 : détection marché fermé ─────────────────────
    derniere_bougie_15m = df_15.index[-1]
    now_utc = pd.Timestamp.now(tz='UTC')
    # Normaliser la timezone
    if derniere_bougie_15m.tzinfo is None:
        derniere_bougie_15m_utc = derniere_bougie_15m.tz_localize('UTC')
    else:
        derniere_bougie_15m_utc = derniere_bougie_15m.tz_convert('UTC')
    age_minutes = (now_utc - derniere_bougie_15m_utc).total_seconds() / 60

    MODE_DONNEES_PERIMEES = age_minutes > 30  # marché fermé ou weekend
    if MODE_DONNEES_PERIMEES:
        st.warning(
            f"⚠️ **Mode données périmées** — Dernière bougie 15 min : "
            f"`{derniere_bougie_15m.strftime('%Y-%m-%d %H:%M')} UTC` "
            f"({age_minutes/60:.1f}h). "
            "Le marché est probablement fermé. Les validations de zone d'entrée sont indicatives uniquement. "
            "Les niveaux Fibonacci et le plan de trade restent valides pour planification."
        )

    # ── Calculs principaux ───────────────────────────────────
    px_actuel = float(df_15['Close'].iloc[-1])

    # FIX #5 : ATR calculé sur la fenêtre lookback, pas sur 1 an complet
    df_lookback = df_d.tail(lookback_max).copy()
    atr_lookback = float((df_lookback['High'] - df_lookback['Low']).rolling(14).mean().dropna().iloc[-1])

    swings_df, dist_calculee = find_dynamic_swings(df_lookback, mode, atr_lookback)

    if swings_df.empty or len(swings_df) < 2:
        st.error("❌ Impossible de trouver 2 points pivots valides. Augmentez la fenêtre swing.")
        st.stop()

    t1_pivot = float(swings_df.iloc[0]['Prix'])
    base_ref = (
        float(df_lookback['Low'].min())  if mode == "ACHAT (Long)"
        else float(df_lookback['High'].max())
    )
    diff = abs(t1_pivot - base_ref)

    # Niveaux Fibonacci
    if mode == "ACHAT (Long)":
        f_entree  = t1_pivot - (0.618 * diff)
        f_soldes  = t1_pivot - (0.786 * diff)
        f_stop    = t1_pivot - (0.950 * diff)
        tp2_final = t1_pivot + (0.618 * diff)
        tp3_max   = t1_pivot + (1.618 * diff)
    else:
        f_entree  = t1_pivot + (0.618 * diff)
        f_soldes  = t1_pivot + (0.786 * diff)
        f_stop    = t1_pivot + (0.950 * diff)
        tp2_final = t1_pivot - (0.618 * diff)
        tp3_max   = t1_pivot - (1.618 * diff)

    tp1_secure = (f_entree + tp2_final) / 2

    # ── Ichimoku ─────────────────────────────────────────────
    score_trend, sa_d, sb_d, tenkan_d, kijun_d = get_ichimoku_score(df_d, mode)

    # FIX #2 : score 15 min pour détecter divergence avec le journalier
    score_15m, sa_15_score, sb_15_score, tenkan_15_score, kijun_15_score = get_ichimoku_score(df_15, mode)

    trend_label = (
        "HAUSSIER 📈" if score_trend >= 3
        else "BAISSIER 📉" if score_trend <= 1
        else "NEUTRE ⚖️"
    )
    trend_color = (
        "#00e676" if "HAUSSIER" in trend_label
        else "#ff4444" if "BAISSIER" in trend_label
        else "#ffb300"
    )

    # FIX #3 : calcul quantité avec sécurité qty=0
    dollar_risk_per_share = abs(f_entree - f_stop)
    min_risk_threshold = px_actuel * 0.005
    if dollar_risk_per_share > min_risk_threshold:
        qty = int((capital * risk_pc) / dollar_risk_per_share)
    else:
        qty = 0

    # ── Choix du TP par l'utilisateur (FIX #8) ──────────────
    tp_choice = st.sidebar.radio(
        "🎯 Take Profit cible",
        ["TP1 — Sécurisé (50%)", "TP2 — Objectif Principal"],
        help="TP1 = point médian entre entrée et TP2 (sortie partielle sécurisée)\nTP2 = objectif principal Fibonacci"
    )
    tp_actif = tp1_secure if tp_choice == "TP1 — Sécurisé (50%)" else tp2_final
    tp_label  = "TP1" if tp_choice == "TP1 — Sécurisé (50%)" else "TP2"

    # ════════════════════════════════════════════════════════
    # AFFICHAGE
    # ════════════════════════════════════════════════════════
    st.divider()

    # ── Header prix + trend ──────────────────────────────────
    col_h1, col_h2 = st.columns([2, 1])
    with col_h1:
        prix_label = f"{px_actuel:.2f} $"
        if MODE_DONNEES_PERIMEES:
            prix_label += " ⏸ (périmé)"
        st.markdown(
            f"<h1 style='margin:0'>{ticker} <span style='color:#00c9ff'>{prix_label}</span></h1>",
            unsafe_allow_html=True
        )
        st.markdown(
            f"<h3 style='color:{trend_color}; margin:0'>Marché {trend_label} — Score Ichimoku Journalier : {score_trend}/4</h3>",
            unsafe_allow_html=True
        )

        # FIX #2 : avertissement divergence timeframes
        if score_trend >= 3 and score_15m <= 1:
            st.markdown(
                "<div style='background:#2a1010;border-left:4px solid #ff4444;padding:8px 14px;border-radius:3px;margin-top:8px;font-size:13px;color:#ef9a9a'>"
                f"⚠️ <b>Divergence de timeframe détectée</b> — Score journalier : {score_trend}/4 (HAUSSIER) "
                f"mais score 15 min : {score_15m}/4 (BAISSIER). "
                "Attendre l'alignement des deux timeframes avant d'entrer en position."
                "</div>",
                unsafe_allow_html=True
            )
        elif score_trend <= 1 and score_15m >= 3:
            st.markdown(
                "<div style='background:#2a1010;border-left:4px solid #ff4444;padding:8px 14px;border-radius:3px;margin-top:8px;font-size:13px;color:#ef9a9a'>"
                f"⚠️ <b>Divergence de timeframe détectée</b> — Score journalier : {score_trend}/4 (BAISSIER) "
                f"mais score 15 min : {score_15m}/4 (HAUSSIER). "
                "Le graphique 15 min contre-indique la tendance de fond."
                "</div>",
                unsafe_allow_html=True
            )
        elif score_trend >= 3 and score_15m >= 3:
            st.markdown(
                f"<div style='background:#0d2010;border-left:4px solid #00e676;padding:8px 14px;border-radius:3px;margin-top:8px;font-size:13px;color:#a5d6a7'>"
                f"✅ <b>Alignement timeframes</b> — Journalier {score_trend}/4 et 15 min {score_15m}/4 concordent."
                f"</div>",
                unsafe_allow_html=True
            )
        else:
            st.markdown(
                f"<div style='background:#252010;border-left:4px solid #ffb300;padding:8px 14px;border-radius:3px;margin-top:8px;font-size:13px;color:#ffe082'>"
                f"⚠️ Score journalier : {score_trend}/4 · Score 15 min : {score_15m}/4 — Alignement partiel."
                f"</div>",
                unsafe_allow_html=True
            )

    with col_h2:
        direction_color = "#00e676" if mode == "ACHAT (Long)" else "#ff4444"
        st.markdown(
            f"<div style='background:{direction_color}22; border:2px solid {direction_color}; "
            f"border-radius:8px; padding:14px; text-align:center;'>"
            f"<div style='font-size:24px; font-weight:900; color:{direction_color}'>"
            f"{'▲ LONG' if mode == 'ACHAT (Long)' else '▼ SHORT'}</div>"
            f"<div style='color:#888; font-size:11px'>Risque {risk_pc*100:.1f}% · ${capital*risk_pc:.0f} max</div>"
            f"<div style='color:#888; font-size:11px'>TP actif : {tp_label}</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.divider()

    # ── Métriques principales ────────────────────────────────
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("🎯 T1 — Pivot",      swings_df.iloc[0]['Date'], f"{t1_pivot:.2f} $")
    c2.metric("📥 C2 — Entrée",     f"{f_entree:.2f} $",       delta=f"{((f_entree/px_actuel-1)*100):+.1f}% vs prix actuel")
    c3.metric(f"✅ {tp_label} — Objectif", f"{tp_actif:.2f} $", delta=f"+{abs(tp_actif-f_entree):.2f} $")
    c4.metric("🛑 Stop Loss",       f"{f_stop:.2f} $",         delta=f"-{abs(f_stop-f_entree):.2f} $", delta_color="inverse")
    c5.metric("📦 Quantité",        f"{qty} actions",          f"${qty * f_entree:.0f} exposé" if qty > 0 else "⛔ Insuffisant")

    st.divider()

    # ── Plan de trade complet ────────────────────────────────
    with st.expander("📋 Plan de Trade Complet", expanded=True):
        col_plan1, col_plan2 = st.columns(2)

        with col_plan1:
            st.markdown("**Niveaux Fibonacci**")
            plan_df = pd.DataFrame({
                "Niveau": ["T1 (Pivot)", "C2 (Entrée 61.8%)", "SOLDES (78.6%)", "TP1 (50%)", "TP2 Principal", "TP3 Extension 161.8%", "STOP (95%)"],
                "Prix ($)": [
                    f"{t1_pivot:.2f}",  f"{f_entree:.2f}",
                    f"{f_soldes:.2f}",  f"{tp1_secure:.2f}",
                    f"{tp2_final:.2f}", f"{tp3_max:.2f}",
                    f"{f_stop:.2f}"
                ],
                "Rôle": [
                    "Point pivot de référence",
                    "Zone d'achat/vente optimale",
                    "Sortie partielle recommandée",
                    "TP sécurisé (50% de la position)",
                    "Objectif principal",
                    "Extension — marché très fort",
                    "Invalidation du scénario"
                ],
                "Actif pour TWS": [
                    "—", "✅ Entrée", "—",
                    "✅ si TP1 sélectionné",
                    "✅ si TP2 sélectionné",
                    "—", "✅ Stop"
                ]
            })
            st.dataframe(plan_df, hide_index=True, use_container_width=True)

            # FIX #1 : affichage des 2 pivots détectés + explication
            st.markdown("---")
            st.markdown("**🔍 Pivots détectés automatiquement**")
            st.caption(
                f"T1 (pivot actif) = `{t1_pivot:.2f}$` · "
                f"2ème pivot détecté = `{float(swings_df.iloc[1]['Prix']):.2f}$` (affiché sur le graphique, non utilisé dans le calcul Fibonacci)"
            )
            st.dataframe(swings_df, hide_index=True, use_container_width=True)

            # FIX #1 : pivot manuel optionnel
            st.markdown("**✏️ Remplacer T1 par un pivot manuel**")
            use_manual_pivot = st.checkbox("Utiliser un pivot manuel comme T1")
            if use_manual_pivot:
                pivot_manuel = st.number_input(
                    "T1 Manuel ($)",
                    value=float(t1_pivot),
                    step=0.01,
                    format="%.2f",
                    help="Entrez le prix du sommet (Long) ou creux (Short) que vous souhaitez utiliser comme T1"
                )
                diff_manuel = abs(pivot_manuel - base_ref)
                if mode == "ACHAT (Long)":
                    f_entree  = pivot_manuel - (0.618 * diff_manuel)
                    f_soldes  = pivot_manuel - (0.786 * diff_manuel)
                    f_stop    = pivot_manuel - (0.950 * diff_manuel)
                    tp2_final = pivot_manuel + (0.618 * diff_manuel)
                    tp3_max   = pivot_manuel + (1.618 * diff_manuel)
                else:
                    f_entree  = pivot_manuel + (0.618 * diff_manuel)
                    f_soldes  = pivot_manuel + (0.786 * diff_manuel)
                    f_stop    = pivot_manuel + (0.950 * diff_manuel)
                    tp2_final = pivot_manuel - (0.618 * diff_manuel)
                    tp3_max   = pivot_manuel - (1.618 * diff_manuel)
                tp1_secure = (f_entree + tp2_final) / 2
                tp_actif   = tp1_secure if tp_choice == "TP1 — Sécurisé (50%)" else tp2_final
                t1_pivot   = pivot_manuel
                st.success(f"✅ Pivot manuel T1 = {pivot_manuel:.2f}$ — Niveaux Fibonacci recalculés.")

        with col_plan2:
            st.markdown("**Statistiques du Trade**")
            risk_dollars  = abs(f_entree - f_stop)
            rew_dollars   = abs(tp_actif - f_entree)
            rr_ratio      = rew_dollars / risk_dollars if risk_dollars > 0 else 0
            max_loss_trade = qty * risk_dollars
            max_gain_trade = qty * rew_dollars

            stats_df = pd.DataFrame({
                "Paramètre": ["Capital risqué", f"Gain potentiel {tp_label}", "Ratio R:R", "Perte max ($)", f"Gain max {tp_label} ($)", "Gain max TP3 ($)", "Filtre Swing (jours)", "ATR fenêtre"],
                "Valeur": [
                    f"${capital * risk_pc:.2f} ({risk_pc*100:.1f}%)",
                    f"${max_gain_trade:.2f}",
                    f"1:{rr_ratio:.2f}",
                    f"-${max_loss_trade:.2f}",
                    f"+${max_gain_trade:.2f}",
                    f"+${qty * abs(tp3_max - f_entree):.2f}",
                    f"{dist_calculee} jours",
                    f"${atr_lookback:.2f} (sur {lookback_max}j)"  # FIX #5 visible
                ]
            })
            st.dataframe(stats_df, hide_index=True, use_container_width=True)

    # ── Validation pré-exécution ─────────────────────────────
    st.markdown("### 🔍 Validation Pré-Exécution")
    checks = valider_plan(mode, f_entree, f_stop, tp_actif, px_actuel, score_trend, qty)  # FIX #3
    nb_fail = sum(1 for c in checks if c[3] == "danger")
    nb_warn = sum(1 for c in checks if c[3] == "warn")

    col_v = st.columns(len(checks))
    for i, (icon, title, msg, status) in enumerate(checks):
        css_class = f"alert-{status}"
        with col_v[i]:
            st.markdown(
                f"<div class='status-box {css_class}'>{icon} <b>{title}</b><br>"
                f"<small>{msg}</small></div>",
                unsafe_allow_html=True
            )

    st.divider()

    # ── Boutons d'action ─────────────────────────────────────
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("📊 Analyser la Confluence Swing"):
            st.markdown("**Points pivots détectés :**")
            st.dataframe(swings_df, hide_index=True, use_container_width=True)

    with col_btn2:
        btn_disabled = nb_fail > 0
        btn_label = (
            f"🚀 ENVOYER LE PLAN À TWS ({qty} × {ticker} @ {f_entree:.2f}$ → {tp_label} {tp_actif:.2f}$)"
            if not btn_disabled
            else f"⛔ EXÉCUTION BLOQUÉE — {nb_fail} validation(s) échouée(s)"
        )

        if nb_warn > 0 and not btn_disabled:
            st.warning(f"⚠️ {nb_warn} avertissement(s) — vous pouvez continuer mais vérifiez les conditions de marché.")

        # FIX #6 : récapitulatif mode avant envoi
        if not btn_disabled:
            dir_color = "#00e676" if mode == "ACHAT (Long)" else "#ff4444"
            dir_icon  = "▲" if mode == "ACHAT (Long)" else "▼"
            st.markdown(
                f"<div style='background:{dir_color}15;border:1px solid {dir_color}44;border-radius:4px;"
                f"padding:8px 12px;font-size:12px;margin-bottom:8px;'>"
                f"<b style='color:{dir_color}'>{dir_icon} {mode}</b> · "
                f"Entrée <b>{f_entree:.2f}$</b> · Stop <b>{f_stop:.2f}$</b> · "
                f"{tp_label} <b>{tp_actif:.2f}$</b> · Qté <b>{qty}</b> · R:R <b>1:{abs(tp_actif-f_entree)/abs(f_entree-f_stop):.2f}</b>"
                f"</div>",
                unsafe_allow_html=True
            )

        execute_btn = st.button(
            btn_label,
            disabled=btn_disabled,
            type="primary" if not btn_disabled else "secondary"
        )

        if execute_btn:
            # FIX #6 : vérification finale cohérence mode/niveaux avant envoi
            coherent = (
                (mode == "ACHAT (Long)"  and f_stop < f_entree < tp_actif) or
                (mode == "VENTE (Short)" and f_stop > f_entree > tp_actif)
            )
            if not coherent:
                st.error(
                    f"⛔ Incohérence détectée juste avant l'envoi : les niveaux ne correspondent pas "
                    f"à la direction {mode}. Ordre annulé par sécurité."
                )
            elif qty == 0:
                st.error("⛔ Quantité = 0. Ordre non envoyé.")
            else:
                with st.spinner(f"Connexion à TWS et envoi des ordres pour {ticker}..."):
                    succes = executer_plan_moons(
                        ticker_str=ticker,
                        qty=qty,
                        entry_px=f_entree,
                        stop_px=f_stop,
                        tp_px=tp_actif,
                        mode=mode
                    )

                if succes:
                    st.success(f"✅ Bracket Order envoyé avec succès !")
                    st.markdown(f"""
                    | Paramètre | Valeur |
                    |---|---|
                    | Titre | **{ticker}** |
                    | Direction | **{mode}** |
                    | Quantité | **{qty} actions** |
                    | Entrée (C2) | **{f_entree:.2f} $** |
                    | Stop Loss | **{f_stop:.2f} $** |
                    | {tp_label} | **{tp_actif:.2f} $** |
                    | Capital exposé | **${qty * f_entree:.2f}** |
                    """)
                    st.balloons()
                else:
                    st.error("❌ Échec de l'envoi à TWS.")
                    st.markdown("""
                    **Checklist de dépannage :**
                    - TWS est-il ouvert et connecté ?
                    - Le port 7497 est-il activé dans TWS > Global Configuration > API > Settings ?
                    - Êtes-vous bien sur un compte **paper trading** (commence par 'DU') ?
                    - L'option *Enable ActiveX and Socket Clients* est-elle cochée dans TWS ?
                    """)

    # ════════════════════════════════════════════════════════
    # GRAPHIQUE PRINCIPAL
    # ════════════════════════════════════════════════════════
    st.divider()
    st.markdown("### 📈 Graphique — Bougies 15 min + Ichimoku + Fibonacci")

    df_plot = df_15.tail(600).copy()

    _, sa_15, sb_15, tenkan_15, kijun_15 = get_ichimoku_score(df_15, mode)

    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.04,
        row_heights=[0.72, 0.28],
        subplot_titles=[f"{ticker} — 15 min", "Volume"]
    )

    # Bougies
    fig.add_trace(go.Candlestick(
        x=df_plot.index,
        open=df_plot['Open'], high=df_plot['High'],
        low=df_plot['Low'],   close=df_plot['Close'],
        name='Prix',
        increasing_line_color='#00e676',
        decreasing_line_color='#ff4444',
    ), row=1, col=1)

    # Nuage Ichimoku 15 min
    if sa_15 is not None and sb_15 is not None:
        fig.add_trace(go.Scatter(
            x=df_15.index, y=sa_15,
            line=dict(color='rgba(0,230,118,0.4)', width=1),
            name='Senkou A', showlegend=True
        ), row=1, col=1)
        fig.add_trace(go.Scatter(
            x=df_15.index, y=sb_15,
            line=dict(color='rgba(255,68,68,0.4)', width=1),
            fill='tonexty',
            fillcolor='rgba(100,100,200,0.07)',
            name='Senkou B', showlegend=True
        ), row=1, col=1)

    if tenkan_15 is not None:
        fig.add_trace(go.Scatter(
            x=df_15.index, y=tenkan_15,
            line=dict(color='#00c9ff', width=1.2),
            name='Tenkan-sen'
        ), row=1, col=1)
    if kijun_15 is not None:
        fig.add_trace(go.Scatter(
            x=df_15.index, y=kijun_15,
            line=dict(color='#ffb300', width=1.2),
            name='Kijun-sen'
        ), row=1, col=1)

    # Lignes Fibonacci avec TP actif mis en évidence
    levels = {
        "T1 Pivot":     (t1_pivot,   "white",   "dash",    1.2),
        "C2 Entrée":    (f_entree,   "#00c9ff", "dot",     1.5),
        "SOLDES 78.6%": (f_soldes,   "#ffd700", "dot",     1.0),
        "TP1 50%":      (tp1_secure, "#ffa500", "dot",     1.2 if tp_choice.startswith("TP1") else 0.7),
        "TP2":          (tp2_final,  "#00e676", "dashdot", 2.0 if tp_choice.startswith("TP2") else 0.7),
        "TP3 161.8%":   (tp3_max,    "#00ffff", "dot",     0.8),
        "STOP":         (f_stop,     "#ff4444", "dash",    1.5),
    }
    for lbl, (val, color, dash, width) in levels.items():
        active_marker = " ◀ ACTIF" if (lbl == "TP1 50%" and tp_choice.startswith("TP1")) or (lbl == "TP2" and tp_choice.startswith("TP2")) else ""
        fig.add_hline(
            y=val,
            line=dict(color=color, dash=dash, width=width),
            annotation_text=f"  {lbl}{active_marker}: {val:.2f}$",
            annotation_position="top left",
            annotation_font=dict(color=color, size=10),
            row=1, col=1
        )

    # Lignes verticales pivots (les 2)
    for _, row_s in swings_df.iterrows():
        swing_dt = pd.to_datetime(row_s['Date'])
        if hasattr(df_plot.index, 'tz') and df_plot.index.tz is not None:
            swing_dt = swing_dt.tz_localize(df_plot.index.tz) if swing_dt.tzinfo is None else swing_dt.tz_convert(df_plot.index.tz)
        if swing_dt >= df_plot.index.min():
            fig.add_vline(
                x=swing_dt,
                line=dict(color='rgba(255,255,255,0.3)', dash='dash'),
                row=1, col=1
            )

    # Volume
    volume_colors = [
        '#00e676' if c >= o else '#ff4444'
        for c, o in zip(df_plot['Close'], df_plot['Open'])
    ]
    fig.add_trace(go.Bar(
        x=df_plot.index, y=df_plot['Volume'],
        marker_color=volume_colors, marker_opacity=0.6,
        name='Volume', showlegend=False
    ), row=2, col=1)

    fig.update_layout(
        template="plotly_dark",
        height=820,
        paper_bgcolor='#04070e',
        plot_bgcolor='#0a111f',
        font=dict(family="Courier New", color='#94a3b8'),
        xaxis_rangeslider_visible=False,
        showlegend=True,
        legend=dict(
            bgcolor='rgba(10,17,31,0.8)',
            bordercolor='#162035',
            borderwidth=1,
            font=dict(size=10)
        ),
        margin=dict(l=10, r=10, t=30, b=10)
    )
    fig.update_xaxes(gridcolor='#102030', showgrid=True)
    fig.update_yaxes(gridcolor='#102030', showgrid=True)

    st.plotly_chart(fig, use_container_width=True)

    # ── Footer ───────────────────────────────────────────────
    st.divider()
    st.caption(
        "⚠️ Terminal Moons Pro — Outil éducatif uniquement. "
        "Ne constitue pas un conseil financier. "
        "Testez toujours sur compte paper avant toute utilisation réelle. "
        f"Données mises à jour toutes les 15 min. Dernière analyse : {datetime.now().strftime('%H:%M:%S')}"
    )

except Exception as e:
    st.error(f"❌ Erreur inattendue : {e}")
    st.exception(e)
    st.info("💡 Vérifiez le symbole entré (NYSE/NASDAQ uniquement) et votre connexion internet.")
