# GitHub Production Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare pfaa-engine for public open-source release — remove artifacts, fix hardcoded paths, add LICENSE, commit all pending work in logical groups.

**Architecture:** Five sequential commits that transform the repo from personal dev state to clean public open-source. Each task produces one commit. No code logic changes — only cleanup, path fixes, and file organization.

**Tech Stack:** Git, Python 3.15, Node.js, TypeScript

---

### Task 1: Commit pending hook fixes + test updates

Already-modified files from this session that are logically grouped.

**Files:**
- Modified: `.claude/hooks/cortex.py`
- Modified: `.claude/hooks/jmem_store_episode.py`
- Modified: `.claude/hooks/stop_scan.cjs`
- Modified: `tests/test_cortex.py`

- [ ] **Step 1: Stage the hook and test files**

```bash
git add .claude/hooks/cortex.py .claude/hooks/jmem_store_episode.py .claude/hooks/stop_scan.cjs tests/test_cortex.py
```

- [ ] **Step 2: Verify tests pass**

```bash
python3 -m pytest tests/test_cortex.py -v --tb=short
```

Expected: 103 passed, 0 failed

- [ ] **Step 3: Commit**

```bash
git commit -m "fix(hooks): silence verbose hook output + raise tool failure threshold

- Cortex Stop handler no longer dumps perf timings to UI
- Dream Phase A completes silently
- JMEM episode store runs silently
- stop_scan.cjs suppresses output
- Tool failure block threshold raised from 5 to 50
- Updated 3 tests to match new silent behavior
- Added 21 new tests (keyword extraction, dedup, phase detection, pressure, interest scoring)
- Total: 103 tests passing

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Commit new core modules (swarm + tasks)

**Files:**
- New: `src/core/swarm.ts`
- New: `src/core/tasks.ts`
- Modified: `src/core/orchestrator.ts`
- Modified: `src/core/types.ts`

- [ ] **Step 1: Verify TypeScript compiles**

```bash
npx tsc --noEmit 2>&1 | grep -E "src/core/(swarm|tasks)" | head -10
```

Expected: No output (no errors in these files)

- [ ] **Step 2: Stage and commit**

```bash
git add src/core/swarm.ts src/core/tasks.ts src/core/orchestrator.ts src/core/types.ts
git commit -m "feat(core): swarm protocol + task dependency system

- SwarmMailbox: file-based message queue with typed messages
- SwarmTeam: team membership with persistence in .pfaa/teams/
- SwarmCoordinator: dispatch goals, collect results, shutdown protocol
- TaskManager: dependency chains (blocks/blockedBy), auto-unblock, event hooks
- Inspired by Claude Code TeamCreateTool/SendMessageTool patterns

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Commit new services

**Files:**
- New: `src/services/autoDream.ts`
- New: `src/services/toolOrchestration.ts`
- New: `src/services/cronScheduler.ts`
- New: `src/services/sessionMemory.ts`
- New: `src/services/index.ts`
- Modified: `src/memory/store.ts`
- Modified: `src/tools/memory.ts`

- [ ] **Step 1: Verify TypeScript compiles**

```bash
npx tsc --noEmit 2>&1 | grep -E "src/services/" | head -10
```

Expected: No output (no errors)

- [ ] **Step 2: Stage and commit**

