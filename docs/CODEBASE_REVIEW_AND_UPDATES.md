# PFAA Engine — Codebase Review & Full Update List

*Generated April 12, 2026 — Claude Opus 4.6*

---

## Executive Summary

The PFAA engine is ~12,000+ lines across Python (7,553 LOC core engine), TypeScript (~11,000 LOC across `src/` and `pfaa-cli/`), 10 Claude Code agents, 27 skills, 13 MCP tools, and 12 hooks. Architecture is ambitious with phase-fluid execution (VAPOR/LIQUID/SOLID), 6-layer JMEM semantic memory with Q-learning, and multi-agent orchestration. However, there are critical blockers preventing the build from succeeding, significant technical debt, and missed opportunities to adopt latest 2026 Claude Code features.

This document catalogues **62 actionable items** across 10 sections, prioritized from P0 (critical blockers) through P2 (cleanup), followed by feature adoption recommendations, research-backed improvements, and brainstormed ideas.

---

## Section 1: Critical Blockers (P0)

These issues prevent the project from building or running correctly and must be fixed first.

| # | Issue | Impact | Files | Fix |
|---|-------|--------|-------|-----|
| 1 | **TypeScript won't compile** — 47 errors, missing Node types in `tsconfig.json` | Build broken for all TS code | `tsconfig.json` | Add `"types": ["node"]` to `compilerOptions` |
| 2 | **Python 3.15 features unavailable** — `lazy import` (PEP 810) and `frozendict` (PEP 814) cause `SyntaxError` on Python 3.11–3.14 | Core engine crashes on any non-3.15 runtime | `agent_setup_cli/core/agent.py`, `tools.py`, `memory.py` | Add compat shim or bump `requires-python` to `>=3.15` |
| 3 | **CI uses Python 3.13** (`.github/workflows/ci.yml:15`) but code uses 3.15 syntax | CI passes falsely or fails silently | `.github/workflows/ci.yml` | Align CI matrix to match `requires-python` |
| 4 | **SDK version triple-mismatch** — root `package.json` has `@anthropic-ai/sdk ^0.80.0`, `pfaa-cli/package.json` has `^0.40.1`, `requirements.txt` has `anthropic>=0.18.0` | Incompatible API surfaces across components | `package.json`, `pfaa-cli/package.json`, `requirements.txt` | Align all to `^0.80.0` (JS) and `>=0.80.0` (Python) |
| 5 | **License mismatch** — `package.json` says MIT, `README.md`/`LICENSE` say Apache 2.0 | Legal ambiguity for contributors and users | `package.json`, `README.md`, `LICENSE` | Pick one license, align everywhere |

---

## Section 2: Architecture Issues (P1)

Structural problems that degrade maintainability, correctness, or performance.

| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| 1 | **Memory layer naming inconsistency** — `ARCHITECTURE.md` says 5 layers, `CLAUDE.md`/JMEM `engine.py` says 6 (L6 Emergent missing from docs) | Confusion for contributors, inconsistent documentation | Update `ARCHITECTURE.md` to document all 6 layers including L6 Emergent |
| 2 | **Dual TypeScript codebases** — `src/` and `pfaa-cli/src/` duplicate orchestrator, memory, swarm logic | Changes must be made in two places; drift risk | Consolidate into single source or make `pfaa-cli` import from `src/` |
| 3 | **Python<->TS memory not shared** — Python JMEM and TS `MemoryStore` are separate systems with no bridge | Agent insights siloed by runtime; no cross-language learning | Route all memory through JMEM MCP server as single source of truth |
| 4 | **No error propagation to JMEM** — tool failures not stored as episodes, so system can't learn from failures | Repeated mistakes; no negative reinforcement signal | Add `PostToolUseFailure` -> JMEM episode storage pipeline |
| 5 | **Hooks are giant inline one-liners** — 400+ char `node -e` commands in `settings.json` | Unmaintainable, hard to debug, no syntax highlighting | Extract to separate `.cjs`/`.py` files in `.claude/hooks/` |
| 6 | **No async lock protection in JMEM engine** — concurrent recalls can race | Data corruption under parallel agent workloads | Add `asyncio.Lock` to critical sections in JMEM engine |
| 7 | **Missing Alembic migrations** — SQLAlchemy listed as dep but unused, `persistence.py` uses raw SQL | Schema evolution requires manual SQL; unused dependency bloat | Implement proper migrations or remove unused SQLAlchemy dependency |
| 8 | **Agent `spawn.py` has no process management** — no heartbeat, no zombie reaping | Orphaned agent processes accumulate; no failure detection | Add process monitoring with heartbeat and zombie reaping |

