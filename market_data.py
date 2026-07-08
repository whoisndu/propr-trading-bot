"""Market data from Hyperliquid's public info API (no auth required).

Propr's own API has no price/candle endpoint - it only exposes account-scoped
orders/positions/trades. Since Propr executes on Hyperliquid, we read prices
directly from the same source Propr trades against.
"""

from decimal import Decimal

import requests

from config import HYPERLIQUID_INFO_URL

_session = requests.Session()


def _info(payload: dict) -> object:
    r = _session.post(HYPERLIQUID_INFO_URL, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()


def get_mid_price(coin: str) -> Decimal:
    """Current mid price for a coin, e.g. get_mid_price('FARTCOIN')."""
    mids = _info({"type": "allMids"})
    price = mids.get(coin)
    if price is None:
        raise ValueError(f"No mid price returned for {coin!r}")
    return Decimal(price)


def get_candles(coin: str, interval: str, start_ms: int, end_ms: int) -> list[dict]:
    """Historical candles, e.g. for eyeballing recent crash/bounce behavior."""
    return _info(
        {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": interval,
                "startTime": start_ms,
                "endTime": end_ms,
            },
        }
    )
