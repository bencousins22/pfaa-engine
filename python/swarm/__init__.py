"""Aussie Agents Swarm — pre-warmed worker pool and tier-parallel pipeline."""

from .process_pool import worker_main
from .parallel_tiers import run_pipeline, run_team_pipeline, TIER_DEPS

__all__ = ["worker_main", "run_pipeline", "run_team_pipeline", "TIER_DEPS"]
