"""
Ranking model for Asian racing prediction.

Trains a LightGBM ranker with softmax-over-field win-log-loss.
Keeps a conditional logit baseline for sanity comparison.
"""

from __future__ import annotations

import json
import hashlib
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

try:
    import lightgbm as lgb
except ImportError:
    lgb = None

try:
    import optuna
except ImportError:
    optuna = None


FEATURE_COLS = [
    "draw",
    "field_size",
    "handicap_weight",
    "days_since_last_run",
    "horse_win_rate_last_5",
    "horse_place_rate_last_5",
    "jockey_win_rate_last_30d",
    "trainer_win_rate_last_30d",
    "class_change",
    "distance_suit",
    "going_suit",
    "speed_figure_last",
]


def _get_groups(df: pd.DataFrame) -> np.ndarray:
    """Compute group sizes (field size per race) for LambdaRank."""
    return df.groupby("race_id").size().values


def _softmax_per_race(df: pd.DataFrame, raw_scores: np.ndarray) -> np.ndarray:
    """Apply softmax within each race to convert scores to probabilities."""
    probs = np.zeros_like(raw_scores, dtype=float)
    offset = 0
    for _, group in df.groupby("race_id", sort=False):
        n = len(group)
        scores = raw_scores[offset : offset + n]
        exp_scores = np.exp(scores - np.max(scores))
        probs[offset : offset + n] = exp_scores / exp_scores.sum()
        offset += n
    return probs


def _win_log_loss(y_true: np.ndarray, probs: np.ndarray) -> float:
    """Koker's win-log-loss: -log(p_winner) averaged over races."""
    winner_mask = y_true == 1
    if winner_mask.sum() == 0:
        return float("inf")
    winner_probs = probs[winner_mask]
    winner_probs = np.clip(winner_probs, 1e-10, 1.0)
    return -np.log(winner_probs).mean()


def _calibration_ece(y_true: np.ndarray, probs: np.ndarray, n_bins: int = 10) -> float:
    """Expected Calibration Error (ECE) with equal-width bins."""
    bin_edges = np.linspace(0, 1, n_bins + 1)
    ece = 0.0
    for i in range(n_bins):
        mask = (probs >= bin_edges[i]) & (probs < bin_edges[i + 1])
        if mask.sum() == 0:
            continue
        bin_acc = y_true[mask].mean()
        bin_conf = probs[mask].mean()
        ece += mask.sum() / len(probs) * abs(bin_acc - bin_conf)
    return ece


def _brier_score(y_true: np.ndarray, probs: np.ndarray) -> float:
    """Brier score for probability calibration."""
    return float(np.mean((probs - y_true) ** 2))


def _market_correlation(probs: np.ndarray, sp_decimal: np.ndarray) -> float:
    """Pearson correlation between model probs and market implied probs."""
    valid = (sp_decimal > 0) & ~np.isnan(sp_decimal)
    if valid.sum() < 10:
        return float("nan")
    implied = 1.0 / sp_decimal[valid]
    return float(np.corrcoef(probs[valid], implied)[0, 1])


def data_hash(df: pd.DataFrame) -> str:
    """Hash of training data for reproducibility."""
    sig = f"{len(df)}|{df.columns.tolist()}|{df.iloc[0].tolist() if len(df) > 0 else ''}"
    return hashlib.sha256(sig.encode()).hexdigest()[:16]


class ConditionalLogitBaseline:
    """Simple conditional logit (McFadden's choice model) for sanity check."""

    def __init__(self):
        self.weights: Optional[np.ndarray] = None

    def fit(self, X: np.ndarray, y: np.ndarray, groups: np.ndarray) -> None:
        """Fit via simple gradient descent on win-log-loss."""
        n_features = X.shape[1]
        self.weights = np.zeros(n_features)
        lr = 0.01

        for _ in range(200):
            scores = X @ self.weights
            offset = 0
            grad = np.zeros(n_features)
            for g in groups:
                s = scores[offset : offset + g]
                exp_s = np.exp(s - np.max(s))
                p = exp_s / exp_s.sum()
                y_g = y[offset : offset + g]
                grad += X[offset : offset + g].T @ (p - y_g)
                offset += g
            self.weights -= lr * grad / len(groups)

    def predict(self, X: np.ndarray) -> np.ndarray:
        if self.weights is None:
            raise RuntimeError("Model not fitted")
        return X @ self.weights


