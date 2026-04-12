"""
Data steward — loads, validates, and manages the racing data snapshot.

Handles HKJC, JRA, and Kaggle data sources.
Enforces temporal integrity and schema compliance.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd


SCHEMA_REQUIRED_RACE_COLS = [
    "race_id", "venue", "jurisdiction", "meeting_date", "race_number",
    "utc_off_time", "distance_m", "field_size",
]

SCHEMA_REQUIRED_RUNNER_COLS = [
    "race_id", "horse_id", "horse_name", "draw", "jockey_id", "trainer_id",
]


class DataValidationError(Exception):
    """Raised when data fails integrity checks."""
    pass


def validate_races(df: pd.DataFrame) -> list[str]:
    """Validate races DataFrame against schema. Returns list of issues."""
    issues = []

    # Required columns
    for col in SCHEMA_REQUIRED_RACE_COLS:
        if col not in df.columns:
            issues.append(f"Missing required column: {col}")

    if issues:
        return issues  # Can't continue without required columns

    # utc_off_time must be parseable
    try:
        pd.to_datetime(df["utc_off_time"], utc=True)
    except Exception as e:
        issues.append(f"utc_off_time parse error: {e}")

    # Field size bounds
    out_of_bounds = df[(df["field_size"] < 2) | (df["field_size"] > 24)]
    if len(out_of_bounds) > 0:
        issues.append(f"{len(out_of_bounds)} races with field_size outside [2, 24]")

    # Distance bounds
    if "distance_m" in df.columns:
        bad_dist = df[(df["distance_m"] < 800) | (df["distance_m"] > 3600)]
        if len(bad_dist) > 0:
            issues.append(f"{len(bad_dist)} races with distance_m outside [800, 3600]")

    # Duplicate race_ids
    dupes = df["race_id"].duplicated().sum()
    if dupes > 0:
        issues.append(f"{dupes} duplicate race_ids")

    return issues


def validate_runners(df: pd.DataFrame, races_df: pd.DataFrame) -> list[str]:
    """Validate runners DataFrame. Returns list of issues."""
    issues = []

    for col in SCHEMA_REQUIRED_RUNNER_COLS:
        if col not in df.columns:
            issues.append(f"Missing required column: {col}")

    if issues:
        return issues

    # Every runner must reference a valid race
    orphan_races = set(df["race_id"]) - set(races_df["race_id"])
    if orphan_races:
        issues.append(f"{len(orphan_races)} runners reference non-existent races")

    # Duplicate (race_id, horse_id)
    dupes = df.duplicated(subset=["race_id", "horse_id"]).sum()
    if dupes > 0:
        issues.append(f"{dupes} duplicate (race_id, horse_id) pairs")

    # Draw bounds
    if "draw" in df.columns:
        bad_draw = df[(df["draw"] < 1) | (df["draw"] > 24)]
        if len(bad_draw) > 0:
            issues.append(f"{len(bad_draw)} runners with draw outside [1, 24]")

    # Verify field sizes match
    actual_sizes = df.groupby("race_id").size().reset_index(name="actual_field")
    merged = actual_sizes.merge(
        races_df[["race_id", "field_size"]], on="race_id", how="inner"
    )
    # Allow scratched horses to reduce field size
    if "is_scratched" in df.columns:
        active = df[~df["is_scratched"]].groupby("race_id").size().reset_index(name="active_field")
        merged = active.merge(
            races_df[["race_id", "field_size"]], on="race_id", how="inner"
        )
        mismatched = merged[merged["active_field"] != merged["field_size"]]
    else:
        mismatched = merged[merged["actual_field"] != merged["field_size"]]

    if len(mismatched) > 0:
        issues.append(
            f"{len(mismatched)} races where runner count doesn't match field_size"
        )

    return issues


def validate_temporal_integrity(races_df: pd.DataFrame) -> list[str]:
    """Check that utc_off_time is monotonically increasing within meetings."""
    issues = []
    races = races_df.copy()
    races["utc_off_time"] = pd.to_datetime(races["utc_off_time"], utc=True)

    for (date, venue), group in races.groupby(["meeting_date", "venue"]):
        sorted_group = group.sort_values("race_number")
        times = sorted_group["utc_off_time"].values
        for i in range(1, len(times)):
            if times[i] <= times[i - 1]:
                issues.append(
                    f"Non-monotonic time at {venue} on {date}: "
                    f"race {sorted_group.iloc[i]['race_number']} "
                    f"off_time <= race {sorted_group.iloc[i-1]['race_number']}"
                )
    return issues


def compute_manifest(
    races_df: pd.DataFrame, runners_df: pd.DataFrame
) -> dict:
    """Compute data manifest with date ranges, counts, and hash."""
    races = races_df.copy()
    races["utc_off_time"] = pd.to_datetime(races["utc_off_time"], utc=True)

    # Hash of the data for reproducibility
    combined = pd.concat([
        races["race_id"].astype(str),
        runners_df["horse_id"].astype(str),
    ])
    data_sig = "|".join(combined.tolist())
    sha = hashlib.sha256(data_sig.encode()).hexdigest()

    return {
        "earliest": str(races["utc_off_time"].min()),
        "latest": str(races["utc_off_time"].max()),
        "n_races": int(len(races)),
        "n_runners": int(len(runners_df)),
        "jurisdictions": sorted(races["jurisdiction"].unique().tolist()),
        "venues": sorted(races["venue"].unique().tolist()),
        "sha256": sha,
        "generated_at": datetime.utcnow().isoformat() + "Z",
    }


def load_kaggle_hkjc(csv_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load HKJC data from Kaggle CSV and split into races + runners DataFrames.

    Expects the standard Kaggle HKJC format with columns like:
    race_id, date, venue, race_no, distance, going, class, horse_name,
    jockey, trainer, draw, weight, finish_pos, win_odds, etc.
    """
    raw = pd.read_csv(csv_path)

    # Normalize column names
    raw.columns = [c.strip().lower().replace(" ", "_") for c in raw.columns]

    # Build races DataFrame
    race_cols = ["race_id", "date", "venue", "race_no", "distance", "going", "class"]
    available_race_cols = [c for c in race_cols if c in raw.columns]

    if not available_race_cols:
        raise DataValidationError("CSV doesn't contain expected HKJC columns")

    races = raw[available_race_cols].drop_duplicates(subset=["race_id"] if "race_id" in raw.columns else None)

    # Map to schema
    races_mapped = pd.DataFrame({
        "race_id": races.get("race_id", races.index.astype(str)),
        "venue": races.get("venue", "SHA"),
        "jurisdiction": "HK",
        "meeting_date": pd.to_datetime(races.get("date", "2000-01-01")).dt.date,
        "race_number": races.get("race_no", 1),
        "utc_off_time": pd.to_datetime(races.get("date", "2000-01-01")),
        "distance_m": races.get("distance", 1200),
        "going": races.get("going", "GOOD"),
        "race_class": races.get("class", ""),
        "surface": "TURF",
        "field_size": 0,  # Will be computed from runners
        "takeout_pct": 0.175,
    })

    # Build runners DataFrame — simplified, real implementation maps all columns
    runners_mapped = pd.DataFrame({
        "race_id": raw.get("race_id", raw.index.astype(str)),
        "horse_id": raw.get("horse_name", raw.index.astype(str)),
        "horse_name": raw.get("horse_name", ""),
        "draw": raw.get("draw", 1),
        "handicap_weight_lb": raw.get("weight", 126),
        "jockey_id": raw.get("jockey", ""),
        "jockey_name": raw.get("jockey", ""),
        "trainer_id": raw.get("trainer", ""),
        "trainer_name": raw.get("trainer", ""),
        "finish_position": raw.get("finish_pos", None),
        "sp_decimal": raw.get("win_odds", None),
        "is_scratched": False,
    })

    # Compute field sizes
    field_sizes = runners_mapped.groupby("race_id").size().reset_index(name="field_size")
    races_mapped = races_mapped.drop(columns=["field_size"]).merge(
        field_sizes, on="race_id", how="left"
    )

    return races_mapped, runners_mapped


def save_snapshot(
    races: pd.DataFrame,
    runners: pd.DataFrame,
    output_dir: str = "data",
) -> str:
    """Save races and runners to parquet, emit manifest."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    races.to_parquet(out / "races.parquet", index=False)
    runners.to_parquet(out / "runners.parquet", index=False)

    manifest = compute_manifest(races, runners)
    state_dir = Path("state")
    state_dir.mkdir(parents=True, exist_ok=True)
    with open(state_dir / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)

    return str(state_dir / "manifest.json")
