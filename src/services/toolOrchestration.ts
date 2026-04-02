/**
 * Tool Orchestration — Partition and execute tool calls optimally.
 *
 * Inspired by Claude Code's toolOrchestration.ts. Partitions tool calls into
 * read-only (concurrency-safe) and side-effecting batches, then executes
 * read-only batches concurrently and side-effecting calls serially.
 *
 * This preserves correctness (writes don't race) while maximizing throughput
 * (reads fan out in parallel, up to a configurable concurrency limit).
 */

// ── Types ─────────────────────────────────────────────────────────

export interface ToolCall {
  id: string
  name: string
  input: Record<string, unknown>
}

export interface ToolResult {
  id: string
  name: string
  result: string
  error?: string
  durationMs: number
}

export type ToolExecutor = (call: ToolCall) => Promise<string>

// ── Tool categorization ───────────────────────────────────────────

/**
 * Tools known to be read-only (no side effects, safe to run concurrently).
 */
const READ_ONLY_TOOLS = new Set([
  // File reading
  'read', 'Read',
  // Search
  'grep', 'Grep', 'rg',
  'glob', 'Glob',
  // Memory reads
  'memory_recall', 'memory_stats',
  'jmem_recall', 'jmem_status', 'jmem_recall_cross',
  // Tool discovery
  'tool_search', 'ToolSearch',
  // Web reads
  'WebFetch', 'WebSearch',
  // Git read-only
  'git_status', 'git_log', 'git_diff',
])

/**
 * Tools known to have side effects (must run serially).
 */
const WRITE_TOOLS = new Set([
  // File modification
  'edit', 'Edit',
  'write', 'Write',
  // Shell (may write)
  'bash', 'Bash',
  // Memory writes
  'memory_store', 'memory_feedback', 'memory_consolidate',
  'jmem_remember', 'jmem_consolidate', 'jmem_reflect',
  'jmem_evolve', 'jmem_reward', 'jmem_reward_recalled',
  'jmem_decay', 'jmem_meta_learn', 'jmem_emergent',
  'jmem_extract_skills',
  // Notebook
  'NotebookEdit',
])

/**
 * Determine if a tool call is concurrency-safe (read-only).
 * Unknown tools default to side-effecting (serial) for safety.
 */
export function isConcurrencySafe(call: ToolCall): boolean {
  if (READ_ONLY_TOOLS.has(call.name)) return true
  if (WRITE_TOOLS.has(call.name)) return false

  // Bash with read-only commands can be concurrent
  if (call.name === 'bash' || call.name === 'Bash') {
    return isBashReadOnly(call.input.command as string | undefined)
  }

  // Default: treat unknown tools as side-effecting
  return false
}

/**
 * Check if a bash command is read-only (no writes, no redirects, no pipes to write commands).
 */
function isBashReadOnly(command: string | undefined): boolean {
  if (!command) return false

  const readOnlyPrefixes = [
    'ls', 'cat', 'head', 'tail', 'grep', 'rg', 'find', 'stat', 'wc',
    'file', 'which', 'type', 'echo', 'printf', 'date', 'pwd', 'env',
    'git status', 'git log', 'git diff', 'git show', 'git branch',
    'git remote', 'git tag', 'node -e', 'python3 -c',
  ]

  const trimmed = command.trim()

  // Reject anything with output redirection or destructive operators
  if (/[>|]/.test(trimmed) && />\s*[^&]/.test(trimmed)) return false
  if (trimmed.includes('>>')) return false
  if (trimmed.includes('rm ') || trimmed.includes('mv ') || trimmed.includes('cp ')) return false

  return readOnlyPrefixes.some(prefix => trimmed.startsWith(prefix))
}

// ── Batching ──────────────────────────────────────────────────────

interface Batch {
  isConcurrencySafe: boolean
  calls: ToolCall[]
}

/**
 * Partition tool calls into batches where each batch is either:
 *   1. Multiple consecutive read-only tools (run concurrently)
 *   2. A single side-effecting tool (run alone, serially)
 *
 * Preserves ordering: the sequence of batches maintains the original
 * call order, so a write between two read groups creates three batches.
 */
