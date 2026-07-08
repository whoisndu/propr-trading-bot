"""Orchestrator: polls prices, runs the strategy, and executes/simulates trades."""

import logging
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import config
import market_data
import state as state_store
from propr_sdk import ProprClient
from strategy import Action, decide

log = logging.getLogger("bot")


def round_quantity(raw_qty: Decimal, size_decimals: int) -> Decimal:
    """Round down to the asset's minimum size increment (Hyperliquid szDecimals)."""
    increment = Decimal(1).scaleb(-size_decimals)
    return (raw_qty // increment) * increment


def get_equity(client: ProprClient | None) -> Decimal:
    if client is None:
        return config.DRY_RUN_EQUITY_USDC
    account = client.get_account()
    balance = Decimal(account.get("balance", "0"))
    unrealized = Decimal(account.get("totalUnrealizedPnl", "0"))
    isolated_margin = Decimal(account.get("isolatedPositionMargin", "0"))
    return balance + unrealized + isolated_margin


def enter_position(client: ProprClient | None, coin: config.CoinConfig, price: Decimal, coin_state: dict) -> dict:
    equity = get_equity(client)
    raw_qty = (equity * config.POSITION_SIZE_PCT) / price
    quantity = round_quantity(raw_qty, coin.size_decimals)
    notional = quantity * price

    if quantity <= 0 or notional < config.MIN_NOTIONAL_USDC:
        log.warning(
            "[%s] skipping entry: computed notional %.2f USDC below minimum %s (equity=%s, price=%s)",
            coin.symbol, notional, config.MIN_NOTIONAL_USDC, equity, price,
        )
        return coin_state

    tp_price = (price * (1 + coin.take_profit_pct)).quantize(price)
    sl_price = (price * (1 - coin.stop_loss_pct)).quantize(price)

    if client is None:
        log.info(
            "[DRY RUN] [%s] would BUY %s @ %s | TP %s (+%.0f%%) SL %s (-%.0f%%)",
            coin.symbol, quantity, price, tp_price, coin.take_profit_pct * 100,
            sl_price, coin.stop_loss_pct * 100,
        )
        return {
            "status": "in_position",
            "position_id": "dry-run",
            "entry_price": str(price),
            "quantity": str(quantity),
            "tp_order_id": "dry-run-tp",
            "sl_order_id": "dry-run-sl",
            "tp_price": str(tp_price),
            "sl_price": str(sl_price),
            "cooldown_until": None,
        }

    log.info("[%s] entering: market buy %s @ ~%s", coin.symbol, quantity, price)
    orders = client.market_buy(coin.symbol, str(quantity))
    order = orders[0]
    order = wait_for_fill(client, order)

    position_id = order.get("positionId")
    fill_price = Decimal(order.get("averageFillPrice") or price)
    if not position_id:
        log.error(
            "[%s] entry order %s did not report a positionId - manual review needed",
            coin.symbol, order.get("orderId"),
        )
        return {
            **coin_state,
            "status": "in_position",
            "entry_price": str(fill_price),
            "quantity": str(quantity),
        }

    tp_price = (fill_price * (1 + coin.take_profit_pct)).quantize(fill_price)
    sl_price = (fill_price * (1 - coin.stop_loss_pct)).quantize(fill_price)
    tp_order_id, sl_order_id = place_exit_orders(client, coin, position_id, quantity, tp_price, sl_price)

    log.info(
        "[%s] entered: %s @ %s | TP %s SL %s", coin.symbol, quantity, fill_price, tp_price, sl_price,
    )
    return {
        "status": "in_position",
        "position_id": position_id,
        "entry_price": str(fill_price),
        "quantity": str(quantity),
        "tp_order_id": tp_order_id,
        "sl_order_id": sl_order_id,
        "tp_price": str(tp_price),
        "sl_price": str(sl_price),
        "cooldown_until": None,
    }


def wait_for_fill(client: ProprClient, order: dict, attempts: int = 5, delay_seconds: float = 1.0) -> dict:
    """Market IOC orders usually fill synchronously, but poll briefly in case
    the create response hasn't caught up with the fill yet."""
    for _ in range(attempts):
        if order.get("status") == "filled" and order.get("positionId"):
            return order
        time.sleep(delay_seconds)
        matches = client.get_orders(order_id=order["orderId"])
        if matches:
            order = matches[0]
    return order


def place_exit_orders(
    client: ProprClient,
    coin: config.CoinConfig,
    position_id: str,
    quantity: Decimal,
    tp_price: Decimal,
    sl_price: Decimal,
) -> tuple[str | None, str | None]:
    """Attach take-profit and stop-loss to an already-open position.

    Each call submits a single order (no orderGroupId needed) referencing
    positionId, per Propr's conditional-order rules.

    Note: Propr's docs show side="sell" + positionSide="long" for a reduceOnly
    close order, but the live API rejects that for conditional orders (error
    13096 order_side_must_align_with_position_side_buy_long_or_sell_short) -
    confirmed by testing against beta. The accepted combination is the
    opposite positionSide from the position being closed.
    """
    base_order = {
        "positionId": position_id,
        "side": "sell",
        "positionSide": "short",
        "asset": coin.symbol,
        "base": coin.symbol,
        "quote": "USDC",
        "quantity": str(quantity),
        "reduceOnly": True,
        "exchange": "hyperliquid",
        "productType": "perp",
        "timeInForce": "GTC",
    }

    tp_order_id = sl_order_id = None
    try:
        tp_result = client.create_orders([{**base_order, "type": "take_profit_market", "triggerPrice": str(tp_price)}])
        tp_order_id = tp_result[0]["orderId"] if tp_result else None
    except Exception:
        log.exception("[%s] failed to place take-profit order", coin.symbol)

    try:
        sl_result = client.create_orders([{**base_order, "type": "stop_market", "triggerPrice": str(sl_price)}])
        sl_order_id = sl_result[0]["orderId"] if sl_result else None
    except Exception:
        log.exception("[%s] failed to place stop-loss order", coin.symbol)

    return tp_order_id, sl_order_id


def check_position_closed(client: ProprClient | None, coin: config.CoinConfig, price: Decimal, coin_state: dict) -> dict:
    if client is None:
        tp_price = Decimal(coin_state["tp_price"])
        sl_price = Decimal(coin_state["sl_price"])
        if price >= tp_price:
            log.info("[DRY RUN] [%s] would hit TAKE PROFIT @ %s (entry %s)", coin.symbol, price, coin_state["entry_price"])
            return start_cooldown(coin_state)
        if price <= sl_price:
            log.info("[DRY RUN] [%s] would hit STOP LOSS @ %s (entry %s)", coin.symbol, price, coin_state["entry_price"])
            return start_cooldown(coin_state)
        return coin_state

    open_positions = client.get_open_positions(base=coin.symbol)
    if open_positions:
        return coin_state

    log.info("[%s] position closed (entry %s)", coin.symbol, coin_state.get("entry_price"))
    return start_cooldown(coin_state)


def start_cooldown(coin_state: dict) -> dict:
    cooldown_until = datetime.now(timezone.utc) + timedelta(minutes=config.COOLDOWN_MINUTES)
    return {
        "status": "cooldown",
        "position_id": None,
        "entry_price": None,
        "quantity": None,
        "tp_order_id": None,
        "sl_order_id": None,
        "tp_price": None,
        "sl_price": None,
        "cooldown_until": cooldown_until.isoformat(),
    }


def reconcile_on_startup(client: ProprClient | None, coin: config.CoinConfig, coin_state: dict) -> dict:
    if client is None or coin_state.get("status") != "in_position":
        return coin_state

    open_positions = client.get_open_positions(base=coin.symbol)
    if not open_positions:
        log.info("[%s] no open position found on startup reconciliation - clearing stale state", coin.symbol)
        return start_cooldown(coin_state)

    if coin_state.get("tp_order_id") and coin_state.get("sl_order_id"):
        log.info("[%s] resuming in-position tracking (positionId=%s)", coin.symbol, coin_state.get("position_id"))
        return coin_state

    position = open_positions[0]
    entry_price = Decimal(position["entryPrice"])
    quantity = Decimal(position["quantity"])
    tp_price = (entry_price * (1 + coin.take_profit_pct)).quantize(entry_price)
    sl_price = (entry_price * (1 - coin.stop_loss_pct)).quantize(entry_price)
    log.warning("[%s] found open position missing TP/SL - re-placing exit orders", coin.symbol)
    tp_order_id, sl_order_id = place_exit_orders(client, coin, position["positionId"], quantity, tp_price, sl_price)
    return {
        "status": "in_position",
        "position_id": position["positionId"],
        "entry_price": str(entry_price),
        "quantity": str(quantity),
        "tp_order_id": tp_order_id,
        "sl_order_id": sl_order_id,
        "tp_price": str(tp_price),
        "sl_price": str(sl_price),
        "cooldown_until": None,
    }


def tick(client: ProprClient | None, coin: config.CoinConfig, all_state: dict) -> None:
    coin_state = state_store.get_coin_state(all_state, coin.symbol)
    price = market_data.get_mid_price(coin.symbol)

    if coin_state["status"] == "in_position":
        coin_state = check_position_closed(client, coin, price, coin_state)
        state_store.set_coin_state(all_state, coin.symbol, coin_state)
        return

    decision = decide(coin, coin_state, price)
    log.debug("[%s] price=%s status=%s decision=%s (%s)", coin.symbol, price, coin_state["status"], decision.action, decision.reason)

    if decision.action == Action.ENTER:
        coin_state = enter_position(client, coin, price, coin_state)
    elif decision.action == Action.REARM:
        log.info("[%s] cooldown elapsed, back to watching", coin.symbol)
        coin_state = dict(state_store.DEFAULT_COIN_STATE)
    else:
        log.info("[%s] watching: price=%s trigger=%s status=%s", coin.symbol, price, coin.trigger_price, coin_state["status"])

    state_store.set_coin_state(all_state, coin.symbol, coin_state)


def run() -> None:
    client: ProprClient | None = None
    if config.DRY_RUN:
        log.info("Running in DRY RUN mode - no real orders will be placed, no API key required.")
    else:
        client = ProprClient()
        health = client.health_services()
        if health.get("core") != "OK":
            raise RuntimeError(f"Propr core service not healthy: {health}")
        account_id = client.setup()
        log.info("Connected to Propr (%s), accountId=%s", config.PROPR_ENV, account_id)

    all_state = state_store.load()
    for coin in config.COINS:
        coin_state = state_store.get_coin_state(all_state, coin.symbol)
        reconciled = reconcile_on_startup(client, coin, coin_state)
        state_store.set_coin_state(all_state, coin.symbol, reconciled)

    log.info("Watching %s coin(s), polling every %ss", len(config.COINS), config.POLL_INTERVAL_SECONDS)
    while True:
        for coin in config.COINS:
            try:
                tick(client, coin, all_state)
            except Exception:
                log.exception("[%s] tick failed", coin.symbol)
        time.sleep(config.POLL_INTERVAL_SECONDS)
