#!/usr/bin/env python3
"""Fast grid-search optimizer for per-category params. Uses 8K candles, tight grid."""
import sys, os, copy, json, itertools, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.dirname(__file__))
from multi_coin_backtest import (COINS, CATEGORY_OVERRIDES, generate_synthetic_ohlcv,
                                  resample_to_1h, compute_metrics, load_btc_data)
from backtest_sandbox import populate_indicators, backtest, PARAMS

SEARCH_CANDLES = 8000

btc_5m, btc_1h = load_btc_data()
btc_log_ret = np.diff(np.log(btc_5m["close"].values))
btc_log_ret = np.insert(btc_log_ret, 0, 0)

cats = {}
for sym, cfg in COINS.items():
    cats.setdefault(cfg["category"], []).append(sym)

print(f"Generating {SEARCH_CANDLES}-candle data...")
search_frames = {}
for sym, cfg in COINS.items():
    if sym == "BTC":
        df5 = btc_5m.iloc[:SEARCH_CANDLES].copy()
        df1 = resample_to_1h(df5)
    else:
        seed = hash(sym) % (2**31)
        df5 = generate_synthetic_ohlcv(
            sym, n_candles=SEARCH_CANDLES, start_price=cfg["start_price"],
            vol_lo=cfg["vol_lo"], vol_hi=cfg["vol_hi"],
            btc_returns=btc_log_ret[:SEARCH_CANDLES], btc_corr=cfg["btc_corr"], seed=seed)
        df1 = resample_to_1h(df5)
    df5 = populate_indicators(df5, df1)
    search_frames[sym] = df5
print("Ready.\n")

# Tight grids: 36 combos each (3*3*2*2)
grids = {
    "major": {
        "stoploss": [-0.015, -0.02, -0.025],
        "atr_sl_loss": [2.0, 3.0, 4.0],
        "trailing_distance": [0.01, 0.015],
        "profit_lock_pct": [0.008, 0.012],
    },
    "L1": {
        "stoploss": [-0.025, -0.035, -0.045],
        "atr_sl_loss": [2.5, 3.5, 4.5],
        "trailing_distance": [0.015, 0.025],
        "profit_lock_pct": [0.01, 0.015],
    },
    "L2": {
        "stoploss": [-0.025, -0.035, -0.045],
        "atr_sl_loss": [2.5, 3.5, 4.5],
        "trailing_distance": [0.015, 0.025],
        "profit_lock_pct": [0.01, 0.015],
    },
    "meme": {
        "stoploss": [-0.04, -0.055, -0.07],
        "atr_sl_loss": [4.0, 5.5, 7.0],
        "trailing_distance": [0.025, 0.04],
        "profit_lock_pct": [0.015, 0.025],
    },
    "dex_token": {
        "stoploss": [-0.035, -0.05, -0.065],
        "atr_sl_loss": [3.0, 4.5, 6.0],
        "trailing_distance": [0.02, 0.035],
        "profit_lock_pct": [0.012, 0.02],
    },
    "defi": {
        "stoploss": [-0.02, -0.03, -0.04],
        "atr_sl_loss": [2.5, 3.0, 4.0],
        "trailing_distance": [0.015, 0.025],
        "profit_lock_pct": [0.008, 0.012],
    },
    "rwa": {
        "stoploss": [-0.015, -0.025, -0.035],
        "atr_sl_loss": [2.0, 2.5, 3.5],
        "trailing_distance": [0.012, 0.02],
        "profit_lock_pct": [0.006, 0.01],
    },
}

best_params = {}
t0 = time.time()

for cat, syms in cats.items():
    grid = grids[cat]
    keys = list(grid.keys())
    combos = list(itertools.product(*grid.values()))
    print(f"=== {cat} ({syms}) -- {len(combos)} combos ===")

    best_score = -9999
    best_combo = None
    best_detail = None

    for combo in combos:
        override = dict(zip(keys, combo))
        base = copy.deepcopy(CATEGORY_OVERRIDES.get(cat, {}))
        base.update(override)

        rets, dds, pfs = [], [], []
        details = {}
        for sym in syms:
            p = copy.deepcopy(PARAMS)
            p.update(base)
            trades, cap = backtest(search_frames[sym], p)
            m = compute_metrics(trades, cap)
            rets.append(m["return_pct"])
            dds.append(m["max_dd"])
            pfs.append(m["profit_factor"])
            details[sym] = m

        avg_ret = np.mean(rets)
        avg_dd = np.mean(dds)
        avg_pf = np.mean(pfs)
        score = avg_ret - max(0, avg_dd - 25) * 2 + (avg_pf - 1) * 20

        if score > best_score:
            best_score = score
            best_combo = override
            best_detail = details

    best_params[cat] = best_combo
    elapsed = time.time() - t0
    print(f"  BEST score={best_score:.1f} ({elapsed:.0f}s elapsed)")
    print(f"  Params: {best_combo}")
    for sym, m in best_detail.items():
        tag = "+" if m["return_pct"] > 0 else "-"
        print(f"    {sym}: {m['return_pct']:+.1f}% WR={m['win_rate']:.0f}% DD={m['max_dd']:.0f}% PF={m['profit_factor']:.2f} {tag}")
    print()

print(f"\nTotal time: {time.time()-t0:.0f}s")
print("\n" + "=" * 80)
print("OPTIMIZED PARAMS (JSON)")
print("=" * 80)
print(json.dumps(best_params, indent=2))
