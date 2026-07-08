"""Pure decision logic for the dip-bounce strategy.

Kept free of any network/IO calls so it can be reasoned about (and adjusted)
without touching the execution or market-data code. The bot loop supplies the
current price and persisted state; this module only says what should happen
next.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from config import CoinConfig


class Action(str, Enum):
    NONE = "none"           # nothing to do, keep watching
    ENTER = "enter"         # price crossed the trigger while watching - buy
    REARM = "rearm"         # cooldown window has elapsed - go back to watching


@dataclass
class Decision:
    action: Action
    reason: str


def decide(coin: CoinConfig, coin_state: dict, price: Decimal, now: datetime | None = None) -> Decision:
    now = now or datetime.now(timezone.utc)
    status = coin_state.get("status", "watching")

    if status == "watching":
        if price <= coin.trigger_price:
            return Decision(
                Action.ENTER,
                f"price {price} <= trigger {coin.trigger_price}",
            )
        return Decision(Action.NONE, f"price {price} above trigger {coin.trigger_price}")

    if status == "cooldown":
        cooldown_until = coin_state.get("cooldown_until")
        if cooldown_until and now >= datetime.fromisoformat(cooldown_until):
            return Decision(Action.REARM, "cooldown window elapsed")
        return Decision(Action.NONE, "cooldown in progress")

    # status == "in_position": whether the position has closed is determined
    # by querying the account, not by price alone - the bot loop handles that.
    return Decision(Action.NONE, "position open, monitoring")
