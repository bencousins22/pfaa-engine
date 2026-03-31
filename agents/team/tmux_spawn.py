#!/usr/bin/env python3
"""
Aussie Agents tmux Team -- Spawn 10 agents in parallel tmux panes.

Each agent runs in its own Claude Code session. The cortex hook system
tracks all SubagentStart/Stop events across panes for RL learning.

Usage:
    python3 agents/team/tmux_spawn.py "analyze and optimize the cortex"
    python3 agents/team/tmux_spawn.py --agents researcher,security,tdd "audit auth"
    python3 agents/team/tmux_spawn.py --layout tall "full system review"
    python3 agents/team/tmux_spawn.py --interactive  # Each pane is interactive claude session
"""
from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# -- ANSI Colors ---------------------------------------------------------------

CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
MAGENTA = "\033[35m"
DIM     = "\033[2m"
BOLD    = "\033[1m"
RESET   = "\033[0m"

BANNER = f"""{CYAN}{BOLD}
+=====================================================================+
|                                                                       |
|    AUSSIE  AGENTS  --  tmux  Team  Spawner                            |
|                                                                       |
|    ████████╗███╗   ███╗██╗   ██╗██╗  ██╗                              |
|    ╚══██╔══╝████╗ ████║██║   ██║╚██╗██╔╝                              |
|       ██║   ██╔████╔██║██║   ██║ ╚███╔╝                               |
|       ██║   ██║╚██╔╝██║██║   ██║ ██╔██╗                               |
|       ██║   ██║ ╚═╝ ██║╚██████╔╝██╔╝ ██╗                             |
|       ╚═╝   ╚═╝     ╚═╝ ╚═════╝ ╚═╝  ╚═╝                             |
|                                                                       |
|    Phase-Fluid Agent Architecture                                     |
|    10 Agents  -  Parallel Panes  -  JMEM Memory  -  Cortex Hooks     |
|                                                                       |
+=====================================================================+{RESET}
"""

# -- Agent definitions ---------------------------------------------------------

PHASE_COLOR = {
    "VAPOR":  "cyan",
    "LIQUID": "yellow",
    "SOLID":  "green",
}

# tmux color names for pane-border-style per phase
PHASE_TMUX_FG = {
    "VAPOR":  "colour6",   # cyan
    "LIQUID": "colour3",   # yellow
    "SOLID":  "colour2",   # green
}

PHASE_ANSI = {
    "VAPOR":  CYAN,
    "LIQUID": YELLOW,
    "SOLID":  GREEN,
}


@dataclass(frozen=True)
class AgentDef:
    name: str
    phase: str
    role: str


ALL_AGENTS: list[AgentDef] = [
    AgentDef("pfaa-lead",          "VAPOR",  "Orchestrator"),
    AgentDef("aussie-researcher",  "VAPOR",  "Research & synthesis"),
    AgentDef("aussie-planner",     "VAPOR",  "Goal decomposition"),
    AgentDef("aussie-architect",   "VAPOR",  "System design"),
    AgentDef("aussie-security",    "VAPOR",  "OWASP audit"),
    AgentDef("aussie-tdd",         "SOLID",  "Test-first dev"),
    AgentDef("pfaa-rewriter",      "LIQUID", "Py3.15 optimize"),
    AgentDef("pfaa-validator",     "SOLID",  "Read-only QA"),
    AgentDef("aussie-deployer",    "SOLID",  "Deployment"),
    AgentDef("aussie-docs",        "VAPOR",  "Doc sync"),
]

# Short aliases for --agents flag (e.g. --agents researcher,security,tdd)
AGENT_ALIASES: dict[str, str] = {}
for _a in ALL_AGENTS:
    AGENT_ALIASES[_a.name] = _a.name
    # "researcher" -> "aussie-researcher", "lead" -> "pfaa-lead", etc.
    short = _a.name.replace("aussie-", "").replace("pfaa-", "")
    AGENT_ALIASES[short] = _a.name

