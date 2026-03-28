"""
PFAA Bitcoin FreqTrade Strategy — Self-Optimizing via Agent Team.

A multi-signal BTC strategy designed for the 2025-2026 market regime:
- BTC peaked at ~$126K in Oct 2025, currently ~$66K (correction phase)
- Support: $64,700 | Resistance: $78K, $82.5K
- 200-week MA support near $52K

Strategy Logic:
1. Triple EMA crossover with RSI momentum filter
2. Bollinger Band squeeze breakout detection
3. MACD histogram divergence with volume confirmation
4. Dynamic trailing stops based on ATR
5. Multi-timeframe confirmation (5m + 1h)

Optimized via hyperopt with:
- SharpeHyperOptLoss (risk-adjusted returns)
- NSGAIIISampler (multi-objective Bayesian optimization)
- Walk-forward validation to prevent overfitting

Python 3.15: lazy import for ta-lib and pandas.
"""

from __future__ import annotations

# FreqTrade strategy imports
from freqtrade.strategy import IStrategy, merge_informative_pair
from freqtrade.strategy import IntParameter, DecimalParameter, BooleanParameter
from freqtrade.persistence import Trade
import freqtrade.vendor.qtpylib.indicators as qtpylib

lazy import numpy as np
lazy import talib.abstract as ta
lazy import pandas as pd

from pandas import DataFrame
from datetime import datetime, timedelta
from typing import Optional


