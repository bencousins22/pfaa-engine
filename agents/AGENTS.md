# PFAA Claude Code Agents

These agents are designed to be spawned from Claude Code using the Agent tool.
Each wraps a specific PFAA capability with full Python 3.15 support.

## Setup

```bash
# Clone the repo
git clone https://github.com/bencousins22/pfaa-engine.git
cd pfaa-engine

# Install deps
pip3 install typer rich

# Verify
python3 agents/pfaa_runner.py status
```

## Spawning Agents from Claude Code

Use the Agent tool with `subagent_type: "general-purpose"` and include
the runner path in the prompt:

```
Agent tool:
  prompt: "Run: python3 /path/to/pfaa-engine/agents/pfaa_runner.py goal 'analyze codebase and find security issues'"
  description: "PFAA codebase analysis"
  run_in_background: true
```

## Agent Catalog

| Agent | Runner Command | Phase | Purpose |
|-------|---------------|-------|---------|
| pfaa-analyst | `goal "analyze..."` | Mixed | Natural language goal execution |
| pfaa-searcher | `tool codebase_search <pattern>` | LIQUID | Code pattern search |
| pfaa-compute | `tool compute <expr>` | LIQUID | Math computation |
| pfaa-git | `parallel git_status git_log git_diff` | SOLID | Git operations |
| pfaa-system | `parallel system_info disk_usage` | VAPOR | System diagnostics |
| pfaa-pipeline | `pipeline step:tool:arg...` | Mixed | Supervised pipeline |
| pfaa-explorer | `explore 200` | Mixed | Train L3 strategies |
| pfaa-builder | `self-build` | Mixed | Self-improvement cycle |
