/**
 * ProcessPool — persistent python3.15 worker pool with JSON-line IPC.
 *
 * Each worker runs ../../python/swarm/process_pool.py, pre-loading anthropic
 * and sentence-transformers at startup.  Workers stay alive between dispatches,
 * communicate over stdin/stdout JSON pipes, and auto-respawn on crash.
 * A built-in queue ensures tasks are buffered when all workers are busy.
 */

import { spawn, ChildProcess } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { resolve, dirname } from 'node:path';
import { createInterface, Interface as ReadlineInterface } from 'node:readline';
import { getLogger } from '../utils/logger.js';

const log = getLogger('pool');

// ── Types ───────────────────────────────────────────────────────────────

interface WorkerHandle {
  proc: ChildProcess;
  rl: ReadlineInterface;
  id: number;
  busy: boolean;
  ready: boolean;
  pid: number | null;
}

interface QueuedTask {
  task: string;
  opts: Record<string, unknown>;
  onEvent: (event: Record<string, unknown>) => void;
  resolve: () => void;
  reject: (err: Error) => void;
}

// ── Constants ───────────────────────────────────────────────────────────

const WORKER_SCRIPT = resolve(
  dirname(new URL(import.meta.url).pathname),
  '..', '..', '..', 'python', 'swarm', 'process_pool.py',
);

const DEFAULT_POOL_SIZE = 4;
const RESPAWN_DELAY_MS = 500;
const READY_TIMEOUT_MS = 30_000;

// ── ProcessPool ─────────────────────────────────────────────────────────

export class ProcessPool extends EventEmitter {
  private workers: Map<number, WorkerHandle> = new Map();
  private queue: QueuedTask[] = [];
  private nextId = 0;
  private poolSize: number;
  private shuttingDown = false;

  constructor(poolSize = DEFAULT_POOL_SIZE) {
    super();
    this.poolSize = poolSize;
  }

  // ── Public API ──────────────────────────────────────────────────────

  /**
   * Spin up all workers and wait until every one has signalled "ready"
   * (i.e. heavy imports are loaded).
   */
  async warmUp(): Promise<void> {
    const starts: Promise<void>[] = [];
    for (let i = 0; i < this.poolSize; i++) {
      starts.push(this.spawnWorker());
    }
    await Promise.all(starts);
    this.emit('pool:ready', { workers: this.poolSize });
  }

  /**
   * Dispatch a task to an available worker.  If none are free the task is
   * queued and will run as soon as a worker finishes its current job.
   *
   * `onEvent` is called for every JSON line the worker writes to stdout
   * while processing this task.
   */
  dispatch(
    task: string,
    onEvent: (event: Record<string, unknown>) => void,
    opts: Record<string, unknown> = {},
  ): Promise<void> {
    return new Promise<void>((resolve, reject) => {
      const idle = this.idleWorker();
      if (idle) {
        this.runOnWorker(idle, task, opts, onEvent, resolve, reject);
      } else {
        this.queue.push({ task, opts, onEvent, resolve, reject });
      }
    });
  }

  /**
   * Gracefully terminate every worker and drain the queue.
   */
  async shutdown(): Promise<void> {
    this.shuttingDown = true;

    // Reject anything still queued.
    for (const q of this.queue) {
      q.reject(new Error('Pool shutting down'));
    }
    this.queue = [];

    // Kill workers.
    const kills: Promise<void>[] = [];
    for (const w of this.workers.values()) {
      kills.push(this.killWorker(w));
    }
    await Promise.all(kills);
    this.workers.clear();
    this.emit('pool:shutdown');
  }

  /** Number of workers currently alive. */
  get size(): number {
    return this.workers.size;
  }

  /** Number of idle (non-busy) workers. */
  get idleCount(): number {
    let n = 0;
    for (const w of this.workers.values()) {
      if (w.ready && !w.busy) n++;
    }
    return n;
  }

  /** Number of tasks waiting in queue. */
  get pendingCount(): number {
    return this.queue.length;
  }

  // ── Internals ───────────────────────────────────────────────────────

  private async spawnWorker(): Promise<void> {
    const id = this.nextId++;

    const proc = spawn('python3.15', [WORKER_SCRIPT], {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PYTHON_GIL: '0' },
    });

    const rl = createInterface({ input: proc.stdout! });

    const handle: WorkerHandle = {
      proc,
      rl,
      id,
      busy: false,
      ready: false,
      pid: null,
    };

