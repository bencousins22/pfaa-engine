"""
API call skeleton for the Claude Opus 4.6 agent team.

Dispatches the 7-agent team via the Anthropic Messages API with adaptive thinking.
Each agent has its own effort level and system prompt.

Usage:
    python -m asian_racing.src.api_runner --cycle 1
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional


PROMPTS_DIR = Path(__file__).parent.parent / "prompts"

AGENT_CONFIG = {
    "orchestrator": {
        "effort": "high",
        "model": "claude-opus-4-6",
        "tools": ["bash", "read", "write", "task-dispatch"],
    },
    "data_steward": {
        "effort": "low",
        "model": "claude-haiku-4-5-20251001",
        "tools": ["bash", "read", "write"],
    },
    "feature_engineer": {
        "effort": "adaptive",
        "model": "claude-opus-4-6",
        "tools": ["bash", "read", "write"],
    },
    "modeller": {
        "effort": "adaptive",
        "model": "claude-opus-4-6",
        "tools": ["bash", "read", "write"],
    },
    "backtester": {
        "effort": "adaptive",
        "model": "claude-opus-4-6",
        "tools": ["bash", "read", "write"],
    },
    "reviewer": {
        "effort": "high",
        "model": "claude-opus-4-6",
        "tools": ["read", "bash"],
    },
    "enhancer": {
        "effort": "high",
        "model": "claude-opus-4-6",
        "tools": ["read", "write"],
    },
}

TOOL_DEFINITIONS = [
    {"type": "bash_20250124", "name": "bash"},
    {"type": "text_editor_20250124", "name": "str_replace_editor"},
]


def load_prompt(agent_name: str) -> str:
    """Load system prompt for an agent."""
    path = PROMPTS_DIR / f"{agent_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")
    return path.read_text()


def create_agent_message(
    agent_name: str,
    user_content: str,
    client=None,
) -> dict:
    """
    Create a message for a specific agent.

    Args:
        agent_name: One of the 7 agent names
        user_content: The user message content
        client: Optional anthropic.Anthropic client (created if not provided)

    Returns:
        API response as dict
    """
    try:
        import anthropic
    except ImportError:
        raise ImportError(
            "anthropic SDK required. Install: pip install anthropic"
        )

    if client is None:
        client = anthropic.Anthropic()

    config = AGENT_CONFIG[agent_name]
    system_prompt = load_prompt(agent_name)

    thinking_config = {"type": "adaptive"}
    if config["effort"] != "adaptive":
        thinking_config["budget_tokens"] = {
            "low": 1024,
            "high": 8192,
            "max": 16384,
        }.get(config["effort"], 4096)

    response = client.messages.create(
        model=config["model"],
        max_tokens=8000,
        thinking=thinking_config,
        system=system_prompt,
        tools=TOOL_DEFINITIONS,
        messages=[{"role": "user", "content": user_content}],
    )

    return {
        "agent": agent_name,
        "model": config["model"],
        "content": [block.to_dict() if hasattr(block, 'to_dict') else str(block) for block in response.content],
        "usage": {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        },
        "stop_reason": response.stop_reason,
    }


def dispatch_cycle(cycle: int) -> dict:
    """
    Dispatch a full enhancement cycle to the agent team.

    This is the top-level entry point that the orchestrator system prompt
    is designed for. It sends the cycle kickoff message to the orchestrator,
    which then coordinates the other 6 agents.

    For a fully agentic loop, the orchestrator would use tool calls to
    dispatch to sub-agents. This function provides the initial kickoff.
    """
    try:
        import anthropic
    except ImportError:
        print("anthropic SDK not installed. Run: pip install anthropic")
        print("Generating dry-run output instead.")
        return _dry_run(cycle)

    client = anthropic.Anthropic()
    kickoff = load_prompt("cycle_kickoff")
    kickoff = kickoff.replace("cycle N", f"cycle {cycle}")

    result = create_agent_message(
        agent_name="orchestrator",
        user_content=kickoff,
        client=client,
    )

    return result


def _dry_run(cycle: int) -> dict:
    """Dry-run output for when the API isn't available."""
    return {
        "cycle": cycle,
        "mode": "dry_run",
        "agents": list(AGENT_CONFIG.keys()),
        "prompts_loaded": {
            name: str(PROMPTS_DIR / f"{name}.md")
            for name in AGENT_CONFIG
        },
        "message": (
            f"Dry run for cycle {cycle}. "
            "Set ANTHROPIC_API_KEY to run the full agent team."
        ),
    }


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Run the Asian Racing Prediction agent team"
    )
    parser.add_argument("--cycle", type=int, default=1, help="Cycle number")
    parser.add_argument(
        "--agent", type=str, default="orchestrator",
        choices=list(AGENT_CONFIG.keys()),
        help="Specific agent to call (default: orchestrator)",
    )
    parser.add_argument(
        "--message", type=str, default="",
        help="Custom user message (overrides cycle kickoff)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print config without calling API",
    )

    args = parser.parse_args()

    if args.dry_run:
        result = _dry_run(args.cycle)
    elif args.message:
        result = create_agent_message(args.agent, args.message)
    else:
        result = dispatch_cycle(args.cycle)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
