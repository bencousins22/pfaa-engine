"""
PFAA Bitcoin FreqTrade Strategy — Self-Optimizing via Agent Team.

A multi-signal BTC strategy designed for the 2025-2026 market regime:
- BTC 4th halving completed April 2024
- ATH: $126,198 (Oct 6, 2025), current price: ~$66.6K (-47% drawdown)
- 2026 regime: POST-PEAK CORRECTION, extreme fear (F&G: 8)
- Mean-reversion + accumulation strategy (NOT markup/breakout)
- 86% of technical indicators bearish, aSOPR < 1 (capitulation zone)
- 5 on-chain bottom signals converging — historically precedes 300%+ rallies
- Key on-chain: MVRV Z-Score 1.2, SOPR 0.97-0.99, exchange reserves at 7-year low
- Support levels: $65K, $62K, $60K (200-week MA)
- Resistance levels: $69K, $72K (major), $80K
- ATR daily: $3,510 (4.9% of price — elevated volatility)

Strategy Logic:
1. Triple EMA crossover with RSI momentum filter
2. Bollinger Band squeeze breakout detection
3. MACD histogram divergence with volume confirmation
4. Mean-reversion entries at BB lower band + extreme oversold RSI
5. Dynamic trailing stops based on ATR
6. Multi-timeframe confirmation (5m + 1h)
7. Market regime detection (accumulation/markup/distribution/markdown)
8. On-chain signal placeholders (MVRV, SOPR, funding rates)

Optimized via hyperopt with:
- CalmarHyperOptLoss (drawdown control — critical in choppy correction markets)
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

import numpy as np
import talib.abstract as ta
import pandas as pd

from pandas import DataFrame
from datetime import datetime, timedelta
from typing import Optional
import logging

logger = logging.getLogger("pfaa.strategy")


class PFAABitcoinStrategy(IStrategy):
    """
    PFAA Phase-Fluid Bitcoin Strategy.

    Market regime: 2026 post-peak correction. BTC at $66.6K, -47% from $126K ATH.
    Extreme fear (F&G: 8). Mean-reversion + accumulation strategy.
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
        "0": 0.10,       # 10% immediate
        "30": 0.05,      # 5% after 30 min
        "120": 0.03,     # 3% after 2 hrs
        "360": 0.018,    # 1.8% after 6 hrs
        "720": 0.01,     # 1% after 12 hrs
        "1440": 0.005,   # 0.5% after 24 hrs
    }

    # Stoploss
    stoploss = -0.055  # -5.5% hard stop

    # Trailing stop — the key to capturing runners
    trailing_stop = True
    trailing_stop_positive = 0.015
    trailing_stop_positive_offset = 0.04
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

    # ── Hyperopt Parameters (widened for 2026 post-halving regime) ──

    # EMA crossover — tightened ranges per strategist analysis
    buy_ema_fast = IntParameter(5, 21, default=8, space="buy", optimize=True)
    buy_ema_slow = IntParameter(13, 55, default=21, space="buy", optimize=True)
    buy_ema_trend = IntParameter(55, 200, default=100, space="buy", optimize=True)

    # RSI filter — tightened thresholds per strategist analysis
    buy_rsi_low = IntParameter(25, 42, default=35, space="buy", optimize=True)
    buy_rsi_high = IntParameter(55, 75, default=68, space="buy", optimize=True)
    buy_rsi_enabled = BooleanParameter(default=True, space="buy", optimize=True)

    # Bollinger Bands — tightened range for squeeze detection
    buy_bb_enabled = BooleanParameter(default=True, space="buy", optimize=True)
    buy_bb_width_threshold = DecimalParameter(0.01, 0.06, default=0.02, decimals=3, space="buy", optimize=True)

    # MACD
    buy_macd_enabled = BooleanParameter(default=True, space="buy", optimize=True)

    # Volume — tightened factor range
    buy_volume_factor = DecimalParameter(1.0, 3.0, default=1.5, decimals=1, space="buy", optimize=True)

    # StochRSI entry signal — oversold crossover
    buy_stochrsi_enabled = BooleanParameter(default=True, space="buy", optimize=True)

    # ADX trend strength filter
    buy_adx_enabled = BooleanParameter(default=True, space="buy", optimize=True)
    buy_adx_threshold = IntParameter(15, 35, default=20, space="buy", optimize=True)

    # Mean-reversion entry (buy dips to BB lower band in extreme oversold)
    buy_mean_reversion_enabled = BooleanParameter(default=True, space="buy", optimize=True)

    # Multi-signal minimum score (max possible ~14)
    # Lowered default from 4 to 3: in extreme fear, fewer signals fire simultaneously
    # so we lower the bar slightly to catch accumulation entries
    buy_min_score = IntParameter(2, 7, default=3, space="buy", optimize=True)

    # Sell parameters — raised default per strategist (let winners run)
    sell_rsi_high = IntParameter(72, 88, default=80, space="sell", optimize=True)
    sell_ema_cross = BooleanParameter(default=True, space="sell", optimize=True)

    # On-chain signal weights (placeholders for external data feeds)
    buy_onchain_enabled = BooleanParameter(default=False, space="buy", optimize=True)

    # ATR stoploss multipliers — hyperopt-optimizable
    sl_atr_high_profit = DecimalParameter(0.8, 2.0, default=1.2, decimals=1, space="sell", optimize=True)
    sl_atr_mid_profit = DecimalParameter(1.0, 2.5, default=1.8, decimals=1, space="sell", optimize=True)
    sl_atr_low_profit = DecimalParameter(1.5, 3.0, default=2.2, decimals=1, space="sell", optimize=True)
    sl_atr_in_loss = DecimalParameter(2.0, 4.0, default=3.0, decimals=1, space="sell", optimize=True)

    # ── Informative Pairs ─────────────────────────────────────────

    def informative_pairs(self):
        pairs = self.dp.current_whitelist()
        return [(pair, self.informative_timeframe) for pair in pairs]

    # ── Indicator Population ──────────────────────────────────────

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        """Calculate all technical indicators."""

        # ── EMAs (extended range for wider hyperopt space) ──
        for period in [3, 5, 9, 13, 21, 34, 55, 89, 100, 200, 233]:
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

        # ── Market Regime Detection (2026 post-halving cycle) ──
        dataframe = self._detect_market_regime(dataframe)

        # ── On-Chain Signal Placeholders ──
        dataframe = self._populate_onchain_signals(dataframe)

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

    # ── Market Regime Detection ───────────────────────────────────

    def _detect_market_regime(self, dataframe: DataFrame) -> DataFrame:
        """
        Detect market regime for 2026 post-peak correction.

        As of March 2026, the current regime is Accumulation (phase 1):
        - BTC at $66.6K, -47% from $126K ATH (Oct 2025)
        - Extreme fear, aSOPR < 1 (capitulation), MVRV Z-Score 1.2
        - Exchange reserves at 7-year low (smart money accumulating)
        - NOT in Markup — do not assume bullish trend continuation

        Regimes (encoded as integers for indicator use):
          1 = Accumulation  (low vol, range-bound, post-correction) ← CURRENT
          2 = Markup         (trending up, expanding vol, bull phase)
          3 = Distribution   (high vol, topping, late cycle)
          4 = Markdown       (trending down, capitulation)

        Uses a combination of:
        - EMA 50/200 relationship (golden/death cross)
        - ADX trend strength
        - Volume trend (expanding vs contracting)
        - RSI regime bands
        - ATR percentile (volatility regime)
        """
        # Volatility regime via ATR percentile (rolling 200-period)
        dataframe["atr_percentile"] = (
            dataframe["atr_pct"].rolling(200).rank(pct=True)
        )

        # Volume trend: 20-period vs 50-period average
        dataframe["volume_trend"] = (
            dataframe["volume_mean_20"] / dataframe["volume_mean_50"]
        )

        # Price momentum: distance from EMA 200 (percent)
        dataframe["ema200_dist_pct"] = (
            (dataframe["close"] - dataframe["ema_200"]) / dataframe["ema_200"]
        )

        # Default: accumulation
        dataframe["market_regime"] = 1

        # Markup: price above EMA 200, EMA 50 > EMA 200, ADX > 25
        markup = (
            (dataframe["close"] > dataframe["ema_200"]) &
            (dataframe["ema_55"] > dataframe["ema_200"]) &
            (dataframe["adx"] > 25)
        )
        dataframe.loc[markup, "market_regime"] = 2

        # Distribution: price above EMA 200, but RSI > 70 and volume expanding
        distribution = (
            (dataframe["close"] > dataframe["ema_200"]) &
            (dataframe["rsi"] > 70) &
            (dataframe["volume_trend"] > 1.3) &
            (dataframe["atr_percentile"] > 0.75)
        )
        dataframe.loc[distribution, "market_regime"] = 3

        # Markdown: price below EMA 200, EMA 50 < EMA 200, ADX > 20
        markdown = (
            (dataframe["close"] < dataframe["ema_200"]) &
            (dataframe["ema_55"] < dataframe["ema_200"]) &
            (dataframe["adx"] > 20)
        )
        dataframe.loc[markdown, "market_regime"] = 4

        return dataframe

    # ── On-Chain Signal Placeholders ──────────────────────────────

    def _populate_onchain_signals(self, dataframe: DataFrame) -> DataFrame:
        """
        Populate on-chain signal columns as placeholders.

        In production these would be fed from an external data source
        (e.g. Glassnode API, CryptoQuant, or a custom JMEM data feed).
        For now they are set to neutral defaults so the strategy runs
        without external dependencies.

        Signals:
        - mvrv_zscore: Market Value to Realized Value Z-Score
          > 7 = overheated (sell zone), < 0 = undervalued (buy zone)
        - sopr: Spent Output Profit Ratio
          > 1 = holders in profit, < 1 = holders at loss (capitulation)
        - funding_rate: Perpetual futures funding rate
          > 0.01% = overleveraged longs, < -0.01% = overleveraged shorts
        - exchange_netflow: Net BTC flow to/from exchanges
          positive = selling pressure, negative = accumulation
        """
        # Defaults reflect March 2026 market conditions — replace with live data feed in production
        dataframe["mvrv_zscore"] = 1.2        # low — undervalued zone (down from 3.8 at peak)
        dataframe["sopr"] = 0.98              # below 1 = coins moving at a loss (capitulation)
        dataframe["funding_rate"] = -0.001    # slightly negative = no long crowding
        dataframe["exchange_netflow"] = -500  # negative = outflows = accumulation (reserves at 7yr low)

        logger.debug(
            "On-chain signals set to neutral defaults. "
            "Connect external data feed for live signals."
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

        # Signal 1: EMA Golden Cross (fast > slow, both above trend) — weight +1
        ema_fast = dataframe[f"ema_{self.buy_ema_fast.value}"]
        ema_slow = dataframe[f"ema_{self.buy_ema_slow.value}"]
        ema_trend = dataframe[f"ema_{self.buy_ema_trend.value}"]

        ema_cross = (
            qtpylib.crossed_above(ema_fast, ema_slow) &
            (dataframe["close"] > ema_trend)
        )
        dataframe.loc[ema_cross, "entry_score"] += 1

        # Signal 2: RSI momentum (oversold recovery) — weight +1
        if self.buy_rsi_enabled.value:
            rsi_signal = (
                (dataframe["rsi"] > self.buy_rsi_low.value) &
                (dataframe["rsi"] < self.buy_rsi_high.value) &
                (dataframe["rsi"] > dataframe["rsi"].shift(1))
            )
            dataframe.loc[rsi_signal, "entry_score"] += 1

        # Signal 3: Bollinger Band squeeze breakout — weight +1
        if self.buy_bb_enabled.value:
            bb_signal = (
                (dataframe["close"] > dataframe["bb_middle"]) &
                (dataframe["bb_width"] > self.buy_bb_width_threshold.value) &
                (dataframe["close"].shift(1) <= dataframe["bb_middle"].shift(1))
            )
            dataframe.loc[bb_signal, "entry_score"] += 1

        # Signal 4: MACD histogram positive crossover — weight +1
        if self.buy_macd_enabled.value:
            macd_signal = (
                (dataframe["macd_hist"] > 0) &
                (dataframe["macd_hist"].shift(1) <= 0) &
                (dataframe["macd"] > dataframe["macd_signal"])
            )
            dataframe.loc[macd_signal, "entry_score"] += 1

        # Signal 5: Volume confirmation — weight +1
        volume_signal = (
            dataframe["volume_ratio"] > self.buy_volume_factor.value
        )
        dataframe.loc[volume_signal, "entry_score"] += 1

        # Signal 6: 1h trend alignment — weight +2 (higher TF = higher conviction)
        if "ema_50_1h" in dataframe.columns:
            trend_1h = (
                (dataframe["ema_50_1h"] > dataframe["ema_200_1h"]) &
                (dataframe["close"] > dataframe["ema_50_1h"])
            )
            dataframe.loc[trend_1h, "entry_score"] += 2

        # Signal 7: Market regime bonus (markup = bullish) — weight +2
        regime_bullish = dataframe["market_regime"] == 2  # markup
        dataframe.loc[regime_bullish, "entry_score"] += 2

        # Signal 8: StochRSI oversold crossover — weight +1
        if self.buy_stochrsi_enabled.value:
            stochrsi_signal = (
                qtpylib.crossed_above(dataframe["stoch_rsi_k"], dataframe["stoch_rsi_d"]) &
                (dataframe["stoch_rsi_k"] < 20)
            )
            dataframe.loc[stochrsi_signal, "entry_score"] += 1

        # Signal 9: ADX trend strength filter — weight +1
        if self.buy_adx_enabled.value:
            adx_signal = dataframe["adx"] > self.buy_adx_threshold.value
            dataframe.loc[adx_signal, "entry_score"] += 1

        # Signal 10: On-chain signals (when live data is connected) — weight +1
        if self.buy_onchain_enabled.value:
            onchain_buy = (
                (dataframe["mvrv_zscore"] < 5.0) &   # not overheated
                (dataframe["sopr"] > 0.95) &           # not deep capitulation
                (dataframe["funding_rate"] < 0.05) &   # not overleveraged longs
                (dataframe["exchange_netflow"] <= 0)    # accumulation (outflows)
            )
            dataframe.loc[onchain_buy, "entry_score"] += 1

        # Signal 11: Mean-reversion entry (extreme oversold at BB lower band) — weight +2
        # High conviction: in a post-peak correction / accumulation regime, buying extreme
        # dips to support with plan to exit at BB middle is a proven mean-reversion setup.
        # Condition: close below BB lower band AND RSI < 28 (extreme oversold)
        if self.buy_mean_reversion_enabled.value:
            mean_reversion_signal = (
                (dataframe["close"] < dataframe["bb_lower"]) &
                (dataframe["rsi"] < 28)
            )
            dataframe.loc[mean_reversion_signal, "entry_score"] += 2

        # Final entry: score must meet minimum threshold
        # Regime guard: never enter during distribution (3) or markdown (4)
        dataframe.loc[
            (dataframe["entry_score"] >= self.buy_min_score.value) &
            (dataframe["volume"] > 0) &
            (dataframe["market_regime"] <= 2),
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

        # Tighter stops in low volatility, wider in high — multipliers are hyperopt-optimizable
        if current_profit > 0.04:
            return -atr_pct * self.sl_atr_high_profit.value
        elif current_profit > 0.02:
            return -atr_pct * self.sl_atr_mid_profit.value
        elif current_profit > 0:
            return -atr_pct * self.sl_atr_low_profit.value
        else:
            return -atr_pct * self.sl_atr_in_loss.value

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

        # Emergency exit: RSI > 88 (extreme overbought — raised to let winners run)
        if last_candle.get("rsi", 50) > 88 and current_profit > 0.01:
            return "rsi_extreme_exit"

        # Emergency exit: ADX collapse (trend dying)
        if last_candle.get("adx", 25) < 15 and current_profit > 0.02:
            return "trend_collapse_exit"

        # Regime shift exit: distribution or markdown detected
        regime = last_candle.get("market_regime", 1)
        if regime >= 3 and current_profit > 0.005:
            return f"regime_shift_exit_{int(regime)}"

        # On-chain danger: MVRV overheated
        if last_candle.get("mvrv_zscore", 3.0) > 7.0 and current_profit > 0.01:
            return "mvrv_overheated_exit"

        # Mean-reversion profit-take: if entry was near BB lower band and price
        # has reverted to BB middle, take profit. In a choppy/correction market,
        # mean-reversion trades should not be held for trend — capture the bounce.
        bb_middle = last_candle.get("bb_middle", 0)
        bb_lower = last_candle.get("bb_lower", 0)
        if (
            bb_middle > 0
            and bb_lower > 0
            and current_rate >= bb_middle
            and current_profit > 0.005
            and trade.open_rate <= bb_lower * 1.005  # entered near/below BB lower
        ):
            return "mean_reversion_bb_middle_exit"

        # Time-based exit: close trades older than 48h with profit
        trade_duration = (current_time - trade.open_date_utc).total_seconds() / 3600
        if trade_duration > 48 and current_profit > 0.005:
            return "time_exit_48h"

        return None
