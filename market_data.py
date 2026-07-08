"""Market data from Hyperliquid's public info API (no auth required).

Propr's own API has no price/candle endpoint - it only exposes account-scoped
orders/positions/trades. Since Propr executes on Hyperliquid, we read prices
directly from the same source Propr trades against.
"""

import time
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


def get_completed_daily_closes(coin: str, lookback_days: int) -> list[Decimal]:
    """Closes of fully-finished daily candles only (today's in-progress candle
    excluded), oldest first. Used as a stable baseline for Bollinger Bands so
    a live intraday crash doesn't drag its own reference band down with it."""
    now = int(time.time() * 1000)
    start = now - (lookback_days + 5) * 86_400_000
    candles = get_candles(coin, "1d", start, now)
    completed = [c for c in candles if c["T"] < now]
    return [Decimal(c["c"]) for c in completed[-lookback_days:]]


def compute_bollinger_bands(closes: list[Decimal], period: int, num_std: Decimal) -> tuple[Decimal, Decimal, Decimal]:
    """Returns (lower, sma, upper) from the most recent `period` closes."""
    window = closes[-period:]
    if len(window) < period:
        raise ValueError(f"need {period} closes, got {len(window)}")
    sma = sum(window) / len(window)
    variance = sum((c - sma) ** 2 for c in window) / len(window)
    std = variance.sqrt()
    return sma - num_std * std, sma, sma + num_std * std


def compute_rsi(closes: list[Decimal], period: int) -> Decimal:
    """Wilder's RSI (matches the default RSI on most charting platforms).
    `closes` should include the current/live price as the last element so it
    reacts to an in-progress crash rather than only yesterday's close."""
    if len(closes) < period + 1:
        raise ValueError(f"need at least {period + 1} closes, got {len(closes)}")

    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [c if c > 0 else Decimal(0) for c in changes]
    losses = [-c if c < 0 else Decimal(0) for c in changes]

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period

    if avg_loss == 0:
        return Decimal(100)
    rs = avg_gain / avg_loss
    return Decimal(100) - (Decimal(100) / (1 + rs))


def get_indicators(coin: str, bb_period: int, rsi_period: int, bb_std: Decimal) -> dict:
    """Live price plus Bollinger Bands (from completed daily candles) and
    Wilder's RSI (including the live price as today's close-so-far)."""
    price = get_mid_price(coin)
    lookback = max(bb_period, rsi_period) + 10
    completed_closes = get_completed_daily_closes(coin, lookback)

    lower_band, sma, upper_band = compute_bollinger_bands(completed_closes, bb_period, bb_std)
    rsi = compute_rsi(completed_closes[-(rsi_period + 1):] + [price], rsi_period)

    return {
        "price": price,
        "lower_band": lower_band,
        "sma": sma,
        "upper_band": upper_band,
        "rsi": rsi,
    }
