#!/usr/bin/env python3
"""
PFAA Agent Team Runner — Spin up and execute the full agent team.

This is the main entry point for running the PFAA agents in team mode.
It initializes all agents, connects JMEM memory, and executes the
requested goal using the multi-agent swarm.

Usage:
    python -m agents.team.runner "optimize bitcoin trading strategy"
    python -m agents.team.runner --mode swarm "analyze codebase security"
    python -m agents.team.runner --mode pipeline "build and deploy"
    python -m agents.team.runner --freqtrade  # Run FreqTrade optimization

Python 3.15: lazy import, frozendict.
"""

from __future__ import annotations

import asyncio
import argparse
import logging
import sys
import time

lazy import json

from agents.team.agent_team import AgentTeam, TeamConfig, TeamRole, spawn_agent_team

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pfaa.runner")


# ── ANSI Colors ──────────────────────────────────────────────────────

CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"

BANNER = f"""
{CYAN}{BOLD}
╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ██████╗ ███████╗ █████╗  █████╗     ████████╗███████╗ █████╗  ║
║   ██╔══██╗██╔════╝██╔══██╗██╔══██╗    ╚══██╔══╝██╔════╝██╔══██╗ ║
║   ██████╔╝█████╗  ███████║███████║       ██║   █████╗  ███████║ ║
║   ██╔═══╝ ██╔══╝  ██╔══██║██╔══██║       ██║   ██╔══╝  ██╔══██║ ║
║   ██║     ██║     ██║  ██║██║  ██║       ██║   ███████╗██║  ██║ ║
║   ╚═╝     ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝       ╚═╝   ╚══════╝╚═╝  ╚═╝ ║
║                                                                  ║
║   Phase-Fluid Agent Architecture — Agent Team Mode               ║
║   Python 3.15 · JMEM Memory · 6 Agents · Q-Learning             ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
{RESET}"""


def print_status(msg: str, color: str = CYAN):
    print(f"  {color}▸{RESET} {msg}")


def print_result(role: str, success: bool, elapsed_ms: float, detail: str = ""):
    icon = f"{GREEN}✓{RESET}" if success else f"{RED}✗{RESET}"
    role_str = f"{YELLOW}{role:14s}{RESET}"
    time_str = f"{DIM}{elapsed_ms:>8.1f}ms{RESET}"
    print(f"  {icon} {role_str} {time_str} {detail}")


async def run_swarm(goal: str, team: AgentTeam) -> list[dict]:
    """Execute a goal across all agents in the team."""
    print_status(f"Swarming all agents on: {goal[:80]}")
    print()

    results = await team.swarm(goal)

    for r in results:
        print_result(
            r.get("role", "?"),
            r.get("success", False),
            r.get("elapsed_ms", 0),
            str(r.get("result", ""))[:60] if r.get("success") else str(r.get("error", ""))[:60],
        )

    succeeded = sum(1 for r in results if r.get("success"))
    print()
    print_status(f"Swarm complete: {succeeded}/{len(results)} agents succeeded", GREEN)
    return results


async def run_pipeline(goal: str, team: AgentTeam) -> list[dict]:
    """Execute a sequential pipeline across agent roles."""
    steps = [
        (TeamRole.RESEARCHER, f"Research: {goal}"),
        (TeamRole.STRATEGIST, f"Strategize: {goal}"),
        (TeamRole.OPTIMIZER, f"Optimize: {goal}"),
        (TeamRole.VALIDATOR, f"Validate: {goal}"),
        (TeamRole.RISK_MGR, f"Risk check: {goal}"),
        (TeamRole.DEPLOYER, f"Deploy: {goal}"),
    ]

    print_status(f"Pipeline: {len(steps)} stages")
    print()

    results = await team.pipeline(steps)

    for r in results:
        print_result(
            r.get("role", "?"),
            r.get("success", False),
            r.get("elapsed_ms", 0),
        )

    return results


async def run_freqtrade_optimization(team: AgentTeam) -> dict:
    """Run the FreqTrade Bitcoin strategy optimization."""
    print_status("Running FreqTrade BTC Strategy Optimization", MAGENTA)
    print()

    from freqtrade_strategy.hyperopt_optimizer import PFAAHyperoptOptimizer
    optimizer = PFAAHyperoptOptimizer()
    optimizer._team = team

    # Execute optimization pipeline using the team
    results = await optimizer.optimize()

    print()
    print_status("Optimization Results:", GREEN)
    print(f"  {DIM}{json.dumps(results.get('team_status', {}), indent=2, default=str)}{RESET}")

    # Generate the hyperopt command for manual execution
    cmd = await optimizer.run_hyperopt_command()
    print()
    print_status("To run hyperopt manually:", YELLOW)
    print(f"  {DIM}{cmd}{RESET}")

    return results


async def main_async(args: argparse.Namespace) -> None:
    """Main async entry point."""
    print(BANNER)

    # Determine roles
    if args.roles:
        roles = [TeamRole(r.strip()) for r in args.roles.split(",")]
    else:
        roles = list(TeamRole)

    print_status(f"Spawning {len(roles)} agents: {', '.join(r.value for r in roles)}")
    print()

    # Start team
    team = await spawn_agent_team(roles=roles, namespace=args.namespace)

    try:
        # Show initial status
        status = await team.status()
        print_status(f"Team active: {status['team_size']} agents, memory: {status.get('memory', {}).get('total_memories', 0)} memories")
        print()

        if args.freqtrade:
            await run_freqtrade_optimization(team)
        elif args.mode == "swarm":
            await run_swarm(args.goal, team)
        elif args.mode == "pipeline":
            await run_pipeline(args.goal, team)
        else:
            # Default: use swarm for short goals, pipeline for complex
            word_count = len(args.goal.split())
            if word_count > 10:
                await run_pipeline(args.goal, team)
            else:
                await run_swarm(args.goal, team)

        # Final status
        print()
        final_status = await team.status()
        print_status(f"Total tasks: {final_status['total_tasks']}", DIM)
        print_status(f"Uptime: {final_status['uptime_s']}s", DIM)

        mem = final_status.get("memory", {})
        if mem:
            print_status(
                f"Memory: {mem.get('total_memories', 0)} memories, "
                f"avg Q={mem.get('average_q', 0):.3f}, "
                f"health={mem.get('health', '?')}",
                DIM,
            )

    finally:
        await team.shutdown()
        print()
        print_status("Agent team shutdown complete", GREEN)


def main():
    parser = argparse.ArgumentParser(
        description="PFAA Agent Team Runner — spin up and execute the full agent team",
    )
    parser.add_argument("goal", nargs="?", default="analyze and optimize", help="Goal to execute")
    parser.add_argument("--mode", choices=["swarm", "pipeline", "auto"], default="auto", help="Execution mode")
    parser.add_argument("--roles", help="Comma-separated agent roles")
    parser.add_argument("--namespace", default="pfaa-team", help="JMEM memory namespace")
    parser.add_argument("--freqtrade", action="store_true", help="Run FreqTrade BTC optimization")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
