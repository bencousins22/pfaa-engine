#!/usr/bin/env python3
"""
PFAA Multi-Coin Backtester — Validate strategy across 16 coins with
different volatility profiles using synthetic OHLCV data.

Usage: python3 freqtrade_strategy/multi_coin_backtest.py
"""

import copy
import json
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime, timedelta

# Add parent to path so we can import from backtest_sandbox
sys.path.insert(0, os.path.dirname(__file__))
from backtest_sandbox import populate_indicators, backtest, PARAMS, SIGNAL_WEIGHTS

# ── Coin Definitions ─────────────────────────────────────────────────

COINS = {
    "BTC":  {"vol_lo": 0.003, "vol_hi": 0.008, "start_price": 95000,   "category": "large_cap"},
    "ETH":  {"vol_lo": 0.004, "vol_hi": 0.010, "start_price": 3500,    "category": "large_cap",  "btc_corr": 0.75},
    "SOL":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 150,     "category": "alt_L1"},
    "HYPE": {"vol_lo": 0.008, "vol_hi": 0.020, "start_price": 25,      "category": "dex_token"},
    "DOGE": {"vol_lo": 0.007, "vol_hi": 0.018, "start_price": 0.18,    "category": "meme"},
    "XRP":  {"vol_lo": 0.004, "vol_hi": 0.012, "start_price": 2.50,    "category": "large_cap"},
    "AVAX": {"vol_lo": 0.005, "vol_hi": 0.012, "start_price": 40,      "category": "alt_L1"},
    "LINK": {"vol_lo": 0.005, "vol_hi": 0.012, "start_price": 18,      "category": "defi"},
    "SUI":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 2.00,    "category": "alt_L1"},
    "ARB":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 1.20,    "category": "alt_L2"},
    "OP":   {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 2.50,    "category": "alt_L2"},
    "PEPE": {"vol_lo": 0.010, "vol_hi": 0.025, "start_price": 0.000012,"category": "meme"},
    "WIF":  {"vol_lo": 0.010, "vol_hi": 0.025, "start_price": 2.50,    "category": "meme"},
    "ONDO": {"vol_lo": 0.005, "vol_hi": 0.012, "start_price": 1.50,    "category": "rwa"},
    "INJ":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 25,      "category": "defi"},
    "TIA":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 8,       "category": "alt_L1"},
}

# ── Synthetic Data Generation ────────────────────────────────────────

