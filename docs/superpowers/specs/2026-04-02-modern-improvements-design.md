# Modern Improvements — Design Spec

**Date:** 2026-04-02
**Goal:** Modernize pfaa-engine across 5 sub-projects: performance, CI/CD, TypeScript, Python, and new capabilities.
**Execution:** Sequential — each sub-project gets its own plan and implementation cycle.

---

## Sub-project 1: Performance — JMEM Daemon

### Problem
Every hook that touches JMEM spawns a fresh Python process (3-8s startup: Python import chain + SQLite + TF-IDF vectorizer rebuild). Three Stop hooks fire after every response, causing visible UI lag.

### Solution: Long-running Unix socket daemon

**Architecture:**
- Python daemon started at `SessionStart`, listens on `/tmp/pfaa-jmem-<pid>.sock`
- JMEM engine stays warm in memory — TF-IDF vectors, SQLite connection, vocab cache pre-loaded once
- Hooks send lightweight JSON requests over the socket via a shared Node.js helper (`jmem-client.cjs`, ~20 lines)
- Response time: 3-8s → <10ms

**Daemon API:**
- `recall(query, limit, min_q)` → memories
- `remember(content, level, tags)` → id
- `status()` → memory count, avg Q, health
- `consolidate()` → trigger consolidation
- `reward_recalled(signal)` → update Q-values

**Lifecycle:**
- `SessionStart` hook spawns as detached background process
- PID file at `/tmp/pfaa-jmem.pid` for health checks
- Graceful shutdown on SIGTERM or 30min socket idle timeout
- If daemon is down, hooks silently skip (no crash, no lag)

**Background offload for Stop hooks:**
- Stop hooks fire as detached background processes (`spawn` with `detached: true, stdio: 'ignore'`)
- Talk to the daemon, write results to `.pfaa/last-stop.json`
- UI never blocks

### Files
- Create: `jmem-mcp-server/jmem/daemon.py` — daemon server
- Create: `.claude/hooks/jmem-client.cjs` — shared Node.js socket client
- Modify: `.claude/hooks/cortex.py` — use socket client instead of direct engine
- Modify: `.claude/hooks/jmem_store_episode.py` — use socket client
- Modify: `.claude/hooks/jmem_recall.py` — use socket client
- Modify: `.claude/hooks/banner.cjs` — use jmem-client for stats
- Modify: `.claude/hooks/statusline.cjs` — use jmem-client for stats
- Modify: `SessionStart` hook in settings.json — start daemon

---

## Sub-project 2: CI/CD — Enterprise GitHub Actions

### Workflows

**`ci.yml`** — every push/PR:
- Python: `pytest tests/ -q`
- TypeScript: `bun typecheck` + `bun test`
- Lint: `ruff check` (Python) + `biome` (TS/JS)
- Coverage: upload to Codecov, badge in README

**`security.yml`** — push to main + weekly:
- CodeQL analysis (Python + TypeScript)
- `pip-audit` for Python deps
- Secret scanning

**`release.yml`** — on git tag `v*`:
- Build Python wheel + TS dist
- GitHub Release with changelog
- Optional PyPI/npm publish (manual approval gate)

**`dependabot.yml`** — weekly PRs:
- Python deps (pip)
- Node deps (npm)
- GitHub Actions versions

**FreqTrade deploy preview** — PRs touching `freqtrade_strategy/`:
- Dry-run backtest with last 30 days of data
- Post results as PR comment

### Files
- Create: `.github/workflows/ci.yml`
- Create: `.github/workflows/security.yml`
- Create: `.github/workflows/release.yml`
- Create: `.github/dependabot.yml`
- Create: `biome.json` — TS/JS linter config
- Modify: `README.md` — add CI/coverage badges

---

## Sub-project 3: TypeScript Modernization — Bun + ES2024

### Runtime swap
- Replace Node.js with Bun for TS execution
- `tsconfig.json` target → `ES2024`
- Delete build step — Bun runs `.ts` directly
- `package.json` scripts use `bun run`, `bun test`

### Testing
- Add `bun:test` for all TS modules
- Priority: `swarm.ts`, `tasks.ts`, `toolOrchestration.ts`, `cronScheduler.ts`, A0 client
- Coverage target: match Python side