```bash
git add src/services/ src/memory/store.ts src/tools/memory.ts
git commit -m "feat(services): autoDream, toolOrchestration, cronScheduler, sessionMemory

- AutoDream: time+session gated JMEM consolidation with PID lock
- ToolOrchestration: parallel/serial execution with read-only categorization
- CronScheduler: 5-field cron with durable persistence, auto-expiry
- SessionMemory: pattern-based memory extraction from conversations
- Inspired by Claude Code services architecture (512K lines analyzed)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Sanitize paths in Python hooks

**Files:**
- Modify: `.claude/hooks/cortex.py:24-28`
- Modify: `.claude/hooks/cortex_dashboard.py:8`
- Modify: `.claude/hooks/jmem_store_episode.py:9`
- Modify: `.claude/hooks/jmem_recall.py:8`

- [ ] **Step 1: Fix cortex.py**

Replace:
```python
PROJECT_ROOT = Path(
    os.environ.get("CLAUDE_PROJECT_DIR")
    or os.environ.get("PWD")
    or "/Users/borris/Desktop/pfaa-engine"
)
```

With:
```python
PROJECT_ROOT = Path(
    os.environ.get("CLAUDE_PROJECT_DIR")
    or os.environ.get("PWD")
    or str(Path(__file__).resolve().parent.parent.parent)
)
```

- [ ] **Step 2: Fix cortex_dashboard.py**

Replace:
```python
PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("PWD", "/Users/borris/Desktop/pfaa-engine")))
```

With:
```python
PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("PWD", str(Path(__file__).resolve().parent.parent.parent))))
```

- [ ] **Step 3: Fix jmem_store_episode.py**

Replace:
```python
sys.path.insert(0, "/Users/borris/Desktop/pfaa-engine/jmem-mcp-server")
```

With:
```python
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "jmem-mcp-server"))
```

Note: `from pathlib import Path` is already imported in cortex.py but needs adding to jmem_store_episode.py.

- [ ] **Step 4: Fix jmem_recall.py**

Replace:
```python
sys.path.insert(0, "/Users/borris/Desktop/pfaa-engine/jmem-mcp-server")
```

With:
```python
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "jmem-mcp-server"))
```

- [ ] **Step 5: Verify cortex tests still pass**

```bash
python3 -m pytest tests/test_cortex.py -v --tb=short
```

Expected: 103 passed

---

### Task 5: Sanitize paths in Node hooks

**Files:**
- Modify: `.claude/hooks/stop_scan.cjs:18`

- [ ] **Step 1: Fix stop_scan.cjs**

Replace:
```javascript
const root = '/Users/borris/Desktop/pfaa-engine';
```

With:
```javascript
const root = path.resolve(__dirname, '..', '..');
```

Note: `path` is already required at the top of the file.

- [ ] **Step 2: Verify banner.cjs and statusline.cjs**

These files do NOT have hardcoded paths (confirmed by grep). No changes needed.

---

### Task 6: Sanitize paths in settings.json

**Files:**
- Modify: `.claude/settings.json` (16 hardcoded paths)

- [ ] **Step 1: Replace all absolute hook command paths with relative paths**

Claude Code runs hook commands from the project root, so relative paths work.

Replace all instances of:
- `"python3 /Users/borris/Desktop/pfaa-engine/.claude/hooks/cortex.py` → `"python3 .claude/hooks/cortex.py`
- `"python3 /Users/borris/Desktop/pfaa-engine/.claude/hooks/jmem_store_episode.py"` → `"python3 .claude/hooks/jmem_store_episode.py"`
- `"python3 /Users/borris/Desktop/pfaa-engine/.claude/hooks/jmem_recall.py"` → `"python3 .claude/hooks/jmem_recall.py"`
- `"node /Users/borris/Desktop/pfaa-engine/.claude/hooks/banner.cjs"` → `"node .claude/hooks/banner.cjs"`
- `"node /Users/borris/Desktop/pfaa-engine/.claude/hooks/stop_scan.cjs"` → `"node .claude/hooks/stop_scan.cjs"`
- `"node /Users/borris/Desktop/pfaa-engine/.claude/hooks/statusline.cjs"` → `"node .claude/hooks/statusline.cjs"`
- `"cwd": "/Users/borris/Desktop/pfaa-engine"` → remove or set to `"."`

Also replace any inline `cd /Users/borris/Desktop/pfaa-engine` in PostToolUse hook commands with `cd .` or remove the cd (hooks already run from project root).

- [ ] **Step 2: Fix aussie-search skill**

File: `.claude/skills/aussie-search/SKILL.md`

Replace all 5 instances of `/Users/borris/Desktop/pfaa-engine/` with relative paths (just remove the prefix, use paths relative to project root like `agent_setup_cli/core/`, `src/`, `pfaa-cli/src/`, `.claude/settings.json`).

---

### Task 7: Remove artifacts and update .gitignore

**Files:**
- Delete: 32 `audit-*.png` and `verify-*.png` files
- Delete: `.playwright-mcp/` directory
- Modify: `.gitignore`

- [ ] **Step 1: Delete screenshot files**

```bash
rm -f audit-*.png verify-*.png
```

- [ ] **Step 2: Delete Playwright session data**

```bash
rm -rf .playwright-mcp/
```

- [ ] **Step 3: Update .gitignore**

Append to existing `.gitignore`:
```
# Screenshots (keep assets/ only)
*.png
!assets/*.png
!assets/**/*.png

