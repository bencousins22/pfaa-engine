/**
 * PFAA Bridge — Node.js ↔ Python 3.15 PFAA Engine Bridge
 *
 * Spawns the PFAA Python engine as a subprocess and communicates
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
        `PFAA engine not found. Expected at ${this.config.enginePath}. ` +
        'Run: pip install -e . in the pfaa-engine root.',
      );
    }

    log.info('Starting PFAA engine', {
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
      log.warn('PFAA engine exited', { code });
      this.ready = false;
      this.process = null;
      this.rejectAll(new Error(`Engine exited with code ${code}`));
      this.emit('exit', code);
    });

    this.process.on('error', (err) => {
      log.error('Engine process error', { error: err.message });
      this.emit('error', err);
    });

    this.ready = true;
    log.info('PFAA engine bridge started');
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
    return resp.data as any;
  }

  async listTools(): Promise<Array<{
    name: string;
    phase: Phase;
    description: string;
    capabilities: string[];
  }>> {
    const resp = await this.send('list_tools', {});
    return resp.data as any;
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
    return resp.data as any;
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
    return resp.data as any;
  }

  async forceLearn(): Promise<{ learned: boolean }> {
    const resp = await this.send('force_learn', {});
    return resp.data as any;
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
    return resp.data as any;
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
    return resp.data as any;
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
    return resp.data as any;
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
      this.process!.stdin!.write(JSON.stringify(cmd) + '\n');
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
    const candidates = [
      join(this.config.enginePath, 'agent_setup_cli', 'core', 'framework.py'),
      join(this.config.enginePath, 'pfaa_bridge.py'),
      join(this.config.enginePath, 'bridge.py'),
    ];
    for (const path of candidates) {
      if (existsSync(path)) return path;
    }
    return null;
  }
}

/**
 * Create a bridge with sensible defaults for the PFAA engine.
 */
export function createBridge(overrides: Partial<BridgeConfig> = {}): PFAABridge {
  const defaults: BridgeConfig = {
    pythonPath: process.env['PFAA_PYTHON_PATH'] || 'python3.15',
    enginePath: join(process.cwd(), '..'),
    workingDir: process.cwd(),
    timeoutMs: 120_000,
    maxConcurrent: 8,
  };

  return new PFAABridge({ ...defaults, ...overrides });
}