PROJECT_DIR = "/Users/borris/Desktop/pfaa-engine"
TMUX_BIN = "/usr/local/bin/tmux"

# -- Helpers -------------------------------------------------------------------


def _tmux(*args: str, check: bool = False) -> subprocess.CompletedProcess[str]:
    """Run a tmux command and return the result."""
    return subprocess.run(
        [TMUX_BIN, *args],
        capture_output=True,
        text=True,
        check=check,
    )


def _find_claude_binary() -> str:
    """Locate the claude CLI binary or abort."""
    for candidate in ["claude", Path.home() / ".claude" / "local" / "claude",
                       Path.home() / ".local" / "bin" / "claude"]:
        found = shutil.which(str(candidate))
        if found:
            return found
    print(f"{RED}Error: 'claude' CLI not found in PATH.{RESET}")
    sys.exit(1)


def _build_cmd(agent: AgentDef, goal: str, interactive: bool, claude_bin: str) -> str:
    """Build the shell command for a single tmux pane."""
    if interactive:
        return f"cd {shlex.quote(PROJECT_DIR)} && {shlex.quote(claude_bin)} --agent {agent.name}"
    safe_goal = shlex.quote(goal)
    return f"cd {shlex.quote(PROJECT_DIR)} && {shlex.quote(claude_bin)} --agent {agent.name} --print {safe_goal}"


def _resolve_agents(names_csv: str) -> list[AgentDef]:
    """Resolve a comma-separated list of agent names/aliases to AgentDef list."""
    if not names_csv:
        return list(ALL_AGENTS)
    lookup = {a.name: a for a in ALL_AGENTS}
    selected: list[AgentDef] = []
    for raw in names_csv.split(","):
        key = raw.strip().lower()
        full_name = AGENT_ALIASES.get(key)
        if full_name and full_name in lookup:
            selected.append(lookup[full_name])
        else:
            print(f"{RED}Unknown agent: {raw!r}{RESET}")
            print(f"  Available: {', '.join(AGENT_ALIASES.keys())}")
            sys.exit(1)
    return selected


# -- Layout builders -----------------------------------------------------------

def _layout_grid(agents: list[AgentDef], session: str, claude_bin: str,
                 goal: str, interactive: bool) -> None:
    """
    Grid layout: 4 rows of 2 + bottom full-width lead.

    +---------------------+---------------------+
    | aussie-researcher   | aussie-security     |
    +---------------------+---------------------+
    | aussie-tdd          | pfaa-rewriter       |
    +---------------------+---------------------+
    | pfaa-validator      | aussie-architect    |
    +---------------------+---------------------+
    | aussie-planner      | aussie-deployer     |
    +---------------------+---------------------+
    | pfaa-lead (orchestrator) -- full width     |
    +-----------+-------------------------------+

    When fewer agents are provided, falls back to tiled layout.
    """
    # Separate lead from the rest
    lead = None
    others: list[AgentDef] = []
    for a in agents:
        if a.name == "pfaa-lead":
            lead = a
        else:
            others.append(a)

    # Preferred row ordering when we have the full set
    preferred_order = [
        "aussie-researcher", "aussie-security",
        "aussie-tdd", "pfaa-rewriter",
        "pfaa-validator", "aussie-architect",
        "aussie-planner", "aussie-deployer",
        "aussie-docs",
    ]
    ordered: list[AgentDef] = []
    others_by_name = {a.name: a for a in others}
    for name in preferred_order:
        if name in others_by_name:
            ordered.append(others_by_name.pop(name))
    # Append any remaining agents not in the preferred order
    ordered.extend(others_by_name.values())

    # Determine the first pane agent (lead goes last for full-width bottom)
    first_agent = ordered[0] if ordered else lead
    if first_agent is None:
        print(f"{RED}No agents to spawn.{RESET}")
        sys.exit(1)

    # Create session with first pane
    first_cmd = _build_cmd(first_agent, goal, interactive, claude_bin)
    _tmux("new-session", "-d", "-s", session, "-n", "aussie-team", first_cmd)
    pane_agents: list[AgentDef] = [first_agent]

    # Split remaining non-lead agents into 2-column rows
    remaining = ordered[1:]
    for i, agent in enumerate(remaining):
        cmd = _build_cmd(agent, goal, interactive, claude_bin)
        if i % 2 == 0:
            # New row: vertical split from pane 0 (creates bottom slice)
            _tmux("split-window", "-t", f"{session}:0.0", "-v", cmd)
        else:
            # Right column: horizontal split from the pane we just created
            _tmux("split-window", "-t", f"{session}:0.{len(pane_agents)}", "-h", cmd)
        pane_agents.append(agent)

    # Add lead as the last pane (full-width bottom) if present and not already added
    if lead and lead is not first_agent:
        cmd = _build_cmd(lead, goal, interactive, claude_bin)
        _tmux("split-window", "-t", f"{session}:0.0", "-v", cmd)
        pane_agents.append(lead)

    # Even out the layout
    _tmux("select-layout", "-t", f"{session}:0", "tiled")

    return pane_agents


