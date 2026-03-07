# ============================================================
# agent_autonome.py — Robot de Trading Autonome v3
# Ichimoku  → Entrée + Stop Loss (dynamique, recalcul 15 min)
# Fibonacci → TP étendu (161.8% ou 261.8% du swing)
# R:R cible : 1:3 à 1:5
# Heures    : 9h30–16h00 EST | NYSE
# ============================================================

import time
import logging
import sqlite3
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time as dtime
import pytz
import sys
import os

# ── Connexion TWS via tunnel Cloudflare ─────────────────
import requests as _req

TUNNEL_URL = os.environ.get("TUNNEL_URL", "https://bat-visitors-cat-refresh.trycloudflare.com")
SECRET     = os.environ.get("SECRET", "moons2026")

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
        log.error(f"Tunnel erreur : {e}")
        return False

# ── Logging ──────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.expanduser('~/terminal_moons/robot.log')),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("agent_moons")

# ════════════════════════════════════════════════════════════
# CONFIGURATION
# ════════════════════════════════════════════════════════════

WATCHLIST = [
    # ── Actions US (NYSE / NASDAQ) ────────────────────────
    "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN",
    "TSLA", "META", "AMD", "AVGO", "QCOM",
    # ── ETFs liquides ─────────────────────────────────────
    "SPY", "QQQ", "IWM",
    # ── Crypto adjacent ───────────────────────────────────
    "COIN", "MSTR",
    # "BTCC"  ← retiré : TSX bloqué via API IBKR Canada
]

CAPITAL          = 10_000   # Capital total ($)
RISQUE_PAR_TRADE = 0.05     # 5% risqué par trade
MAX_POSITIONS    = 3        # Max positions simultanées
SCORE_MIN        = 3        # Score Ichimoku minimum (3 ou 4/4)
SCAN_INTERVAL    = 15       # Minutes entre chaque scan
RR_MIN           = 2.0      # R:R minimum (plus élevé grâce à Fibonacci)
PROXIMITY_CLOUD  = 0.03     # Prix doit être à ±3% du bord du nuage
TIMEZONE         = pytz.timezone('America/New_York')

# Niveaux Fibonacci pour le TP étendu (par ordre de préférence)
# 161.8% = extension classique | 261.8% = extension majeure
FIB_TP_LEVELS = [1.618, 2.618]

# ════════════════════════════════════════════════════════════
# BASE DE DONNÉES
# ════════════════════════════════════════════════════════════

DB_PATH = os.path.expanduser('~/terminal_moons/trades.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            date        TEXT,
            ticker      TEXT,
            mode        TEXT,
            qty         INTEGER,
            entry       REAL,
            stop        REAL,
            tp          REAL,
            tp_fib      TEXT,
            rr          REAL,
            score       INTEGER,
            sa          REAL,
            sb          REAL,
            tenkan      REAL,
            kijun       REAL,
            fib_swing_h REAL,
            fib_swing_l REAL,
            statut      TEXT DEFAULT 'OUVERT',
            created_at  TEXT DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    log.info("✅ Base de données initialisée")

def sauvegarder_trade(t, mode, qty, entry, stop, tp, tp_fib,
                      rr, score, sa, sb, tenkan, kijun, swing_h, swing_l):
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT INTO trades
           (date,ticker,mode,qty,entry,stop,tp,tp_fib,rr,score,
            sa,sb,tenkan,kijun,fib_swing_h,fib_swing_l)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (datetime.now().strftime('%Y-%m-%d %H:%M'),
         t, mode, qty, entry, stop, tp, tp_fib, rr, score,
         sa, sb, tenkan, kijun, swing_h, swing_l)
    )
    conn.commit()
    conn.close()

# ════════════════════════════════════════════════════════════
# ICHIMOKU — Calcul et score
# ════════════════════════════════════════════════════════════

def calculer_ichimoku(df):
    """Calcule toutes les composantes Ichimoku. Retourne dict ou None."""
    if len(df) < 52:
        return None

    h9,  l9  = df['High'].rolling(9).max(),  df['Low'].rolling(9).min()
    h26, l26 = df['High'].rolling(26).max(), df['Low'].rolling(26).min()
    h52, l52 = df['High'].rolling(52).max(), df['Low'].rolling(52).min()

    tenkan = (h9  + l9)  / 2
    kijun  = (h26 + l26) / 2
    sa     = ((tenkan + kijun) / 2).shift(26)
    sb     = ((h52 + l52) / 2).shift(26)
    chikou = df['Close'].shift(-26)

    t  = float(tenkan.iloc[-1])
    k  = float(kijun.iloc[-1])
    a  = float(sa.iloc[-1])
    b  = float(sb.iloc[-1])
    c  = float(chikou.iloc[-27]) if len(chikou) > 27 else float(df['Close'].iloc[-1])
    px = float(df['Close'].iloc[-1])

    if any(pd.isna(v) for v in [t, k, a, b]):
        return None

    return {
        'px':         px,
        'tenkan':     round(t, 4),
        'kijun':      round(k, 4),
        'sa':         round(a, 4),
        'sb':         round(b, 4),
        'chikou':     round(c, 4),
        'nuage_haut': round(max(a, b), 4),
        'nuage_bas':  round(min(a, b), 4),
    }

