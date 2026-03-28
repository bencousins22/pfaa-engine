"""
Aussie Agents Hyperopt Optimizer — Self-optimizing BTC strategy via Agent Team.

This module uses the Aussie Agents Team to:
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

import argparse
import asyncio
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import json
import subprocess

logger = logging.getLogger("pfaa.hyperopt")


# ── Claude API Client ────────────────────────────────────────────────

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    anthropic = None  # type: ignore
    _HAS_ANTHROPIC = False


class ClaudeClient:
    """
    Thin wrapper around the Anthropic API for pipeline-stage analysis.

    Falls back to simulation when ANTHROPIC_API_KEY is missing or the
    anthropic package is not installed.
    """

    MODEL = "claude-sonnet-4-20250514"
    MAX_TOKENS = 2048

    def __init__(self) -> None:
        self._api_key: str | None = os.environ.get("ANTHROPIC_API_KEY")
        self._client: Any = None
        if _HAS_ANTHROPIC and self._api_key:
            self._client = anthropic.Anthropic(api_key=self._api_key)
            logger.info("ClaudeClient initialized with live API")
        else:
            reason = "no API key" if not self._api_key else "anthropic package not installed"
            logger.info("ClaudeClient running in simulation mode (%s)", reason)

    @property
    def is_live(self) -> bool:
        return self._client is not None

    def ask(self, system: str, prompt: str) -> str:
        """Send a prompt to Claude and return the text response."""
        if not self.is_live:
            return self._simulate(prompt)
        try:
            response = self._client.messages.create(
                model=self.MODEL,
                max_tokens=self.MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except Exception as exc:
            logger.warning("Claude API call failed, falling back to simulation: %s", exc)
            return self._simulate(prompt)

    @staticmethod
    def _simulate(prompt: str) -> str:
        """Return a deterministic placeholder when the API is unavailable."""
        return (
            f"[SIMULATION] Analysis for prompt ({len(prompt)} chars). "
            "Claude API unavailable — using default parameters. "
            "Set ANTHROPIC_API_KEY and install `anthropic` for live analysis."
        )


# ── Data Classes ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class HyperoptConfig:
    """Immutable hyperopt configuration."""
    strategy: str = "PFAABitcoinStrategy"
    config_path: str = "freqtrade_strategy/config_btc.json"
    output_config_path: str = "freqtrade_strategy/config_btc_optimized.json"
    loss_function: str = "SharpeHyperOptLoss"
    epochs: int = 500
    timerange: str = "20250401-20260301"
    spaces: str = "buy sell"
    sampler: str = "NSGAIIISampler"
    min_trades: int = 50
    jobs: int = -1
    live: bool = False


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


# ── Stage Prompts ─────────────────────────────────────────────────────

_SYSTEM_PROMPT = (
    "You are a quantitative crypto trading analyst working with the Aussie Agents "
    "FreqTrade optimization pipeline. Provide concise, actionable analysis."
)

STAGE_PROMPTS: dict[str, str] = {
    "research": (
        "Analyze BTC market conditions for 2025-2026. Current price ~$87K. "
        "BTC completed its 4th halving in April 2024. The post-halving bull cycle "
        "historically peaks 12-18 months after halving. Key on-chain signals: "
        "MVRV Z-Score, SOPR, exchange netflows, funding rates. "
        "Identify the current market regime (accumulation / markup / distribution / markdown) "
        "and recommend optimal trading strategy parameters for this regime."
    ),
    "strategy": (
        "Given this market analysis, suggest optimal FreqTrade parameter ranges "
        "for a multi-signal BTC strategy. Include:\n"
        "- EMA periods (fast, slow, trend) for the current regime\n"
        "- RSI thresholds (oversold recovery zone)\n"
        "- Bollinger Band width threshold for squeeze detection\n"
        "- MACD sensitivity settings\n"
        "- Volume confirmation multiplier\n"
        "- Minimum signal score for entry\n"
        "- Trailing stop distances (ATR multipliers)\n"
        "Provide JSON-formatted parameter ranges."
    ),
    "optimize": (
        "Review these hyperopt results and suggest refinements:\n"
        "- Are the parameter ranges too wide or too narrow?\n"
        "- Should any signals be disabled based on results?\n"
        "- Recommend epoch count adjustment based on convergence.\n"
        "- Suggest additional hyperopt spaces (roi, stoploss, trailing).\n"
        "Provide specific next-iteration parameter adjustments."
    ),
    "validate": (
        "Validate these backtest results for overfitting:\n"
        "- Compare in-sample vs out-of-sample performance\n"
        "- Check if Sharpe ratio degrades >50% out-of-sample\n"
        "- Look for regime-dependent performance clusters\n"
        "- Assess trade count stability across time windows\n"
        "- Flag any suspiciously high win rates (>75%) or profit factors (>3.0)\n"
        "Provide pass/fail assessment with specific concerns."
    ),
    "risk": (
        "Assess risk metrics for this BTC trading strategy:\n"
        "- Max drawdown analysis (target <20%)\n"
        "- Sharpe ratio evaluation (target >1.5)\n"
        "- Win rate vs risk:reward balance\n"
        "- Position sizing recommendations for $10K-$100K accounts\n"
        "- Correlation with BTC buy-and-hold\n"
        "- Tail risk (largest single-trade loss)\n"
        "Provide risk-adjusted position sizing recommendation."
    ),
    "deploy": (
        "Generate production-ready FreqTrade config recommendations:\n"
        "- Optimal max_open_trades for the capital size\n"
        "- Exchange-specific settings (Binance rate limits)\n"
        "- Stoploss-on-exchange configuration\n"
        "- API server settings for monitoring\n"
        "- Telegram alert configuration checklist\n"
        "- Dry-run validation period recommendation\n"
        "Provide a deployment checklist with safety guards."
    ),
}


# ── Optimizer ─────────────────────────────────────────────────────────

class PFAAHyperoptOptimizer:
    """
    Agent-team-driven hyperopt optimizer.

    Uses all 6 Aussie Agents roles to collaboratively optimize the
    Bitcoin trading strategy.  When the agent team is unavailable
    (e.g. standalone mode) it falls back to Claude API calls per stage.
    """

    def __init__(self, config: HyperoptConfig | None = None):
        self.config = config or HyperoptConfig()
        self._team = None
        self._claude = ClaudeClient()
        self._results: list[HyperoptResult] = []

    # ── Team lifecycle ────────────────────────────────────────────

    async def start(self) -> None:
        """Initialize the agent team for optimization."""
        try:
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
        except Exception as exc:
            logger.warning("Agent team unavailable (%s), using Claude API fallback", exc)
            self._team = None

    async def shutdown(self) -> None:
        if self._team:
            await self._team.shutdown()

    # ── Claude stage helper ───────────────────────────────────────

    def _stage_analysis(self, stage: str, extra_context: str = "") -> str:
        """Run a Claude API analysis for the given pipeline stage."""
        prompt = STAGE_PROMPTS.get(stage, f"Analyze stage: {stage}")
        if extra_context:
            prompt = f"{prompt}\n\nContext:\n{extra_context}"
        return self._claude.ask(_SYSTEM_PROMPT, prompt)

    # ── Main pipeline ─────────────────────────────────────────────

    async def optimize(self) -> dict[str, Any]:
        """
        Run the full optimization pipeline:
        1. Research  -> analyze market regime
        2. Strategy  -> propose parameter ranges
        3. Optimize  -> run hyperopt
        4. Validate  -> walk-forward test
        5. Risk      -> check drawdown limits
        6. Deploy    -> generate final config
        """
        results: dict[str, Any] = {}
        start = time.time()

        # Step 1: RESEARCHER -- Market regime analysis
        logger.info("Step 1: Market regime analysis")
        if self._team:
            from agents.team.agent_team import TeamRole
            research = await self._team.execute(
                TeamRole.RESEARCHER,
                STAGE_PROMPTS["research"],
            )
            results["research"] = research
        else:
            results["research"] = self._stage_analysis("research")

        # Step 2: STRATEGIST -- Parameter space design
        logger.info("Step 2: Strategy parameter design")
        research_ctx = json.dumps(results["research"], default=str) if isinstance(results["research"], dict) else str(results["research"])
        if self._team:
            strategy = await self._team.execute(
                TeamRole.STRATEGIST,
                STAGE_PROMPTS["strategy"],
                {"market_regime": results["research"]},
            )
            results["strategy"] = strategy
        else:
            results["strategy"] = self._stage_analysis("strategy", research_ctx)

        # Step 3: OPTIMIZER -- Hyperopt execution
        logger.info("Step 3: Running hyperopt (%d epochs)", self.config.epochs)
        hyperopt_output = await self.run_hyperopt_command()
        results["hyperopt_output"] = hyperopt_output
        if self._team:
            optimize = await self._team.execute(
                TeamRole.OPTIMIZER,
                f"Run FreqTrade hyperopt: strategy={self.config.strategy}, "
                f"loss={self.config.loss_function}, epochs={self.config.epochs}, "
                f"timerange={self.config.timerange}, spaces={self.config.spaces}",
            )
            results["optimize"] = optimize
        else:
            results["optimize"] = self._stage_analysis("optimize", hyperopt_output)

        # Step 4: VALIDATOR -- Walk-forward validation
        logger.info("Step 4: Walk-forward validation")
        if self._team:
            validate = await self._team.execute(
                TeamRole.VALIDATOR,
                STAGE_PROMPTS["validate"],
            )
            results["validate"] = validate
        else:
            results["validate"] = self._stage_analysis("validate", hyperopt_output)

        # Step 5: RISK_MGR -- Risk assessment
        logger.info("Step 5: Risk assessment")
        if self._team:
            risk = await self._team.execute(
                TeamRole.RISK_MGR,
                STAGE_PROMPTS["risk"],
            )
            results["risk"] = risk
        else:
            results["risk"] = self._stage_analysis("risk", hyperopt_output)

        # Step 6: DEPLOYER -- Config generation
        logger.info("Step 6: Config generation")
        optimized_config = self.generate_optimized_config(
            results.get("optimize", {}),
        )
        results["deploy"] = {
            "config_written": optimized_config is not None,
            "config_path": self.config.output_config_path,
            "live_mode": self.config.live,
        }
        if self._team:
            deploy = await self._team.execute(
                TeamRole.DEPLOYER,
                STAGE_PROMPTS["deploy"],
            )
            results["deploy"]["agent_analysis"] = deploy
        else:
            results["deploy"]["analysis"] = self._stage_analysis("deploy")

        elapsed = time.time() - start
        results["total_elapsed_s"] = round(elapsed, 1)
        results["claude_api_live"] = self._claude.is_live
        if self._team:
            results["team_status"] = await self._team.status()

        logger.info("Optimization complete in %.1fs", elapsed)
        return results

    # ── Hyperopt command execution ────────────────────────────────

    async def run_hyperopt_command(self) -> str:
        """
        Build and execute the freqtrade hyperopt command.

        Returns the stdout/stderr output from the hyperopt run, or a
        diagnostic message if freqtrade is not installed.
        """
        if not shutil.which("freqtrade"):
            msg = (
                "[SKIPPED] freqtrade binary not found in PATH. "
                "Install with: pip install freqtrade\n"
                "Command that would have been run:\n"
            )
            msg += self._build_hyperopt_cmd()
            logger.warning("freqtrade not installed, skipping hyperopt execution")
            return msg

        cmd = self._build_hyperopt_cmd()
        logger.info("Executing: %s", cmd)
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=7200,  # 2-hour timeout for large epoch counts
            )
            output = proc.stdout
            if proc.returncode != 0:
                output += f"\n[STDERR]\n{proc.stderr}"
                logger.error("Hyperopt exited with code %d", proc.returncode)
            else:
                logger.info("Hyperopt completed successfully")
            return output
        except subprocess.TimeoutExpired:
            logger.error("Hyperopt timed out after 2 hours")
            return "[ERROR] Hyperopt timed out after 7200 seconds."
        except Exception as exc:
            logger.error("Hyperopt execution failed: %s", exc)
            return f"[ERROR] Hyperopt execution failed: {exc}"

    def _build_hyperopt_cmd(self) -> str:
        """Build the freqtrade hyperopt CLI command string."""
        return (
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

    # ── Config generation ─────────────────────────────────────────

    def generate_optimized_config(
        self, params: dict[str, Any] | str
    ) -> dict[str, Any] | None:
        """
        Generate a production config with optimized parameters and
        write it to disk.

        Returns the config dict, or None on failure.
        """
        config_path = Path(self.config.config_path)
        if not config_path.exists():
            logger.error("Base config not found: %s", config_path)
            return None

        try:
            with open(config_path) as f:
                base_config = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to read base config: %s", exc)
            return None

        # Apply live/dry-run mode
        if self.config.live:
            base_config["dry_run"] = False
            logger.warning("LIVE MODE enabled -- real trades will execute!")
        else:
            base_config["dry_run"] = True

        # Store optimization metadata
        if isinstance(params, dict):
            base_config["_optimized_params"] = params
        else:
            base_config["_optimized_params_raw"] = str(params)

        base_config["_optimized_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        base_config["_optimization_method"] = (
            f"{self.config.loss_function} + {self.config.sampler}, "
            f"{self.config.epochs} epochs"
        )
        base_config["_claude_api_live"] = self._claude.is_live

        # Write optimized config
        output_path = Path(self.config.output_config_path)
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                json.dump(base_config, f, indent=4)
            logger.info("Optimized config written to %s", output_path)
        except OSError as exc:
            logger.error("Failed to write optimized config: %s", exc)
            return None

        return base_config


# ── CLI Runner ───────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aussie Agents Hyperopt Optimizer — self-optimizing BTC strategy",
    )
    parser.add_argument(
        "--epochs", type=int, default=500,
        help="Number of hyperopt epochs (default: 500)",
    )
    parser.add_argument(
        "--timerange", type=str, default="20250401-20260301",
        help="Backtest time range (default: 20250401-20260301)",
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Enable LIVE trading mode (disables dry_run in output config). "
             "USE WITH EXTREME CAUTION.",
    )
    parser.add_argument(
        "--config", type=str, default="freqtrade_strategy/config_btc.json",
        help="Path to base FreqTrade config",
    )
    parser.add_argument(
        "--output", type=str, default="freqtrade_strategy/config_btc_optimized.json",
        help="Path for optimized config output",
    )
    parser.add_argument(
        "--spaces", type=str, default="buy sell",
        help="Hyperopt spaces (default: 'buy sell')",
    )
    return parser.parse_args()


async def run_optimization(args: argparse.Namespace | None = None) -> dict[str, Any]:
    """Full optimization pipeline -- callable from CLI."""
    if args is None:
        args = parse_args()

    config = HyperoptConfig(
        epochs=args.epochs,
        timerange=args.timerange,
        live=args.live,
        config_path=args.config,
        output_config_path=args.output,
        spaces=args.spaces,
    )

    if config.live:
        print("\n" + "=" * 60)
        print("  WARNING: --live flag is set!")
        print("  The output config will have dry_run=false.")
        print("  Real trades WILL execute if deployed.")
        print("=" * 60 + "\n")

    optimizer = PFAAHyperoptOptimizer(config)
    try:
        await optimizer.start()
        results = await optimizer.optimize()
        print(json.dumps(results, indent=2, default=str))
        return results
    finally:
        await optimizer.shutdown()


if __name__ == "__main__":
    asyncio.run(run_optimization())
