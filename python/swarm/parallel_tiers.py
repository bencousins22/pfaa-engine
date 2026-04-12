"""
Pipeline parallelism with dependency graph — structured concurrency via asyncio.TaskGroup.

All tiers launch simultaneously inside a single TaskGroup. Each tier self-gates
on its dependencies via asyncio.Event, so independent tiers (intelligence,
acquisition) start immediately while downstream tiers wait only for the deps
they actually need.

Python 3.15 features:
  - PEP 695 type aliases
  - match/case for tier-result routing
  - asyncio.TaskGroup for structured concurrency
  - ExceptionGroup / except* for fault isolation
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, asdict, field
from typing import Any, Callable, Awaitable, TypeAlias

# ---------------------------------------------------------------------------
# PEP 695 type aliases
# ---------------------------------------------------------------------------
TierName: TypeAlias = str
JsonDict: TypeAlias = dict[str, Any]
TierRunner: TypeAlias = Callable[[TierName, JsonDict], Awaitable[JsonDict]]
OnTierDone: TypeAlias = Callable[[TierName, JsonDict], None]

# ---------------------------------------------------------------------------
# Dependency graph — defines execution order constraints
# ---------------------------------------------------------------------------
TIER_DEPS: dict[TierName, list[TierName]] = {
    "intelligence":  [],
    "acquisition":   [],
    "enrichment":    ["acquisition"],
    "scoring":       ["enrichment"],
    "outreach":      ["scoring", "intelligence"],
    "content":       ["intelligence"],
    "conversion":    ["scoring"],
    "nurture":       ["scoring"],
    "operations":    ["conversion", "nurture", "content"],
}

# Execution order for display/logging (topological)
TIER_ORDER: list[TierName] = [
    "intelligence", "acquisition", "enrichment", "scoring",
    "outreach", "content", "conversion", "nurture", "operations",
]


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TierResult:
    tier: TierName
    output: JsonDict
    duration_ms: int
    error: str | None = None


@dataclass(slots=True)
class PipelineResult:
    results: dict[TierName, TierResult] = field(default_factory=dict)
    total_duration_ms: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Core pipeline runner
# ---------------------------------------------------------------------------
async def run_pipeline(
    task: JsonDict,
    runner: TierRunner,
    *,
    on_tier_done: OnTierDone | None = None,
    tiers: list[TierName] | None = None,
) -> PipelineResult:
    """
    Run tiers in parallel with dependency gating.

    All tiers launch at the same time inside a TaskGroup. Each tier awaits
    asyncio.Events for its dependencies before calling `runner`. Independent
    tiers (intelligence, acquisition) start immediately.

    Args:
        task:         Shared task context passed to every tier runner.
        runner:       async callable(tier_name, task) -> result dict.
        on_tier_done: Optional sync callback invoked when each tier completes.
        tiers:        Subset of tiers to run (defaults to all).
    """
    selected = tiers or list(TIER_DEPS.keys())
    pipeline_start = time.monotonic()

    # One Event per tier — set when that tier completes
    events: dict[TierName, asyncio.Event] = {
        t: asyncio.Event() for t in selected
    }

    # Collected results
    tier_results: dict[TierName, TierResult] = {}

    async def _run_tier(tier: TierName) -> None:
        """Gate on deps, run, signal completion."""
        # Wait for all dependencies
        deps = TIER_DEPS.get(tier, [])
        for dep in deps:
            if dep in events:
                await events[dep].wait()

        start = time.monotonic()
        try:
            output = await runner(tier, task)
            result = TierResult(
                tier=tier,
                output=output,
                duration_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as exc:
            result = TierResult(
                tier=tier,
                output={},
                duration_ms=int((time.monotonic() - start) * 1000),
                error=str(exc),
            )

        tier_results[tier] = result

        # Signal downstream tiers
        events[tier].set()

        # Streaming callback
        if on_tier_done is not None:
            match result.error:
                case None:
                    on_tier_done(tier, {
                        "status": "done",
                        "duration_ms": result.duration_ms,
                        "output": result.output,
                    })
                case err:
                    on_tier_done(tier, {
                        "status": "error",
                        "duration_ms": result.duration_ms,
                        "error": err,
                    })

    # Launch all tiers simultaneously — TaskGroup ensures structured cleanup
    try:
        async with asyncio.TaskGroup() as tg:
            for tier in selected:
                tg.create_task(_run_tier(tier), name=f"tier:{tier}")
    except* Exception as eg:
        for exc in eg.exceptions:
            tier_results.setdefault("__infrastructure__", TierResult(
                tier="__infrastructure__",
                output={},
                duration_ms=0,
                error=str(exc),
            ))

    errors = [r.error for r in tier_results.values() if r.error]
    return PipelineResult(
        results=tier_results,
        total_duration_ms=int((time.monotonic() - pipeline_start) * 1000),
        errors=errors,
    )


# ---------------------------------------------------------------------------
# Convenience: run with the real team_runner agents
# ---------------------------------------------------------------------------
async def run_team_pipeline(
    task: JsonDict,
    opts: JsonDict,
    *,
    on_tier_done: OnTierDone | None = None,
) -> PipelineResult:
    """
    Run the full agent pipeline using team_runner.run_agent_safe for each tier.
    Agents are grouped by their tier field and run in parallel within each tier.
    """
    import os, sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from team_runner import run_agent_safe, TIER_REGISTRY

    async def tier_runner(tier: TierName, t: JsonDict) -> JsonDict:
        agents = TIER_REGISTRY.get(tier, [])
        if not agents:
            return {"skipped": True, "reason": f"no agents for tier {tier}"}

        prompt = t.get("prompt", "")
        results = []

        # Run all agents within the tier concurrently
        async with asyncio.TaskGroup() as tg:
            tasks = [
                tg.create_task(run_agent_safe(spec, opts, prompt), name=spec["id"])
                for spec in agents
            ]

        results = [tk.result() for tk in tasks]
        return {
            "agents": [asdict(r) for r in results],
            "agent_count": len(results),
        }

    return await run_pipeline(
        task, tier_runner, on_tier_done=on_tier_done,
    )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    """Demo: run pipeline with a stub runner that sleeps proportional to tier depth."""
    import json

    async def stub_runner(tier: TierName, task: JsonDict) -> JsonDict:
        # Simulate work — deeper tiers take slightly longer
        depth = len(TIER_DEPS.get(tier, []))
        await asyncio.sleep(0.05 * (depth + 1))
        return {"tier": tier, "simulated": True}

    def on_done(tier: TierName, info: JsonDict) -> None:
        print(json.dumps({"tier_done": tier, **info}))

    result = await run_pipeline(
        task={"prompt": "demo"},
        runner=stub_runner,
        on_tier_done=on_done,
    )
    print(json.dumps({
        "pipeline_done": True,
        "total_ms": result.total_duration_ms,
        "errors": result.errors,
        "tiers_completed": list(result.results.keys()),
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
