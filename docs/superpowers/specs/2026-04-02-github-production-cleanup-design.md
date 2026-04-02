# GitHub Production Cleanup — Design Spec

**Date:** 2026-04-02
**Goal:** Prepare pfaa-engine for public open-source release on GitHub.
**License:** Apache 2.0

## 1. File Cleanup & .gitignore

### Remove
- 32 screenshot files (`audit-*.png`, `verify-*.png`) — CORA audit artifacts, not PFAA
- `.playwright-mcp/` — browser session data
- Any `.DS_Store` files in the repo

### Add to .gitignore
```
*.png
!assets/*.png
!assets/**/*.png
.playwright-mcp/
*.db
.pfaa/
.claude/hooks/cortex_state.json
.claude/hooks/cortex_state.tmp
.claude/hooks/analyzers/__pycache__/
```

### Keep
- `freqtrade_strategy/` — self-optimizing BTC strategy, part of PFAA
- `railway.json` — FreqTrade deployment config
- `assets/logo.jpeg` — README logo

## 2. Path Sanitization

Replace all hardcoded `/Users/borris/Desktop/pfaa-engine` with dynamic resolution.

### Python hooks
Use `Path(__file__).resolve().parent.parent.parent` to walk from `.claude/hooks/` to project root.

**Files:**
- `.claude/hooks/cortex.py` — `PROJECT_ROOT` constant
- `.claude/hooks/jmem_store_episode.py` — `sys.path.insert` hardcoded path
- `.claude/hooks/jmem_recall.py` — same pattern
- `.claude/hooks/cortex_dashboard.py` — if applicable

### Node hooks
Use `path.resolve(__dirname, '..', '..')` for project root.

**Files:**
- `.claude/hooks/stop_scan.cjs` — `root` constant
- `.claude/hooks/banner.cjs` — if applicable
- `.claude/hooks/statusline.cjs` — if applicable

### JMEM
`~/.jmem/claude-code/memory.db` already uses `~` expansion — no change needed.

## 3. A0 Integration

### 3a. Commit CORA frontend fix
Commit the `LuminaChat.tsx` iframe URL resolution fix in the CORA repo at `/Users/borris/realestate/frontend/`.

### 3b. Add A0 module to pfaa-engine
Create `src/integrations/a0/`:
- `client.ts` — Agent Zero API client adapted for PFAA agent-to-agent communication
- `bridge.ts` — A0 bridge logic (plugin creation, A2A communication, memory sync)
- `index.ts` — Barrel export

## 4. LICENSE & Documentation

- Add `LICENSE` file — Apache 2.0 with copyright
- Verify `README.md` reflects current state (10 agents, 27 skills, JMEM 6-layer, FreqTrade)
- `.env.example` has placeholder patterns (`sk-ant-...`, `AIza...`) — safe to keep

## 5. Commit Strategy

Group changes into logical commits:

1. `fix(hooks): silence verbose hook output + raise tool failure threshold`
2. `feat(core): swarm protocol + task dependency system`
3. `feat(services): autoDream, toolOrchestration, cronScheduler, sessionMemory`
4. `chore: sanitize paths, cleanup artifacts, add LICENSE`
5. `feat(a0): Agent Zero integration module`

## Out of Scope

- Git history rewriting (no force pushes, no squash of existing history)
- CI/CD pipeline setup (future work)
- npm/pip package publishing (future work)
- CORA frontend changes beyond the LuminaChat.tsx fix