def generate_synthetic_ohlcv(
    symbol: str,
    n_candles: int = 131328,
    start_price: float = 100.0,
    vol_lo: float = 0.005,
    vol_hi: float = 0.012,
    btc_returns: np.ndarray = None,
    btc_corr: float = 0.0,
    seed: int = None,
    **kwargs,
) -> pd.DataFrame:
    """
    Generate realistic synthetic 5m OHLCV data using geometric Brownian
    motion with regime-switching volatility, mean reversion, and optional
    correlation to BTC returns.
    """
    rng = np.random.default_rng(seed)

    # Base log-returns
    raw_returns = rng.standard_normal(n_candles)

    # Correlate with BTC if requested
    if btc_returns is not None and btc_corr > 0:
        btc_z = (btc_returns - btc_returns.mean()) / (btc_returns.std() + 1e-12)
        # Ensure same length
        min_len = min(len(raw_returns), len(btc_z))
        raw_returns[:min_len] = btc_corr * btc_z[:min_len] + np.sqrt(1 - btc_corr**2) * raw_returns[:min_len]

    # Regime-switching volatility: cycle between low and high vol
    regime_period = rng.integers(2000, 8000)  # candles per regime
    vol_series = np.empty(n_candles)
    i = 0
    while i < n_candles:
        regime_len = rng.integers(regime_period // 2, regime_period * 2)
        vol = rng.uniform(vol_lo, vol_hi)
        end = min(i + regime_len, n_candles)
        vol_series[i:end] = vol
        i = end

    # Smooth volatility transitions
    kernel = np.ones(200) / 200
    vol_series = np.convolve(vol_series, kernel, mode="same")

    # Light mean reversion drift (prevents runaway prices)
    log_price = np.log(start_price)
    log_prices = np.empty(n_candles)
    drift = 0.0
    for i in range(n_candles):
        # Mean reversion toward starting price (very weak)
        mr = -0.00001 * (log_price - np.log(start_price))
        log_price += mr + vol_series[i] * raw_returns[i]
        log_prices[i] = log_price

    close = np.exp(log_prices)

    # Generate OHLC from close
    intra_vol = vol_series * 0.6  # intra-candle volatility
    high_excess = np.abs(rng.standard_normal(n_candles)) * intra_vol * close
    low_excess = np.abs(rng.standard_normal(n_candles)) * intra_vol * close

    open_prices = np.empty(n_candles)
    open_prices[0] = start_price
    open_prices[1:] = close[:-1] + rng.standard_normal(n_candles - 1) * intra_vol[1:] * close[1:] * 0.1

    high = np.maximum(close, open_prices) + high_excess
    low = np.minimum(close, open_prices) - low_excess
    # Ensure low > 0
    low = np.maximum(low, close * 0.95)

    # Volume: base + spikes correlated with price moves
    base_volume = start_price * rng.uniform(200, 600)
    vol_multiplier = 1.0 + 2.0 * np.abs(raw_returns)  # bigger moves = more volume
    volume = base_volume * vol_multiplier * rng.uniform(0.5, 1.5, n_candles)

    # Timestamps: 5m candles starting 2025-01-01
    start_ts = int(datetime(2025, 1, 1).timestamp() * 1000)
    timestamps = start_ts + np.arange(n_candles) * 5 * 60 * 1000

    df = pd.DataFrame({
        "timestamp": timestamps,
        "open": open_prices,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("date", inplace=True)

    return df


def resample_to_1h(df_5m: pd.DataFrame) -> pd.DataFrame:
    """Resample 5m OHLCV to 1h."""
    df_1h = df_5m.resample("1h").agg({
        "timestamp": "first",
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
    }).dropna()
    return df_1h


# ── Load BTC from existing file ──────────────────────────────────────

def load_btc_data():
    """Load existing BTC synthetic data."""
    data_dir = os.path.join(os.path.dirname(__file__), "..", "user_data", "data", "binance")
    path_5m = os.path.join(data_dir, "BTC_USDT-5m.json")
    path_1h = os.path.join(data_dir, "BTC_USDT-1h.json")

    with open(path_5m) as f:
        raw = json.load(f)
    df_5m = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df_5m["date"] = pd.to_datetime(df_5m["timestamp"], unit="ms")
    df_5m.set_index("date", inplace=True)

    with open(path_1h) as f:
        raw = json.load(f)
    df_1h = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df_1h["date"] = pd.to_datetime(df_1h["timestamp"], unit="ms")
    df_1h.set_index("date", inplace=True)

    return df_5m, df_1h


# ── Compute backtest metrics ─────────────────────────────────────────

def compute_metrics(trades, final_capital, initial=10000.0):
    """Return a dict of key metrics for a backtest run."""
    if not trades:
        return {
            "return_pct": 0, "win_rate": 0, "max_dd": 0,
            "profit_factor": 0, "n_trades": 0, "avg_win": 0,
            "avg_loss": 0, "sharpe": 0, "avg_bars": 0,
        }

    wins = [t for t in trades if t["profit_pct"] > 0]
    losses = [t for t in trades if t["profit_pct"] <= 0]
    total_return = (final_capital - initial) / initial * 100

    # Max drawdown
    equity = [initial]
    for t in trades:
        equity.append(equity[-1] + t["pnl"])
    peak = equity[0]
    max_dd = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak
        if dd > max_dd:
            max_dd = dd

    # Profit factor
    gross_profit = sum(t["pnl"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0.01
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Sharpe
    returns = [t["profit_pct"] / 100 for t in trades]
    avg_ret = np.mean(returns)
    std_ret = np.std(returns) if len(returns) > 1 else 1
    sharpe = (avg_ret / std_ret) * np.sqrt(365 * 288 / max(len(trades), 1)) if std_ret > 0 else 0

    avg_bars = np.mean([t["bars_held"] for t in trades])

    return {
        "return_pct": total_return,
        "win_rate": len(wins) / len(trades) * 100 if trades else 0,
        "max_dd": max_dd * 100,
        "profit_factor": pf,
        "n_trades": len(trades),
        "avg_win": np.mean([t["profit_pct"] for t in wins]) if wins else 0,
        "avg_loss": np.mean([t["profit_pct"] for t in losses]) if losses else 0,
        "sharpe": sharpe,
        "avg_bars": avg_bars,
        "final_capital": final_capital,
    }


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("\n  PFAA Multi-Coin Backtester")
    print("  " + "=" * 60)

    # Step 1: Load BTC data (existing)
    print("\n  [1/4] Loading BTC data from file...")
    btc_5m, btc_1h = load_btc_data()
    n_candles = len(btc_5m)
    print(f"        BTC: {n_candles} candles, ${btc_5m['close'].iloc[0]:,.0f} -> ${btc_5m['close'].iloc[-1]:,.0f}")

    # Compute BTC log-returns for correlation
    btc_log_returns = np.diff(np.log(btc_5m["close"].values))
    btc_log_returns = np.insert(btc_log_returns, 0, 0)

    # Step 2: Generate synthetic data for all coins
    print("\n  [2/4] Generating synthetic data for 15 altcoins...")
    coin_data = {}  # symbol -> (df_5m, df_1h)

    # BTC already loaded
    print(f"        Computing BTC indicators...")
    btc_5m_ind = populate_indicators(btc_5m.copy(), btc_1h.copy())
    coin_data["BTC"] = (btc_5m_ind, btc_1h)

    for symbol, cfg in COINS.items():
        if symbol == "BTC":
            continue
        seed = hash(symbol) % (2**31)
        corr = cfg.get("btc_corr", 0.3 + np.random.uniform(-0.1, 0.1))  # default ~0.3 correlation

        print(f"        Generating {symbol:5s} (vol={cfg['vol_lo']:.3f}-{cfg['vol_hi']:.3f}, "
              f"start=${cfg['start_price']}, cat={cfg['category']})...")

        df_5m = generate_synthetic_ohlcv(
            symbol=symbol,
            n_candles=n_candles,
            start_price=cfg["start_price"],
            vol_lo=cfg["vol_lo"],
            vol_hi=cfg["vol_hi"],
            btc_returns=btc_log_returns,
            btc_corr=corr,
            seed=seed,
        )
        df_1h = resample_to_1h(df_5m)

        print(f"                 price: ${df_5m['close'].iloc[0]:,.6g} -> ${df_5m['close'].iloc[-1]:,.6g}")

        df_5m_ind = populate_indicators(df_5m.copy(), df_1h.copy())
        coin_data[symbol] = (df_5m_ind, df_1h)

    # Step 3: Run backtests
    print(f"\n  [3/4] Running backtests with v9 params (min_score={PARAMS['min_score']}, "
          f"sl={PARAMS['stoploss']}, trail={PARAMS['trailing_distance']})...")

    results = {}
    for symbol in COINS:
        df_5m_ind, _ = coin_data[symbol]
        trades, final_cap = backtest(df_5m_ind, PARAMS)
        metrics = compute_metrics(trades, final_cap)
        results[symbol] = metrics
        status = "OK" if metrics["return_pct"] > 0 else "LOSS"
        print(f"        {symbol:5s}: {metrics['return_pct']:+7.1f}% | "
              f"{metrics['n_trades']:3d} trades | "
              f"WR {metrics['win_rate']:5.1f}% | "
              f"DD {metrics['max_dd']:5.1f}% | {status}")

    # Step 4: Print results table
    print("\n  [4/4] Results Summary")
    print("  " + "=" * 100)
    header = (f"  {'Coin':6s} {'Category':10s} {'Return':>8s} {'Trades':>7s} "
              f"{'WinRate':>8s} {'MaxDD':>7s} {'PF':>6s} {'Sharpe':>7s} "
              f"{'AvgWin':>7s} {'AvgLoss':>8s} {'AvgBars':>8s} {'Final$':>10s}")
    print(header)
    print("  " + "-" * 100)

    profitable = 0
    for symbol in COINS:
        m = results[symbol]
        cat = COINS[symbol]["category"]
        ret_color = "\033[32m" if m["return_pct"] > 0 else "\033[31m"
        wr_color = "\033[32m" if m["win_rate"] > 50 else "\033[31m"
        dd_color = "\033[32m" if m["max_dd"] < 15 else ("\033[33m" if m["max_dd"] < 25 else "\033[31m")
        pf_color = "\033[32m" if m["profit_factor"] > 1.5 else ("\033[33m" if m["profit_factor"] > 1 else "\033[31m")
        reset = "\033[0m"

        if m["return_pct"] > 0:
            profitable += 1

        print(f"  {symbol:6s} {cat:10s} "
              f"{ret_color}{m['return_pct']:+7.1f}%{reset} "
              f"{m['n_trades']:7d} "
              f"{wr_color}{m['win_rate']:7.1f}%{reset} "
              f"{dd_color}{m['max_dd']:6.1f}%{reset} "
              f"{pf_color}{m['profit_factor']:6.2f}{reset} "
              f"{m['sharpe']:7.2f} "
              f"{m['avg_win']:+6.2f}% "
              f"{m['avg_loss']:+7.2f}% "
              f"{m['avg_bars']:7.0f} "
              f"${m['final_capital']:>9,.0f}")

    print("  " + "-" * 100)

    avg_return = np.mean([results[s]["return_pct"] for s in COINS])
    avg_wr = np.mean([results[s]["win_rate"] for s in COINS if results[s]["n_trades"] > 0])
    avg_dd = np.mean([results[s]["max_dd"] for s in COINS if results[s]["n_trades"] > 0])
    avg_pf = np.mean([results[s]["profit_factor"] for s in COINS if results[s]["n_trades"] > 0 and results[s]["profit_factor"] < 100])

    print(f"  {'AVG':6s} {'':10s} {avg_return:+7.1f}%         {avg_wr:7.1f}%  {avg_dd:6.1f}%  {avg_pf:6.2f}")
    print(f"\n  Profitable coins: {profitable}/{len(COINS)}")

    # Step 5: Per-category analysis and parameter suggestions
    print("\n\n  PER-CATEGORY ANALYSIS & PARAMETER SUGGESTIONS")
    print("  " + "=" * 70)

    categories = {}
    for symbol, cfg in COINS.items():
        cat = cfg["category"]
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((symbol, results[symbol]))

    needs_adjustment = []

    for cat, coin_results in sorted(categories.items()):
        avg_ret = np.mean([m["return_pct"] for _, m in coin_results])
        avg_wr_cat = np.mean([m["win_rate"] for _, m in coin_results if m["n_trades"] > 0])
        avg_dd_cat = np.mean([m["max_dd"] for _, m in coin_results if m["n_trades"] > 0])
        n_profitable = sum(1 for _, m in coin_results if m["return_pct"] > 0)
        symbols = [s for s, _ in coin_results]

        print(f"\n  Category: {cat.upper()} ({', '.join(symbols)})")
        print(f"    Avg Return: {avg_ret:+.1f}% | Avg WR: {avg_wr_cat:.1f}% | Avg DD: {avg_dd_cat:.1f}% | Profitable: {n_profitable}/{len(coin_results)}")

        # Identify problems and suggest fixes
        if avg_dd_cat > 20:
            needs_adjustment.append((cat, "high_dd"))
            print(f"    WARNING: High drawdown ({avg_dd_cat:.1f}%) -- needs wider stops or lower allocation")
        if avg_wr_cat < 45:
            needs_adjustment.append((cat, "low_wr"))
            print(f"    WARNING: Low win rate ({avg_wr_cat:.1f}%) -- needs higher min_score or better filters")
        if avg_ret < -5:
            needs_adjustment.append((cat, "losing"))
            print(f"    WARNING: Losing strategy ({avg_ret:+.1f}%) -- significant parameter changes needed")

    # Specific suggestions
    print("\n\n  SUGGESTED PER-COIN PARAMETER ADJUSTMENTS")
    print("  " + "=" * 70)

    for symbol in COINS:
        m = results[symbol]
        cat = COINS[symbol]["category"]
        vol_hi = COINS[symbol]["vol_hi"]
        suggestions = []

        if m["n_trades"] == 0:
            suggestions.append("No trades: lower min_score to 4, lower accumulation_min_score to 5")
        else:
            # High drawdown -> wider stoploss + lower allocation
            if m["max_dd"] > 25:
                new_sl = round(PARAMS["stoploss"] * (1 + vol_hi * 10), 3)
                suggestions.append(f"stoploss: {PARAMS['stoploss']} -> {new_sl} (wider for high vol)")
                suggestions.append(f"atr_sl_loss: {PARAMS['atr_sl_loss']} -> {PARAMS['atr_sl_loss'] + 1.0:.1f}")

            # Low win rate -> higher entry bar
            if m["win_rate"] < 45:
                suggestions.append(f"min_score: {PARAMS['min_score']} -> {PARAMS['min_score'] + 1}")
                suggestions.append(f"accumulation_min_score: {PARAMS['accumulation_min_score']} -> {PARAMS['accumulation_min_score'] + 1}")

            # Meme coins: wider everything
            if cat == "meme":
                suggestions.append(f"stoploss: -> -0.035 (meme needs breathing room)")
                suggestions.append(f"trailing_distance: -> 0.025 (wider trail for meme spikes)")
                suggestions.append(f"trailing_activation: -> 0.04 (let meme runs develop)")
                suggestions.append(f"cooldown_candles: -> 72 (longer cooldown for meme chop)")

            # DEX tokens: similar to meme
            if cat == "dex_token":
                suggestions.append(f"stoploss: -> -0.03 (new DEX tokens need room)")
                suggestions.append(f"trailing_distance: -> 0.02 (moderate trail)")

            # Very few trades -> relax entry
            if m["n_trades"] < 20:
                suggestions.append(f"min_score: {PARAMS['min_score']} -> {max(3, PARAMS['min_score'] - 1)} (too few entries)")

            # Good PF but low return -> more trades needed
            if m["profit_factor"] > 1.5 and m["return_pct"] < 5 and m["n_trades"] < 50:
                suggestions.append("Strategy is profitable but conservative -- lower min_score for more entries")

            # High avg loss -> tighter stops
            if m["avg_loss"] < -2.0:
                suggestions.append(f"atr_sl_loss: -> {max(2.0, PARAMS['atr_sl_loss'] - 0.5):.1f} (cut losses faster)")

        if suggestions:
            print(f"\n  {symbol} ({cat}):")
            for s in suggestions:
                print(f"    - {s}")
        else:
            print(f"\n  {symbol} ({cat}): v9 params work well, no changes needed")

    # Final summary
    print("\n\n  OVERALL ASSESSMENT")
    print("  " + "=" * 70)
    print(f"  Coins profitable with default v9 params: {profitable}/{len(COINS)} ({profitable/len(COINS)*100:.0f}%)")
    print(f"  Average return across all coins: {avg_return:+.1f}%")
    if profitable >= 12:
        print("  VERDICT: Strategy generalizes well. Minor per-coin tuning recommended.")
    elif profitable >= 8:
        print("  VERDICT: Strategy works for most coins. Meme/high-vol coins need wider stops.")
    else:
        print("  VERDICT: Strategy needs significant adaptation for altcoins.")
    print()


if __name__ == "__main__":
    main()
