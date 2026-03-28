#!/usr/bin/env python3
"""
Aussie Agents Team Runner — Python 3.15
Structured concurrency for agent teams using asyncio.TaskGroup + ExceptionGroup.

Run: echo '<json>' | python3 team_runner.py
Env: PYTHON_GIL=0 for free-threaded embedding

Python 3.15 features used:
  - asyncio.TaskGroup (structured concurrency)
  - ExceptionGroup / except* (fault isolation)
  - asyncio.timeout() context manager
  - match/case for event routing
"""
from __future__ import annotations

import asyncio
import json
import sys
import os
import time
from dataclasses import dataclass, asdict, field
from typing import Any

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent_base import PFAAAgent, AgentContext, Response, emit

# Import tier agents
from agents.intelligence import INTELLIGENCE_AGENTS
from agents.acquisition import ACQUISITION_AGENTS
from agents.enrichment import ENRICHMENT_AGENTS
from agents.scoring import SCORING_AGENTS
from agents.outreach import OUTREACH_AGENTS
from agents.conversion import CONVERSION_AGENTS
from agents.nurture import NURTURE_AGENTS
from agents.content import CONTENT_AGENTS
from agents.operations import OPERATIONS_AGENTS

AgentId = str
JsonDict = dict[str, Any]
TierName = str

TIER_REGISTRY: dict[TierName, list[JsonDict]] = {
    "intelligence": INTELLIGENCE_AGENTS,
    "acquisition":  ACQUISITION_AGENTS,
    "enrichment":   ENRICHMENT_AGENTS,
    "scoring":      SCORING_AGENTS,
    "outreach":     OUTREACH_AGENTS,
    "conversion":   CONVERSION_AGENTS,
    "nurture":      NURTURE_AGENTS,
    "content":      CONTENT_AGENTS,
    "operations":   OPERATIONS_AGENTS,
}


@dataclass
class AgentResult:
    agent_id: AgentId
    tier: str
    output: str
    tool_calls: int = 0
    token_count: int = 0
    duration_ms: int = 0
    error: str | None = None


@dataclass
class TeamResult:
    task_id: str
    results: list[AgentResult]
    merged: str
    total_tokens: int
    duration_ms: int
    errors: list[str]
    type: str = "final_result"


def build_context(spec: JsonDict, opts: JsonDict) -> AgentContext:
    return AgentContext(
        agent_id=spec["id"],
        tier=spec.get("tier", ""),
        role=spec["role"],
        model=spec.get("model") or opts.get("model") or "claude-sonnet-4-6",
        provider=opts.get("provider", "claude"),
        workspace=opts.get("workspace", os.getcwd()),
        tools=spec.get("tools", ["file", "shell", "python", "memory_recall"]),
        memory_area=spec.get("memory_area", "main"),
        system_prompt=spec.get("system_prompt", ""),
        qdrant_url=opts.get("qdrantUrl", "http://localhost:6333"),
    )


async def run_agent_safe(agent_spec: JsonDict, opts: JsonDict, prompt: str) -> AgentResult:
    """Run a single agent with full fault isolation."""
    start = time.monotonic()
    ctx = build_context(agent_spec, opts)

    # Find the specialised agent class
    tier_agents = TIER_REGISTRY.get(ctx.tier, [])
    agent_cls = next(
        (a["cls"] for a in tier_agents if a["id"] == ctx.agent_id),
        PFAAAgent
    )
    agent = agent_cls(ctx)

    try:
        response: Response = await agent.execute(prompt)
        return AgentResult(
            agent_id=ctx.agent_id,
            tier=ctx.tier,
            output=response.message,
            tool_calls=response.tool_calls,
            token_count=response.token_count,
            duration_ms=int((time.monotonic() - start) * 1000),
            error=response.error,
        )
    except Exception as e:
        return AgentResult(
            agent_id=ctx.agent_id,
            tier=ctx.tier,
            output="",
            duration_ms=int((time.monotonic() - start) * 1000),
            error=str(e),
        )


async def run_team(task: JsonDict, opts: JsonDict) -> TeamResult:
    """
    Run all agents using asyncio.TaskGroup (Python 3.11+ structured concurrency).
    Individual errors are caught in run_agent_safe so TaskGroup never propagates.
    """
    start = time.monotonic()
    agent_specs: list[JsonDict] = task["agents"]
    prompt: str = task["prompt"]
    parallel: bool = task.get("parallel", True)
    task_id: str = task["taskId"]

    emit({
        "type": "team_start",
        "task_id": task_id,
        "agent_count": len(agent_specs),
        "parallel": parallel,
    })

    results: list[AgentResult] = []

    if parallel:
        task_map: dict[AgentId, asyncio.Task[AgentResult]] = {}
        try:
            async with asyncio.TaskGroup() as tg:
                for spec in agent_specs:
                    t = tg.create_task(
                        run_agent_safe(spec, opts, prompt),
                        name=spec["id"],
                    )
                    task_map[spec["id"]] = t
        except* Exception as eg:
            for exc in eg.exceptions:
                emit({"type": "infrastructure_error", "error": str(exc)})

        results = [t.result() for t in task_map.values() if not t.cancelled()]
    else:
        for spec in agent_specs:
            r = await run_agent_safe(spec, opts, prompt)
            results.append(r)

    merged = _merge(results)
    errors = [r.error for r in results if r.error]
    total_tokens = sum(r.token_count for r in results)
    duration_ms = int((time.monotonic() - start) * 1000)

    result = TeamResult(
        task_id=task_id,
        results=results,
        merged=merged,
        total_tokens=total_tokens,
        duration_ms=duration_ms,
        errors=errors,
    )

    emit(asdict(result))
    return result


def _merge(results: list[AgentResult]) -> str:
    """Group by tier, concatenate outputs."""
    sections: list[str] = []
    by_tier: dict[str, list[AgentResult]] = {}

    for r in results:
        by_tier.setdefault(r.tier, []).append(r)

    for tier, tier_results in by_tier.items():
        sections.append(f"## {tier.title()} tier\n")
        for r in tier_results:
            if r.output:
                sections.append(f"**{r.agent_id}** ({r.tool_calls} tool calls, {r.token_count} tokens)\n")
                sections.append(r.output + "\n")
            if r.error:
                sections.append(f"Warning {r.agent_id}: {r.error}\n")

    return "\n".join(sections)


async def main() -> None:
    raw = sys.stdin.read()
    payload = json.loads(raw)
    task = payload["task"]
    opts = payload["opts"]
    await run_team(task, opts)


if __name__ == "__main__":
    asyncio.run(main())
