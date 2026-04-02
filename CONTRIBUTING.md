# Contributing to PFAA

Thanks for your interest in contributing to the Phase-Fluid Agent Architecture.

## Getting Started

```bash
git clone https://github.com/bencousins22/pfaa-engine.git
cd pfaa-engine
npm install && pip install -e .
python3 -m pytest tests/ -v  # 262 tests should pass
```

## Development

- **Python 3.15** required (3.15.0a7+)
- **Node.js 22+** for TypeScript modules
- Tests: `python3 -m pytest tests/ -v`
- Type check: `npx tsc --noEmit`
- Lint: `ruff check agent_setup_cli/ jmem-mcp-server/jmem/`

## Pull Requests

1. Fork the repo and create a feature branch
2. Write tests for new functionality
3. Ensure all 262+ tests pass
4. Follow existing code patterns
5. Keep PRs focused — one feature per PR

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the technical deep-dive. Key areas:

- `agent_setup_cli/core/` — Python engine (phase-fluid execution)
- `jmem-mcp-server/jmem/` — JMEM semantic memory
- `src/` — TypeScript core (orchestrator, services, providers)
- `.claude/` — Claude Code agents, skills, hooks

## Code Style

- Python: ruff (config in pyproject.toml)
- TypeScript: strict mode, ESM, `.js` extensions in imports
- Commit messages: conventional commits (`feat:`, `fix:`, `chore:`, `docs:`)

## License

By contributing, you agree that your contributions will be licensed under the Apache 2.0 License.
