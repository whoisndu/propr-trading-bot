"""Pure decision logic for the dip-bounce strategy.

Kept free of any network/IO calls so it can be reasoned about (and adjusted)
without touching the execution or market-data code. The bot loop supplies the
current price/indicators and persisted state; this module only says what
should happen next.

Entry requires all three to agree: price at/below the manual trigger_price
ceiling, price at/below the daily Bollinger lower band, and daily RSI at/below
the oversold threshold.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

import config
from config import CoinConfig


class Action(str, Enum):
    NONE = "none"           # nothing to do, keep watching
    ENTER = "enter"         # price crossed the trigger while watching - buy
    REARM = "rearm"         # cooldown window has elapsed - go back to watching


@dataclass
class Decision:
    action: Action
    reason: str


def decide(coin: CoinConfig, coin_state: dict, indicators: dict, now: datetime | None = None) -> Decision:
    now = now or datetime.now(timezone.utc)
    status = coin_state.get("status", "watching")
    price = indicators["price"]

    if status == "watching":
        below_ceiling = price <= coin.trigger_price
        below_band = price <= indicators["lower_band"]
        oversold = indicators["rsi"] <= config.RSI_OVERSOLD

        checks = (
            f"price={price} ceiling={coin.trigger_price} ({'ok' if below_ceiling else 'no'}), "
            f"lower_band={indicators['lower_band']:.6g} ({'ok' if below_band else 'no'}), "
            f"rsi={indicators['rsi']:.1f} oversold<={config.RSI_OVERSOLD} ({'ok' if oversold else 'no'})"
        )

        if below_ceiling and below_band and oversold:
            return Decision(Action.ENTER, checks)
        return Decision(Action.NONE, checks)

    if status == "cooldown":
        cooldown_until = coin_state.get("cooldown_until")
        if cooldown_until and now >= datetime.fromisoformat(cooldown_until):
            return Decision(Action.REARM, "cooldown window elapsed")
        return Decision(Action.NONE, "cooldown in progress")

    # status == "in_position": whether the position has closed is determined
    # by querying the account, not by price alone - the bot loop handles that.
    return Decision(Action.NONE, "position open, monitoring")
