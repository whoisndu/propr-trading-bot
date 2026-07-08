"""Bot configuration: env toggles + per-coin strategy parameters."""

import os
from dataclasses import dataclass
from decimal import Decimal

from dotenv import load_dotenv

load_dotenv()

PROPR_ENV = os.getenv("PROPR_ENV", "beta")
DRY_RUN = os.getenv("DRY_RUN", "true").strip().lower() != "false"

PROPR_API_URL = (
    "https://api.propr.xyz/v1"
    if PROPR_ENV == "live"
    else "https://api.beta.propr.xyz/v1"
)

HYPERLIQUID_INFO_URL = "https://api.hyperliquid.xyz/info"

POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "5"))
COOLDOWN_MINUTES = int(os.getenv("COOLDOWN_MINUTES", "60"))

# Fraction of account equity risked per trade.
POSITION_SIZE_PCT = Decimal(os.getenv("POSITION_SIZE_PCT", "0.03"))

# Skip an entry if the resulting notional value would be below this (USDC).
MIN_NOTIONAL_USDC = Decimal(os.getenv("MIN_NOTIONAL_USDC", "10"))

# Used only in dry-run, where there's no real account to read equity from.
DRY_RUN_EQUITY_USDC = Decimal(os.getenv("DRY_RUN_EQUITY_USDC", "1000"))


@dataclass
class CoinConfig:
    symbol: str
    trigger_price: Decimal
    take_profit_pct: Decimal
    stop_loss_pct: Decimal
    size_decimals: int  # Hyperliquid szDecimals - rounding increment for order quantity


COINS: list[CoinConfig] = [
    CoinConfig(
        symbol="FARTCOIN",
        trigger_price=Decimal(os.getenv("FARTCOIN_TRIGGER_PRICE", "0.11")),
        take_profit_pct=Decimal(os.getenv("FARTCOIN_TP_PCT", "0.45")),
        stop_loss_pct=Decimal(os.getenv("FARTCOIN_SL_PCT", "0.18")),
        size_decimals=1,
    ),
    CoinConfig(
        symbol="SOL",
        trigger_price=Decimal(os.getenv("SOL_TRIGGER_PRICE", "65")),
        take_profit_pct=Decimal(os.getenv("SOL_TP_PCT", "0.45")),
        stop_loss_pct=Decimal(os.getenv("SOL_SL_PCT", "0.18")),
        size_decimals=2,
    ),
    CoinConfig(
        symbol="ZEC",
        trigger_price=Decimal(os.getenv("ZEC_TRIGGER_PRICE", "380")),
        take_profit_pct=Decimal(os.getenv("ZEC_TP_PCT", "0.45")),
        stop_loss_pct=Decimal(os.getenv("ZEC_SL_PCT", "0.18")),
        size_decimals=2,
    ),
    CoinConfig(
        symbol="XPL",
        trigger_price=Decimal(os.getenv("XPL_TRIGGER_PRICE", "0.07")),
        take_profit_pct=Decimal(os.getenv("XPL_TP_PCT", "0.45")),
        stop_loss_pct=Decimal(os.getenv("XPL_SL_PCT", "0.18")),
        size_decimals=0,
    ),
    CoinConfig(
        symbol="JUP",
        trigger_price=Decimal(os.getenv("JUP_TRIGGER_PRICE", "0.15")),
        take_profit_pct=Decimal(os.getenv("JUP_TP_PCT", "0.45")),
        stop_loss_pct=Decimal(os.getenv("JUP_SL_PCT", "0.18")),
        size_decimals=0,
    ),
]