def calculer_score_ichimoku(ich, mode):
    """Score Ichimoku 0–4."""
    px = ich['px']
    if mode == "ACHAT (Long)":
        conds = [
            px > ich['nuage_haut'],
            ich['sa'] > ich['sb'],
            ich['tenkan'] > ich['kijun'],
            ich['chikou'] > ich['px'],
        ]
    else:
        conds = [
            px < ich['nuage_bas'],
            ich['sa'] < ich['sb'],
            ich['tenkan'] < ich['kijun'],
            ich['chikou'] < ich['px'],
        ]
    return sum(conds)

# ════════════════════════════════════════════════════════════
# FIBONACCI — TP étendu depuis le dernier swing
# ════════════════════════════════════════════════════════════

def trouver_swing(df, mode, fenetre=60):
    """
    Trouve le dernier swing significatif (haut ou bas)
    pour ancrer les extensions Fibonacci.

    LONG  → cherche le dernier creux majeur (swing low)
    SHORT → cherche le dernier sommet majeur (swing high)
    """
    df_look = df.tail(fenetre).copy()

    if mode == "ACHAT (Long)":
        # Swing low = le plus bas récent avant la montée
        swing_low_idx  = df_look['Low'].idxmin()
        swing_low      = float(df_look.loc[swing_low_idx, 'Low'])
        # Swing high = le plus haut avant ce creux (pour mesurer l'amplitude)
        df_before = df_look.loc[:swing_low_idx]
        if df_before.empty:
            return None
        swing_high = float(df_before['High'].max())
        return {
            'haut':      round(swing_high, 4),
            'bas':       round(swing_low,  4),
            'amplitude': round(swing_high - swing_low, 4),
        }
    else:
        # Swing high = le plus haut récent avant la baisse
        swing_high_idx = df_look['High'].idxmax()
        swing_high     = float(df_look.loc[swing_high_idx, 'High'])
        df_before = df_look.loc[:swing_high_idx]
        if df_before.empty:
            return None
        swing_low = float(df_before['Low'].min())
        return {
            'haut':      round(swing_high, 4),
            'bas':       round(swing_low,  4),
            'amplitude': round(swing_high - swing_low, 4),
        }

def calculer_tp_fibonacci(entry, swing, mode):
    """
    Calcule le TP étendu via extensions Fibonacci.

    LONG  :  TP = swing_bas + amplitude × niveau_fib
             → projection vers le haut depuis le creux
    SHORT :  TP = swing_haut - amplitude × niveau_fib
             → projection vers le bas depuis le sommet

    Sélectionne le premier niveau qui donne R:R ≥ RR_MIN.
    """
    if swing is None:
        return None, None

    amplitude = swing['amplitude']
    if amplitude <= 0:
        return None, None

    for niveau in FIB_TP_LEVELS:
        if mode == "ACHAT (Long)":
            tp = round(swing['bas'] + amplitude * niveau, 2)
            if tp > entry:
                return tp, f"Fib {niveau*100:.1f}%"
        else:
            tp = round(swing['haut'] - amplitude * niveau, 2)
            if tp < entry:
                return tp, f"Fib {niveau*100:.1f}%"

    return None, None

# ════════════════════════════════════════════════════════════
# PLAN COMPLET : Ichimoku + Fibonacci
# ════════════════════════════════════════════════════════════

