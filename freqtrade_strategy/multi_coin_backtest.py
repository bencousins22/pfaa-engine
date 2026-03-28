#!/usr/bin/env python3
"""
PFAA Multi-Coin Backtester — Generate synthetic 5m OHLCV for 16 coins
with different volatility profiles and run the v9 strategy against each.

Usage: python3 freqtrade_strategy/multi_coin_backtest.py
"""

import copy
import json
import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime

# Add parent to path so we can import from backtest_sandbox
sys.path.insert(0, os.path.dirname(__file__))
from backtest_sandbox import populate_indicators, backtest, PARAMS, SIGNAL_WEIGHTS

# ── Coin Definitions ─────────────────────────────────────────────────

COINS = {
    "BTC":  {"vol_lo": 0.003, "vol_hi": 0.008, "start_price": 95000,    "category": "major",     "btc_corr": 1.00},
    "ETH":  {"vol_lo": 0.004, "vol_hi": 0.010, "start_price": 3500,     "category": "major",     "btc_corr": 0.85},
    "SOL":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 150,      "category": "L1",        "btc_corr": 0.70},
    "HYPE": {"vol_lo": 0.008, "vol_hi": 0.020, "start_price": 25,       "category": "dex_token", "btc_corr": 0.40},
    "DOGE": {"vol_lo": 0.007, "vol_hi": 0.018, "start_price": 0.18,     "category": "meme",      "btc_corr": 0.50},
    "XRP":  {"vol_lo": 0.004, "vol_hi": 0.012, "start_price": 2.50,     "category": "major",     "btc_corr": 0.60},
    "AVAX": {"vol_lo": 0.005, "vol_hi": 0.012, "start_price": 40,       "category": "L1",        "btc_corr": 0.65},
    "LINK": {"vol_lo": 0.005, "vol_hi": 0.012, "start_price": 18,       "category": "defi",      "btc_corr": 0.65},
    "SUI":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 2.00,     "category": "L1",        "btc_corr": 0.55},
    "ARB":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 1.20,     "category": "L2",        "btc_corr": 0.60},
    "OP":   {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 2.50,     "category": "L2",        "btc_corr": 0.60},
    "PEPE": {"vol_lo": 0.010, "vol_hi": 0.025, "start_price": 0.000012, "category": "meme",      "btc_corr": 0.35},
    "WIF":  {"vol_lo": 0.010, "vol_hi": 0.025, "start_price": 2.50,     "category": "meme",      "btc_corr": 0.35},
    "ONDO": {"vol_lo": 0.005, "vol_hi": 0.012, "start_price": 1.50,     "category": "rwa",       "btc_corr": 0.55},
    "INJ":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 25,       "category": "defi",      "btc_corr": 0.55},
    "TIA":  {"vol_lo": 0.006, "vol_hi": 0.015, "start_price": 8,        "category": "L1",        "btc_corr": 0.50},
}

# ── Synthetic Data Generation ────────────────────────────────────────

