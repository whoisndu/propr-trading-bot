"""Quick at-a-glance check: is the bot running, and how far is each coin from
triggering? Read-only - doesn't touch state or place orders.

Usage: python status.py
"""

import subprocess
from decimal import Decimal

import config
import market_data
import state as state_store


def is_running() -> bool:
    result = subprocess.run(["pgrep", "-f", "main.py"], capture_output=True)
    return result.returncode == 0


def main() -> None:
    running = is_running()
    print(f"Bot process: {'RUNNING' if running else 'NOT RUNNING'}")
    print()

    all_state = state_store.load()
    for coin in config.COINS:
        coin_state = state_store.get_coin_state(all_state, coin.symbol)
        try:
            price = market_data.get_mid_price(coin.symbol)
        except Exception as e:
            print(f"{coin.symbol:<10} price fetch failed: {e}")
            continue

        status = coin_state["status"]
        if status == "watching":
            try:
                indicators = market_data.get_indicators(coin.symbol, config.BB_PERIOD, config.RSI_PERIOD, config.BB_STD)
                band_pct_away = (price - indicators["lower_band"]) / indicators["lower_band"] * 100
                print(
                    f"{coin.symbol:<10} watching  price={price:<12} ceiling={coin.trigger_price:<10} "
                    f"lower_band={indicators['lower_band']:<12.6g} ({band_pct_away:+.1f}% away) rsi={indicators['rsi']:.1f}"
                )
            except Exception as e:
                print(f"{coin.symbol:<10} watching  price={price:<12} ceiling={coin.trigger_price:<10} (indicators unavailable: {e})")
        elif status == "in_position":
            entry = Decimal(coin_state["entry_price"])
            unrealized_pct = (price - entry) / entry * 100
            print(
                f"{coin.symbol:<10} IN POSITION  entry={entry} qty={coin_state['quantity']} "
                f"current={price} ({unrealized_pct:+.1f}%) tp={coin_state.get('tp_price')} sl={coin_state.get('sl_price')}"
            )
        elif status == "cooldown":
            print(f"{coin.symbol:<10} cooldown until {coin_state['cooldown_until']}")


if __name__ == "__main__":
    main()