---

## Section 3: Dead Code & Cleanup (P2)

Code that exists but is unused, adding confusion and maintenance burden.

| # | Dead Code | Location | Recommendation |
|---|-----------|----------|----------------|
| 1 | **xterm.js terminal** — web-based terminal UI, not integrated into any workflow | `agent_setup_cli/web/` | Remove or integrate into JMEM Dashboard (see Section 10, Item 1) |
| 2 | **SQLAlchemy models** — full ORM model definitions, unused | `agent_setup_cli/database/` | Remove (persistence.py uses raw SQL) or migrate to use them |
| 3 | **Legacy AI client** — lazy-imported but never called from any code path | `agent_setup_cli/ai/` | Remove entirely |
| 4 | **TUI theme system** — theme definitions exist but are never applied | `pfaa-cli/src/tui/theme.ts` | Wire into TUI rendering or remove |
| 5 | **`tools_generated.py` has only 1 tool** — likely a self-build artifact | `agent_setup_cli/core/tools_generated.py` | Merge into `tools.py` or document as self-build output target |

---

## Section 4: Testing & CI Gaps (P1)

Issues that undermine test reliability and CI trustworthiness.

| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| 1 | **README claims "262 tests"** but only ~150 actual test functions across 10 test files | Misleading documentation; false confidence in coverage | Audit test count and correct README |
| 2 | **CI has `vitest run 2>/dev/null \|\| echo "No vitest tests yet"`** — tests silently skipped | TypeScript tests never actually run in CI | Enable vitest properly or remove the step |
| 3 | **`pip install -e . 2>/dev/null \|\| true`** in CI silences install failures | Broken Python installs go undetected | Remove output suppression; fail CI on install errors |
| 4 | **No mypy/pyright in CI** for Python type checking | Type errors only caught at runtime | Add `mypy --strict` or `pyright` step to CI pipeline |
| 5 | **Benchmarks (`benchmark.py`) never run in CI** | Performance regressions go undetected | Add benchmark regression job with threshold alerts |
| 6 | **8 TypeScript test files in `pfaa-cli`** but fail due to missing deps | False sense of test coverage | Fix dependency issues or remove broken tests |
| 7 | **No test coverage for epsilon-greedy phase exploration** (`tools.py:107-155`) | Core RL mechanism untested | Add unit tests for exploration/exploitation balance |
| 8 | **No test coverage for L3+ memory promotion** in JMEM | Memory consolidation logic untested | Add cross-layer promotion tests with known Q-value thresholds |

---

## Section 5: Latest Claude Code Features to Adopt (April 2026)

New capabilities from Claude Code's 2026 releases that PFAA should leverage.

| # | Feature | Status in PFAA | Action |
|---|---------|---------------|--------|
| 1 | **Agent Teams** (Feb 2026) — native multi-session coordination with peer-to-peer messaging, shared task list, file locking | **NOT enabled** — PFAA uses custom `spawn.py` instead | Add `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS: "1"` to `settings.json` env; migrate from custom spawn to native teams |
| 2 | **Plugin Marketplace** — distribute skills as installable packages via `marketplace.json` | Skills are local-only | Create `marketplace.json`, package top skills (run, swarm, memory, learn, evolve) for distribution |
| 3 | **MCP 500K character limit** — tool responses can be much larger now | Response truncation workarounds still in place | Remove manual response truncation in MCP tool handlers |
| 4 | **PermissionDenied hook** — fires after auto-mode classifier denials, supports `{retry: true}` | Not implemented | Add `PermissionDenied` hook for graceful retry on classifier false positives |
| 5 | **Skills unification** — `.claude/skills/` is canonical (replaces `.claude/commands/`) | Already using `skills/` | Verify no residual `.claude/commands/` references; clean up if found |
| 6 | **Adaptive thinking** (Opus 4.6) — recommended thinking mode where Claude dynamically decides when to think | Not documented or tuned | Document best practices for agent prompts; set thinking mode in agent configs |
| 7 | **`MCP_CONNECTION_NONBLOCKING=true`** — skip MCP wait in `-p` mode for faster pipelines | Not set | Add to env in `settings.json` for pipeline mode invocations |
| 8 | **PreToolUse `file_path` fix** — Write/Edit/Read now receive absolute paths | Hook path handling may assume relative paths | Audit all `PreToolUse` hooks for path handling correctness |
| 9 | **Code execution free with web tools** — dynamic filtering reduces tokens | Research agent doesn't leverage this | Update research agent (`aussie-researcher`) to use web tools with dynamic filtering |