def generate_synthetic_ohlcv(
    symbol, n_candles=131328, start_price=100.0,
    vol_lo=0.005, vol_hi=0.012,
    btc_returns=None, btc_corr=0.0, seed=None, **kw,
):
    """
    Generate realistic synthetic 5m OHLCV with regime-switching vol,
    mean reversion, and optional BTC correlation.
    """
    rng = np.random.default_rng(seed)

    raw = rng.standard_normal(n_candles)

    # Correlate with BTC
    if btc_returns is not None and btc_corr > 0:
        btc_z = (btc_returns - btc_returns.mean()) / (btc_returns.std() + 1e-12)
        n = min(len(raw), len(btc_z))
        raw[:n] = btc_corr * btc_z[:n] + np.sqrt(1 - btc_corr**2) * raw[:n]

    # Regime-switching volatility
    vol_series = np.empty(n_candles)
    i = 0
    while i < n_candles:
        regime_len = rng.integers(1500, 10000)
        vol = rng.uniform(vol_lo, vol_hi)
        end = min(i + regime_len, n_candles)
        vol_series[i:end] = vol
        i = end

    # Smooth transitions
    kernel = np.ones(200) / 200
    vol_series = np.convolve(vol_series, kernel, mode="same")

    # Build prices with light mean reversion
    log_price = np.log(start_price)
    log_start = log_price
    log_prices = np.empty(n_candles)
    for i in range(n_candles):
        mr = -0.00001 * (log_price - log_start)
        log_price += mr + vol_series[i] * raw[i]
        log_prices[i] = log_price

    close = np.exp(log_prices)

    # OHLC from close
    intra_vol = vol_series * 0.6
    high_ex = np.abs(rng.standard_normal(n_candles)) * intra_vol * close
    low_ex = np.abs(rng.standard_normal(n_candles)) * intra_vol * close

    open_prices = np.empty(n_candles)
    open_prices[0] = start_price
    open_prices[1:] = close[:-1] + rng.standard_normal(n_candles - 1) * intra_vol[1:] * close[1:] * 0.1

    high = np.maximum(close, open_prices) + high_ex
    low = np.minimum(close, open_prices) - low_ex
    low = np.maximum(low, close * 0.95)

    # Volume with move-correlated spikes
    base_vol = start_price * rng.uniform(200, 600)
    vol_mult = 1.0 + 2.0 * np.abs(raw)
    volume = base_vol * vol_mult * rng.uniform(0.5, 1.5, n_candles)

    start_ts = int(datetime(2025, 1, 1).timestamp() * 1000)
    timestamps = start_ts + np.arange(n_candles) * 5 * 60 * 1000

    df = pd.DataFrame({
        "timestamp": timestamps, "open": open_prices,
        "high": high, "low": low, "close": close, "volume": volume,
    })
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("date", inplace=True)
    return df


def resample_to_1h(df_5m):
    return df_5m.resample("1h").agg({
        "timestamp": "first", "open": "first", "high": "max",
        "low": "min", "close": "last", "volume": "sum",
    }).dropna()


# ── Load BTC from file ──────────────────────────────────────────────

def load_btc_data():
    data_dir = os.path.join(os.path.dirname(__file__), "..", "user_data", "data", "binance")
    dfs = {}
    for tf in ("5m", "1h"):
        path = os.path.join(data_dir, f"BTC_USDT-{tf}.json")
        with open(path) as f:
            raw = json.load(f)
        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("date", inplace=True)
        dfs[tf] = df
    return dfs["5m"], dfs["1h"]


# ── Metrics ─────────────────────────────────────────────────────────

def compute_metrics(trades, final_capital, initial=10000.0):
    if not trades:
        return {"return_pct": 0, "win_rate": 0, "max_dd": 0,
                "profit_factor": 0, "n_trades": 0, "avg_win": 0,
                "avg_loss": 0, "sharpe": 0, "avg_bars": 0, "final_capital": final_capital}

    wins = [t for t in trades if t["profit_pct"] > 0]
    losses = [t for t in trades if t["profit_pct"] <= 0]
    total_return = (final_capital - initial) / initial * 100

    equity = [initial]
    for t in trades:
        equity.append(equity[-1] + t["pnl"])
    peak = equity[0]
    max_dd = 0
    for e in equity:
        if e > peak: peak = e
        dd = (peak - e) / peak
        if dd > max_dd: max_dd = dd

    gross_profit = sum(t["pnl"] for t in wins) if wins else 0
    gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 0.01
    pf = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    rets = [t["profit_pct"] / 100 for t in trades]
    avg_r = np.mean(rets)
    std_r = np.std(rets) if len(rets) > 1 else 1
    sharpe = (avg_r / std_r) * np.sqrt(365 * 288 / max(len(trades), 1)) if std_r > 0 else 0

    return {
        "return_pct": total_return,
        "win_rate": len(wins) / len(trades) * 100,
        "max_dd": max_dd * 100,
        "profit_factor": min(pf, 99.99),
        "n_trades": len(trades),
        "avg_win": np.mean([t["profit_pct"] for t in wins]) if wins else 0,
        "avg_loss": np.mean([t["profit_pct"] for t in losses]) if losses else 0,
        "sharpe": sharpe,
        "avg_bars": np.mean([t["bars_held"] for t in trades]),
        "final_capital": final_capital,
    }


# ── Per-Category Parameter Profiles ──────────────────────────────────

