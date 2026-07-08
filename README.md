# Propr Dip-Bounce Bot

Watches a set of coins for a drop to a set trigger price, buys the dip, and
exits on a fixed take-profit or stop-loss. Trades via [Propr](https://propr.xyz),
which executes on Hyperliquid.

## Coins

Each coin runs independently — its own trigger, TP/SL, and position state
(so one coin being in a position or cooldown doesn't block the others).

| Coin | Trigger price | TP / SL | `szDecimals` |
|------|---------------|---------|--------------|
| FARTCOIN | $0.11 | 45% / 18% | 1 |
| SOL | $65 | 45% / 18% | 2 |
| ZEC | $380 | 45% / 18% | 2 |
| XPL | $0.07 | 45% / 18% | 0 |
| JUP | $0.15 | 45% / 18% | 0 |

## How it works

- Price is read from Hyperliquid's public API (no account needed) since Propr
  itself doesn't expose a market-data endpoint.
- When a coin's price drops to its configured trigger, the bot places a market
  buy sized at a fixed % of account equity, then attaches a take-profit and
  stop-loss order to the resulting position.
- Once a position closes (either exit), that coin enters a cooldown window
  before watching for the next dip. Other coins keep watching independently.
- State (open position, cooldown timer) is persisted to `state.json`, keyed
  per coin, so a restart doesn't lose track or double-enter.

## Strategy math

All of this lives in `strategy.py` (trigger/rearm) and `bot.py` (sizing/exits).

**Entry trigger** — fires when a coin's live mid price $P_t$ drops to or through
its configured trigger price $P_0$ (`<COIN>_TRIGGER_PRICE`, e.g. `SOL_TRIGGER_PRICE`):

$$P_t \le P_0$$

**Position size** — a fixed fraction of account equity, converted to a
quantity and rounded down to the asset's minimum size increment:

$$q_{raw} = \frac{E \cdot r}{P_t} \qquad \delta = 10^{-d} \qquad q = \left\lfloor \frac{q_{raw}}{\delta} \right\rfloor \cdot \delta$$

- $E$ = account equity in USDC (`get_account` balance + unrealized PnL + isolated margin)
- $r$ = `POSITION_SIZE_PCT`, e.g. $0.03$ = 3% of equity per trade, applied per coin independently
- $d$ = the coin's `szDecimals` from Hyperliquid — see the table above ($d=1$ for FARTCOIN → $\delta=0.1$; $d=0$ for XPL/JUP → $\delta=1$)

The entry is skipped if the resulting notional falls below a minimum $N$
(`MIN_NOTIONAL_USDC`):

$$q \cdot P_t < N \implies \text{skip}$$

**Exit levels** — computed from the *actual* average fill price $P_f$
returned by the exchange, not the trigger price, since market orders can slip:

$$P_{TP} = P_f \cdot (1 + k_{tp}) \qquad P_{SL} = P_f \cdot (1 - k_{sl})$$

where $k_{tp}$, $k_{sl}$ are `<COIN>_TP_PCT` / `<COIN>_SL_PCT`. With the current
defaults for every coin ($k_{tp}=0.45$, $k_{sl}=0.18$), the position's expected
value assuming a bounce probability $p$ is:

$$E[\text{return}] = p \cdot 0.45 - (1-p) \cdot 0.18$$

which is breakeven at $p \approx 0.286$ — i.e. the trigger level only needs to
produce a bounce (rather than a further crash through the stop) better than
~29% of the time for this TP/SL ratio to be worth taking, before fees/funding.

**Cooldown** — after a position closes, the bot re-arms once the cooldown
window $C$ (`COOLDOWN_MINUTES`) elapses:

$$t_{rearm} = t_{close} + C, \qquad \text{rearm when } t_{now} \ge t_{rearm}$$

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

Edit `config.py` (or set the corresponding env vars). Each coin has its own
trigger/TP/SL, overridable independently:

- `<COIN>_TRIGGER_PRICE` — price that triggers a buy, e.g. `SOL_TRIGGER_PRICE`,
  `ZEC_TRIGGER_PRICE`, `XPL_TRIGGER_PRICE`, `JUP_TRIGGER_PRICE`,
  `FARTCOIN_TRIGGER_PRICE` (see the coins table above for current values).
- `<COIN>_TP_PCT` / `<COIN>_SL_PCT` — take-profit / stop-loss as a fraction of
  entry price (all coins default to `0.45` / `0.18`).
- `POSITION_SIZE_PCT` — fraction of account equity risked per trade (default
  `0.03`, i.e. 3%), applied independently to each coin. Ignored in dry-run,
  where `DRY_RUN_EQUITY_USDC` is used instead as a stand-in equity.
- `COOLDOWN_MINUTES` — how long to wait after a position closes before that
  coin watches for a new entry (default `60`).
- `POLL_INTERVAL_SECONDS` — how often to check prices, across all coins
  (default `5`).

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
