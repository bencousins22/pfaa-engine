"""
PFAA Hyperopt Optimizer — Self-optimizing BTC strategy via Agent Team.

This module uses the PFAA Agent Team to:
1. RESEARCHER agent: Analyze historical BTC data for regime detection
2. STRATEGIST agent: Generate optimal indicator parameters
3. OPTIMIZER agent: Run hyperopt with SharpeHyperOptLoss
4. VALIDATOR agent: Walk-forward test to prevent overfitting
5. RISK_MGR agent: Validate position sizing and max drawdown
6. DEPLOYER agent: Generate final production config

The optimizer learns from each backtest run via JMEM memory,
storing successful parameter combinations as L2 concepts and
promoting validated configs to L3 principles.

Python 3.15: lazy import, frozendict.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

lazy import json
lazy import subprocess

logger = logging.getLogger("pfaa.hyperopt")


@dataclass(frozen=True)
class HyperoptConfig:
    """Immutable hyperopt configuration."""
    strategy: str = "PFAABitcoinStrategy"
    config_path: str = "freqtrade_strategy/config_btc.json"
    loss_function: str = "SharpeHyperOptLoss"
    epochs: int = 500
    timerange: str = "20250401-20260301"
    spaces: str = "buy sell"
    sampler: str = "NSGAIIISampler"
    min_trades: int = 50
    jobs: int = -1


@dataclass
class HyperoptResult:
    """Result from a hyperopt run."""
    epoch: int
    trades: int
    avg_profit_pct: float
    total_profit_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    win_rate: float
    avg_duration_min: float
    params: dict[str, Any]
    elapsed_s: float


class PFAAHyperoptOptimizer:
    """
    Agent-team-driven hyperopt optimizer.

    Uses all 6 PFAA agent roles to collaboratively optimize the
    Bitcoin trading strategy.
    """

    def __init__(self, config: HyperoptConfig | None = None):
        self.config = config or HyperoptConfig()
        self._team = None
        self._results: list[HyperoptResult] = []

    async def start(self) -> None:
        """Initialize the agent team for optimization."""
        from agents.team.agent_team import spawn_agent_team, TeamRole
        self._team = await spawn_agent_team(
            roles=[
                TeamRole.RESEARCHER,
                TeamRole.STRATEGIST,
                TeamRole.OPTIMIZER,
                TeamRole.RISK_MGR,
                TeamRole.VALIDATOR,
                TeamRole.DEPLOYER,
            ],
            namespace="pfaa-hyperopt",
        )
        logger.info("Hyperopt optimizer started with full agent team")

    async def shutdown(self) -> None:
        if self._team:
            await self._team.shutdown()

    async def optimize(self) -> dict[str, Any]:
        """
        Run the full optimization pipeline:
        1. Research → analyze market regime
        2. Strategy → propose parameter ranges
        3. Optimize → run hyperopt
        4. Validate → walk-forward test
        5. Risk → check drawdown limits
        6. Deploy → generate final config
        """
        from agents.team.agent_team import TeamRole

        results = {}
        start = time.time()

        # Step 1: RESEARCHER — Market regime analysis
        logger.info("Step 1: Market regime analysis")
        research = await self._team.execute(
            TeamRole.RESEARCHER,
            "Analyze BTC/USDT 2025-2026: price peaked $126K Oct 2025, corrected to $66K Mar 2026. "
            "Key levels: support $64.7K, resistance $78K/$82.5K. 200-week MA at $52K. "
            "Identify optimal trading regime and timeframe parameters.",
        )
        results["research"] = research

        # Step 2: STRATEGIST — Parameter space design
        logger.info("Step 2: Strategy parameter design")
        strategy = await self._team.execute(
            TeamRole.STRATEGIST,
            "Design optimal parameter ranges for BTC correction/recovery regime: "
            "EMA periods, RSI thresholds, BB width, MACD settings, volume filters. "
            "Focus on capturing rebounds from $64.7K support with tight risk management.",
            {"market_regime": research.get("result", {})},
        )
        results["strategy"] = strategy

        # Step 3: OPTIMIZER — Hyperopt execution
        logger.info("Step 3: Running hyperopt (%d epochs)", self.config.epochs)
        optimize = await self._team.execute(
            TeamRole.OPTIMIZER,
            f"Run FreqTrade hyperopt: strategy={self.config.strategy}, "
            f"loss={self.config.loss_function}, epochs={self.config.epochs}, "
            f"timerange={self.config.timerange}, spaces={self.config.spaces}",
        )
        results["optimize"] = optimize

        # Step 4: VALIDATOR — Walk-forward validation
        logger.info("Step 4: Walk-forward validation")
        validate = await self._team.execute(
            TeamRole.VALIDATOR,
            "Validate strategy with walk-forward analysis: "
            "Split data 70/30 train/test. Check for overfitting by comparing "
            "in-sample vs out-of-sample Sharpe ratios. Flag if OOS Sharpe < 50% of IS.",
        )
        results["validate"] = validate

        # Step 5: RISK_MGR — Risk assessment
        logger.info("Step 5: Risk assessment")
        risk = await self._team.execute(
            TeamRole.RISK_MGR,
            "Validate risk parameters: max drawdown < 20%, position size limits, "
            "ensure trailing stop captures 80%+ of moves, verify stoploss at -6% "
            "is appropriate for BTC volatility (ATR ~2-3% daily).",
        )
        results["risk"] = risk

        # Step 6: DEPLOYER — Config generation
        logger.info("Step 6: Config generation")
        deploy = await self._team.execute(
            TeamRole.DEPLOYER,
            "Generate production FreqTrade config with optimized parameters. "
            "Set dry_run=true for initial validation. Include all safety guards.",
        )
        results["deploy"] = deploy

        elapsed = time.time() - start
        results["total_elapsed_s"] = round(elapsed, 1)
        results["team_status"] = await self._team.status()

        logger.info("Optimization complete in %.1fs", elapsed)
        return results

    async def run_hyperopt_command(self) -> str:
        """Generate the freqtrade hyperopt command."""
        cmd = (
            f"freqtrade hyperopt "
            f"--strategy {self.config.strategy} "
            f"--config {self.config.config_path} "
            f"--hyperopt-loss {self.config.loss_function} "
            f"--timerange {self.config.timerange} "
            f"--spaces {self.config.spaces} "
            f"--epochs {self.config.epochs} "
            f"--min-trades {self.config.min_trades} "
            f"--jobs {self.config.jobs}"
        )
        return cmd

    def generate_optimized_config(self, params: dict[str, Any]) -> dict[str, Any]:
        """Generate a production config with optimized parameters."""
        with open(self.config.config_path) as f:
            base_config = json.load(f)

        base_config["dry_run"] = True  # Safety: start with dry run
        base_config["_optimized_params"] = params
        base_config["_optimized_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        base_config["_optimization_method"] = (
            f"{self.config.loss_function} + {self.config.sampler}, "
            f"{self.config.epochs} epochs"
        )

        return base_config


# ── CLI Runner ───────────────────────────────────────────────────────

async def run_optimization():
    """Full optimization pipeline — callable from CLI."""
    optimizer = PFAAHyperoptOptimizer()
    try:
        await optimizer.start()
        results = await optimizer.optimize()
        print(json.dumps(results, indent=2, default=str))
        return results
    finally:
        await optimizer.shutdown()


if __name__ == "__main__":
    asyncio.run(run_optimization())
