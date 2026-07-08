# Propr Dip-Bounce Bot

Watches FARTCOIN for a drop to a set trigger price, buys the dip, and exits on a
fixed take-profit or stop-loss. Trades via [Propr](https://propr.xyz), which
executes on Hyperliquid.

## How it works

- Price is read from Hyperliquid's public API (no account needed) since Propr
  itself doesn't expose a market-data endpoint.
- When price drops to the configured trigger, the bot places a market buy sized
  at a fixed % of account equity, then attaches a take-profit and stop-loss
  order to the resulting position.
- Once the position closes (either exit), the bot enters a cooldown window
  before watching for the next dip.
- State (open position, cooldown timer) is persisted to `state.json` so a
  restart doesn't lose track or double-enter.

## Setup

This repo doesn't ship `propr_sdk.py` (it's gitignored). Get it from Propr's
own docs/SDK repo and drop it in the project root before running:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# copy propr_sdk.py from Propr's docs repo (python/propr_sdk.py) into this directory
```

Edit `.env`:
- `DRY_RUN=true` (default) — runs against live prices and logs what it *would*
  do, with no real orders and no API key required. Start here.
- `PROPR_ENV=beta` (default) — switch to `live` only once you've validated
  behavior on beta.
- `PROPR_API_KEY` — only needed once `DRY_RUN=false`. Get one from
  [app.propr.xyz/settings](https://app.propr.xyz/settings) after purchasing a
  challenge (required before the API can place trades).

Run:

```bash
python main.py
```

To run it persistently in the background:

```bash
nohup .venv/bin/python main.py > /dev/null 2>&1 & disown
```

Logs go to `bot.log` regardless of how it's started (`tail -f bot.log`). Stop it
with `pkill -f "main.py"`.

## Tuning the strategy

Edit `config.py` (or set the corresponding env vars):

- `FARTCOIN_TRIGGER_PRICE` — price that triggers a buy (default `0.11`).
- `FARTCOIN_TP_PCT` / `FARTCOIN_SL_PCT` — take-profit / stop-loss as a
  fraction of entry price (defaults `0.45` / `0.18`).
- `POSITION_SIZE_PCT` — fraction of account equity risked per trade (default
  `0.03`, i.e. 3%). Ignored in dry-run, where `DRY_RUN_EQUITY_USDC` is used
  instead as a stand-in equity.
- `COOLDOWN_MINUTES` — how long to wait after a position closes before
  watching for a new entry (default `60`).
- `POLL_INTERVAL_SECONDS` — how often to check price (default `5`).

## Adding another coin

Add a `CoinConfig(...)` entry to `COINS` in `config.py`. You'll need that
coin's `szDecimals` from Hyperliquid (`POST /info {"type": "meta"}`) to round
order quantities correctly, and to confirm the coin is actually listed on
Hyperliquid — Propr only trades what Hyperliquid lists (checked via the same
`meta`/`spotMeta` endpoints).

## Notes

- `reference/propr-docs/` is a gitignored reference checkout of Propr's API
  docs/SDKs — used to build this bot, never committed.
- `propr_sdk.py` is also gitignored — it's Propr's copy-paste SDK, sourced
  locally from that reference rather than committed here.
- Uses `Decimal` throughout for price/quantity math, per Propr's own guidance
  (never `float` for money).