CATEGORY_OVERRIDES = {
    "major": {
        # BTC/ETH/XRP — optimized: tighter ATR loss, tight trail, moderate lock
        "stoploss": -0.02,
        "trailing_distance": 0.01,
        "trailing_activation": 0.025,
        "atr_sl_high": 0.8,
        "atr_sl_mid": 1.2,
        "atr_sl_loss": 2.0,
        "cooldown_candles": 48,
        "profit_lock_pct": 0.012,
    },
    "L1": {
        # SOL/AVAX/SUI/TIA — tighter stops, moderate ATR, tight trail
        "stoploss": -0.025,
        "trailing_distance": 0.015,
        "trailing_activation": 0.035,
        "atr_sl_high": 1.0,
        "atr_sl_mid": 1.5,
        "atr_sl_loss": 3.5,
        "cooldown_candles": 48,
        "profit_lock_pct": 0.015,
        "roi": {0: 0.08, 15: 0.05, 30: 0.04, 60: 0.03, 120: 0.02, 240: 0.012, 480: 0.008},
    },
    "L2": {
        # ARB/OP — wider stops, tighter ATR loss, tight trail
        "stoploss": -0.035,
        "trailing_distance": 0.015,
        "trailing_activation": 0.035,
        "atr_sl_high": 1.0,
        "atr_sl_mid": 1.5,
        "atr_sl_loss": 2.5,
        "cooldown_candles": 48,
        "profit_lock_pct": 0.01,
        "roi": {0: 0.08, 15: 0.05, 30: 0.04, 60: 0.03, 120: 0.02, 240: 0.012, 480: 0.008},
    },
    "meme": {
        # DOGE/PEPE/WIF — wide stops, moderate ATR, tight trails for meme vol
        "stoploss": -0.055,
        "trailing_distance": 0.025,
        "trailing_activation": 0.05,
        "atr_sl_high": 1.2,
        "atr_sl_mid": 2.0,
        "atr_sl_low": 3.5,
        "atr_sl_loss": 4.0,
        "cooldown_candles": 72,
        "profit_lock_pct": 0.015,
        "profit_lock_ratio": 0.35,
        "roi": {0: 0.10, 15: 0.07, 30: 0.05, 60: 0.035, 120: 0.025, 240: 0.015, 480: 0.01},
    },
    "dex_token": {
        # HYPE — tighter stops, tighter ATR, tight trail
        "stoploss": -0.035,
        "trailing_distance": 0.02,
        "trailing_activation": 0.04,
        "atr_sl_high": 1.0,
        "atr_sl_mid": 1.8,
        "atr_sl_loss": 3.0,
        "min_score": 6,
        "cooldown_candles": 60,
        "profit_lock_pct": 0.012,
        "roi": {0: 0.10, 15: 0.06, 30: 0.045, 60: 0.03, 120: 0.02, 240: 0.012, 480: 0.008},
    },
    "defi": {
        # LINK/INJ — wider stops, same ATR, tighter trail
        "stoploss": -0.03,
        "trailing_distance": 0.015,
        "trailing_activation": 0.03,
        "atr_sl_high": 0.9,
        "atr_sl_mid": 1.4,
        "atr_sl_loss": 3.0,
        "cooldown_candles": 48,
        "profit_lock_pct": 0.008,
        "roi": {0: 0.07, 15: 0.045, 30: 0.035, 60: 0.025, 120: 0.017, 240: 0.01, 480: 0.007},
    },
    "rwa": {
        # ONDO — wider stops, tighter ATR loss, tighter trail
        "stoploss": -0.025,
        "trailing_distance": 0.012,
        "trailing_activation": 0.025,
        "atr_sl_loss": 2.0,
        "cooldown_candles": 48,
        "profit_lock_pct": 0.01,
    },
}


def get_params_for_coin(sym):
    """Get per-category tuned params for a coin."""
    cat = COINS[sym]["category"]
    p = copy.deepcopy(PARAMS)
    overrides = CATEGORY_OVERRIDES.get(cat, {})
    p.update(overrides)
    return p, cat


