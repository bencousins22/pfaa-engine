"""
Adversarial reviewer — audits the pipeline before fold_test is touched.

Checks for lookahead leakage, overfitting, p-hacking, and calibration issues.
Blocks the cycle if any critical issue is found.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


class ReviewResult:
    """Structured result of a review cycle."""

    def __init__(self, cycle: int):
        self.cycle = cycle
        self.status = "PASS"  # or "BLOCK"
        self.leakage_check = "not run"
        self.overfitting_check = "not run"
        self.calibration_ece: Optional[float] = None
        self.market_correlation: Optional[float] = None
        self.val_trials_spent = 0
        self.blocking_issues: list[str] = []
        self.warnings: list[str] = []

    def block(self, reason: str) -> None:
        self.status = "BLOCK"
        self.blocking_issues.append(reason)

    def warn(self, reason: str) -> None:
        self.warnings.append(reason)

    def to_markdown(self) -> str:
        blocking = "\n".join(f"- {b}" for b in self.blocking_issues) if self.blocking_issues else "none"
        warnings = "\n".join(f"- {w}" for w in self.warnings) if self.warnings else "none"

        return f"""# Review — Cycle {self.cycle}

## Status: {self.status}

## Leakage check: {self.leakage_check}

## Overfitting check: {self.overfitting_check}

## Calibration: ECE = {self.calibration_ece or 'N/A'}, market_corr = {self.market_correlation or 'N/A'}

## Val trials spent: {self.val_trials_spent} / 20

## Blocking issues:
{blocking}

## Warnings:
{warnings}

