"""
Orchestrator — runs the full enhancement cycle.

Coordinates data-steward → feature-engineer → modeller → reviewer → backtester → enhancer.
Implements halt conditions and cycle state management.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from .data_steward import validate_races, validate_runners, validate_temporal_integrity, compute_manifest, save_snapshot
from .features import build_features, split_folds, save_fold, feature_hash, write_feature_registry
from .modeller import RacingRanker, hyperparameter_search, FEATURE_COLS
from .backtester import run_backtest, save_report, save_summary
from .reviewer import run_review, save_review


class CycleState:
    """Tracks state across enhancement cycles."""

    STATE_FILE = Path("state") / "cycle_state.json"

    def __init__(self):
        self.current_cycle: int = 0
        self.roi_history: list[float] = []
        self.val_trials: int = 0
        self.halted: bool = False
        self.halt_reason: str = ""

    def load(self) -> None:
        if self.STATE_FILE.exists():
            with open(self.STATE_FILE) as f:
                data = json.load(f)
            self.current_cycle = data.get("current_cycle", 0)
            self.roi_history = data.get("roi_history", [])
            self.val_trials = data.get("val_trials", 0)
            self.halted = data.get("halted", False)
            self.halt_reason = data.get("halt_reason", "")

    def save(self) -> None:
        self.STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(self.STATE_FILE, "w") as f:
            json.dump({
                "current_cycle": self.current_cycle,
                "roi_history": self.roi_history,
                "val_trials": self.val_trials,
                "halted": self.halted,
                "halt_reason": self.halt_reason,
                "updated_at": datetime.utcnow().isoformat() + "Z",
            }, f, indent=2)

    def check_three_cycle_decline(self) -> bool:
        """Return True if last 3 cycles show declining ROI."""
        if len(self.roi_history) < 3:
            return False
        last3 = self.roi_history[-3:]
        return last3[0] > last3[1] > last3[2]

    def record_roi(self, roi: float) -> None:
        self.roi_history.append(roi)


def run_cycle(
    races_path: str,
    runners_path: str,
    train_end: str,
    val_end: str,
    optimize_hyperparams: bool = False,
    n_optuna_trials: int = 50,
) -> dict:
    """
    Run a single enhancement cycle end-to-end.

    Args:
        races_path: Path to races parquet
        runners_path: Path to runners parquet
        train_end: Cutoff date for train fold (ISO format)
        val_end: Cutoff date for val fold (ISO format)
        optimize_hyperparams: Whether to run Optuna search
        n_optuna_trials: Number of Optuna trials

    Returns:
        Cycle result dict with status, metrics, and report paths.
    """
    state = CycleState()
    state.load()

    if state.halted:
        return {"status": "HALTED", "reason": state.halt_reason}

    cycle = state.current_cycle + 1
    print(f"=== Starting Cycle {cycle} ===")

    result = {
        "cycle": cycle,
        "status": "IN_PROGRESS",
        "steps": {},
    }

    # Step 1: Validate data
    print("Step 1: Validating data...")
    races = pd.read_parquet(races_path)
    runners = pd.read_parquet(runners_path)

    race_issues = validate_races(races)
    runner_issues = validate_runners(runners, races)
    temporal_issues = validate_temporal_integrity(races)

    all_issues = race_issues + runner_issues + temporal_issues
    if all_issues:
        result["status"] = "DATA_ERROR"
        result["steps"]["validation"] = {"issues": all_issues}
        print(f"Data validation failed: {all_issues}")
        return result

    result["steps"]["validation"] = {"status": "PASS", "n_races": len(races), "n_runners": len(runners)}
    manifest = compute_manifest(races, runners)
    print(f"  Data: {manifest['n_races']} races, {manifest['n_runners']} runners")

    # Step 2: Build features
    print("Step 2: Building features...")
    from .features import load_data
    merged = load_data(races_path, runners_path)
    features = build_features(merged)

    fold_train, fold_val, fold_test = split_folds(features, train_end, val_end)
    print(f"  Folds: train={len(fold_train)}, val={len(fold_val)}, test={len(fold_test)}")

    if len(fold_train) == 0 or len(fold_val) == 0:
        result["status"] = "INSUFFICIENT_DATA"
        result["steps"]["features"] = {"error": "Empty train or val fold"}
        return result

    # Save feature files
    base_dir = str(Path(__file__).parent.parent)
    train_path = save_fold(fold_train, "fold_train", f"{base_dir}/features")
    val_path = save_fold(fold_val, "fold_val", f"{base_dir}/features")
    test_path = save_fold(fold_test, "fold_test", f"{base_dir}/features")
    write_feature_registry(features, f"{base_dir}/features/feature_registry.json")

    result["steps"]["features"] = {
        "status": "BUILT",
        "hash": feature_hash(features),
        "n_features": len(FEATURE_COLS),
    }

    # Step 3: Train model
    print("Step 3: Training model...")
    params = None
    if optimize_hyperparams:
        print("  Running hyperparameter search...")
        params = hyperparameter_search(fold_train, fold_val, cycle, n_optuna_trials)
        print(f"  Best params: {params}")

    ranker = RacingRanker(cycle=cycle)
    metrics = ranker.train(fold_train, fold_val, params=params)
    ranker.save(f"{base_dir}/models")
    ranker.save_metrics(f"{base_dir}/mlruns")

    result["steps"]["model"] = {
        "status": "TRAINED",
        "metrics": metrics,
        "calibration_ok": ranker.check_calibration(),
        "market_edge": ranker.check_market_edge(),
    }
    print(f"  ECE={metrics['ece_val']:.4f}, market_corr={metrics['market_correlation']:.4f}")
    print(f"  Top features: {metrics['top3_features']}")

    # Step 4: Review
    print("Step 4: Running review...")
    prev_features = f"{base_dir}/features/fold_val_prev.parquet" if cycle > 1 else ""
    review = run_review(
        cycle=cycle,
        features_current=val_path,
        features_previous=prev_features,
        mlruns_dir=f"{base_dir}/mlruns",
        hypotheses_path=f"{base_dir}/state/hypotheses.md",
        metrics=metrics,
        test_fold_dates=(val_end, ""),
    )
    save_review(review, f"{base_dir}/state")
    result["steps"]["review"] = {
        "status": review.status,
        "val_trials": review.val_trials_spent,
        "blocking_issues": review.blocking_issues,
        "warnings": review.warnings,
    }

    if review.status == "BLOCK":
        result["status"] = "BLOCKED_BY_REVIEWER"
        print(f"  BLOCKED: {review.blocking_issues}")
        return result

    print(f"  Review: {review.status}")

    # Step 5: Backtest
    print("Step 5: Running backtest...")
    if len(fold_test) == 0:
        result["status"] = "NO_TEST_DATA"
        result["steps"]["backtest"] = {"error": "Empty test fold"}
        return result

    backtest_result = run_backtest(ranker, fold_test, cycle)
    save_report(backtest_result, cycle, f"{base_dir}/reports")
    save_summary(backtest_result, cycle, f"{base_dir}/reports")

    stats = backtest_result["stats"]
    bootstrap = stats.get("bootstrap", {})
    result["steps"]["backtest"] = {
        "status": "COMPLETE",
        "stats": stats,
        "evidence_of_edge": bootstrap.get("evidence_of_edge", False),
    }
    print(f"  ROI after takeout: {stats['roi_after_takeout']:.4f}")
    print(f"  Bootstrap 5th pct: {bootstrap.get('pct_5', 0):.4f}")
    print(f"  Edge evidence: {bootstrap.get('evidence_of_edge', False)}")

    # Update state
    state.current_cycle = cycle
    state.record_roi(stats["roi_after_takeout"])
    state.val_trials = review.val_trials_spent

    # Check halt conditions
    if state.check_three_cycle_decline():
        state.halted = True
        state.halt_reason = "Three consecutive cycles of declining ROI"
        result["status"] = "HALTED_ROI_DECLINE"
    elif state.val_trials > 20:
        state.halted = True
        state.halt_reason = "Fold_val trial budget exhausted (>20 trials)"
        result["status"] = "HALTED_VAL_EXHAUSTED"
    else:
        result["status"] = "COMPLETE"

    state.save()

    # Save current val as "previous" for next cycle's diff
    fold_val.to_parquet(f"{base_dir}/features/fold_val_prev.parquet", index=False)

    print(f"=== Cycle {cycle} complete: {result['status']} ===")
    return result


def main():
    """CLI entry point for running a cycle."""
    import argparse

    parser = argparse.ArgumentParser(description="Run an Asian Racing Prediction cycle")
    parser.add_argument("--races", required=True, help="Path to races.parquet")
    parser.add_argument("--runners", required=True, help="Path to runners.parquet")
    parser.add_argument("--train-end", required=True, help="Train fold cutoff (ISO date)")
    parser.add_argument("--val-end", required=True, help="Val fold cutoff (ISO date)")
    parser.add_argument("--optimize", action="store_true", help="Run hyperparameter search")
    parser.add_argument("--n-trials", type=int, default=50, help="Optuna trial count")

    args = parser.parse_args()

    result = run_cycle(
        races_path=args.races,
        runners_path=args.runners,
        train_end=args.train_end,
        val_end=args.val_end,
        optimize_hyperparams=args.optimize,
        n_optuna_trials=args.n_trials,
    )

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