def _layout_tall(agents: list[AgentDef], session: str, claude_bin: str,
                 goal: str, interactive: bool) -> list[AgentDef]:
    """Vertical stack: all panes in a single column."""
    first_cmd = _build_cmd(agents[0], goal, interactive, claude_bin)
    _tmux("new-session", "-d", "-s", session, "-n", "aussie-team", first_cmd)
    pane_agents = [agents[0]]

    for agent in agents[1:]:
        cmd = _build_cmd(agent, goal, interactive, claude_bin)
        _tmux("split-window", "-t", f"{session}:0", "-v", cmd)
        pane_agents.append(agent)

    _tmux("select-layout", "-t", f"{session}:0", "even-vertical")
    return pane_agents


# -- Main spawn logic ----------------------------------------------------------

def spawn_team(
    goal: str,
    agents: list[AgentDef],
    session: str,
    layout: str,
    interactive: bool,
    dry_run: bool = False,
) -> None:
    """Spawn the agent team in a tmux session."""

    # -- Pre-flight checks -----------------------------------------------------
    if not shutil.which(TMUX_BIN) and not Path(TMUX_BIN).exists():
        print(f"{RED}Error: tmux not found at {TMUX_BIN}{RESET}")
        sys.exit(1)

    claude_bin = _find_claude_binary()

    # -- Banner ----------------------------------------------------------------
    print(BANNER)

    # -- Summary ---------------------------------------------------------------
    mode = "interactive" if interactive else f"--print {goal!r}"
    print(f"  {CYAN}Session:{RESET}  {BOLD}{session}{RESET}")
    print(f"  {CYAN}Layout:{RESET}   {layout}")
    print(f"  {CYAN}Mode:{RESET}     {mode}")
    print(f"  {CYAN}Claude:{RESET}   {DIM}{claude_bin}{RESET}")
    print(f"  {CYAN}Agents:{RESET}   {BOLD}{len(agents)}{RESET}")
    print()

    for agent in agents:
        phase_c = PHASE_ANSI.get(agent.phase, RESET)
        print(f"    {GREEN}>{RESET} {YELLOW}{agent.name:22s}{RESET} "
              f"[{phase_c}{agent.phase}{RESET}] "
              f"{DIM}{agent.role}{RESET}")
    print()

    if dry_run:
        print(f"  {YELLOW}(dry-run: not spawning tmux session){RESET}")
        return

    # -- Kill existing session if any ------------------------------------------
    _tmux("kill-session", "-t", session)
    time.sleep(0.2)

    # -- Build layout ----------------------------------------------------------
    if layout == "tall":
        pane_agents = _layout_tall(agents, session, claude_bin, goal, interactive)
    else:
        pane_agents = _layout_grid(agents, session, claude_bin, goal, interactive)

    # -- Configure pane titles and borders -------------------------------------
    for i, agent in enumerate(pane_agents):
        pane_target = f"{session}:0.{i}"
        title = f" {agent.name} [{agent.phase}] "

        # Set pane title
        _tmux("select-pane", "-t", pane_target, "-T", title)

        # Color-code border per phase
        fg = PHASE_TMUX_FG.get(agent.phase, "colour7")
        _tmux("set-option", "-t", pane_target, "-p", "pane-border-style", f"fg={fg}")
        _tmux("set-option", "-t", pane_target, "-p", "pane-active-border-style", f"fg={fg},bold")

    # -- Pane border titles ----------------------------------------------------
    _tmux("set-option", "-t", session, "pane-border-status", "top")
    _tmux("set-option", "-t", session, "pane-border-format",
          " #[bold]#{pane_title} ")

    # -- Status bar ------------------------------------------------------------
    phase_counts = {}
    for a in agents:
        phase_counts[a.phase] = phase_counts.get(a.phase, 0) + 1
    phase_summary = "  ".join(f"{p}={c}" for p, c in sorted(phase_counts.items()))

    _tmux("set-option", "-t", session, "status", "on")
    _tmux("set-option", "-t", session, "status-style", "bg=colour235,fg=colour6")
    _tmux("set-option", "-t", session, "status-left-length", "60")
    _tmux("set-option", "-t", session, "status-right-length", "60")
    _tmux("set-option", "-t", session, "status-left",
          f" AUSSIE TEAM  |  {len(agents)} agents  |  {phase_summary} ")
    _tmux("set-option", "-t", session, "status-right",
          f" {session}  |  %H:%M ")

    # -- Select first pane and attach ------------------------------------------
    _tmux("select-pane", "-t", f"{session}:0.0")

    print(f"  {GREEN}Spawned {len(pane_agents)} agents in tmux session "
          f"'{BOLD}{session}{RESET}{GREEN}'.{RESET}")
    print(f"  {DIM}Attaching...{RESET}\n")

    # Attach (replaces this process's terminal)
    subprocess.run([TMUX_BIN, "attach-session", "-t", session])