---
Reviewed: {datetime.utcnow().isoformat()}Z
"""


def run_lookahead_test() -> tuple[bool, str]:
    """Run tests/test_no_lookahead.py and return (passed, output)."""
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", "tests/test_no_lookahead.py", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(Path(__file__).parent.parent),
        )
        passed = result.returncode == 0
        return passed, result.stdout + result.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, f"Test execution failed: {e}"


def check_feature_diff(
    current_path: str, previous_path: str
) -> tuple[list[str], list[str]]:
    """
    Compare feature columns between current and previous cycle.

    Returns (new_columns, removed_columns).
    """
    try:
        current = pd.read_parquet(current_path)
        previous = pd.read_parquet(previous_path)
    except FileNotFoundError:
        return [], []

    current_cols = set(current.columns)
    previous_cols = set(previous.columns)

    new_cols = sorted(current_cols - previous_cols)
    removed_cols = sorted(previous_cols - current_cols)

    return new_cols, removed_cols


def check_hypothesis_preregistered(
    new_features: list[str], hypotheses_path: str, cycle: int
) -> list[str]:
    """Check that new features have pre-registered hypotheses."""
    unregistered = []
    try:
        with open(hypotheses_path) as f:
            content = f.read()
    except FileNotFoundError:
        return new_features  # All unregistered if no hypotheses file

    for feat in new_features:
        if feat.lower() not in content.lower():
            unregistered.append(feat)

    return unregistered


def check_test_fold_leakage(mlruns_dir: str, test_fold_dates: tuple[str, str]) -> list[str]:
    """Grep mlruns/ for any reference to test-fold date ranges."""
    leaks = []
    mlruns = Path(mlruns_dir)
    if not mlruns.exists():
        return leaks

    start, end = test_fold_dates
    for json_file in mlruns.rglob("*.json"):
        try:
            content = json_file.read_text()
            if start in content or end in content or "fold_test" in content:
                leaks.append(str(json_file))
        except Exception:
            continue

    return leaks


def check_softmax_sums(features_path: str, probs_col: str = "p_model") -> tuple[bool, float]:
    """Verify softmax probabilities sum to ~1.0 per race."""
    try:
        df = pd.read_parquet(features_path)
    except FileNotFoundError:
        return True, 0.0

    if probs_col not in df.columns:
        return True, 0.0

    race_sums = df.groupby("race_id")[probs_col].sum()
    max_deviation = (race_sums - 1.0).abs().max()
    return max_deviation < 0.001, float(max_deviation)


def count_val_trials(mlruns_dir: str) -> int:
    """Count effective trials on fold_val across all cycles."""
    mlruns = Path(mlruns_dir)
    if not mlruns.exists():
        return 0

    trials = 0
    for metrics_file in mlruns.rglob("metrics.json"):
        try:
            with open(metrics_file) as f:
                data = json.load(f)
            # Each cycle with a model trained counts as a trial
            if "win_log_loss_val" in data:
                trials += 1
        except Exception:
            continue

    return trials


def feature_distribution_check(
    current_path: str, previous_path: str, top_n: int = 10, p_threshold: float = 0.01
) -> list[str]:
    """KS-test on top features between folds. Returns features with significant shift."""
    from scipy import stats as scipy_stats

    shifted = []
    try:
        current = pd.read_parquet(current_path)
        previous = pd.read_parquet(previous_path)
    except (FileNotFoundError, ImportError):
        return shifted

    numeric_cols = current.select_dtypes(include=[np.number]).columns.tolist()
    # Exclude metadata columns
    exclude = {"race_id", "horse_id", "utc_off_time", "target_win", "finish_position", "sp_decimal"}
    feature_cols = [c for c in numeric_cols if c not in exclude][:top_n]

    for col in feature_cols:
        if col in previous.columns:
            try:
                stat, p_val = scipy_stats.ks_2samp(
                    current[col].dropna(), previous[col].dropna()
                )
                if p_val < p_threshold:
                    shifted.append(f"{col} (KS p={p_val:.4f})")
            except Exception:
                continue

    return shifted


def run_review(
    cycle: int,
    features_current: str = "",
    features_previous: str = "",
    mlruns_dir: str = "mlruns",
    hypotheses_path: str = "state/hypotheses.md",
    metrics: Optional[dict] = None,
    test_fold_dates: tuple[str, str] = ("", ""),
) -> ReviewResult:
    """
    Run the full review checklist.

    Returns a ReviewResult with PASS or BLOCK status.
    """
    review = ReviewResult(cycle)

    # 1. Lookahead test
    passed, output = run_lookahead_test()
    if passed:
        review.leakage_check = "PASS — test_no_lookahead.py passed"
    else:
        review.leakage_check = f"FAIL — {output[:200]}"
        review.block("Lookahead test failed")

    # 2. Feature diff
    if features_current and features_previous:
        new_cols, _ = check_feature_diff(features_current, features_previous)
        if new_cols:
            unregistered = check_hypothesis_preregistered(
                new_cols, hypotheses_path, cycle
            )
            if unregistered:
                review.block(
                    f"New features without pre-registered hypothesis: {unregistered}"
                )

    # 3. Test fold leakage
    if test_fold_dates[0]:
        leaks = check_test_fold_leakage(mlruns_dir, test_fold_dates)
        if leaks:
            review.block(f"Test fold referenced in training logs: {leaks}")

    # 4. Calibration
    if metrics:
        ece = metrics.get("ece_val")
        corr = metrics.get("market_correlation")
        review.calibration_ece = ece
        review.market_correlation = corr

        if ece is not None and ece > 0.05:
            review.block(f"ECE too high: {ece:.4f} > 0.05")
        if corr is not None and not np.isnan(corr) and corr > 0.97:
            review.warn(f"Market correlation too high ({corr:.4f}) — likely no edge")

        review.overfitting_check = f"ECE={ece}, market_corr={corr}"
    else:
        review.overfitting_check = "No metrics provided"

    # 5. Val trial budget
    trials = count_val_trials(mlruns_dir)
    review.val_trials_spent = trials
    if trials > 20:
        review.warn(
            f"Effective val trials = {trials} > 20. Fold_val is burned. "
            "Recommend advancing the walk-forward window."
        )

    # 6. Feature distribution shift
    if features_current and features_previous:
        try:
            shifted = feature_distribution_check(features_current, features_previous)
            if shifted:
                review.warn(f"Feature distribution shift detected: {shifted}")
        except ImportError:
            pass  # scipy not available

    return review


def save_review(review: ReviewResult, output_dir: str = "state") -> str:
    """Save review to markdown file."""
    path = Path(output_dir) / f"review_{review.cycle}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(review.to_markdown())
    return str(path)
