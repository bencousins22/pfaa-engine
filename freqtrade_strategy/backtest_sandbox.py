#!/usr/bin/env python3
"""
Aussie Agents Sandbox Backtester — Run strategy logic against generated BTC data.

Bypasses FreqTrade exchange connectivity requirement by implementing
the core backtesting engine directly with ta-lib indicators.

Usage: python3 freqtrade_strategy/backtest_sandbox.py
"""

import json
import numpy as np
import os
import sys

try:
    import talib
except ImportError:
    print("Installing ta-lib...")
    os.system("pip3 install ta-lib 2>/dev/null || pip3 install TA-Lib 2>/dev/null")
    import talib

import pandas as pd
from datetime import datetime

# ── Load Data ─────────────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "user_data", "data", "binance")

def load_data(timeframe="5m"):
    path = os.path.join(DATA_DIR, f"BTC_USDT-{timeframe}.json")
    with open(path) as f:
        raw = json.load(f)
    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["date"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("date", inplace=True)
    return df

# ── Indicators ────────────────────────────────────────────────────────

def populate_indicators(df, df_1h=None):
    """Calculate all indicators matching PFAABitcoinStrategy."""
    # EMAs
    for p in [3, 5, 8, 9, 13, 21, 34, 55, 89, 100, 200, 233]:
        df[f"ema_{p}"] = talib.EMA(df["close"], timeperiod=p)

    # RSI
    df["rsi"] = talib.RSI(df["close"], timeperiod=14)

    # Stochastic RSI
    df["stoch_rsi_k"], df["stoch_rsi_d"] = talib.STOCHRSI(
        df["close"], timeperiod=14, fastk_period=3, fastd_period=3
    )

    # Bollinger Bands
    df["bb_upper"], df["bb_middle"], df["bb_lower"] = talib.BBANDS(
        df["close"], timeperiod=20, nbdevup=2.0, nbdevdn=2.0
    )
    df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]

    # MACD
    df["macd"], df["macd_signal"], df["macd_hist"] = talib.MACD(
        df["close"], fastperiod=12, slowperiod=26, signalperiod=9
    )

    # ATR
    df["atr"] = talib.ATR(df["high"], df["low"], df["close"], timeperiod=14)
    df["atr_pct"] = df["atr"] / df["close"]

    # Volume
    df["volume_mean_20"] = df["volume"].rolling(20).mean()
    df["volume_ratio"] = df["volume"] / df["volume_mean_20"].replace(0, 1)

    # ADX
    df["adx"] = talib.ADX(df["high"], df["low"], df["close"], timeperiod=14)

    # Market regime (simplified)
    df["ema_50"] = talib.EMA(df["close"], timeperiod=50)
    df["ema_200_calc"] = talib.EMA(df["close"], timeperiod=200)
    df["market_regime"] = 1  # default accumulation
    df.loc[(df["ema_50"] > df["ema_200_calc"]) & (df["adx"] > 20), "market_regime"] = 2  # markup
    df.loc[(df["ema_50"] < df["ema_200_calc"]) & (df["adx"] > 25) & (df["rsi"] > 65), "market_regime"] = 3  # distribution
    df.loc[(df["ema_50"] < df["ema_200_calc"]) & (df["adx"] > 20) & (df["rsi"] < 40), "market_regime"] = 4  # markdown

    # 1h trend (if available)
    if df_1h is not None:
        df_1h["ema_50_1h"] = talib.EMA(df_1h["close"], timeperiod=50)
        df_1h["ema_200_1h"] = talib.EMA(df_1h["close"], timeperiod=200)
        # Merge to 5m
        df_1h_resampled = df_1h[["ema_50_1h", "ema_200_1h"]].reindex(df.index, method="ffill")
        df["ema_50_1h"] = df_1h_resampled["ema_50_1h"]
        df["ema_200_1h"] = df_1h_resampled["ema_200_1h"]
    else:
        df["ema_50_1h"] = df["ema_50"]
        df["ema_200_1h"] = df["ema_200_calc"]

    return df

# ── Strategy Parameters ──────────────────────────────────────────────