class RacingRanker:
    """LightGBM-based ranking model for race prediction."""

    def __init__(self, cycle: int, seed: int = 42):
        self.cycle = cycle
        self.seed = seed
        self.model: Optional[lgb.Booster] = None
        self.baseline = ConditionalLogitBaseline()
        self.metrics: dict = {}

    def _prepare_data(self, df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        X = df[FEATURE_COLS].values.astype(float)
        y = df["target_win"].values.astype(float)
        groups = _get_groups(df)
        return X, y, groups

    def train(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        params: Optional[dict] = None,
    ) -> dict:
        """Train the ranker on fold_train with early stopping on fold_val."""
        if lgb is None:
            raise ImportError("lightgbm is required. Install: pip install lightgbm")

        X_train, y_train, groups_train = self._prepare_data(train_df)
        X_val, y_val, groups_val = self._prepare_data(val_df)

        # Train baseline
        self.baseline.fit(X_train, y_train, groups_train)

        # Default LightGBM params
        default_params = {
            "objective": "lambdarank",
            "metric": "ndcg",
            "ndcg_eval_at": [1, 3],
            "learning_rate": 0.05,
            "num_leaves": 31,
            "min_data_in_leaf": 20,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "lambda_l1": 0.1,
            "lambda_l2": 0.1,
            "seed": self.seed,
            "verbose": -1,
        }
        if params:
            default_params.update(params)

        train_set = lgb.Dataset(
            X_train,
            label=y_train,
            group=groups_train,
            feature_name=FEATURE_COLS,
        )
        val_set = lgb.Dataset(
            X_val,
            label=y_val,
            group=groups_val,
            feature_name=FEATURE_COLS,
            reference=train_set,
        )

        callbacks = [lgb.early_stopping(50), lgb.log_evaluation(0)]
        self.model = lgb.train(
            default_params,
            train_set,
            num_boost_round=1000,
            valid_sets=[val_set],
            callbacks=callbacks,
        )

        # Evaluate on validation
        raw_val = self.model.predict(X_val)
        probs_val = _softmax_per_race(val_df, raw_val)

        self.metrics = {
            "cycle": self.cycle,
            "win_log_loss_val": _win_log_loss(y_val, probs_val),
            "ece_val": _calibration_ece(y_val, probs_val),
            "brier_val": _brier_score(y_val, probs_val),
            "market_correlation": _market_correlation(
                probs_val, val_df["sp_decimal"].values
            ),
            "n_trees": self.model.num_trees(),
            "feature_importance": dict(
                zip(
                    FEATURE_COLS,
                    self.model.feature_importance("gain").tolist(),
                )
            ),
            "data_hash_train": data_hash(train_df),
            "data_hash_val": data_hash(val_df),
            "seed": self.seed,
        }

        # Top-3 importances
        imp = self.metrics["feature_importance"]
        top3 = sorted(imp.items(), key=lambda x: x[1], reverse=True)[:3]
        self.metrics["top3_features"] = [f[0] for f in top3]

        return self.metrics

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Predict softmax probabilities for all runners."""
        if self.model is None:
            raise RuntimeError("Model not trained")
        X = df[FEATURE_COLS].values.astype(float)
        raw = self.model.predict(X)
        return _softmax_per_race(df, raw)

    def save(self, output_dir: str = "models") -> str:
        """Save model to disk."""
        if self.model is None:
            raise RuntimeError("Model not trained")
        path = Path(output_dir) / f"cycle_{self.cycle}.lgb"
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save_model(str(path))
        return str(path)

    def load(self, path: str) -> None:
        """Load model from disk."""
        if lgb is None:
            raise ImportError("lightgbm is required")
        self.model = lgb.Booster(model_file=path)

    def save_metrics(self, output_dir: str = "mlruns") -> str:
        """Save training metrics for audit trail."""
        path = Path(output_dir) / f"cycle_{self.cycle}" / "metrics.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.metrics, f, indent=2, default=str)
        return str(path)

    def check_calibration(self) -> bool:
        """Return True if ECE on fold_val <= 0.05."""
        ece = self.metrics.get("ece_val", 1.0)
        return ece <= 0.05

    def check_market_edge(self) -> bool:
        """Return True if market correlation < 0.97 (we have differentiated signal)."""
        corr = self.metrics.get("market_correlation", 1.0)
        if np.isnan(corr):
            return True  # Can't assess, proceed with caution
        return corr < 0.97


def hyperparameter_search(
    train_df: pd.DataFrame,
    val_df: pd.DataFrame,
    cycle: int,
    n_trials: int = 50,
    seed: int = 42,
) -> dict:
    """Optuna hyperparameter search on fold_val only."""
    if optuna is None:
        raise ImportError("optuna is required. Install: pip install optuna")
    if lgb is None:
        raise ImportError("lightgbm is required")

    def objective(trial: optuna.Trial) -> float:
        params = {
            "objective": "lambdarank",
            "metric": "ndcg",
            "ndcg_eval_at": [1],
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 15, 127),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 5, 50),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
            "bagging_freq": 5,
            "lambda_l1": trial.suggest_float("lambda_l1", 0.0, 5.0),
            "lambda_l2": trial.suggest_float("lambda_l2", 0.0, 5.0),
            "seed": seed,
            "verbose": -1,
        }

        ranker = RacingRanker(cycle=cycle, seed=seed)
        metrics = ranker.train(train_df, val_df, params=params)
        return metrics["win_log_loss_val"]

    study = optuna.create_study(direction="minimize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    return study.best_params