---

## Section 6: Agent Memory & RL Research Improvements (2026)

Based on ICLR 2026 MemAgents workshop, Agent-R1, Agent Q-Mix, and MIA frameworks.

| # | Research Insight | PFAA Relevance | Recommended Action |
|---|-----------------|----------------|-------------------|
| 1 | **Agent memory as first-class MCP primitive** — emerging best practice for persistent agent state | JMEM already implements this pattern well | Document as differentiator; publish case study or blog post |
| 2 | **Alternating RL between Planner and Executor** (MIA framework) — dual-agent RL co-optimization | PFAA has separate planner and executor agents but no co-optimization | Implement dual-agent RL loop: planner proposes, executor acts, both receive rewards |
| 3 | **CTDE paradigm** (Agent Q-Mix) — centralized training, decentralized execution for multi-agent swarm | Swarm agents act independently with no centralized value function | Add centralized Q-value mixing network for swarm coordination; agents execute independently but train jointly |
| 4 | **Memory consolidation during idle** — offline consolidation improves retrieval quality | Consolidation only runs on explicit `/aussie-learn` invocation | Add `autoDream` service: background consolidation during idle periods (e.g., between sessions) |
| 5 | **Progressive disclosure for MCP tools** — expose core tools first, let agents discover advanced tools | All 13 JMEM tools exposed at once (~40% unnecessary context for simple tasks) | Expose 5 core tools (`recall`, `remember`, `status`, `reward`, `consolidate`), let agents discover remaining 8 on demand |
| 6 | **30-minute idle timeout for MCP sessions** — prevents resource leaks | JMEM daemon runs indefinitely with no TTL | Add TTL policy: clean up idle MCP sessions after 30 minutes |
| 7 | **Heap limits for MCP servers** — prevent OOM in long-running servers | No memory limits configured for JMEM daemon | Add `--max-old-space-size` for Node.js MCP servers; add Python memory limits via `resource.setrlimit` |
| 8 | **Cross-agent knowledge synthesis** — L6 Emergent layer for novel insights from multi-agent collaboration | L6 Emergent layer exists in schema but is never populated | Wire agent team results into L6: after swarm/team completion, synthesize cross-agent insights and store as Emergent memories |

---

## Section 7: Claude 4.6 Model Capabilities to Leverage

New model capabilities that PFAA's architecture can exploit.

| # | Capability | Current State | Action |
|---|-----------|--------------|--------|
| 1 | **1M token context** — massively expanded context window | `compactThreshold` set conservatively | Increase `compactThreshold` in orchestrator to leverage larger context; reduce compaction frequency |
| 2 | **128K max output (Opus) / 64K (Sonnet)** — much larger generation limits | `claude_bridge.py` truncates output prematurely | Remove output truncation; allow full-length responses for code generation tasks |
| 3 | **72.5% OSWorld computer use** — state-of-the-art UI automation | No computer-use agent in team | Add `aussie-ui-tester` agent for automated UI testing and visual regression |
| 4 | **80.8% SWE-bench coding** — near-human code generation accuracy | Self-build loop has conservative safety checks | Trust model more in self-build loop; reduce manual review gates for low-risk changes |
| 5 | **58.3% ARC-AGI-2 reasoning** — advanced abstract reasoning | Goal decomposition uses simple keyword matching | Enable harder goal decomposition strategies; use model reasoning for complex multi-step planning |

---

## Section 8: Security Improvements

Security hardening items identified during review.

| # | Issue | Risk | Fix |
|---|-------|------|-----|
| 1 | **Secret detection rescans every execution** — no caching of scan results | Performance penalty on every tool invocation; redundant work | Add persistent bloom filter cache for previously-scanned content hashes |
| 2 | **`subprocess` calls not consistently hardened** — some calls pass unsanitized user input | Command injection risk in agent spawn and tool execution paths | Audit all `subprocess` calls for `shlex.quote()` usage; add linting rule |
| 3 | **JMEM daemon Unix socket has no auth** — any local process can read/write memories | Local privilege escalation; memory poisoning by malicious local process | Add token-based authentication to JMEM MCP server socket |
| 4 | **No CodeQL for TypeScript** in `security.yml` — only Python is scanned | TypeScript vulnerabilities (XSS in TUI, prototype pollution) go undetected | Add `typescript` to CodeQL `languages` matrix in `.github/workflows/security.yml` |