PARAMS = {
    "ema_fast": 8,
    "ema_slow": 21,
    "ema_trend": 100,
    "rsi_low": 35,
    "rsi_high": 68,
    "bb_width_threshold": 0.02,
    "volume_factor": 1.5,
    "min_score": 5,
    "adx_threshold": 20,
    "sell_rsi_high": 88,
    "stoploss": -0.02,             # v9: -2% optimal
    "trailing_activation": 0.025,  # start trailing early
    "trailing_distance": 0.015,    # tight trail — lock profits aggressively
    "roi": {0: 0.06, 15: 0.04, 30: 0.03, 60: 0.022, 120: 0.015, 240: 0.01, 480: 0.006},
    "atr_sl_high": 0.8,           # v9: very tight in profit
    "atr_sl_mid": 1.2,            # v9: tight mid-profit ATR
    "atr_sl_low": 2.5,            # moderate when barely profitable
    "atr_sl_loss": 3.0,           # tight in loss — exit quickly, re-enter later
    "cooldown_candles": 48,        # 4hr cooldown — wait for conditions to change
    "profit_lock_pct": 0.01,      # v9: lock 1% profit (earlier trigger)
    "max_dd_circuit": 0.25,       # pause trading if drawdown > 25%
    "dd_recovery_pct": 0.4,       # resume when DD recovers 40%
    "accumulation_min_score": 6,  # higher bar during accumulation regime
}

# Optimized weights from signal weight search: [ema, rsi, bb, macd, vol, 1h_trend, regime, stochrsi, adx, mean_rev]
SIGNAL_WEIGHTS = [2, 0, 1, 0, 2, 3, 2, 1, 1, 2]  # RSI=0 MACD=0: single-candle noise. 1h_trend=3: highest conviction

# ── Entry Signal Scoring ─────────────────────────────────────────────

def compute_entry_scores(df, p=PARAMS, weights=None):
    """Compute weighted entry scores matching the strategy."""
    w = weights or SIGNAL_WEIGHTS
    scores = pd.Series(0, index=df.index, dtype=float)

    ema_fast = f"ema_{p['ema_fast']}"
    ema_slow = f"ema_{p['ema_slow']}"
    ema_trend = f"ema_{p['ema_trend']}"

    # Signal 1: EMA cross (w=2)
    cross = (df[ema_fast] > df[ema_slow]) & (df[ema_fast].shift(1) <= df[ema_slow].shift(1))
    above_trend = df["close"] > df[ema_trend]
    scores += (cross & above_trend).astype(int) * w[0]

    # Signal 2: RSI momentum (w=0 — noise on 5m, doesn't help)
    rsi_in_range = (df["rsi"] > p["rsi_low"]) & (df["rsi"] < p["rsi_high"])
    rsi_rising = df["rsi"] > df["rsi"].shift(1)
    scores += (rsi_in_range & rsi_rising).astype(int) * w[1]

    # Signal 3: BB squeeze breakout (w=1)
    bb_cross = (df["close"] > df["bb_middle"]) & (df["close"].shift(1) <= df["bb_middle"].shift(1))
    bb_wide = df["bb_width"] > p["bb_width_threshold"]
    scores += (bb_cross & bb_wide).astype(int) * w[2]

    # Signal 4: MACD crossover (w=0 — fires on single candle, too noisy)
    macd_cross = (df["macd_hist"] > 0) & (df["macd_hist"].shift(1) <= 0)
    macd_pos = df["macd"] > df["macd_signal"]
    scores += (macd_cross & macd_pos).astype(int) * w[3]

    # Signal 5: Volume confirmation (w=2)
    scores += (df["volume_ratio"] > p["volume_factor"]).astype(int) * w[4]

    # Signal 6: 1h trend alignment (w=3 — highest conviction signal)
    trend_aligned = (df["ema_50_1h"] > df["ema_200_1h"]) & (df["close"] > df["ema_50_1h"])
    scores += trend_aligned.astype(int) * w[5]

    # Signal 7: Market regime bonus (w=2)
    scores += (df["market_regime"] == 2).astype(int) * w[6]

    # Signal 8: StochRSI crossover (w=1)
    stoch_cross = (df["stoch_rsi_k"] > df["stoch_rsi_d"]) & (df["stoch_rsi_k"].shift(1) <= df["stoch_rsi_d"].shift(1))
    stoch_oversold = df["stoch_rsi_k"] < 20
    scores += (stoch_cross & stoch_oversold).astype(int) * w[7]

    # Signal 9: ADX filter (w=1)
    scores += (df["adx"] > p["adx_threshold"]).astype(int) * w[8]

    # Signal 10: Mean reversion (w=2)
    mean_rev = (df["close"] < df["bb_lower"]) & (df["rsi"] < 28)
    scores += mean_rev.astype(int) * w[9]

    return scores