# Playwright session data
.playwright-mcp/

# PFAA runtime state
.pfaa/

# Cortex state (regenerated per session)
.claude/hooks/cortex_state.json
.claude/hooks/cortex_state.tmp
.claude/hooks/analyzers/__pycache__/
```

Note: `*.db`, `.DS_Store`, and `node_modules/` are already covered.

---

### Task 8: Add LICENSE file

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Create Apache 2.0 LICENSE**

```
                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   ...standard Apache 2.0 text...

   Copyright 2026 Jamie (bencousins22)

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
```

Use the full standard Apache 2.0 license text.

---

### Task 9: Update README badges

**Files:**
- Modify: `README.md:24` (badges line)

- [ ] **Step 1: Update stale badges**

Change:
- `tests-77%2F77_(100%25)` → `tests-103%2F103_(100%25)` (103 cortex tests now)
- `memory-5_layer_meta--learning` → `memory-6_layer_JMEM` (JMEM has 6 layers: L1-L6)
- `tools-27` → `tools-44` (44 tools per banner)

- [ ] **Step 2: Add license badge**

Add after the existing badges:
```html
<img src="https://img.shields.io/badge/license-Apache_2.0-blue?style=flat-square" alt="Apache 2.0" />
```

---

### Task 10: Commit cleanup + LICENSE + README

**Files:**
- All changes from Tasks 4-9

- [ ] **Step 1: Stage all cleanup changes**

```bash
git add .gitignore LICENSE README.md \
  .claude/hooks/cortex.py .claude/hooks/cortex_dashboard.py \
  .claude/hooks/jmem_store_episode.py .claude/hooks/jmem_recall.py \
  .claude/hooks/stop_scan.cjs .claude/settings.json \
  .claude/skills/aussie-search/SKILL.md
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: sanitize paths, cleanup artifacts, add Apache 2.0 LICENSE

- Replace 16+ hardcoded /Users/borris paths with dynamic resolution
- Python hooks use Path(__file__).resolve() for project root
- Node hooks use path.resolve(__dirname) for project root
- settings.json hooks use relative paths (CWD is project root)
- Remove 32 CORA audit screenshots and .playwright-mcp session data
- Update .gitignore for screenshots, Playwright, PFAA runtime state
- Add Apache 2.0 LICENSE
- Update README badges (103 tests, 6-layer JMEM, 44 tools)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 11: Commit remaining modified files (CLI + TUI)

**Files:**
- Modified: `pfaa-cli/package.json`
- Modified: `pfaa-cli/package-lock.json`
- Modified: `pfaa-cli/src/cli.ts`
- Modified: `pfaa-cli/tsconfig.json`
- Modified: `package.json`
- Modified: `package-lock.json`
- New: `pfaa-cli/src/tui/` (if any files exist)

- [ ] **Step 1: Check what's in the TUI directory**

```bash
ls -la pfaa-cli/src/tui/
```

- [ ] **Step 2: Stage and commit**

```bash
git add pfaa-cli/ package.json package-lock.json
git commit -m "feat(cli): enterprise CLI updates + TUI components

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 12: Create A0 integration module

**Files:**
- Create: `src/integrations/a0/client.ts`
- Create: `src/integrations/a0/bridge.ts`
- Create: `src/integrations/a0/index.ts`

- [ ] **Step 1: Create directory**

```bash
mkdir -p src/integrations/a0
```

- [ ] **Step 2: Create `src/integrations/a0/client.ts`**

Agent Zero API client for PFAA agent-to-agent communication:

```typescript
/**
 * Agent Zero API Client for PFAA — agent-to-agent communication.
 *
 * Lightweight client for A0's external API (v0.9.8+).
 * Used by PFAA agents to delegate tasks to Agent Zero and retrieve results.
 */

