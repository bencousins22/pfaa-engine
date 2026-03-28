/**
 * Python 3.15 sandbox — isolated code execution with REPL state persistence.
 * Uses PYTHON_GIL=0 for free-threaded mode where available.
 */

import { execa } from 'execa'
import { writeFile, unlink, mkdir } from 'fs/promises'
import { join } from 'path'
import { tmpdir } from 'os'
import { randomUUID } from 'crypto'

export interface SandboxOptions {
  timeout: number
  memoryLimitMb: number
  allowNetwork: boolean
  persist: boolean
  workspace: string
  pythonBin: string
}

export interface ExecResult {
  stdout: string
  stderr: string
  durationMs: number
  error?: { type: string; message: string }
}

export class PythonSandbox {
  private opts: SandboxOptions
  private replState: Map<string, string> = new Map()

  constructor(opts: SandboxOptions) {
    this.opts = opts
  }

  async execute(code: string, sessionId?: string): Promise<ExecResult> {
    const sandboxDir = join(tmpdir(), `pfaa-sandbox-${randomUUID()}`)
    await mkdir(sandboxDir, { recursive: true })

    let fullCode = code
    if (sessionId && this.replState.has(sessionId)) {
      fullCode = this.replState.get(sessionId)! + '\n\n' + code
    }

    const scriptPath = join(sandboxDir, 'script.py')
    await writeFile(scriptPath, fullCode, 'utf8')

    const start = Date.now()

    try {
      const proc = await execa(this.opts.pythonBin, [scriptPath], {
        timeout: this.opts.timeout,
        cwd: this.opts.workspace,
        env: {
          ...process.env,
          PYTHONPATH: this.opts.workspace,
          PYTHONWARNINGS: 'default',
          PYTHON_GIL: '0',
          ...(this.opts.allowNetwork ? {} : {
            http_proxy: 'http://127.0.0.1:0',
            https_proxy: 'http://127.0.0.1:0',
          }),
        },
        maxBuffer: 50 * 1024 * 1024,
      })

      if (sessionId && this.opts.persist) {
        this.replState.set(sessionId, fullCode)
      }

      return {
        stdout: proc.stdout,
        stderr: proc.stderr,
        durationMs: Date.now() - start,
      }
    } catch (err: any) {
      return {
        stdout: err.stdout ?? '',
        stderr: err.stderr ?? '',
        durationMs: Date.now() - start,
        error: {
          type: err.timedOut ? 'TimeoutError' : err.code ? 'ExitError' : 'RuntimeError',
          message: err.timedOut
            ? `Timed out after ${this.opts.timeout}ms`
            : err.stderr ?? err.message,
        },
      }
    } finally {
      await unlink(scriptPath).catch(() => {})
    }
  }
}