# ── Backtester ────────────────────────────────────────────────────────

def backtest(df, p=PARAMS, initial_capital=10000.0):
    """Run backtest with the strategy logic."""
    scores = compute_entry_scores(df, p)

    capital = initial_capital
    position = None  # {"entry_price", "entry_idx", "size", "trailing_high"}
    trades = []
    cooldown_until = 0  # index until which we skip entries after a loss
    equity_peak = initial_capital
    circuit_tripped = False

    for i in range(200, len(df)):  # skip warmup
        row = df.iloc[i]
        price = row["close"]
        atr_pct = row.get("atr_pct", 0.003)

        if position is not None:
            # Update trailing high and max profit
            if price > position["trailing_high"]:
                position["trailing_high"] = price

            entry_price = position["entry_price"]
            profit_pct = (price - entry_price) / entry_price
            if profit_pct > position.get("max_profit", 0):
                position["max_profit"] = profit_pct
            bars_held = i - position["entry_idx"]

            # Exit checks
            exit_reason = None

            # 1. Hard stoploss
            if profit_pct <= p["stoploss"]:
                exit_reason = "stoploss"

            # 2. ATR-based dynamic stoploss
            if not exit_reason:
                if profit_pct > 0.04:
                    sl = -atr_pct * p["atr_sl_high"]
                elif profit_pct > 0.02:
                    sl = -atr_pct * p["atr_sl_mid"]
                elif profit_pct > 0:
                    sl = -atr_pct * p["atr_sl_low"]
                else:
                    sl = -atr_pct * p["atr_sl_loss"]

                drawdown = (price - position["trailing_high"]) / position["trailing_high"]
                if drawdown < sl:
                    exit_reason = "atr_trailing"

            # 2b. Profit lock — once we hit profit_lock_pct, never give it all back
            if not exit_reason and position.get("max_profit", 0) >= p.get("profit_lock_pct", 0.02):
                if profit_pct < position["max_profit"] * 0.4:  # gave back 60% of max profit
                    exit_reason = "profit_lock"

            # 3. Trailing stop
            if not exit_reason and profit_pct > p["trailing_activation"]:
                trail_sl = position["trailing_high"] * (1 - p["trailing_distance"])
                if price < trail_sl:
                    exit_reason = "trailing_stop"

            # 4. ROI table
            if not exit_reason:
                minutes = bars_held * 5
                for roi_min, roi_pct in sorted(p["roi"].items()):
                    if minutes >= roi_min and profit_pct >= roi_pct:
                        exit_reason = f"roi_{roi_min}m"
                        break

            # 5. RSI overbought
            if not exit_reason and row["rsi"] > p["sell_rsi_high"]:
                exit_reason = "rsi_exit"

            # 6. Mean reversion exit (BB middle)
            if not exit_reason and profit_pct > 0.005:
                if entry_price <= row.get("bb_lower", entry_price) * 1.005:
                    if price >= row["bb_middle"]:
                        exit_reason = "mean_rev_exit"

            # 7. Regime shift
            if not exit_reason and row["market_regime"] >= 3 and profit_pct > 0.005:
                exit_reason = "regime_exit"

            # 8. RSI extreme
            if not exit_reason and row["rsi"] > 88:
                exit_reason = "rsi_extreme"

            # 9. Timeout (48 hours)
            if not exit_reason and bars_held > 576:
                exit_reason = "timeout"

            if exit_reason:
                pnl = position["size"] * profit_pct
                capital += position["size"] + pnl
                # Cooldown after losing trade
                if profit_pct < 0:
                    cooldown_until = i + p.get("cooldown_candles", 24)
                trades.append({
                    "entry_idx": position["entry_idx"],
                    "exit_idx": i,
                    "entry_price": entry_price,
                    "exit_price": price,
                    "profit_pct": profit_pct * 100,
                    "pnl": pnl,
                    "bars_held": bars_held,
                    "exit_reason": exit_reason,
                    "entry_date": df.index[position["entry_idx"]].strftime("%Y-%m-%d %H:%M"),
                    "exit_date": df.index[i].strftime("%Y-%m-%d %H:%M"),
                })
                position = None

        else:
            # Circuit breaker — pause trading during drawdowns
            equity = capital  # (no position = all cash)
            if equity > equity_peak:
                equity_peak = equity
            current_dd = (equity_peak - equity) / equity_peak if equity_peak > 0 else 0

            if circuit_tripped:
                # Check if we've recovered enough to resume
                if current_dd < p.get("max_dd_circuit", 0.20) * (1 - p.get("dd_recovery_pct", 0.5)):
                    circuit_tripped = False
                else:
                    continue  # skip this candle
            elif current_dd > p.get("max_dd_circuit", 0.20):
                circuit_tripped = True
                continue

            # Entry check
            score = scores.iloc[i]
            regime = row["market_regime"]
            ema_trend_val = row.get(f"ema_{p['ema_trend']}", 0)

            # Regime-adaptive min_score: higher bar in accumulation
            required_score = p.get("accumulation_min_score", 7) if regime == 1 else p["min_score"]

            if (score >= required_score and regime <= 2 and row["volume"] > 0
                    and price > ema_trend_val and i >= cooldown_until):
                size = capital * 0.95  # 95% allocation
                capital -= size
                position = {
                    "entry_price": price,
                    "entry_idx": i,
                    "size": size,
                    "trailing_high": price,
                }

    # Close any open position at end
    if position:
        price = df.iloc[-1]["close"]
        profit_pct = (price - position["entry_price"]) / position["entry_price"]
        pnl = position["size"] * profit_pct
        capital += position["size"] + pnl
        trades.append({
            "entry_idx": position["entry_idx"],
            "exit_idx": len(df) - 1,
            "entry_price": position["entry_price"],
            "exit_price": price,
            "profit_pct": profit_pct * 100,
            "pnl": pnl,
            "bars_held": len(df) - 1 - position["entry_idx"],
            "exit_reason": "end_of_data",
            "entry_date": df.index[position["entry_idx"]].strftime("%Y-%m-%d %H:%M"),
            "exit_date": df.index[-1].strftime("%Y-%m-%d %H:%M"),
        })

    return trades, capital