export interface A0MessageOptions {
  contextId?: string
  lifetimeHours?: number
  attachments?: Array<{ filename: string; base64: string }>
}

export interface A0Response {
  context_id: string
  response?: string
  message?: string
}

export interface A0LogItem {
  no: number
  type: string
  heading: string
  content: string
  timestamp: number
}

export class AgentZeroClient {
  private baseUrl: string
  private apiKey: string
  private timeout: number

  constructor(baseUrl: string, apiKey: string, timeout = 180_000) {
    this.baseUrl = baseUrl.replace(/\/$/, '')
    this.apiKey = apiKey
    this.timeout = timeout
  }

  private async request<T = unknown>(
    method: string,
    path: string,
    body?: object,
  ): Promise<T> {
    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.timeout)
    try {
      const res = await fetch(`${this.baseUrl}${path}`, {
        method,
        headers: {
          'X-API-KEY': this.apiKey,
          'Content-Type': 'application/json',
        },
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })
      if (!res.ok) throw new Error(`A0 API ${res.status}: ${await res.text()}`)
      return res.json() as Promise<T>
    } finally {
      clearTimeout(timer)
    }
  }

  async health(): Promise<{ status: string }> {
    return this.request('GET', '/health')
  }

  async message(text: string, opts: A0MessageOptions = {}): Promise<A0Response> {
    return this.request('POST', '/api_message', {
      message: text,
      lifetime_hours: opts.lifetimeHours ?? 24,
      ...(opts.contextId && { context_id: opts.contextId }),
      ...(opts.attachments && { attachments: opts.attachments }),
    })
  }

  async getLogs(
    contextId: string,
    length = 100,
  ): Promise<{ log: { items: A0LogItem[]; progress_active: boolean } }> {
    return this.request('POST', '/api_log_get', {
      context_id: contextId,
      length,
    })
  }

  async resetContext(contextId: string): Promise<void> {
    await this.request('POST', '/api_reset_chat', { context_id: contextId })
  }

  async messageAndWait(
    text: string,
    contextId?: string,
    pollMs = 2000,
    timeoutMs = 300_000,
  ): Promise<string> {
    const result = await this.message(text, { contextId })
    const cid = result.context_id
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      const logs = await this.getLogs(cid, 1)
      if (!logs.log.progress_active) {
        const full = await this.getLogs(cid, 50)
        const responses = full.log.items.filter((i) => i.type === 'response')
        return responses[responses.length - 1]?.content ?? ''
      }
      await new Promise((r) => setTimeout(r, pollMs))
    }
    throw new Error(`A0 timeout after ${timeoutMs}ms`)
  }
}
```

- [ ] **Step 3: Create `src/integrations/a0/bridge.ts`**

A0 bridge for plugin creation, A2A communication, and memory sync:

```typescript
/**
 * A0 Bridge — connects PFAA agents with Agent Zero v1.5+.
 *
 * Capabilities:
 * - Create A0 plugins from PFAA skills
 * - Bidirectional A2A communication
 * - Memory sync between JMEM and A0's vector memory
 */

import { AgentZeroClient, type A0Response } from './client'

export interface A0BridgeConfig {
  a0Url: string
  a0ApiKey: string
  timeout?: number
}

export interface PluginManifest {
  name: string
  title: string
  description: string
  version: string
}

export interface A2AMessage {
  from: string
  to: string
  type: 'task' | 'result' | 'memory_sync' | 'status'
  content: string
  metadata?: Record<string, unknown>
}

export class A0Bridge {
  private client: AgentZeroClient

  constructor(config: A0BridgeConfig) {
    this.client = new AgentZeroClient(
      config.a0Url,
      config.a0ApiKey,
      config.timeout,
    )
  }

  async isAvailable(): Promise<boolean> {
    try {
      await this.client.health()
      return true
    } catch {
      return false
    }
  }

