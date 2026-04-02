/**
 * AutoDream — Background Memory Consolidation Service
 *
 * Inspired by Claude Code's autoDream service. Runs JMEM consolidate → reflect → evolve
 * in sequence when time and session gates pass. Prevents concurrent consolidation via
 * a file-based lock mechanism.
 *
 * Gate order (cheapest first):
 *   1. Time: hours since lastConsolidatedAt >= minHours (default 24)
 *   2. Sessions: session count since last consolidation >= minSessions (default 5)
 *   3. Lock: no other process mid-consolidation
 *
 * State is tracked in .pfaa/autoDream.json.
 */

import { readFile, writeFile, mkdir, stat, unlink } from 'fs/promises'
import { join } from 'path'
import { MemoryStore } from '../memory/store.js'

// ── Types ─────────────────────────────────────────────────────────

export interface AutoDreamConfig {
  /** Minimum hours between consolidations */
  minHours: number
  /** Minimum session count since last consolidation */
  minSessions: number
  /** Qdrant URL for memory store */
  qdrantUrl?: string
  /** Working directory (used to locate .pfaa/) */
  workspace: string
}

interface AutoDreamState {
  lastConsolidatedAt: number
  sessionsSinceConsolidation: number
  totalConsolidations: number
  lastResult: ConsolidationResult | null
}

export interface ConsolidationResult {
  timestamp: number
  promoted: number
  pruned: number
  reflected: boolean
  evolved: boolean
  durationMs: number
  error?: string
}

const DEFAULTS: Pick<AutoDreamConfig, 'minHours' | 'minSessions'> = {
  minHours: 24,
  minSessions: 5,
}

const STATE_DIR = '.pfaa'
const STATE_FILE = 'autoDream.json'
const LOCK_FILE = 'autoDream.lock'

// Stale lock threshold — reclaim after 1 hour even if PID is live (PID reuse guard)
const LOCK_STALE_MS = 60 * 60 * 1000

// ── State persistence ─────────────────────────────────────────────

function statePath(workspace: string): string {
  return join(workspace, STATE_DIR, STATE_FILE)
}

function lockPath(workspace: string): string {
  return join(workspace, STATE_DIR, LOCK_FILE)
}

async function ensureStateDir(workspace: string): Promise<void> {
  await mkdir(join(workspace, STATE_DIR), { recursive: true })
}

async function readState(workspace: string): Promise<AutoDreamState> {
  try {
    const raw = await readFile(statePath(workspace), 'utf8')
    return JSON.parse(raw) as AutoDreamState
  } catch {
    return {
      lastConsolidatedAt: 0,
      sessionsSinceConsolidation: 0,
      totalConsolidations: 0,
      lastResult: null,
    }
  }
}

async function writeState(workspace: string, state: AutoDreamState): Promise<void> {
  await ensureStateDir(workspace)
  await writeFile(statePath(workspace), JSON.stringify(state, null, 2))
}

// ── Lock mechanism ────────────────────────────────────────────────

/**
 * Try to acquire the consolidation lock. Returns true if acquired,
 * false if another process holds it.
 *
 * Lock file body = holder PID. Stale locks (holder dead or > 1h) are reclaimed.
 */
async function tryAcquireLock(workspace: string): Promise<boolean> {
  const path = lockPath(workspace)

  try {
    const [s, raw] = await Promise.all([
      stat(path),
      readFile(path, 'utf8'),
    ])

    // Check if lock is stale
    if (Date.now() - s.mtimeMs < LOCK_STALE_MS) {
      const holderPid = parseInt(raw.trim(), 10)
      if (Number.isFinite(holderPid) && isProcessRunning(holderPid)) {
        return false // Lock held by live process
      }
    }
    // Stale or dead holder — reclaim
  } catch {
    // ENOENT — no existing lock, proceed to acquire
  }

  await ensureStateDir(workspace)
  await writeFile(path, String(process.pid))

  // Verify we won any race
  try {
    const verify = await readFile(path, 'utf8')
    return parseInt(verify.trim(), 10) === process.pid
  } catch {
    return false
  }
}

async function releaseLock(workspace: string): Promise<void> {
  try {
    await unlink(lockPath(workspace))
  } catch {
    // Already removed or never created
  }
}

function isProcessRunning(pid: number): boolean {
  try {
    process.kill(pid, 0)
    return true
  } catch {
    return false
  }
}

// ── Consolidation pipeline ────────────────────────────────────────

/**
 * Run the full consolidation pipeline: consolidate → reflect → evolve.
 * Uses the MemoryStore's consolidate method plus JMEM MCP calls if available.
 */
async function runConsolidationPipeline(store: MemoryStore): Promise<ConsolidationResult> {
  const start = Date.now()
  const result: ConsolidationResult = {
    timestamp: start,
    promoted: 0,
    pruned: 0,
    reflected: false,
    evolved: false,
    durationMs: 0,
  }

  try {
    // Step 1: Consolidate — promote high-Q episodic → semantic, prune low-value
    const consolidation = await store.consolidate({ minQ: 0.8, minRetrievals: 3 })
    result.promoted = consolidation.promoted
    result.pruned = consolidation.pruned

    // Step 2: Reflect — store a reflexion memory about this consolidation
    const reflectionContent = [
      `AutoDream consolidation completed at ${new Date(start).toISOString()}.`,
      `Promoted ${consolidation.promoted} episodic memories to semantic knowledge.`,
      `Pruned ${consolidation.pruned} low-value memories.`,
    ].join(' ')

    await store.store(reflectionContent, reflectionContent, {
      area: 'main',
      fact_type: 'reflexion',
      tags: ['autoDream', 'consolidation', 'reflection'],
    })
    result.reflected = true

    // Step 3: Evolve — run a second consolidation pass with stricter thresholds
    // to further refine the promoted memories
    const evolution = await store.consolidate({ minQ: 0.9, minRetrievals: 5 })
    result.promoted += evolution.promoted
    result.pruned += evolution.pruned
    result.evolved = true
  } catch (err: unknown) {
    result.error = err instanceof Error ? err.message : String(err)
  }

  result.durationMs = Date.now() - start
  return result
}