export function partitionToolCalls(calls: ToolCall[]): Batch[] {
  return calls.reduce<Batch[]>((batches, call) => {
    const safe = isConcurrencySafe(call)
    const last = batches[batches.length - 1]

    if (safe && last?.isConcurrencySafe) {
      // Append to existing read-only batch
      last.calls.push(call)
    } else {
      // Start a new batch
      batches.push({ isConcurrencySafe: safe, calls: [call] })
    }

    return batches
  }, [])
}

// ── Execution ─────────────────────────────────────────────────────

const DEFAULT_MAX_CONCURRENCY = 10

/**
 * Execute an array of tool calls concurrently with a concurrency limit.
 * Returns results in the same order as the input calls.
 */
export async function executeParallel(
  calls: ToolCall[],
  executor: ToolExecutor,
  maxConcurrency = DEFAULT_MAX_CONCURRENCY,
): Promise<ToolResult[]> {
  if (calls.length === 0) return []

  // If within concurrency limit, just Promise.all
  if (calls.length <= maxConcurrency) {
    return Promise.all(calls.map(call => executeSingle(call, executor)))
  }

  // Chunked execution for larger batches
  const results: ToolResult[] = []
  for (let i = 0; i < calls.length; i += maxConcurrency) {
    const chunk = calls.slice(i, i + maxConcurrency)
    const chunkResults = await Promise.all(
      chunk.map(call => executeSingle(call, executor)),
    )
    results.push(...chunkResults)
  }
  return results
}

/**
 * Execute an array of tool calls sequentially, one at a time.
 * Each call completes before the next begins.
 */
export async function executeSerial(
  calls: ToolCall[],
  executor: ToolExecutor,
): Promise<ToolResult[]> {
  const results: ToolResult[] = []
  for (const call of calls) {
    results.push(await executeSingle(call, executor))
  }
  return results
}

/**
 * Execute a single tool call, capturing timing and errors.
 */
async function executeSingle(call: ToolCall, executor: ToolExecutor): Promise<ToolResult> {
  const start = Date.now()
  try {
    const result = await executor(call)
    return {
      id: call.id,
      name: call.name,
      result,
      durationMs: Date.now() - start,
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err)
    return {
      id: call.id,
      name: call.name,
      result: '',
      error: message,
      durationMs: Date.now() - start,
    }
  }
}

// ── Orchestrator ──────────────────────────────────────────────────

export interface OrchestrateOptions {
  /** Maximum concurrent read-only calls (default 10) */
  maxConcurrency?: number
  /** Called for each completed result (for streaming progress) */
  onResult?: (result: ToolResult) => void
}

/**
 * Auto-partition tool calls and execute them optimally:
 *   - Consecutive read-only calls run concurrently (up to maxConcurrency)
 *   - Side-effecting calls run one at a time
 *   - Order is preserved across batches
 *
 * Returns all results in the original call order.
 */
export async function orchestrate(
  calls: ToolCall[],
  executor: ToolExecutor,
  options: OrchestrateOptions = {},
): Promise<ToolResult[]> {
  const { maxConcurrency = DEFAULT_MAX_CONCURRENCY, onResult } = options

  if (calls.length === 0) return []

  const batches = partitionToolCalls(calls)
  const allResults: ToolResult[] = []

  for (const batch of batches) {
    let batchResults: ToolResult[]

    if (batch.isConcurrencySafe) {
      batchResults = await executeParallel(batch.calls, executor, maxConcurrency)
    } else {
      batchResults = await executeSerial(batch.calls, executor)
    }

    for (const result of batchResults) {
      if (onResult) onResult(result)
      allResults.push(result)
    }
  }

  return allResults
}

/**
 * Register additional read-only or write tool names at runtime.
 * Useful for plugins or MCP tools discovered after startup.
 */
export function registerToolCategory(
  name: string,
  category: 'read-only' | 'write',
): void {
  if (category === 'read-only') {
    READ_ONLY_TOOLS.add(name)
    WRITE_TOOLS.delete(name)
  } else {
    WRITE_TOOLS.add(name)
    READ_ONLY_TOOLS.delete(name)
  }
}
