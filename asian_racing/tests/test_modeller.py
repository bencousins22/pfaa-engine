"""
Unit tests for the modeller module.

Tests softmax correctness, calibration metrics, and model save/load.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from asian_racing.src.modeller import (
    _softmax_per_race,
    _win_log_loss,
    _calibration_ece,
    _brier_score,
    _market_correlation,
    ConditionalLogitBaseline,
    FEATURE_COLS,
)


def _make_dummy_race_df(n_races: int = 5, field_size: int = 8) -> pd.DataFrame:
    """Create a dummy DataFrame with multiple races."""
    rows = []
    for r in range(n_races):
        for h in range(field_size):
            row = {"race_id": f"race_{r}", "horse_id": f"horse_{r}_{h}"}
            for col in FEATURE_COLS:
                row[col] = np.random.randn()
            row["target_win"] = 1.0 if h == 0 else 0.0
            row["finish_position"] = h + 1
            row["sp_decimal"] = max(1.5, np.random.exponential(5))
            rows.append(row)
    return pd.DataFrame(rows)


class TestSoftmax:
    def test_sums_to_one_per_race(self):
        """Softmax probabilities must sum to ~1.0 within each race."""
        df = _make_dummy_race_df(n_races=10)
        raw_scores = np.random.randn(len(df))
        probs = _softmax_per_race(df, raw_scores)

        for _, group in df.groupby("race_id"):
            idx = group.index
            race_sum = probs[idx].sum()
            assert abs(race_sum - 1.0) < 1e-6, f"Softmax sum = {race_sum}"

    def test_all_positive(self):
        """Softmax probabilities must be positive."""
        df = _make_dummy_race_df()
        probs = _softmax_per_race(df, np.random.randn(len(df)))
        assert (probs > 0).all()


class TestWinLogLoss:
    def test_perfect_prediction(self):
        """Perfect prediction should give low loss."""
        y = np.array([1, 0, 0, 0])
        probs = np.array([0.99, 0.003, 0.003, 0.004])
        loss = _win_log_loss(y, probs)
        assert loss < 0.02

    def test_bad_prediction(self):
        """Bad prediction should give high loss."""
        y = np.array([1, 0, 0, 0])
        probs = np.array([0.01, 0.33, 0.33, 0.33])
        loss = _win_log_loss(y, probs)
        assert loss > 3.0


class TestCalibration:
    def test_ece_perfect(self):
        """Perfectly calibrated predictions should have low ECE."""
        y = np.array([1, 0, 1, 0, 1, 0, 1, 0, 1, 0])
        probs = np.array([0.9, 0.1, 0.8, 0.2, 0.7, 0.3, 0.9, 0.1, 0.8, 0.2])
        ece = _calibration_ece(y, probs)
        assert ece < 0.3

    def test_brier_bounds(self):
        """Brier score should be between 0 and 1."""
        y = np.random.randint(0, 2, 100).astype(float)
        probs = np.random.rand(100)
        bs = _brier_score(y, probs)
        assert 0 <= bs <= 1


class TestConditionalLogit:
    def test_fit_and_predict(self):
        """Baseline model should produce predictions of correct shape."""
        df = _make_dummy_race_df(n_races=20)
        X = df[FEATURE_COLS].values
        y = df["target_win"].values
        groups = df.groupby("race_id").size().values

        model = ConditionalLogitBaseline()
        model.fit(X, y, groups)
        preds = model.predict(X)

        assert preds.shape == (len(df),)
        assert not np.isnan(preds).any()
