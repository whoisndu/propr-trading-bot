"""Tiny JSON-file persistence so the bot survives restarts without losing track
of an open position or a cooldown window."""

import json
import os

STATE_PATH = os.path.join(os.path.dirname(__file__), "state.json")

# status: "watching" | "in_position" | "cooldown"
DEFAULT_COIN_STATE = {
    "status": "watching",
    "position_id": None,
    "entry_price": None,
    "quantity": None,
    "tp_order_id": None,
    "sl_order_id": None,
    "cooldown_until": None,  # ISO timestamp string
}


def load() -> dict:
    if not os.path.exists(STATE_PATH):
        return {}
    with open(STATE_PATH) as f:
        return json.load(f)


def save(state: dict) -> None:
    tmp_path = STATE_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp_path, STATE_PATH)


def get_coin_state(state: dict, symbol: str) -> dict:
    return state.get(symbol, dict(DEFAULT_COIN_STATE))


def set_coin_state(state: dict, symbol: str, coin_state: dict) -> None:
    state[symbol] = coin_state
    save(state)