def calculer_plan_complet(ich, swing, mode, capital, risque):
    """
    Construit le plan de trade complet :

    Ichimoku  → Entrée + Stop Loss
    Fibonacci → TP étendu (161.8% ou 261.8%)
    """
    px = ich['px']
    sa = ich['sa']
    sb = ich['sb']

    # ── Entrée et Stop (Ichimoku) ────────────────────────────
    if mode == "ACHAT (Long)":
        entry = round(max(sa, sb), 2)   # Bord supérieur du nuage
        stop  = round(min(sa, sb), 2)   # Bord inférieur du nuage

        if px <= entry:
            log.debug(f"  LONG rejeté : prix {px} ≤ bord nuage {entry}")
            return None
        dist = (px - entry) / entry
        if dist > PROXIMITY_CLOUD:
            log.debug(f"  LONG rejeté : prix trop loin du nuage ({dist*100:.1f}%)")
            return None

    else:  # SHORT
        entry = round(min(sa, sb), 2)   # Bord inférieur du nuage
        stop  = round(max(sa, sb), 2)   # Bord supérieur du nuage

        if px >= entry:
            log.debug(f"  SHORT rejeté : prix {px} ≥ bord nuage {entry}")
            return None
        dist = (entry - px) / entry
        if dist > PROXIMITY_CLOUD:
            log.debug(f"  SHORT rejeté : prix trop loin du nuage ({dist*100:.1f}%)")
            return None

    risk_per_share = abs(entry - stop)
    if risk_per_share < px * 0.002:
        log.debug(f"  Rejeté : nuage trop mince ({risk_per_share:.2f}$)")
        return None

    # ── TP étendu (Fibonacci) ────────────────────────────────
    tp, tp_label = calculer_tp_fibonacci(entry, swing, mode)

    # Fallback : TP classique R:R 1:2 si Fibonacci échoue
    if tp is None:
        tp       = round(entry + (entry - stop) * 2, 2) if mode == "ACHAT (Long)" \
                   else round(entry - (stop - entry) * 2, 2)
        tp_label = "R:R 1:2 (fallback)"
        log.debug(f"  Fibonacci TP non trouvé → fallback R:R 1:2")

    # ── Validation R:R ───────────────────────────────────────
    rr = abs(tp - entry) / risk_per_share
    if rr < RR_MIN:
        log.debug(f"  Rejeté : R:R 1:{rr:.2f} < minimum 1:{RR_MIN}")
        return None

    # ── Quantité ─────────────────────────────────────────────
    qty = int((capital * risque) / risk_per_share)
    if qty < 1:
        log.debug(f"  Rejeté : quantité = 0")
        return None

    return {
        'entry':    entry,
        'stop':     stop,
        'tp':       tp,
        'tp_label': tp_label,
        'qty':      qty,
        'rr':       round(rr, 2),
        'risk':     round(qty * risk_per_share, 2),
    }

# ════════════════════════════════════════════════════════════
# DONNÉES MARCHÉ
# ════════════════════════════════════════════════════════════