  /** Send a task to Agent Zero and wait for the response. */
  async delegateTask(
    task: string,
    context?: string,
    contextId?: string,
  ): Promise<A0Response> {
    const prompt = context ? `Context: ${context}\n\nTask: ${task}` : task
    return this.client.message(prompt, { contextId })
  }

  /** Send a task and poll until Agent Zero finishes. */
  async delegateAndWait(
    task: string,
    context?: string,
    contextId?: string,
  ): Promise<string> {
    const prompt = context ? `Context: ${context}\n\nTask: ${task}` : task
    return this.client.messageAndWait(prompt, contextId)
  }

  /** Generate an A0 plugin manifest from a PFAA skill definition. */
  generatePluginManifest(
    skillName: string,
    description: string,
  ): PluginManifest {
    return {
      name: `pfaa_${skillName.replace(/-/g, '_')}`,
      title: `PFAA: ${skillName}`,
      description,
      version: '1.0.0',
    }
  }

  /** Sync a JMEM memory to Agent Zero via message. */
  async syncMemory(
    content: string,
    level: string,
    contextId?: string,
  ): Promise<void> {
    const prompt = `Store this knowledge in your memory:\n\nLevel: ${level}\nContent: ${content}`
    await this.client.message(prompt, { contextId })
  }

  /** Get the underlying client for direct API access. */
  getClient(): AgentZeroClient {
    return this.client
  }
}
```

- [ ] **Step 4: Create `src/integrations/a0/index.ts`**

```typescript
export { AgentZeroClient } from './client'
export type { A0MessageOptions, A0Response, A0LogItem } from './client'
export { A0Bridge } from './bridge'
export type { A0BridgeConfig, PluginManifest, A2AMessage } from './bridge'
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
npx tsc --noEmit 2>&1 | grep "integrations/a0" | head -10
```

Expected: No output (no errors)

- [ ] **Step 6: Stage and commit**

```bash
git add src/integrations/
git commit -m "feat(a0): Agent Zero integration module

- AgentZeroClient: lightweight A0 API client for agent-to-agent communication
- A0Bridge: task delegation, plugin manifest generation, memory sync
- Adapted from CORA frontend agentZeroClient patterns for PFAA use case

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 13: Commit CORA frontend LuminaChat fix

**Files:**
- Modified: `/Users/borris/realestate/frontend/src/components/layout/LuminaChat.tsx`

This is in a SEPARATE git repo.

- [ ] **Step 1: Commit in the CORA repo**

```bash
cd /Users/borris/realestate/frontend
git add src/components/layout/LuminaChat.tsx
git commit -m "fix(a0): resolve iframe URL dynamically instead of broken /a0/ proxy

- Added resolveA0Url() with priority: localStorage > /api/config > env > fallback
- Replaced 5-retry health check loop (10s+ lag) with single 8s timeout check
- Added iframe sandbox attributes for cross-origin security
- Fixed retry handler to re-trigger URL resolution

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 14: Commit design spec and plan

**Files:**
- New: `docs/superpowers/specs/2026-04-02-github-production-cleanup-design.md`
- New: `docs/superpowers/plans/2026-04-02-github-production-cleanup.md`

- [ ] **Step 1: Stage and commit**

```bash
git add docs/
git commit -m "docs: add GitHub production cleanup design spec and implementation plan

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
```

---

### Task 15: Final verification

- [ ] **Step 1: Verify no hardcoded paths remain**

```bash
grep -r "/Users/borris" .claude/hooks/ .claude/settings.json .claude/skills/ --include="*.py" --include="*.cjs" --include="*.json" --include="*.md" 2>/dev/null
```

Expected: No output

- [ ] **Step 2: Verify no screenshots remain**

```bash
ls audit-*.png verify-*.png 2>/dev/null
```

Expected: No output

- [ ] **Step 3: Verify all tests pass**

```bash
python3 -m pytest tests/test_cortex.py -v --tb=short
```

Expected: 103 passed

- [ ] **Step 4: Verify TypeScript compiles**

```bash
npx tsc --noEmit
```

Expected: Only pre-existing pipeline/page.tsx errors (not from our changes)

- [ ] **Step 5: Verify git status is clean**

```bash
git status
```

Expected: Clean working tree (no untracked or modified files)
