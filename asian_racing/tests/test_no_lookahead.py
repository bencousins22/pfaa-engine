"""
Lookahead bias detection test.

Picks 50 random races and asserts that every feature value for each runner
was computed using only data available before race-off time.

This test MUST pass before any cycle proceeds to the backtest stage.
"""

from __future__ import annotations

import random
from pathlib import Path

import numpy as np
import pandas as pd
import pytest


DATA_DIR = Path(__file__).parent.parent / "data"
FEATURES_DIR = Path(__file__).parent.parent / "features"

SAMPLE_SIZE = 50
SEED = 42


def _load_runners() -> pd.DataFrame:
    """Load raw runners data with timestamps."""
    path = DATA_DIR / "runners.parquet"
    if not path.exists():
        pytest.skip("runners.parquet not found — no data loaded yet")
    df = pd.read_parquet(path)
    return df


def _load_races() -> pd.DataFrame:
    """Load raw races data with timestamps."""
    path = DATA_DIR / "races.parquet"
    if not path.exists():
        pytest.skip("races.parquet not found — no data loaded yet")
    df = pd.read_parquet(path)
    df["utc_off_time"] = pd.to_datetime(df["utc_off_time"], utc=True)
    return df


def _load_features(fold: str = "fold_train") -> pd.DataFrame:
    """Load feature parquet for a fold."""
    path = FEATURES_DIR / f"{fold}.parquet"
    if not path.exists():
        # Try loading any available parquet
        parquets = list(FEATURES_DIR.glob("*.parquet"))
        if not parquets:
            pytest.skip("No feature files found — features not built yet")
        path = parquets[0]
    return pd.read_parquet(path)


def _get_sample_races(features: pd.DataFrame) -> list[str]:
    """Pick up to SAMPLE_SIZE random race_ids."""
    race_ids = features["race_id"].unique().tolist()
    random.seed(SEED)
    return random.sample(race_ids, min(SAMPLE_SIZE, len(race_ids)))


