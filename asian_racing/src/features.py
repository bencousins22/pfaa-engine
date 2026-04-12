"""
Feature engineering for Asian racing prediction.

Every feature for race R uses only data with event_time < R.utc_off_time.
This is the core leak-free contract enforced by tests/test_no_lookahead.py.
"""

from __future__ import annotations

import json
import hashlib
from datetime import timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd


FEATURE_REGISTRY_PATH = Path(__file__).parent.parent / "features" / "feature_registry.json"

BASELINE_FEATURES = [
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

MISSING_NUMERIC = -1.0
MISSING_CATEGORICAL = "UNKNOWN"


def load_data(races_path: str, runners_path: str) -> pd.DataFrame:
    """Load and merge races + runners into a single DataFrame."""
    races = pd.read_parquet(races_path)
    runners = pd.read_parquet(runners_path)

    races["utc_off_time"] = pd.to_datetime(races["utc_off_time"], utc=True)
    if "last_run_date" in runners.columns:
        runners["last_run_date"] = pd.to_datetime(runners["last_run_date"], utc=True)

    merged = runners.merge(races, on="race_id", how="inner")
    merged = merged[~merged["is_scratched"]].copy()
    return merged.sort_values("utc_off_time").reset_index(drop=True)


def _rolling_rate(
    df: pd.DataFrame,
    group_col: str,
    target_col: str,
    window: int,
    cutoff_col: str = "utc_off_time",
) -> pd.Series:
    """
    Compute a rolling success rate for a group, using only past data.

    For each row, looks at the last `window` rows for the same group
    where event_time < current row's cutoff time.
    """
    rates = []
    for idx, row in df.iterrows():
        group_val = row[group_col]
        cutoff = row[cutoff_col]
        past = df[
            (df[group_col] == group_val)
            & (df[cutoff_col] < cutoff)
        ].tail(window)

        if len(past) == 0:
            rates.append(MISSING_NUMERIC)
        else:
            rates.append(past[target_col].mean())
    return pd.Series(rates, index=df.index)


def _time_windowed_rate(
    df: pd.DataFrame,
    group_col: str,
    target_col: str,
    days: int,
    cutoff_col: str = "utc_off_time",
) -> pd.Series:
    """
    Compute success rate for a group within a calendar-day window before cutoff.
    """
    rates = []
    for idx, row in df.iterrows():
        group_val = row[group_col]
        cutoff = row[cutoff_col]
        window_start = cutoff - timedelta(days=days)
        past = df[
            (df[group_col] == group_val)
            & (df[cutoff_col] < cutoff)
            & (df[cutoff_col] >= window_start)
        ]

        if len(past) == 0:
            rates.append(MISSING_NUMERIC)
        else:
            rates.append(past[target_col].mean())
    return pd.Series(rates, index=df.index)


def _distance_suit(df: pd.DataFrame, tolerance_m: int = 100) -> pd.Series:
    """Win rate at similar distance (±tolerance_m), using only past data."""
    rates = []
    for idx, row in df.iterrows():
        horse = row["horse_id"]
        cutoff = row["utc_off_time"]
        dist = row["distance_m"]
        past = df[
            (df["horse_id"] == horse)
            & (df["utc_off_time"] < cutoff)
            & (df["distance_m"].between(dist - tolerance_m, dist + tolerance_m))
        ]
        if len(past) == 0:
            rates.append(MISSING_NUMERIC)
        else:
            rates.append((past["finish_position"] == 1).mean())
    return pd.Series(rates, index=df.index)


def _going_suit(df: pd.DataFrame) -> pd.Series:
    """Win rate on the same going category, using only past data."""
    rates = []
    for idx, row in df.iterrows():
        horse = row["horse_id"]
        cutoff = row["utc_off_time"]
        going = row["going"]
        past = df[
            (df["horse_id"] == horse)
            & (df["utc_off_time"] < cutoff)
            & (df["going"] == going)
        ]
        if len(past) == 0:
            rates.append(MISSING_NUMERIC)
        else:
            rates.append((past["finish_position"] == 1).mean())
    return pd.Series(rates, index=df.index)


def _speed_figure_last(df: pd.DataFrame) -> pd.Series:
    """Best sectional-derived speed figure from the horse's last start."""
    figures = []
    for idx, row in df.iterrows():
        horse = row["horse_id"]
        cutoff = row["utc_off_time"]
        past = df[
            (df["horse_id"] == horse)
            & (df["utc_off_time"] < cutoff)
        ].tail(1)

        if len(past) == 0 or pd.isna(past.iloc[0].get("sectional_last_600")):
            figures.append(MISSING_NUMERIC)
        else:
            last = past.iloc[0]
            dist = last["distance_m"]
            time = last.get("finish_time_sec", None)
            if time and time > 0:
                figures.append(dist / time)
            else:
                figures.append(MISSING_NUMERIC)
    return pd.Series(figures, index=df.index)


def _parse_class_numeric(class_str: Optional[str]) -> float:
    """Extract numeric class level. Higher = lower class (e.g. Class 5 > Class 1)."""
    if not class_str or class_str == MISSING_CATEGORICAL:
        return MISSING_NUMERIC
    for part in str(class_str).split():
        try:
            return float(part)
        except ValueError:
            continue
    return MISSING_NUMERIC


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Build all baseline features. Returns DataFrame with (race_id, horse_id) + features.

    Every feature uses only data before the target race's utc_off_time.
    """
    df = df.copy()
    df["is_winner"] = (df["finish_position"] == 1).astype(float)
    df["is_placed"] = (df["finish_position"].between(1, 3)).astype(float)

    features = pd.DataFrame()
    features["race_id"] = df["race_id"]
    features["horse_id"] = df["horse_id"]
    features["utc_off_time"] = df["utc_off_time"]

    # Static features
    features["draw"] = df["draw"]
    features["field_size"] = df["field_size"]
    features["handicap_weight"] = df["handicap_weight_lb"].fillna(MISSING_NUMERIC)

    # Days since last run
    features["days_since_last_run"] = df.apply(
        lambda row: (
            (row["utc_off_time"] - row["last_run_date"]).days
            if pd.notna(row.get("last_run_date"))
            else MISSING_NUMERIC
        ),
        axis=1,
    )

    # Rolling rates — horse
    features["horse_win_rate_last_5"] = _rolling_rate(
        df, "horse_id", "is_winner", window=5
    )
    features["horse_place_rate_last_5"] = _rolling_rate(
        df, "horse_id", "is_placed", window=5
    )

    # Time-windowed rates — jockey, trainer
    features["jockey_win_rate_last_30d"] = _time_windowed_rate(
        df, "jockey_id", "is_winner", days=30
    )
    features["trainer_win_rate_last_30d"] = _time_windowed_rate(
        df, "trainer_id", "is_winner", days=30
    )

    # Class change
    features["class_change"] = df.apply(
        lambda row: (
            _parse_class_numeric(row.get("race_class"))
            - _parse_class_numeric(row.get("race_class_last"))
            if _parse_class_numeric(row.get("race_class")) != MISSING_NUMERIC
            and _parse_class_numeric(row.get("race_class_last")) != MISSING_NUMERIC
            else MISSING_NUMERIC
        ),
        axis=1,
    )

    # Suitability features
    features["distance_suit"] = _distance_suit(df)
    features["going_suit"] = _going_suit(df)
    features["speed_figure_last"] = _speed_figure_last(df)

    # Target (not a feature — for training only)
    features["target_win"] = df["is_winner"]
    features["finish_position"] = df["finish_position"]
    features["sp_decimal"] = df.get("sp_decimal", pd.Series(dtype=float))

    return features


def split_folds(
    features: pd.DataFrame,
    train_end: str,
    val_end: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Split features into train/val/test folds by utc_off_time.

    train: utc_off_time < train_end
    val:   train_end <= utc_off_time < val_end
    test:  utc_off_time >= val_end
    """
    train_end_ts = pd.Timestamp(train_end, tz="UTC")
    val_end_ts = pd.Timestamp(val_end, tz="UTC")

    fold_train = features[features["utc_off_time"] < train_end_ts]
    fold_val = features[
        (features["utc_off_time"] >= train_end_ts)
        & (features["utc_off_time"] < val_end_ts)
    ]
    fold_test = features[features["utc_off_time"] >= val_end_ts]

    return fold_train, fold_val, fold_test


def save_fold(df: pd.DataFrame, fold_name: str, output_dir: str = "features") -> str:
    """Save a fold to parquet. Returns the file path."""
    path = Path(output_dir) / f"{fold_name}.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    return str(path)


def feature_hash(df: pd.DataFrame) -> str:
    """SHA-256 hash of feature column names + dtypes for reproducibility tracking."""
    sig = "|".join(f"{c}:{df[c].dtype}" for c in sorted(df.columns))
    return hashlib.sha256(sig.encode()).hexdigest()[:16]


def write_feature_registry(features: pd.DataFrame, path: Optional[str] = None) -> None:
    """Write feature registry JSON with column names and descriptions."""
    path = Path(path) if path else FEATURE_REGISTRY_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    registry = {}
    descriptions = {
        "draw": "Barrier position (1-indexed)",
        "field_size": "Number of runners in the race",
        "handicap_weight": "Weight carried in pounds (-1 if missing)",
        "days_since_last_run": "Calendar days since horse's previous start",
        "horse_win_rate_last_5": "Win rate in horse's last 5 starts",
        "horse_place_rate_last_5": "Top-3 rate in horse's last 5 starts",
        "jockey_win_rate_last_30d": "Jockey win rate in last 30 days",
        "trainer_win_rate_last_30d": "Trainer win rate in last 30 days",
        "class_change": "Today's class minus last-start class (positive = dropped)",
        "distance_suit": "Horse win rate at this distance ±100m",
        "going_suit": "Horse win rate on this going category",
        "speed_figure_last": "Sectional-derived speed figure from last start",
    }

    for col in features.columns:
        if col in ("race_id", "horse_id", "utc_off_time", "target_win", "finish_position", "sp_decimal"):
            continue
        registry[col] = {
            "dtype": str(features[col].dtype),
            "description": descriptions.get(col, "No description"),
            "missing_sentinel": MISSING_NUMERIC,
        }

    with open(path, "w") as f:
        json.dump(registry, f, indent=2)