# ── Results ───────────────────────────────────────────────────────────

def print_results(trades, final_capital, initial=10000.0):
    if not trades:
        print("\n  ❌ No trades executed!")
        return

    wins = [t for t in trades if t["profit_pct"] > 0]
    losses = [t for t in trades if t["profit_pct"] <= 0]
    total_pnl = sum(t["pnl"] for t in trades)
    total_return = (final_capital - initial) / initial * 100

    # Sharpe ratio (annualized from 5m returns)
    returns = [t["profit_pct"] / 100 for t in trades]
    avg_ret = np.mean(returns)
    std_ret = np.std(returns) if len(returns) > 1 else 1
    sharpe = (avg_ret / std_ret) * np.sqrt(365 * 288 / max(len(trades), 1)) if std_ret > 0 else 0

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
    gross_loss = abs(sum(t["pnl"] for t in losses)) if losses else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

    # Average trade duration
    avg_bars = np.mean([t["bars_held"] for t in trades])
    avg_duration_hrs = avg_bars * 5 / 60

    # Exit reason breakdown
    exit_reasons = {}
    for t in trades:
        r = t["exit_reason"]
        exit_reasons[r] = exit_reasons.get(r, 0) + 1

    # Monthly returns
    monthly = {}
    for t in trades:
        month = t["entry_date"][:7]
        monthly[month] = monthly.get(month, 0) + t["pnl"]

    print(f"""
\033[36m\033[1m╔══════════════════════════════════════════════════════════════════╗
║  Aussie Agents BTC Strategy — Backtest Results                   ║
╠══════════════════════════════════════════════════════════════════╣\033[0m

  \033[1mPerformance\033[0m
    Total Return:     \033[{'32' if total_return > 0 else '31'}m{total_return:+.2f}%\033[0m
    Final Capital:    ${final_capital:,.2f} (from ${initial:,.2f})
    Total P&L:        ${total_pnl:+,.2f}

  \033[1mTrade Statistics\033[0m
    Total Trades:     {len(trades)}
    Winning Trades:   {len(wins)} ({len(wins)/len(trades)*100:.1f}%)
    Losing Trades:    {len(losses)} ({len(losses)/len(trades)*100:.1f}%)
    Win Rate:         \033[{'32' if len(wins)/len(trades) > 0.5 else '31'}m{len(wins)/len(trades)*100:.1f}%\033[0m

  \033[1mRisk Metrics\033[0m
    Sharpe Ratio:     \033[{'32' if sharpe > 2 else '33' if sharpe > 1 else '31'}m{sharpe:.2f}\033[0m
    Max Drawdown:     \033[{'32' if max_dd < 0.15 else '33' if max_dd < 0.25 else '31'}m{max_dd*100:.2f}%\033[0m
    Profit Factor:    \033[{'32' if profit_factor > 1.5 else '33' if profit_factor > 1 else '31'}m{profit_factor:.2f}\033[0m
    Avg Win:          {np.mean([t['profit_pct'] for t in wins]):.2f}% (${np.mean([t['pnl'] for t in wins]):,.2f})
    Avg Loss:         {np.mean([t['profit_pct'] for t in losses]):.2f}% (${np.mean([t['pnl'] for t in losses]):,.2f})
    Best Trade:       {max(t['profit_pct'] for t in trades):+.2f}%
    Worst Trade:      {min(t['profit_pct'] for t in trades):+.2f}%
    Avg Duration:     {avg_duration_hrs:.1f} hours ({avg_bars:.0f} candles)

  \033[1mExit Reasons\033[0m""")
    for reason, count in sorted(exit_reasons.items(), key=lambda x: -x[1]):
        pct = count / len(trades) * 100
        avg_pnl = np.mean([t["profit_pct"] for t in trades if t["exit_reason"] == reason])
        print(f"    {reason:20s}  {count:4d} ({pct:5.1f}%)  avg: {avg_pnl:+.2f}%")

    print(f"\n  \033[1mMonthly P&L\033[0m")
    for month, pnl in sorted(monthly.items()):
        bar = "█" * max(1, int(abs(pnl) / 50))
        color = "32" if pnl > 0 else "31"
        print(f"    {month}  \033[{color}m${pnl:+8,.2f}\033[0m  \033[{color}m{bar}\033[0m")

    print(f"""
\033[36m\033[1m╚══════════════════════════════════════════════════════════════════╝\033[0m

  \033[2mStrategy: PFAABitcoinStrategy (14-signal weighted scoring)
  Data: Synthetic BTC/USDT 5m+1h, Jan 2025 - Mar 2026
  Params: min_score={PARAMS['min_score']}, stoploss={PARAMS['stoploss']}, trailing={PARAMS['trailing_distance']}\033[0m
""")

# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n  Loading BTC data...")
    df_5m = load_data("5m")
    df_1h = load_data("1h")
    print(f"  5m: {len(df_5m)} candles, 1h: {len(df_1h)} candles")
    print(f"  Price range: ${df_5m['close'].min():,.0f} - ${df_5m['close'].max():,.0f}")

    print("  Computing indicators...")
    df_5m = populate_indicators(df_5m, df_1h)

    print("  Running backtest...")
    trades, final_capital = backtest(df_5m)

    print_results(trades, final_capital)