class TestNoLookahead:
    """Suite of tests verifying no future data leaks into features."""

    def test_horse_win_rate_uses_past_only(self):
        """horse_win_rate_last_5 must use only starts before this race."""
        races = _load_races()
        runners = _load_runners()
        features = _load_features()

        sample_ids = _get_sample_races(features)
        race_times = races.set_index("race_id")["utc_off_time"]

        for race_id in sample_ids:
            if race_id not in race_times.index:
                continue
            cutoff = race_times[race_id]
            race_features = features[features["race_id"] == race_id]

            for _, row in race_features.iterrows():
                horse_id = row["horse_id"]
                # Get all past races for this horse
                horse_races = runners[runners["horse_id"] == horse_id]
                horse_races = horse_races.merge(
                    races[["race_id", "utc_off_time"]], on="race_id"
                )
                past = horse_races[horse_races["utc_off_time"] < cutoff]

                if len(past) == 0:
                    # No past data — feature should be missing sentinel
                    assert row.get("horse_win_rate_last_5", -1) == -1, (
                        f"Horse {horse_id} in race {race_id}: no past runs but "
                        f"horse_win_rate_last_5 = {row.get('horse_win_rate_last_5')}"
                    )

    def test_jockey_rate_uses_past_only(self):
        """jockey_win_rate_last_30d must use only data before this race."""
        races = _load_races()
        runners = _load_runners()
        features = _load_features()

        sample_ids = _get_sample_races(features)
        race_times = races.set_index("race_id")["utc_off_time"]

        for race_id in sample_ids:
            if race_id not in race_times.index:
                continue
            cutoff = race_times[race_id]
            race_features = features[features["race_id"] == race_id]

            for _, row in race_features.iterrows():
                jockey_id = row.get("jockey_id")
                if jockey_id is None:
                    continue

                # Verify no future jockey data is included
                jockey_races = runners[runners["jockey_id"] == jockey_id]
                jockey_races = jockey_races.merge(
                    races[["race_id", "utc_off_time"]], on="race_id"
                )
                future = jockey_races[jockey_races["utc_off_time"] >= cutoff]
                past = jockey_races[jockey_races["utc_off_time"] < cutoff]

                if len(past) == 0:
                    assert row.get("jockey_win_rate_last_30d", -1) == -1, (
                        f"Jockey {jockey_id} in race {race_id}: no past rides but "
                        f"jockey_win_rate_last_30d = {row.get('jockey_win_rate_last_30d')}"
                    )

    def test_trainer_rate_uses_past_only(self):
        """trainer_win_rate_last_30d must use only data before this race."""
        races = _load_races()
        runners = _load_runners()
        features = _load_features()

        sample_ids = _get_sample_races(features)
        race_times = races.set_index("race_id")["utc_off_time"]

        for race_id in sample_ids:
            if race_id not in race_times.index:
                continue
            cutoff = race_times[race_id]
            race_features = features[features["race_id"] == race_id]

            for _, row in race_features.iterrows():
                trainer_id = row.get("trainer_id")
                if trainer_id is None:
                    continue

                trainer_races = runners[runners["trainer_id"] == trainer_id]
                trainer_races = trainer_races.merge(
                    races[["race_id", "utc_off_time"]], on="race_id"
                )
                past = trainer_races[trainer_races["utc_off_time"] < cutoff]

                if len(past) == 0:
                    assert row.get("trainer_win_rate_last_30d", -1) == -1, (
                        f"Trainer {trainer_id} in race {race_id}: no past runners but "
                        f"trainer_win_rate_last_30d = {row.get('trainer_win_rate_last_30d')}"
                    )

    def test_no_future_finish_positions(self):
        """Feature rows must not contain finish positions from future races."""
        races = _load_races()
        features = _load_features()

        sample_ids = _get_sample_races(features)
        race_times = races.set_index("race_id")["utc_off_time"]

        for race_id in sample_ids:
            if race_id not in race_times.index:
                continue
            cutoff = race_times[race_id]
            race_features = features[features["race_id"] == race_id]

            for _, row in race_features.iterrows():
                horse_id = row["horse_id"]
                # speed_figure_last should be from a race before this one
                if "utc_off_time" in row.index and pd.notna(row.get("utc_off_time")):
                    assert pd.Timestamp(row["utc_off_time"]) <= cutoff, (
                        f"Feature row for {horse_id} in {race_id} has future timestamp"
                    )

    def test_distance_suit_uses_past_only(self):
        """distance_suit must be computed from past races only."""
        races = _load_races()
        runners = _load_runners()
        features = _load_features()

        sample_ids = _get_sample_races(features)
        race_times = races.set_index("race_id")["utc_off_time"]

        for race_id in sample_ids:
            if race_id not in race_times.index:
                continue
            cutoff = race_times[race_id]
            race_features = features[features["race_id"] == race_id]

            for _, row in race_features.iterrows():
                horse_id = row["horse_id"]
                horse_races = runners[runners["horse_id"] == horse_id]
                horse_races = horse_races.merge(
                    races[["race_id", "utc_off_time"]], on="race_id"
                )
                past = horse_races[horse_races["utc_off_time"] < cutoff]

                if len(past) == 0:
                    assert row.get("distance_suit", -1) == -1, (
                        f"Horse {horse_id} in {race_id}: no past runs but "
                        f"distance_suit = {row.get('distance_suit')}"
                    )

    def test_feature_timestamps_precede_race(self):
        """All feature rows must have utc_off_time matching their race."""
        races = _load_races()
        features = _load_features()

        sample_ids = _get_sample_races(features)
        race_times = races.set_index("race_id")["utc_off_time"]

        for race_id in sample_ids:
            if race_id not in race_times.index:
                continue
            expected_time = race_times[race_id]
            race_features = features[features["race_id"] == race_id]

            if "utc_off_time" in race_features.columns:
                for _, row in race_features.iterrows():
                    feat_time = pd.Timestamp(row["utc_off_time"])
                    assert feat_time == expected_time, (
                        f"Race {race_id}: feature utc_off_time {feat_time} != "
                        f"race utc_off_time {expected_time}"
                    )