# -- CLI -----------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aussie Agents tmux Team Spawner -- 10 agents in parallel panes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""\
examples:
  %(prog)s "analyze and optimize the cortex"
  %(prog)s --agents researcher,security,tdd "audit auth"
  %(prog)s --layout tall "full system review"
  %(prog)s --interactive
  %(prog)s --dry-run "test layout"

agents:
  {', '.join(a.name for a in ALL_AGENTS)}

aliases (short names also accepted):
  {', '.join(sorted(set(k for k in AGENT_ALIASES if '-' not in k)))}
""",
    )
    parser.add_argument(
        "goal", nargs="?", default="",
        help="Goal/task prompt for agents (required unless --interactive)",
    )
    parser.add_argument(
        "--agents", "-a", type=str, default="",
        help="Comma-separated agent names or aliases (default: all 10)",
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true",
        help="Spawn interactive claude sessions instead of --print mode",
    )
    parser.add_argument(
        "--session", "-s", type=str, default="aussie-team",
        help="tmux session name (default: aussie-team)",
    )
    parser.add_argument(
        "--layout", "-l", type=str, default="grid", choices=["grid", "tall"],
        help="Pane layout: grid (4x2 + lead) or tall (vertical stack)",
    )
    parser.add_argument(
        "--dry-run", "-n", action="store_true",
        help="Print spawn plan without creating tmux session",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Validate: need a goal unless interactive or dry-run
    if not args.goal and not args.interactive:
        parser.error("a goal is required unless --interactive is used")

    agents = _resolve_agents(args.agents)

    spawn_team(
        goal=args.goal,
        agents=agents,
        session=args.session,
        layout=args.layout,
        interactive=args.interactive,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
