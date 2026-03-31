/**
 * Aussie Agents Bridge — Node.js ↔ Python 3.15 Engine Bridge
 *
 * Spawns the Aussie Agents Python engine as a subprocess and communicates
 * via JSON-over-stdin/stdout. Supports streaming results, phase
 * transitions, and memory synchronization.
 *
 * This is the core integration point: the Node.js CLI orchestrates
 * while the Python 3.15 engine does the heavy lifting.
 */

import { spawn, type ChildProcess } from 'node:child_process';
import { join } from 'node:path';
import { existsSync } from 'node:fs';
import { EventEmitter } from 'node:events';
import { getLogger } from '../utils/logger.js';
import type {
  Phase,
  ToolResult,
  MemoryStatus,
  AgentResult,
  AgentRole,
  StreamEvent,
  EventType,
} from '../types.js';

const log = getLogger('bridge');

export interface BridgeConfig {
  pythonPath: string;
  enginePath: string;
  workingDir: string;
  timeoutMs: number;
  maxConcurrent: number;
  /** Max milliseconds to wait for the Python engine to become ready (default 30s). */
  startupTimeoutMs: number;
}

interface BridgeCommand {
  action: string;
  args: Record<string, unknown>;
  id: string;
}

interface BridgeResponse {
  id: string;
  success: boolean;
  data: unknown;
  error?: string;
  elapsed_us?: number;
  phase?: Phase;
}

export class PFAABridge extends EventEmitter {
  private config: BridgeConfig;
  private process: ChildProcess | null = null;
  private pending = new Map<string, {
    resolve: (val: BridgeResponse) => void;
    reject: (err: Error) => void;
    timer: ReturnType<typeof setTimeout>;
  }>();
  private buffer = '';
  private ready = false;
  private commandId = 0;

  constructor(config: BridgeConfig) {
    super();
    this.config = config;
  }

  async start(): Promise<void> {
    if (this.process) return;

    const engineEntry = this.findEngineEntry();
    if (!engineEntry) {
      throw new Error(
        `Aussie Agents engine not found. Expected at ${this.config.enginePath}. ` +
        'Run: pip install -e . in the pfaa-engine root.',
      );
    }

    log.info('Starting Aussie Agents engine', {
      python: this.config.pythonPath,
      engine: engineEntry,
    });

    this.process = spawn(this.config.pythonPath, ['-u', engineEntry], {
      cwd: this.config.workingDir,
      stdio: ['pipe', 'pipe', 'pipe'],
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
        PFAA_MODE: 'bridge',
      },
    });

    this.process.stdout?.on('data', (chunk: Buffer) => {
      this.buffer += chunk.toString();
      this.processBuffer();
    });

    this.process.stderr?.on('data', (chunk: Buffer) => {
      const msg = chunk.toString().trim();
      if (msg) log.debug(`[engine] ${msg}`);
    });

    this.process.on('exit', (code) => {
      log.warn('Aussie Agents engine exited', { code });
      this.ready = false;
      this.process = null;
      this.rejectAll(new Error(`Engine exited with code ${code}`));
      this.emit('exit', code);
    });

    this.process.on('error', (err) => {
      log.error('Engine process error', { error: err.message });
      this.emit('error', err);
    });

    // Wait for the engine to signal readiness (or timeout)
    await new Promise<void>((resolve, reject) => {
      const startupTimeout = setTimeout(() => {
        reject(new Error(
          `Engine failed to become ready within ${this.config.startupTimeoutMs}ms. ` +
          'Check that the Python engine is installed and pfaa_bridge.py prints a ready message.',
        ));
      }, this.config.startupTimeoutMs);

      const onData = (chunk: Buffer) => {
        const text = chunk.toString();
        // Engine sends a JSON line with "ready" or we see any valid JSON response
        if (text.includes('"ready"') || text.includes('"status"')) {
          clearTimeout(startupTimeout);
          this.process?.stdout?.off('data', onData);
          resolve();
        }
      };

      // If the process exits before ready, reject immediately
      const onExit = (code: number | null) => {
        clearTimeout(startupTimeout);
        this.process?.stdout?.off('data', onData);
        reject(new Error(`Engine exited with code ${code} before becoming ready`));
      };

      this.process!.stdout?.on('data', onData);
      this.process!.once('exit', onExit);

      // Also resolve after the timeout if stdout is already flowing
      // (covers engines that don't send an explicit ready message)
    });