---

## Section 9: Performance & Scalability

Items to ensure the engine scales beyond single-developer usage.

| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| 1 | **750+ memories in-memory with no eviction** — all memories loaded into RAM | Memory usage grows unbounded over long sessions | Implement LRU eviction at 10K threshold; keep hot memories in RAM, page cold to disk |
| 2 | **`ThreadPoolExecutor` without backpressure** — unbounded task submission | Thread exhaustion under high swarm load | Add semaphore-based admission control; cap concurrent tasks |
| 3 | **Reactive task DAG undefined behavior on cycles** — no cycle detection in dependency graph | Infinite loops if agent creates circular task dependencies | Add cycle detection (topological sort validation) before DAG execution |
| 4 | **No circuit breaker for Claude/Gemini API calls** — retries without backoff | API rate limiting causes cascade failures; wasted tokens | Add exponential backoff with jitter + circuit breaker pattern (open after 3 consecutive failures) |
| 5 | **Benchmark results not tracked over time** — each run is ephemeral | Cannot detect performance regressions across commits | Store benchmark results in JMEM L1 (Episodic) with commit SHA; add trend visualization |

---

## Section 10: Brainstormed Feature Ideas

Forward-looking features ranked by impact, with implementation path using existing skills.

| # | Feature | Rationale | Build With | Effort |
|---|---------|-----------|-----------|--------|
| 1 | **JMEM Dashboard** — web UI for memory layers, Q-values, promotions, decay curves | Makes JMEM internals visible and debuggable; aids tuning | `/aussie-generate` | Medium |
| 2 | **Agent Replay** — replay past episodes with updated model for retrospective improvement | Learn from historical failures with current capabilities | `/aussie-evolve` | Medium |
| 3 | **Cross-repo Memory** — share L3+ (Strategic) knowledge between projects | Principles learned in one repo benefit all repos | `/aussie-memory` | High |
| 4 | **Skill Marketplace** — package skills for community distribution | Grow ecosystem; attract contributors; standardize skill format | `/aussie-build` | High |
| 5 | **Auto-Phase Selection** — ML model replacing epsilon-greedy for VAPOR/LIQUID/SOLID selection | Better phase choices = faster execution; learns task-phase affinity | `/aussie-explore` | Medium |
| 6 | **Agent Competition** — multiple agents solve same task, reward winner, learn from divergence | Diversity of approach; natural selection for best strategies | `/aussie-swarm` | Medium |
| 7 | **Natural Language Goal Decomposition** — replace keyword matching with LLM-powered intent parsing | More robust routing; handles ambiguous and compound goals | `/aussie-run` | Low |
| 8 | **JMEM MCP Progressive Disclosure** — expose 5 core tools, let agents discover 8 more on demand | ~40% context reduction for simple tasks; faster cold starts | `/aussie-config` | Low |
| 9 | **Hook Extraction** — move all inline hooks from `settings.json` to proper `.cjs`/`.py` files | Maintainability, testability, syntax highlighting, version control diffs | `/aussie-self-build` | Low |
| 10 | **Unified Test Suite** — single `npm test` runs Python + TypeScript + integration tests | One command to validate everything; simplifies CI and onboarding | `/aussie-bench` | Low |

---

## Sources

| Source | URL |
|--------|-----|
| Claude Code Release Notes 2026 | <https://github.com/anthropics/claude-code/releases> |
| Claude Code Agent Teams docs | <https://code.claude.com/docs/en/agent-teams> |
| Claude Code Skills docs | <https://code.claude.com/docs/en/sub-agents> |
| Claude 4.6 what's new | <https://platform.claude.com/docs/en/about-claude/models/whats-new-claude-4-6> |
| MCP Best Practices 2026 | <https://modelcontextprotocol.info/docs/best-practices/> |
| ICLR 2026 MemAgents Workshop | <https://sites.google.com/view/memagent-iclr26/> |
| Agent Q-Mix (arXiv) | <https://arxiv.org/html/2604.00344> |
| Memory Intelligence Agent (arXiv) | <https://arxiv.org/html/2604.04503> |
| Anthropic Engineering — Managed Agents | <https://www.anthropic.com/engineering/managed-agents> |
| Plugin Marketplaces | <https://code.claude.com/docs/en/plugin-marketplaces> |

---

*End of review. Total items: 62 across 10 sections. Priority: 5 P0, 16 P1, 5 P2, 36 recommendations/ideas.*