def get_data(ticker):
    try:
        df = yf.download(
            ticker, period="1y", interval="1d",
            auto_adjust=True, progress=False
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.empty or len(df) < 52:
            return None
        return df
    except Exception as e:
        log.warning(f"⚠️ Données {ticker} : {e}")
        return None

# ════════════════════════════════════════════════════════════
# GESTION POSITIONS
# ════════════════════════════════════════════════════════════

positions_actives = {}

def verifier_positions_actives():
    """Alerte si prix entre dans le nuage sur une position ouverte."""
    for ticker, pos in list(positions_actives.items()):
        df = get_data(ticker)
        if df is None:
            continue
        ich = calculer_ichimoku(df)
        if ich is None:
            continue
        px = ich['px']
        if ich['nuage_bas'] <= px <= ich['nuage_haut']:
            log.warning(
                f"⚠️ {ticker} : prix {px:.2f}$ entré dans le nuage "
                f"[{ich['nuage_bas']:.2f}–{ich['nuage_haut']:.2f}] "
                f"— signal invalidé, surveiller manuellement"
            )

# ════════════════════════════════════════════════════════════
# SCAN PRINCIPAL
# ════════════════════════════════════════════════════════════

def est_heures_marche():
    now = datetime.now(TIMEZONE)
    if now.weekday() >= 5:
        return False
    return dtime(9, 30) <= now.time() <= dtime(15, 45)

def scanner_et_executer():
    now_str = datetime.now(TIMEZONE).strftime('%H:%M')

    if not est_heures_marche():
        log.info(f"🕐 {now_str} EST — Hors heures NYSE")
        return

    slots = MAX_POSITIONS - len(positions_actives)
    if slots <= 0:
        log.info(f"📊 {MAX_POSITIONS}/{MAX_POSITIONS} positions actives")
        verifier_positions_actives()
        return

    log.info(f"🔍 {now_str} — Scan {len(WATCHLIST)} titres | {slots} slot(s) libre(s)")
    opportunites = []

    for ticker in WATCHLIST:
        if ticker in positions_actives:
            continue

        df = get_data(ticker)
        if df is None:
            continue

        ich = calculer_ichimoku(df)
        if ich is None:
            continue

        px = ich['px']

        # Ignorer si prix dans le nuage
        if ich['nuage_bas'] <= px <= ich['nuage_haut']:
            continue

        # Direction automatique
        mode = "ACHAT (Long)" if px > ich['nuage_haut'] else "VENTE (Short)"

        # Score Ichimoku
        score = calculer_score_ichimoku(ich, mode)
        if score < SCORE_MIN:
            continue

        # Swing pour Fibonacci
        swing = trouver_swing(df, mode)

        # Plan complet
        plan = calculer_plan_complet(ich, swing, mode, CAPITAL, RISQUE_PAR_TRADE)
        if plan is None:
            continue

        opportunites.append({
            'ticker': ticker,
            'mode':   mode,
            'score':  score,
            'plan':   plan,
            'ich':    ich,
            'swing':  swing,
        })

        log.info(
            f"  ✨ {ticker} {mode} | Score {score}/4 | "
            f"Entry={plan['entry']}$ (nuage) | SL={plan['stop']}$ | "
            f"TP={plan['tp']}$ ({plan['tp_label']}) | R:R=1:{plan['rr']}"
        )

    if not opportunites:
        log.info("📭 Aucun signal qualifié")
        return

    # Trier : score puis R:R
    opportunites.sort(key=lambda x: (x['score'], x['plan']['rr']), reverse=True)
    log.info(f"🏆 {len(opportunites)} signal(s) — exécution des {min(slots, len(opportunites))} meilleurs")

    for opp in opportunites[:slots]:
        ticker = opp['ticker']
        mode   = opp['mode']
        plan   = opp['plan']
        score  = opp['score']
        ich    = opp['ich']
        swing  = opp['swing'] or {'haut': 0, 'bas': 0}

        log.info(
            f"🚀 ORDRE {ticker} {mode} x{plan['qty']} | "
            f"Entry={plan['entry']}$ | SL={plan['stop']}$ | "
            f"TP={plan['tp']}$ ({plan['tp_label']}) | "
            f"Risque=${plan['risk']} | R:R=1:{plan['rr']}"
        )

        succes = executer_plan_moons(
            ticker_str = ticker,
            qty        = plan['qty'],
            entry_px   = plan['entry'],
            stop_px    = plan['stop'],
            tp_px      = plan['tp'],
            mode       = mode
        )

        if succes:
            positions_actives[ticker] = {**plan, 'mode': mode, 'score': score}
            sauvegarder_trade(
                ticker, mode, plan['qty'],
                plan['entry'], plan['stop'], plan['tp'], plan['tp_label'],
                plan['rr'], score,
                ich['sa'], ich['sb'], ich['tenkan'], ich['kijun'],
                swing['haut'], swing['bas']
            )
            log.info(f"✅ {ticker} — Bracket confirmé dans TWS")
        else:
            log.error(f"❌ {ticker} — Échec TWS (ouvert ? Port 7497 ?)")

# ════════════════════════════════════════════════════════════
# RAPPORT QUOTIDIEN
# ════════════════════════════════════════════════════════════

def rapport_quotidien():
    conn  = sqlite3.connect(DB_PATH)
    today = datetime.now().strftime('%Y-%m-%d')
    df    = pd.read_sql(
        f"SELECT * FROM trades WHERE date LIKE '{today}%'", conn
    )
    conn.close()
    log.info("=" * 55)
    log.info(f"📊 RAPPORT JOURNALIER — {today}")
    log.info(f"   Trades envoyés    : {len(df)}")
    log.info(f"   Positions actives : {list(positions_actives.keys())}")
    if not df.empty:
        log.info(f"   Score moyen       : {df['score'].mean():.1f}/4")
        log.info(f"   R:R moyen         : 1:{df['rr'].mean():.2f}")
        fib_trades = df[df['tp_fib'].str.contains('Fib', na=False)]
        log.info(f"   Trades Fib TP     : {len(fib_trades)}/{len(df)}")
        log.info(f"   LONG / SHORT      : "
                 f"{len(df[df['mode']=='ACHAT (Long)'])} / "
                 f"{len(df[df['mode']=='VENTE (Short)'])}")
    log.info("=" * 55)

# ════════════════════════════════════════════════════════════
# DÉMARRAGE
# ════════════════════════════════════════════════════════════

def demarrer_robot():
    log.info("=" * 55)
    log.info("🤖 AGENT MOONS v3 — Ichimoku + Fibonacci TP")
    log.info(f"   Entrée    : Bord du nuage Ichimoku")
    log.info(f"   Stop Loss : Autre bord du nuage")
    log.info(f"   Take Profit: Extension Fib 161.8% ou 261.8%")
    log.info(f"   R:R cible : 1:{RR_MIN}+")
    log.info(f"   Watchlist : {len(WATCHLIST)} titres")
    log.info(f"   Capital   : ${CAPITAL:,} | Risque {RISQUE_PAR_TRADE*100:.0f}%/trade")
    log.info(f"   Heures    : 9h30–16h00 EST (NYSE)")
    log.info("=" * 55)

    init_db()

    # GitHub Actions : un seul scan par exécution (toutes les 15 min via cron)
    if not est_heures_marche():
        log.info("🕐 Hors heures NYSE — scan ignoré")
        return

    scanner_et_executer()
    rapport_quotidien()

if __name__ == "__main__":
    demarrer_robot()
