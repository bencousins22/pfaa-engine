"""
Walk-forward backtester with Kelly staking and bootstrap ROI confidence intervals.

Applies real takeout rates: HK 17.5%, JRA 20%.
Reports 5th-percentile bootstrap ROI — if < 0, "no evidence of edge."
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .modeller import RacingRanker, _softmax_per_race, FEATURE_COLS


TAKEOUT_RATES = {
    "HK": 0.175,
    "JRA": 0.20,
    "SG": 0.18,
    "DEFAULT": 0.20,
}

EDGE_THRESHOLD = 1.05  # Reject bets where p_model * (SP + 1) < this
KELLY_FRACTION = 0.25  # Quarter Kelly


def _kelly_fraction(p_model: float, sp_decimal: float) -> float:
    """
    Fractional Kelly criterion.

    f* = (p * SP - 1) / (SP - 1), clamped to [0, 1], then multiplied by KELLY_FRACTION.
    """
    if sp_decimal <= 1.0 or p_model <= 0:
        return 0.0
    edge = p_model * sp_decimal - 1.0
    if edge <= 0:
        return 0.0
    f_star = edge / (sp_decimal - 1.0)
    return min(f_star, 1.0) * KELLY_FRACTION


def _edge_filter(p_model: float, sp_decimal: float) -> bool:
    """Reject bets without sufficient edge after friction."""
    return p_model * (sp_decimal + 1) >= EDGE_THRESHOLD


def _get_takeout(jurisdiction: str) -> float:
    return TAKEOUT_RATES.get(jurisdiction, TAKEOUT_RATES["DEFAULT"])


def run_backtest(
    model: RacingRanker,
    test_df: pd.DataFrame,
    cycle: int,
) -> dict:
    """
    Run walk-forward backtest on fold_test.

    Returns per-bet detail and aggregate statistics.
    """
    probs = model.predict(test_df)
    test_df = test_df.copy()
    test_df["p_model"] = probs

    bets = []
    for race_id, group in test_df.groupby("race_id", sort=False):
        jurisdiction = group["jurisdiction"].iloc[0] if "jurisdiction" in group.columns else "HK"
        takeout = _get_takeout(jurisdiction)

        for _, runner in group.iterrows():
            p = runner["p_model"]
            sp = runner.get("sp_decimal", 0)

            if pd.isna(sp) or sp <= 1.0:
                continue

            if not _edge_filter(p, sp):
                continue

            stake = _kelly_fraction(p, sp)
            if stake <= 0:
                continue

            won = runner.get("finish_position") == 1
            gross_return = stake * sp if won else 0.0
            net_return = gross_return * (1 - takeout) if won else 0.0
            pnl = net_return - stake

            bets.append({
                "race_id": race_id,
                "horse_id": runner["horse_id"],
                "p_model": float(p),
                "sp_decimal": float(sp),
                "stake": float(stake),
                "finish_position": int(runner.get("finish_position", 0)),
                "won": bool(won),
                "gross_return": float(gross_return),
                "pnl_after_takeout": float(pnl),
                "jurisdiction": jurisdiction,
                "takeout_pct": takeout,
            })

    bets_df = pd.DataFrame(bets) if bets else pd.DataFrame()

    # Aggregate stats
    stats = _compute_stats(bets_df, cycle)

    # Bootstrap
    bootstrap = _bootstrap_roi(bets_df, test_df)
    stats["bootstrap"] = bootstrap

    return {"bets": bets, "stats": stats}


def _compute_stats(bets_df: pd.DataFrame, cycle: int) -> dict:
    """Compute aggregate backtest statistics."""
    if len(bets_df) == 0:
        return {
            "cycle": cycle,
            "n_bets": 0,
            "hit_rate": 0.0,
            "mean_odds": 0.0,
            "gross_roi": 0.0,
            "roi_after_takeout": 0.0,
            "sharpe_per_race": 0.0,
            "max_drawdown": 0.0,
            "turnover": 0.0,
        }

    total_staked = bets_df["stake"].sum()
    total_pnl = bets_df["pnl_after_takeout"].sum()
    n_bets = len(bets_df)

    # Per-race Sharpe
    race_pnl = bets_df.groupby("race_id")["pnl_after_takeout"].sum()
    sharpe = race_pnl.mean() / race_pnl.std() if race_pnl.std() > 0 else 0.0

    # Max drawdown
    cumulative = bets_df["pnl_after_takeout"].cumsum()
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max).min()

    return {
        "cycle": cycle,
        "n_bets": n_bets,
        "hit_rate": float(bets_df["won"].mean()),
        "mean_odds": float(bets_df["sp_decimal"].mean()),
        "gross_roi": float(
            (bets_df["gross_return"].sum() - total_staked) / total_staked
            if total_staked > 0
            else 0.0
        ),
        "roi_after_takeout": float(
            total_pnl / total_staked if total_staked > 0 else 0.0
        ),
        "sharpe_per_race": float(sharpe),
        "max_drawdown": float(drawdown),
        "turnover": float(total_staked),
    }


def _bootstrap_roi(
    bets_df: pd.DataFrame,
    test_df: pd.DataFrame,
    n_iterations: int = 10_000,
    seed: int = 42,
) -> dict:
    """
    Bootstrap ROI over race-meeting blocks (not individual bets).

    A block = all bets from one race meeting (same venue + date).
    """
    if len(bets_df) == 0:
        return {
            "mean_roi": 0.0,
            "median_roi": 0.0,
            "pct_5": 0.0,
            "pct_95": 0.0,
            "evidence_of_edge": False,
        }

    # Identify meeting blocks
    if "meeting_date" in test_df.columns and "venue" in test_df.columns:
        race_meetings = test_df.drop_duplicates("race_id")[["race_id", "meeting_date", "venue"]]
        bets_with_meeting = bets_df.merge(
            race_meetings, on="race_id", how="left"
        )
        bets_with_meeting["block"] = (
            bets_with_meeting["meeting_date"].astype(str)
            + "_"
            + bets_with_meeting["venue"].astype(str)
        )
    else:
        # Fallback: use race_id as block
        bets_with_meeting = bets_df.copy()
        bets_with_meeting["block"] = bets_with_meeting["race_id"]

    # Aggregate PnL and stakes per block
    block_stats = bets_with_meeting.groupby("block").agg(
        total_pnl=("pnl_after_takeout", "sum"),
        total_stake=("stake", "sum"),
    )

    rng = np.random.RandomState(seed)
    n_blocks = len(block_stats)
    rois = np.zeros(n_iterations)

    for i in range(n_iterations):
        sample_idx = rng.randint(0, n_blocks, size=n_blocks)
        sampled = block_stats.iloc[sample_idx]
        total_stake = sampled["total_stake"].sum()
        if total_stake > 0:
            rois[i] = sampled["total_pnl"].sum() / total_stake
        else:
            rois[i] = 0.0

    pct_5 = float(np.percentile(rois, 5))
    return {
        "mean_roi": float(np.mean(rois)),
        "median_roi": float(np.median(rois)),
        "pct_5": pct_5,
        "pct_95": float(np.percentile(rois, 95)),
        "evidence_of_edge": pct_5 >= 0.0,
    }


def save_report(result: dict, cycle: int, output_dir: str = "reports") -> str:
    """Save backtest report as JSON."""
    path = Path(output_dir) / f"cycle_{cycle}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f, indent=2, default=str)
    return str(path)


def save_summary(result: dict, cycle: int, output_dir: str = "reports") -> str:
    """Save 1-page markdown summary of the backtest."""
    stats = result["stats"]
    bootstrap = stats.get("bootstrap", {})

    evidence = "YES" if bootstrap.get("evidence_of_edge") else "NO"

    md = f"""# Backtest Report — Cycle {cycle}

