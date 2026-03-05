# ============================================================
# ib_bridge.py — Version Corrigée & Complète
# Terminal Moons Pro — Connexion TWS Interactive Brokers
# Supporte LONG et SHORT | Sécurité compte simulation
# ============================================================

from ib_insync import IB, Stock, LimitOrder, StopOrder
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger("ib_bridge")


def executer_plan_moons(
    ticker_str: str,
    qty: int,
    entry_px: float,
    stop_px: float,
    tp_px: float,
    mode: str = "ACHAT (Long)"
) -> bool:
    """
    Envoie un Bracket Order complet à TWS (Interactive Brokers).

    Paramètres
    ----------
    ticker_str : str   — Symbole boursier ex: "NVDA", "MSI"
    qty        : int   — Nombre d'actions
    entry_px   : float — Prix d'entrée (C2 Fibonacci)
    stop_px    : float — Prix du Stop Loss
    tp_px      : float — Prix du Take Profit principal (TP2)
    mode       : str   — "ACHAT (Long)" ou "VENTE (Short)"

    Retourne
    --------
    True si tous les ordres sont acceptés par TWS, False sinon.
    """
    ib = IB()
    try:
        # ── 1. Connexion TWS ────────────────────────────────────────────
        log.info(f"Connexion à TWS (paper port 7497)...")
        ib.connect('127.0.0.1', 7497, clientId=10, timeout=10)
        log.info(f"Connecté — comptes disponibles : {ib.managedAccounts()}")

        # ── 2. Vérification OBLIGATOIRE : compte simulation ─────────────
        accounts = ib.managedAccounts()
        if not any(acc.startswith('DU') for acc in accounts):
            log.error("⛔ COMPTE RÉEL DÉTECTÉ — Arrêt immédiat par sécurité !")
            log.error(f"   Comptes trouvés : {accounts}")
            log.error("   Les comptes paper IBKR commencent par 'DU'.")
            return False
        log.info(f"✅ Compte simulation confirmé : {accounts[0]}")

        # ── 3. Qualification du contrat ─────────────────────────────────
        contract = Stock(ticker_str, 'SMART', 'USD')
        ib.qualifyContracts(contract)
        log.info(f"Contrat qualifié : {contract.symbol} ({contract.exchange})")

        # ── 4. Arrondi des prix (tick minimum IBKR = $0.01) ─────────────
        entry_px = round(float(entry_px), 2)
        stop_px  = round(float(stop_px),  2)
        tp_px    = round(float(tp_px),    2)

        # ── 5. Validation logique des niveaux de prix ───────────────────
        if mode == "ACHAT (Long)":
            if not (stop_px < entry_px < tp_px):
                log.error(
                    f"❌ Niveaux LONG incohérents : "
                    f"stop={stop_px} < entry={entry_px} < tp={tp_px} → FAUX"
                )
                return False
            action_open  = 'BUY'
            action_close = 'SELL'

        else:  # VENTE (Short)
            if not (stop_px > entry_px > tp_px):
                log.error(
                    f"❌ Niveaux SHORT incohérents : "
                    f"stop={stop_px} > entry={entry_px} > tp={tp_px} → FAUX"
                )
                return False
            action_open  = 'SELL'
            action_close = 'BUY'

        log.info(
            f"Plan validé — {mode} | {ticker_str} x{qty} | "
            f"Entry={entry_px}$ | SL={stop_px}$ | TP={tp_px}$"
        )

        # ── 6. Génération des IDs uniques depuis TWS ────────────────────
        parent_id = ib.client.getReqId()

        # ── 7. Construction du Bracket Order ────────────────────────────
        # Ordre parent (entrée en position)
        parent             = LimitOrder(action_open, qty, entry_px)
        parent.orderId     = parent_id
        parent.transmit    = False  # Ne pas envoyer encore

        # Ordre stop loss (protection contre la perte)
        stop_loss             = StopOrder(action_close, qty, stop_px)
        stop_loss.orderId     = parent_id + 1
        stop_loss.parentId    = parent_id
        stop_loss.transmit    = False

        # Ordre take profit (prise de bénéfice principale)
        take_profit             = LimitOrder(action_close, qty, tp_px)
        take_profit.orderId     = parent_id + 2
        take_profit.parentId    = parent_id
        take_profit.transmit    = True  # Envoie TOUT le groupe d'un coup

        # ── 8. Envoi à TWS & confirmation ───────────────────────────────
        bracket = [parent, stop_loss, take_profit]
        placed  = []
        for ordre in bracket:
            trade = ib.placeOrder(contract, ordre)
            placed.append(trade)

        # Laisser TWS traiter et confirmer
        ib.sleep(2)

        # ── 9. Vérification des statuts retournés ───────────────────────
        labels = ["Parent (Entrée)", "Stop Loss", "Take Profit"]
        for i, trade in enumerate(placed):
            status = trade.orderStatus.status
            log.info(
                f"  [{labels[i]}] OrderId={trade.order.orderId} "
                f"| Action={trade.order.action} "
                f"| Prix={trade.order.lmtPrice if hasattr(trade.order,'lmtPrice') else trade.order.auxPrice}$ "
                f"| Statut={status}"
            )
            if status in ('Cancelled', 'Inactive'):
                log.error(f"❌ Ordre '{labels[i]}' rejeté par TWS (statut: {status})")
                return False

        log.info(
            f"✅ Bracket complet accepté par TWS — "
            f"{ticker_str} x{qty} | Entry={entry_px}$ | SL={stop_px}$ | TP={tp_px}$"
        )
        return True

    except ConnectionRefusedError:
        log.error("❌ Impossible de se connecter à TWS.")
        log.error("   → Vérifiez que TWS est ouvert et que le port 7497 est activé.")
        log.error("   → TWS > File > Global Configuration > API > Settings > Socket port: 7497")
        return False

    except Exception as e:
        log.error(f"❌ Erreur inattendue dans ib_bridge : {type(e).__name__}: {e}")
        return False

    finally:
        if ib.isConnected():
            ib.disconnect()
            log.info("Déconnexion TWS propre.")