### ES2024 features to adopt
- `Object.groupBy()` for tool categorization
- `Promise.withResolvers()` for async patterns in swarm/daemon
- `Iterator.prototype.map/filter` for streaming tool results
- `using` declarations for resource cleanup (sockets, DB connections)

### CLI migration
- `pfaa-cli/` switches from `npx tsx` to `bun run`
- TUI components (Ink-based) verified with Bun's React JSX support

### Files
- Modify: `tsconfig.json` — ES2024 target
- Modify: `package.json` — bun scripts, remove tsx dep
- Create: `tests/ts/` — Bun test files for each module
- Modify: `pfaa-cli/package.json` — bun migration
- Modify: all `src/**/*.ts` — adopt ES2024 features where applicable

---

## Sub-project 4: Python 3.15 Modernization

### pyproject.toml
- `requires-python = ">=3.15"`
- Add `[tool.ruff]` with Python 3.15 target
- Ruff replaces any flake8/black config

### Language features across codebase
- PEP 810: `lazy import` for heavy modules (numpy, torch, sentence-transformers, anthropic) in `agent_setup_cli/core/`
- PEP 814: `frozendict` for agent configs, tool registries, event payloads
- PEP 695: `def func[T]()` type parameter syntax replacing `TypeVar`
- PEP 634: `match/case` replacing if/elif chains

### Package structure
- Proper `src/` layout with `__init__.py` files
- `py.typed` marker for PEP 561 compliance
- Entry point via `pyproject.toml` `[project.scripts]`

### Type checking
- Add `pyright` or `mypy` strict mode
- CI enforces zero type errors

### Files
- Modify: `pyproject.toml` — Python 3.15, ruff config
- Modify: `agent_setup_cli/core/*.py` — PEP 810/814/695 features
- Modify: `jmem-mcp-server/jmem/*.py` — same
- Modify: `.claude/hooks/cortex.py` — already uses match/case, add remaining
- Create: `py.typed` marker
- Modify: `tests/conftest.py` — shared fixtures

---

## Sub-project 5: New Capabilities

### 5a. MagicDocs
- Files marked with `# MAGIC DOC: [title]` auto-update when related code changes
- `FileChanged` hook detects source changes, scans for magic docs that reference the changed file, queues update via JMEM daemon
- Reuses existing cortex `FileChanged` handler

### 5b. Remote Sessions
- WebSocket server extending the JMEM daemon (Sub-project 1)
- Agents execute on remote machines via SSH tunnel or direct WebSocket
- Protocol: JSON-RPC over WebSocket, same message format as MCP
- Use case: run PFAA agents on a cloud VM, control from local CLI

### 5c. Voice Mode
- Push-to-talk via SoX (`rec` command) for audio capture
- Stream to Whisper API or local whisper.cpp for STT
- Inject transcribed text as prompt — no new UI, pipes into existing input
- Toggle with `/voice` command or keybinding

### 5d. IDE Integration
- VS Code extension connecting to PFAA daemon via WebSocket
- Inline agent suggestions in editor
- Status bar showing `◆ Aussie · 48t · JMEM 6L` in VS Code
- Shares the daemon process — no separate server

### 5e. Session Resume
- Save full conversation state to `.pfaa/sessions/<id>.json` on Stop
- `/resume` command lists recent sessions, restores messages + context
- Survives terminal crashes and compaction

### Files
- Create: `src/services/magicDocs.ts`
- Create: `src/services/remoteSession.ts`
- Create: `src/services/voice.ts`
- Create: `src/services/sessionResume.ts`
- Create: `vscode-extension/` — VS Code extension scaffolding
- Create: `.claude/skills/aussie-voice/SKILL.md`
- Create: `.claude/skills/aussie-resume/SKILL.md`

---

## Execution Order

1. **Performance (JMEM daemon)** — immediate daily impact
2. **CI/CD (GitHub Actions)** — quality gates before more code lands
3. **TypeScript (Bun + ES2024)** — foundation for new TS work
4. **Python 3.15** — modernize the engine
5. **New capabilities** — MagicDocs → Session Resume → Remote Sessions → Voice → IDE

Each sub-project gets its own implementation plan via `writing-plans`.

## Out of Scope
- Rewriting existing working code that doesn't need modernization
- Mobile app
- Cloud-hosted SaaS version
- Breaking changes to the JMEM MCP protocol