    this.ready = true;
    log.info('Aussie Agents engine bridge started');
  }

  async stop(): Promise<void> {
    if (!this.process) return;
    this.process.kill('SIGTERM');
    this.process = null;
    this.ready = false;
    this.rejectAll(new Error('Bridge stopped'));
  }

  get isRunning(): boolean {
    return this.ready && this.process !== null;
  }

  // ── Engine Commands ──────────────────────────────────────────────

  async status(): Promise<MemoryStatus & { tools: number; uptime_ms: number }> {
    const resp = await this.send('status', {});
    return resp.data as MemoryStatus & { tools: number; uptime_ms: number };
  }

  async listTools(): Promise<Array<{
    name: string;
    phase: Phase;
    description: string;
    capabilities: string[];
  }>> {
    const resp = await this.send('list_tools', {});
    return (resp.data ?? []) as Array<{ name: string; phase: Phase; description: string; capabilities: string[] }>;
  }

  async executeTool(name: string, ...args: unknown[]): Promise<ToolResult> {
    const resp = await this.send('execute_tool', { name, args });
    return {
      tool: name,
      success: resp.success,
      result: resp.data,
      phaseUsed: resp.phase || ('VAPOR' as Phase),
      elapsedUs: resp.elapsed_us || 0,
    };
  }

  async runGoal(goal: string): Promise<AgentResult> {
    const resp = await this.send('run_goal', { goal }, this.config.timeoutMs);
    return resp.data as AgentResult;
  }

  async scatter(
    toolName: string,
    inputs: unknown[],
  ): Promise<ToolResult[]> {
    const resp = await this.send('scatter', { tool: toolName, inputs });
    return resp.data as ToolResult[];
  }

  async selfBuild(autoApply: boolean = false): Promise<Record<string, unknown>> {
    const resp = await this.send('self_build', { auto_apply: autoApply }, 300_000);
    return resp.data as Record<string, unknown>;
  }

  async benchmark(): Promise<Record<string, unknown>> {
    const resp = await this.send('benchmark', {}, 600_000);
    return resp.data as Record<string, unknown>;
  }

  // ── Goal & Task Management ──────────────────────────────────────

  async listCheckpoints(): Promise<Array<{
    goal_id: string;
    goal: string;
    status: string;
    subtasks: number;
    completed: number;
  }>> {
    const resp = await this.send('list_checkpoints', {});
    return (resp.data ?? []) as Array<{ goal_id: string; goal: string; status: string; subtasks: number; completed: number }>;
  }

  async resumeGoal(goalId: string): Promise<AgentResult> {
    const resp = await this.send('resume_goal', { goal_id: goalId }, this.config.timeoutMs);
    return resp.data as AgentResult;
  }

  // ── Memory Operations ─────────────────────────────────────────

  async getMemory(): Promise<{
    patterns: Array<{ tool: string; best_phase: string; avg_latency_us: number; confidence: number }>;
    strategies: Array<{ tool: string; from_phase: string; to_phase: string; speedup: string }>;
    episodes: number;
    knowledge: Array<{ pattern: string; frequency: number }>;
  }> {
    const resp = await this.send('get_memory', {});
    return resp.data as { patterns: Array<{ tool: string; best_phase: string; avg_latency_us: number; confidence: number }>; strategies: Array<{ tool: string; from_phase: string; to_phase: string; speedup: string }>; episodes: number; knowledge: Array<{ pattern: string; frequency: number }> };
  }

  async forceLearn(): Promise<{ learned: boolean }> {
    const resp = await this.send('force_learn', {});
    return resp.data as { learned: boolean };
  }

  // ── Scatter / Pipeline ────────────────────────────────────────

  async pipeline(steps: Array<{ tool: string; args: unknown[] }>): Promise<Array<{
    tool: string;
    success: boolean;
    result: unknown;
    phase: string;
    elapsed_us: number;
  }>> {
    const resp = await this.send('pipeline', { steps }, this.config.timeoutMs);
    return (resp.data ?? []) as Array<{ tool: string; success: boolean; result: unknown; phase: string; elapsed_us: number }>;
  }

  // ── Exploration ───────────────────────────────────────────────

  async explore(rounds: number = 200, epsilon: number = 0.3): Promise<Record<string, unknown>> {
    const resp = await this.send('explore', { rounds, epsilon }, 300_000);
    return resp.data as Record<string, unknown>;
  }

  // ── Team Spawning ─────────────────────────────────────────────

  async spawnTeam(goal: string, mode: 'basic' | 'remix' = 'basic'): Promise<Record<string, unknown>> {
    const resp = await this.send('spawn_team', { goal, mode }, 600_000);
    return resp.data as Record<string, unknown>;
  }

  // ── Claude Integration ───────────────────────────────────────────

  async askClaude(prompt: string, model?: string): Promise<{
    success: boolean;
    output: string;
    elapsedMs: number;
  }> {
    const resp = await this.send('ask_claude', { prompt, model }, 120_000);
    return resp.data as { success: boolean; output: string; elapsedMs: number };
  }

  async generateCode(
    description: string,
    language: string = 'python',
    outputFile?: string,
  ): Promise<{ success: boolean; code: string; file?: string }> {
    const resp = await this.send('generate_code', {
      description,
      language,
      output_file: outputFile,
    }, 120_000);
    return resp.data as { success: boolean; code: string; file?: string };
  }

  // ── Session Persistence ──────────────────────────────────────────

  async saveSession(sessionId: string, state: Record<string, unknown>): Promise<{saved: string}> {
    const resp = await this.send('save_session', { session_id: sessionId, state });
    return resp.data as {saved: string};
  }

  async loadSession(sessionId?: string): Promise<Record<string, unknown>> {
    const resp = await this.send('load_session', sessionId ? { session_id: sessionId } : {});
    return resp.data as Record<string, unknown>;
  }

  // ── Deferred Tool Discovery ──────────────────────────────────────

  async searchTools(query: string, limit: number = 5): Promise<Array<{
    name: string;
    description: string;
    phase: string;
    capabilities: string[];
  }>> {
    const resp = await this.send('deferred_tool_search', { query, limit });
    return (resp.data ?? []) as Array<{ name: string; description: string; phase: string; capabilities: string[] }>;
  }

  // ── Internal ─────────────────────────────────────────────────────

  private async send(
    action: string,
    args: Record<string, unknown>,
    timeoutMs?: number,
  ): Promise<BridgeResponse> {
    if (!this.ready || !this.process?.stdin) {
      throw new Error('Bridge not started. Call bridge.start() first.');
    }

    const id = `cmd_${++this.commandId}`;
    const cmd: BridgeCommand = { action, args, id };

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`Bridge command '${action}' timed out after ${timeoutMs || this.config.timeoutMs}ms`));
      }, timeoutMs || this.config.timeoutMs);

      this.pending.set(id, { resolve, reject, timer });
      try {
        this.process!.stdin!.write(JSON.stringify(cmd) + '\n');
      } catch (err) {
        this.pending.delete(id);
        clearTimeout(timer);
        reject(new Error(`Bridge stdin write failed: ${err}`));
      }
    });
  }

  private processBuffer(): void {
    const lines = this.buffer.split('\n');
    this.buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.trim()) continue;
      try {
        const resp = JSON.parse(line) as BridgeResponse;
        if (resp.id && this.pending.has(resp.id)) {
          const { resolve, timer } = this.pending.get(resp.id)!;
          clearTimeout(timer);
          this.pending.delete(resp.id);
          resolve(resp);
        } else {
          // Streaming event from engine
          this.emit('event', resp);
        }
      } catch {
        log.trace('Non-JSON from engine', { line: line.slice(0, 200) });
      }
    }
  }

  private rejectAll(err: Error): void {
    for (const [id, { reject, timer }] of this.pending) {
      clearTimeout(timer);
      reject(err);
    }
    this.pending.clear();
  }

  private findEngineEntry(): string | null {
    // pfaa_bridge.py is the ONLY valid entry point — it has the stdin/stdout loop.
    // framework.py defines classes but has no bridge protocol.
    const candidates = [
      // 1. Same directory as this package (pfaa-cli/pfaa_bridge.py)
      join(this.config.workingDir, 'pfaa_bridge.py'),
      // 2. Relative to enginePath (when cwd is project root)
      join(this.config.enginePath, 'pfaa-cli', 'pfaa_bridge.py'),
      // 3. One level up from cwd (pfaa-cli/../pfaa-cli/pfaa_bridge.py)
      join(this.config.enginePath, 'pfaa_bridge.py'),
      // 4. Resolve from this file's package location
      new URL('../../../pfaa_bridge.py', import.meta.url).pathname,
    ];
    for (const path of candidates) {
      if (existsSync(path)) return path;
    }
    return null;
  }
}

/**
 * Create a bridge with sensible defaults for the Aussie Agents engine.
 */
export function createBridge(overrides: Partial<BridgeConfig> = {}): PFAABridge {
  const defaults: BridgeConfig = {
    pythonPath: process.env['PFAA_PYTHON_PATH'] || 'python3.15',
    enginePath: join(process.cwd(), '..'),
    workingDir: process.cwd(),
    timeoutMs: 120_000,
    maxConcurrent: 8,
    startupTimeoutMs: 30_000,
  };

  return new PFAABridge({ ...defaults, ...overrides });
}