## Summary

| Metric | Value |
|--------|-------|
| Bets placed | {stats['n_bets']} |
| Hit rate | {stats['hit_rate']:.3f} |
| Mean odds | {stats['mean_odds']:.2f} |
| Gross ROI | {stats['gross_roi']:.4f} |
| ROI after takeout | {stats['roi_after_takeout']:.4f} |
| Sharpe (per race) | {stats['sharpe_per_race']:.3f} |
| Max drawdown | {stats['max_drawdown']:.4f} |
| Turnover | {stats['turnover']:.2f} |

## Bootstrap (10,000 iterations, race-block resampling)

| Metric | Value |
|--------|-------|
| Mean ROI | {bootstrap.get('mean_roi', 0):.4f} |
| Median ROI | {bootstrap.get('median_roi', 0):.4f} |
| 5th percentile | {bootstrap.get('pct_5', 0):.4f} |
| 95th percentile | {bootstrap.get('pct_95', 0):.4f} |
| Evidence of edge | {evidence} |

## Verdict

{"The 5th-percentile bootstrap ROI is non-negative — consistent with a real edge." if bootstrap.get('evidence_of_edge') else "No evidence of edge: 5th-percentile bootstrap ROI is below zero. The point estimate may be driven by variance, not skill."}

Generated: {datetime.utcnow().isoformat()}Z
"""

    path = Path(output_dir) / f"cycle_{cycle}_summary.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(md)
    return str(path)