    this.workers.set(id, handle);

    // Forward stderr for debugging.
    proc.stderr?.on('data', (chunk: Buffer) => {
      this.emit('worker:stderr', { id, data: chunk.toString() });
    });

    // Auto-respawn on unexpected exit.
    proc.on('exit', (code, signal) => {
      this.workers.delete(id);
      this.emit('worker:exit', { id, code, signal });

      if (!this.shuttingDown) {
        setTimeout(() => {
          this.spawnWorker().then(() => this.drainQueue());
        }, RESPAWN_DELAY_MS);
      }
    });

    // Wait for the "ready" handshake from the worker.
    await new Promise<void>((resolve, reject) => {
      const timeout = setTimeout(() => {
        reject(new Error(`Worker ${id} did not become ready within ${READY_TIMEOUT_MS}ms`));
      }, READY_TIMEOUT_MS);

      const onLine = (line: string) => {
        try {
          const msg = JSON.parse(line);
          if (msg.status === 'ready') {
            clearTimeout(timeout);
            handle.ready = true;
            handle.pid = msg.pid ?? null;
            this.emit('worker:ready', { id, pid: handle.pid });
            // Re-attach generic listener after handshake.
            resolve();
          }
        } catch (err) {
          log.trace('Non-JSON line during worker startup', { id, line: line.slice(0, 120), error: String(err) });
        }
      };

      rl.on('line', onLine);
    });
  }

  private runOnWorker(
    w: WorkerHandle,
    task: string,
    opts: Record<string, unknown>,
    onEvent: (event: Record<string, unknown>) => void,
    resolve: () => void,
    reject: (err: Error) => void,
  ): void {
    w.busy = true;

    const lineHandler = (line: string) => {
      try {
        const msg = JSON.parse(line) as Record<string, unknown>;

        // Stream every event to the caller.
        onEvent(msg);

        // When the worker signals completion (or error), free it.
        if (msg.type === 'done' || msg.type === 'worker_error') {
          cleanup();
          w.busy = false;

          if (msg.type === 'worker_error') {
            reject(new Error(String(msg.error ?? 'unknown worker error')));
          } else {
            resolve();
          }

          this.drainQueue();
        }
      } catch (err) {
        log.trace('Non-JSON line from worker', { line: line.slice(0, 100), error: String(err) });
      }
    };

    const exitHandler = (code: number | null) => {
      cleanup();
      reject(new Error(`Worker ${w.id} exited unexpectedly (code ${code}) during task`));
      // Respawn is handled by the global exit listener.
    };

    const cleanup = () => {
      w.rl.removeListener('line', lineHandler);
      w.proc.removeListener('exit', exitHandler);
    };

    w.rl.on('line', lineHandler);
    w.proc.on('exit', exitHandler);

    // Send the task.
    const payload = JSON.stringify({ task, opts }) + '\n';
    w.proc.stdin!.write(payload);
  }

  private idleWorker(): WorkerHandle | undefined {
    for (const w of this.workers.values()) {
      if (w.ready && !w.busy) return w;
    }
    return undefined;
  }

  private drainQueue(): void {
    while (this.queue.length > 0) {
      const idle = this.idleWorker();
      if (!idle) break;
      const next = this.queue.shift()!;
      this.runOnWorker(idle, next.task, next.opts, next.onEvent, next.resolve, next.reject);
    }
  }

  private killWorker(w: WorkerHandle): Promise<void> {
    return new Promise<void>((resolve) => {
      w.rl.close();

      if (w.proc.exitCode !== null) {
        resolve();
        return;
      }

      w.proc.on('exit', () => resolve());

      // Close stdin first so the worker's readline loop exits cleanly.
      w.proc.stdin!.end();

      // If it doesn't exit within 2 s, force-kill.
      setTimeout(() => {
        try {
          w.proc.kill('SIGKILL');
        } catch (err) {
          log.trace('Worker already dead on SIGKILL', { id: w.id, error: String(err) });
        }
      }, 2_000);
    });
  }
}

// ── Singleton ─────────────────────────────────────────────────────────

let _pool: ProcessPool | null = null;

/**
 * Return (and optionally create) the shared ProcessPool singleton.
 * The pool is NOT warmed up automatically — call `pool.warmUp()` when ready.
 */
export function getPool(poolSize = DEFAULT_POOL_SIZE): ProcessPool {
  if (!_pool) {
    _pool = new ProcessPool(poolSize);
  }
  return _pool;
}