class PFAABitcoinStrategy(IStrategy):
    """
    PFAA Phase-Fluid Bitcoin Strategy.

    Market regime: 2025-2026 BTC correction + recovery.
    Designed for 5-minute timeframe with 1-hour informative.

    Key features:
    - Adaptive entry via EMA/RSI/BB/MACD multi-signal scoring
    - ATR-based dynamic trailing stops
    - Volume confirmation filter
    - Multi-timeframe trend alignment
    - Hyperopt-optimized parameters
    """

    # ── Strategy Settings ─────────────────────────────────────────

    INTERFACE_VERSION = 3

    timeframe = "5m"
    informative_timeframe = "1h"

    # ROI table — aggressive early exit, patient for runners
    minimal_roi = {
        "0": 0.08,      # 8% immediate
        "30": 0.04,     # 4% after 30 min
        "120": 0.025,   # 2.5% after 2 hrs
        "360": 0.015,   # 1.5% after 6 hrs
        "720": 0.008,   # 0.8% after 12 hrs
    }

    # Stoploss
    stoploss = -0.06  # -6% hard stop

    # Trailing stop — the key to capturing runners
    trailing_stop = True
    trailing_stop_positive = 0.018
    trailing_stop_positive_offset = 0.045
    trailing_only_offset_is_reached = True

    # Position settings
    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    # Order types
    order_types = {
        "entry": "limit",
        "exit": "limit",
        "stoploss": "market",
        "stoploss_on_exchange": True,
    }

    # Protections
    startup_candle_count: int = 200

    # ── Hyperopt Parameters ───────────────────────────────────────

    # EMA crossover
    buy_ema_fast = IntParameter(5, 21, default=9, space="buy", optimize=True)
    buy_ema_slow = IntParameter(15, 55, default=21, space="buy", optimize=True)
    buy_ema_trend = IntParameter(50, 200, default=100, space="buy", optimize=True)

    # RSI filter
    buy_rsi_low = IntParameter(20, 40, default=30, space="buy", optimize=True)
    buy_rsi_high = IntParameter(55, 75, default=65, space="buy", optimize=True)
    buy_rsi_enabled = BooleanParameter(default=True, space="buy", optimize=True)

    # Bollinger Bands
    buy_bb_enabled = BooleanParameter(default=True, space="buy", optimize=True)
    buy_bb_width_threshold = DecimalParameter(0.01, 0.05, default=0.025, space="buy", optimize=True)

    # MACD
    buy_macd_enabled = BooleanParameter(default=True, space="buy", optimize=True)

    # Volume
    buy_volume_factor = DecimalParameter(1.0, 3.0, default=1.5, space="buy", optimize=True)

    # Multi-signal minimum score
    buy_min_score = IntParameter(2, 5, default=3, space="buy", optimize=True)

    # Sell parameters
    sell_rsi_high = IntParameter(65, 85, default=75, space="sell", optimize=True)
    sell_ema_cross = BooleanParameter(default=True, space="sell", optimize=True)

    # ── Informative Pairs ─────────────────────────────────────────

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    # ── Indicator Population ──────────────────────────────────────

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators."""

        # ── EMAs ──
        for period in [5, 9, 13, 21, 34, 55, 89, 100, 200]:
            dataframe[f"ema_{period}"] = ta.EMA(dataframe, timeperiod=period)

        # ── RSI ──
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["rsi_fast"] = ta.RSI(dataframe, timeperiod=7)

        # ── MACD ──
        macd = ta.MACD(dataframe, fastperiod=12, slowperiod=26, signalperiod=9)
        dataframe["macd"] = macd["macd"]
        dataframe["macd_signal"] = macd["macdsignal"]
        dataframe["macd_hist"] = macd["macdhist"]

        # ── Bollinger Bands ──
        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lower"] = bb["lower"]
        dataframe["bb_middle"] = bb["mid"]
        dataframe["bb_upper"] = bb["upper"]
        dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe["bb_middle"]

        # ── ATR (for dynamic stops) ──
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = dataframe["atr"] / dataframe["close"]

        # ── Volume ──
        dataframe["volume_mean_20"] = dataframe["volume"].rolling(20).mean()
        dataframe["volume_mean_50"] = dataframe["volume"].rolling(50).mean()
        dataframe["volume_ratio"] = dataframe["volume"] / dataframe["volume_mean_20"]

        # ── Stochastic RSI ──
        stoch_rsi = ta.STOCHRSI(dataframe, timeperiod=14, fastk_period=3, fastd_period=3)
        dataframe["stoch_rsi_k"] = stoch_rsi["fastk"]
        dataframe["stoch_rsi_d"] = stoch_rsi["fastd"]

        # ── ADX (trend strength) ──
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        # ── Multi-timeframe: get 1h data ──
        if self.dp:
            informative = self.dp.get_pair_dataframe(
                pair=metadata["pair"],
                timeframe=self.informative_timeframe,
            )
            if len(informative) > 0:
                informative["ema_50_1h"] = ta.EMA(informative, timeperiod=50)
                informative["ema_200_1h"] = ta.EMA(informative, timeperiod=200)
                informative["rsi_1h"] = ta.RSI(informative, timeperiod=14)
                informative["adx_1h"] = ta.ADX(informative, timeperiod=14)

                dataframe = merge_informative_pair(
                    dataframe, informative,
                    self.timeframe, self.informative_timeframe,
                    ffill=True,
                )

        return dataframe

    # ── Entry Signal ──────────────────────────────────────────────

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """
        Multi-signal scoring entry system.

        Each signal contributes a point. Entry when score >= buy_min_score.
        This prevents false signals from any single indicator.
        """
        conditions = []
        dataframe["entry_score"] = 0

        # Signal 1: EMA Golden Cross (fast > slow, both above trend)
        ema_fast = dataframe[f"ema_{self.buy_ema_fast.value}"]
        ema_slow = dataframe[f"ema_{self.buy_ema_slow.value}"]
        ema_trend = dataframe[f"ema_{self.buy_ema_trend.value}"]

        ema_cross = (
            qtpylib.crossed_above(ema_fast, ema_slow) &
            (dataframe["close"] > ema_trend)
        )
        dataframe.loc[ema_cross, "entry_score"] += 1

        # Signal 2: RSI momentum (oversold recovery)
        if self.buy_rsi_enabled.value:
            rsi_signal = (
                (dataframe["rsi"] > self.buy_rsi_low.value) &
                (dataframe["rsi"] < self.buy_rsi_high.value) &
                (dataframe["rsi"] > dataframe["rsi"].shift(1))
            )
            dataframe.loc[rsi_signal, "entry_score"] += 1

        # Signal 3: Bollinger Band squeeze breakout
        if self.buy_bb_enabled.value:
            bb_signal = (
                (dataframe["close"] > dataframe["bb_middle"]) &
                (dataframe["bb_width"] > self.buy_bb_width_threshold.value) &
                (dataframe["close"].shift(1) <= dataframe["bb_middle"].shift(1))
            )
            dataframe.loc[bb_signal, "entry_score"] += 1

        # Signal 4: MACD histogram positive crossover
        if self.buy_macd_enabled.value:
            macd_signal = (
                (dataframe["macd_hist"] > 0) &
                (dataframe["macd_hist"].shift(1) <= 0) &
                (dataframe["macd"] > dataframe["macd_signal"])
            )
            dataframe.loc[macd_signal, "entry_score"] += 1

        # Signal 5: Volume confirmation
        volume_signal = (
            dataframe["volume_ratio"] > self.buy_volume_factor.value
        )
        dataframe.loc[volume_signal, "entry_score"] += 1

        # Signal 6: 1h trend alignment (if available)
        if "ema_50_1h" in dataframe.columns:
            trend_1h = (
                (dataframe["ema_50_1h"] > dataframe["ema_200_1h"]) &
                (dataframe["close"] > dataframe["ema_50_1h"])
            )
            dataframe.loc[trend_1h, "entry_score"] += 1

        # Final entry: score must meet minimum threshold
        dataframe.loc[
            (dataframe["entry_score"] >= self.buy_min_score.value) &
            (dataframe["volume"] > 0),
            "enter_long",
        ] = 1

        return dataframe

    # ── Exit Signal ───────────────────────────────────────────────

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Exit on RSI overbought + EMA death cross."""
        conditions = []

        # RSI overbought
        rsi_exit = dataframe["rsi"] > self.sell_rsi_high.value

        # EMA death cross
        if self.sell_ema_cross.value:
            ema_fast = dataframe[f"ema_{self.buy_ema_fast.value}"]
            ema_slow = dataframe[f"ema_{self.buy_ema_slow.value}"]
            ema_exit = qtpylib.crossed_below(ema_fast, ema_slow)
            exit_signal = rsi_exit | ema_exit
        else:
            exit_signal = rsi_exit

        dataframe.loc[
            exit_signal & (dataframe["volume"] > 0),
            "exit_long",
        ] = 1

        return dataframe

    # ── Custom Stop Loss (ATR-based) ─────────────────────────────

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        """Dynamic stop loss based on ATR volatility."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return self.stoploss

        last_candle = dataframe.iloc[-1]
        atr_pct = last_candle.get("atr_pct", 0.02)

        # Tighter stops in low volatility, wider in high
        if current_profit > 0.04:
            return -atr_pct * 1.0  # Tight: 1x ATR when profitable
        elif current_profit > 0.02:
            return -atr_pct * 1.5  # Medium: 1.5x ATR
        elif current_profit > 0:
            return -atr_pct * 2.0  # Wide: 2x ATR when barely profitable
        else:
            return -atr_pct * 2.5  # Very wide: 2.5x ATR when in loss (give room)

    # ── Custom Exit ───────────────────────────────────────────────

    def custom_exit(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        **kwargs,
    ) -> Optional[str]:
        """Emergency exits for regime changes."""
        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if len(dataframe) < 1:
            return None

        last_candle = dataframe.iloc[-1]

        # Emergency exit: RSI > 85 (extreme overbought)
        if last_candle.get("rsi", 50) > 85 and current_profit > 0.01:
            return "rsi_extreme_exit"

        # Emergency exit: ADX collapse (trend dying)
        if last_candle.get("adx", 25) < 15 and current_profit > 0.02:
            return "trend_collapse_exit"

        # Time-based exit: close trades older than 48h with profit
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        if trade_duration > 48 and current_profit > 0.005:
            return "time_exit_48h"

        return None