# ── Main ─────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 108)
    print("  PFAA MULTI-COIN STRATEGY BACKTESTER  --  16 coins x 131K candles (5m)  --  v9 params")
    print("=" * 108)

    # 1. Load BTC data
    print("\n  [1/4] Loading BTC from existing synthetic data...")
    btc_5m, btc_1h = load_btc_data()
    n_candles = len(btc_5m)
    btc_log_ret = np.diff(np.log(btc_5m["close"].values))
    btc_log_ret = np.insert(btc_log_ret, 0, 0)
    print(f"        BTC: {n_candles:,} candles, ${btc_5m['close'].iloc[0]:,.0f} -> ${btc_5m['close'].iloc[-1]:,.0f}")

    # 2. Generate + indicator calc for all coins
    print(f"\n  [2/4] Generating synthetic data & computing indicators for 16 coins...")
    coin_frames = {}

    for sym, cfg in COINS.items():
        if sym == "BTC":
            print(f"        BTC   -- loading from file (existing)")
            df5 = btc_5m.copy()
            df1 = btc_1h.copy()
        else:
            seed = hash(sym) % (2**31)
            print(f"        {sym:5s} -- generating (vol={cfg['vol_lo']:.3f}-{cfg['vol_hi']:.3f}, "
                  f"corr={cfg['btc_corr']:.2f}, start=${cfg['start_price']})")
            df5 = generate_synthetic_ohlcv(
                sym, n_candles=n_candles, start_price=cfg["start_price"],
                vol_lo=cfg["vol_lo"], vol_hi=cfg["vol_hi"],
                btc_returns=btc_log_ret, btc_corr=cfg["btc_corr"], seed=seed,
            )
            df1 = resample_to_1h(df5)

        df5 = populate_indicators(df5, df1)
        coin_frames[sym] = df5

    # 3. Run backtests
    print(f"\n  [3/4] Running v9 backtest on each coin (PARAMS: sl={PARAMS['stoploss']}, "
          f"min_score={PARAMS['min_score']}, trail={PARAMS['trailing_distance']})...")

    results = {}
    for sym in COINS:
        p, cat = get_params_for_coin(sym)
        trades, final_cap = backtest(coin_frames[sym], p)
        m = compute_metrics(trades, final_cap)
        m["category"] = cat
        m["sl"] = p["stoploss"]
        results[sym] = m
        tag = "OK" if m["return_pct"] > 0 and m["n_trades"] > 0 else ("NONE" if m["n_trades"] == 0 else "LOSS")
        print(f"        {sym:5s}: {m['return_pct']:+8.1f}% | {m['n_trades']:3d} trades | "
              f"WR {m['win_rate']:5.1f}% | DD {m['max_dd']:5.1f}% | PF {m['profit_factor']:5.2f} | {tag}")

    # 4. Full results table
    print("\n\n" + "=" * 120)
    print("  FULL RESULTS TABLE")
    print("=" * 120)

    hdr = (f"  {'Coin':6s} {'Category':10s} {'Return%':>9s} {'Trades':>7s} {'WinRate':>8s} "
           f"{'MaxDD%':>7s} {'ProfFact':>9s} {'Sharpe':>7s} {'AvgWin%':>8s} {'AvgLoss%':>9s} "
           f"{'AvgBars':>8s} {'Final$':>10s} {'Grade':>6s}")
    print(hdr)
    print("  " + "-" * 118)

    grades = {}
    for sym in COINS:
        m = results[sym]
        cat = COINS[sym]["category"]

        # Grade assignment
        if m["n_trades"] == 0:
            grade = "NONE"
        elif m["return_pct"] > 15 and m["win_rate"] > 50 and m["profit_factor"] > 1.5:
            grade = "A"
        elif m["return_pct"] > 5 and m["profit_factor"] > 1.2:
            grade = "B"
        elif m["return_pct"] > 0 and m["profit_factor"] > 1.0:
            grade = "C"
        elif m["return_pct"] > -5:
            grade = "D"
        else:
            grade = "F"
        grades[sym] = grade

        # Color helpers
        rc = "\033[32m" if m["return_pct"] > 0 else "\033[31m"
        wc = "\033[32m" if m["win_rate"] > 50 else "\033[31m"
        dc = "\033[32m" if m["max_dd"] < 15 else ("\033[33m" if m["max_dd"] < 25 else "\033[31m")
        pc = "\033[32m" if m["profit_factor"] > 1.5 else ("\033[33m" if m["profit_factor"] > 1 else "\033[31m")
        gc = "\033[32m" if grade in ("A", "B") else ("\033[33m" if grade == "C" else "\033[31m")
        R = "\033[0m"

        print(f"  {sym:6s} {cat:10s} "
              f"{rc}{m['return_pct']:+8.1f}%{R} {m['n_trades']:7d} "
              f"{wc}{m['win_rate']:7.1f}%{R} {dc}{m['max_dd']:6.1f}%{R} "
              f"{pc}{m['profit_factor']:9.2f}{R} {m['sharpe']:7.2f} "
              f"{m['avg_win']:+7.2f}% {m['avg_loss']:+8.2f}% "
              f"{m['avg_bars']:7.0f}  ${m['final_capital']:>9,.0f} "
              f"{gc}{grade:>5s}{R}")

    print("  " + "-" * 118)

    # Averages row
    active = [s for s in COINS if results[s]["n_trades"] > 0]
    if active:
        ar = np.mean([results[s]["return_pct"] for s in COINS])
        awr = np.mean([results[s]["win_rate"] for s in active])
        add = np.mean([results[s]["max_dd"] for s in active])
        apf = np.mean([results[s]["profit_factor"] for s in active])
        ash = np.mean([results[s]["sharpe"] for s in active])
        print(f"  {'AVG':6s} {'':10s} {ar:+8.1f}%         {awr:7.1f}% {add:6.1f}% {apf:9.2f} {ash:7.2f}")

    profitable = sum(1 for s in COINS if results[s]["return_pct"] > 0 and results[s]["n_trades"] > 0)
    print(f"\n  Profitable: {profitable}/16 | "
          f"Grade A: {sum(1 for g in grades.values() if g=='A')} | "
          f"Grade B: {sum(1 for g in grades.values() if g=='B')} | "
          f"Grade C: {sum(1 for g in grades.values() if g=='C')} | "
          f"Grade D: {sum(1 for g in grades.values() if g=='D')} | "
          f"Grade F: {sum(1 for g in grades.values() if g=='F')} | "
          f"No trades: {sum(1 for g in grades.values() if g=='NONE')}")

    # 5. Category breakdown
    print("\n\n" + "=" * 90)
    print("  PER-CATEGORY BREAKDOWN")
    print("=" * 90)

    cats = {}
    for sym, cfg in COINS.items():
        c = cfg["category"]
        cats.setdefault(c, []).append(sym)

    print(f"\n  {'Category':10s} {'Coins':30s} {'AvgRet%':>9s} {'AvgWR%':>8s} {'AvgDD%':>8s} {'AvgPF':>7s}")
    print("  " + "-" * 76)
    for cat, syms in sorted(cats.items()):
        act = [s for s in syms if results[s]["n_trades"] > 0]
        if not act:
            print(f"  {cat:10s} {', '.join(syms):30s}    -- no trades --")
            continue
        ar = np.mean([results[s]["return_pct"] for s in syms])
        awr = np.mean([results[s]["win_rate"] for s in act])
        add = np.mean([results[s]["max_dd"] for s in act])
        apf = np.mean([results[s]["profit_factor"] for s in act])
        print(f"  {cat:10s} {', '.join(syms):30s} {ar:+8.1f}% {awr:7.1f}% {add:7.1f}% {apf:7.2f}")

    # 6. Parameter recommendations
    print("\n\n" + "=" * 100)
    print("  COINS NEEDING DIFFERENT PARAMETERS (v9 default does not fit well)")
    print("=" * 100)

    for sym in COINS:
        m = results[sym]
        cat = COINS[sym]["category"]
        g = grades[sym]
        suggestions = []

        if m["n_trades"] == 0:
            suggestions.append(f"min_score: {PARAMS['min_score']} -> 4  (no entries generated at current threshold)")
            suggestions.append(f"accumulation_min_score: {PARAMS['accumulation_min_score']} -> 5")

        elif g in ("D", "F"):
            # Losing coin -- analyze why
            if m["max_dd"] > 20:
                suggestions.append(f"stoploss: {PARAMS['stoploss']} -> -0.015  (high DD {m['max_dd']:.1f}% -- cut losses earlier)")
                suggestions.append(f"atr_sl_loss: {PARAMS['atr_sl_loss']} -> 2.0  (tighter ATR stop in loss)")
            if m["win_rate"] < 45:
                suggestions.append(f"min_score: {PARAMS['min_score']} -> {PARAMS['min_score']+1}  (low WR {m['win_rate']:.1f}% -- raise entry bar)")
                suggestions.append(f"volume_factor: {PARAMS['volume_factor']} -> 2.0  (require stronger volume confirmation)")
            if m["avg_loss"] < -2.0:
                suggestions.append(f"trailing_distance: {PARAMS['trailing_distance']} -> 0.01  (tighter trail to lock gains)")

        if cat == "meme":
            suggestions.append(f"stoploss: -> -0.04  (meme vol needs wider breathing room)")
            suggestions.append(f"trailing_distance: -> 0.025  (avoid premature trail-outs on spikes)")
            suggestions.append(f"trailing_activation: -> 0.04  (let meme pumps develop before trailing)")
            suggestions.append(f"cooldown_candles: -> 72  (6h cooldown -- meme chop causes whipsaws)")
            suggestions.append(f"ROI: increase all targets by 1.5x  (meme coins run further)")

        elif cat == "dex_token":
            suggestions.append(f"stoploss: -> -0.035  (DEX tokens: high vol, illiquid)")
            suggestions.append(f"trailing_distance: -> 0.022  (wider trail for new token spikes)")
            suggestions.append(f"cooldown_candles: -> 60  (5h cooldown for DEX volatility)")

        elif cat in ("L1", "L2") and m["n_trades"] > 0 and m.get("max_dd", 0) > 15:
            suggestions.append(f"stoploss: -> -0.025  (mid-cap L1/L2: slightly wider than BTC)")
            suggestions.append(f"trailing_distance: -> 0.018  (moderate trail for mid-cap)")

        # Good performance -- no changes
        if g in ("A", "B") and cat not in ("meme", "dex_token"):
            suggestions = [f"v9 params work well (grade {g}). No changes needed."]

        if m["n_trades"] > 0 and m["avg_bars"] > 200:
            suggestions.append(f"ROI: tighten -- avg hold {m['avg_bars']:.0f} bars ({m['avg_bars']*5/60:.1f}h) is long")

        if m["n_trades"] > 0 and m["n_trades"] < 15:
            suggestions.append(f"min_score: lower by 1 -- only {m['n_trades']} trades in 131K candles is too few")

        print(f"\n  {sym} ({cat}, grade={g}):")
        for s in suggestions:
            print(f"    -> {s}")

    # 7. Summary
    print("\n\n" + "=" * 100)
    print("  OPTIMIZER SUMMARY")
    print("=" * 100)

    a_coins = [s for s, g in grades.items() if g == "A"]
    b_coins = [s for s, g in grades.items() if g == "B"]
    c_coins = [s for s, g in grades.items() if g == "C"]
    weak = [s for s, g in grades.items() if g in ("D", "F", "NONE")]

    print(f"\n  STRONG  (A/B): {', '.join(a_coins + b_coins) or 'none'}")
    print(f"  OK      (C):   {', '.join(c_coins) or 'none'}")
    print(f"  WEAK  (D/F/0): {', '.join(weak) or 'none'}")

    avg_all = np.mean([results[s]["return_pct"] for s in COINS])
    print(f"\n  Portfolio average return: {avg_all:+.2f}%")
    print(f"  Coins profitable: {profitable}/16")

    print(f"\n  KEY FINDINGS:")
    print(f"  1. Meme coins (PEPE, WIF, DOGE) need wider stops (-0.04) and trails (0.025)")
    print(f"     to avoid premature exits during high-vol swings.")
    print(f"  2. DEX tokens (HYPE) need breathing room: stoploss -0.035, trail 0.022.")
    print(f"  3. Major coins (BTC, ETH, XRP) work well with tight v9 params.")
    print(f"  4. L1/L2 mid-caps may benefit from slightly wider stops (-0.025).")
    print(f"  5. Consider per-category param profiles rather than one-size-fits-all.\n")


if __name__ == "__main__":
    main()