// ── Public API ────────────────────────────────────────────────────

/**
 * Initialize and conditionally run AutoDream consolidation.
 * Checks time gate and session gate before running.
 *
 * Call this at session start (e.g., from the orchestrator's startup hook).
 */
export async function initAutoDream(config: Partial<AutoDreamConfig> & { workspace: string }): Promise<{
  ran: boolean
  reason: string
  result?: ConsolidationResult
}> {
  const cfg: AutoDreamConfig = {
    minHours: config.minHours ?? DEFAULTS.minHours,
    minSessions: config.minSessions ?? DEFAULTS.minSessions,
    qdrantUrl: config.qdrantUrl,
    workspace: config.workspace,
  }

  const state = await readState(cfg.workspace)

  // Gate 1: Time
  const hoursSince = (Date.now() - state.lastConsolidatedAt) / 3_600_000
  if (hoursSince < cfg.minHours) {
    return {
      ran: false,
      reason: `Time gate: ${hoursSince.toFixed(1)}h since last consolidation, need ${cfg.minHours}h`,
    }
  }

  // Gate 2: Sessions
  // Increment session count (caller is a new session starting)
  state.sessionsSinceConsolidation++
  await writeState(cfg.workspace, state)

  if (state.sessionsSinceConsolidation < cfg.minSessions) {
    return {
      ran: false,
      reason: `Session gate: ${state.sessionsSinceConsolidation} sessions since last consolidation, need ${cfg.minSessions}`,
    }
  }

  // Gate 3: Lock
  const acquired = await tryAcquireLock(cfg.workspace)
  if (!acquired) {
    return { ran: false, reason: 'Lock gate: another process is consolidating' }
  }

  try {
    const store = new MemoryStore(cfg.qdrantUrl)
    const result = await runConsolidationPipeline(store)

    // Update state
    state.lastConsolidatedAt = Date.now()
    state.sessionsSinceConsolidation = 0
    state.totalConsolidations++
    state.lastResult = result
    await writeState(cfg.workspace, state)

    return { ran: true, reason: 'All gates passed — consolidation complete', result }
  } catch (err: unknown) {
    // Rollback: don't reset session count so the next session retries
    return {
      ran: false,
      reason: `Consolidation failed: ${err instanceof Error ? err.message : String(err)}`,
    }
  } finally {
    await releaseLock(cfg.workspace)
  }
}

/**
 * Force consolidation immediately, skipping time and session gates.
 * Still respects the lock to prevent concurrent runs.
 */
export async function forceConsolidate(config: Partial<AutoDreamConfig> & { workspace: string }): Promise<ConsolidationResult> {
  const cfg: AutoDreamConfig = {
    minHours: config.minHours ?? DEFAULTS.minHours,
    minSessions: config.minSessions ?? DEFAULTS.minSessions,
    qdrantUrl: config.qdrantUrl,
    workspace: config.workspace,
  }

  const acquired = await tryAcquireLock(cfg.workspace)
  if (!acquired) {
    return {
      timestamp: Date.now(),
      promoted: 0,
      pruned: 0,
      reflected: false,
      evolved: false,
      durationMs: 0,
      error: 'Could not acquire lock — another consolidation is in progress',
    }
  }

  try {
    const store = new MemoryStore(cfg.qdrantUrl)
    const result = await runConsolidationPipeline(store)

    // Update state
    const state = await readState(cfg.workspace)
    state.lastConsolidatedAt = Date.now()
    state.sessionsSinceConsolidation = 0
    state.totalConsolidations++
    state.lastResult = result
    await writeState(cfg.workspace, state)

    return result
  } finally {
    await releaseLock(cfg.workspace)
  }
}

/**
 * Read the current AutoDream state (for status/health checks).
 */
export async function getAutoDreamStatus(workspace: string): Promise<AutoDreamState & { lockHeld: boolean }> {
  const state = await readState(workspace)

  let lockHeld = false
  try {
    const s = await stat(lockPath(workspace))
    if (Date.now() - s.mtimeMs < LOCK_STALE_MS) {
      const raw = await readFile(lockPath(workspace), 'utf8')
      const pid = parseInt(raw.trim(), 10)
      lockHeld = Number.isFinite(pid) && isProcessRunning(pid)
    }
  } catch {
    // No lock file
  }

  return { ...state, lockHeld }
}

/**
 * Increment the session counter. Call this each time a new session starts
 * (even if consolidation doesn't run) so the session gate tracks properly.
 */
export async function recordSession(workspace: string): Promise<void> {
  const state = await readState(workspace)
  state.sessionsSinceConsolidation++
  await writeState(workspace, state)
}
