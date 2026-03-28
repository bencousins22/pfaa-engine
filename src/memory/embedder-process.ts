/**
 * Persistent embedder subprocess — keeps sentence-transformers model loaded.
 * Avoids reloading all-mpnet-base-v2 (420MB) on every embed call.
 */

import { spawn, type ChildProcess } from 'child_process'
import { createInterface } from 'readline'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

export class EmbedderProcess {
  private proc: ChildProcess | null = null
  ready = false
  private dim = 768
  private queue: Array<{ texts: string[]; resolve: (vecs: number[][]) => void; reject: (e: Error) => void }> = []
  private pending: typeof this.queue[0] | null = null

  async start(pythonBin = 'python3', model = 'sentence-transformers/all-mpnet-base-v2'): Promise<void> {
    const scriptPath = resolve(__dirname, '../../python/memory/embedder.py')
    this.proc = spawn(pythonBin, [scriptPath, '--model', model], {
      stdio: ['pipe', 'pipe', 'pipe'],
    })

    const rl = createInterface({ input: this.proc.stdout! })

    rl.on('line', (line) => {
      try {
        const msg = JSON.parse(line)
        if (msg.status === 'ready') {
          this.dim = msg.dim
          this.ready = true
          this.flush()
          return
        }
        if (this.pending) {
          if (msg.vectors) this.pending.resolve(msg.vectors)
          else this.pending.reject(new Error(msg.error ?? 'embed failed'))
          this.pending = null
          this.flush()
        }
      } catch { /* ignore parse errors */ }
    })

    this.proc.stderr?.on('data', () => {}) // suppress stderr

    // Wait for ready with timeout
    await new Promise<void>((res, rej) => {
      const t = setTimeout(() => rej(new Error('embedder timeout')), 30000)
      const check = setInterval(() => {
        if (this.ready) { clearInterval(check); clearTimeout(t); res() }
      }, 100)
    })
  }

  async embed(texts: string[]): Promise<number[][]> {
    return new Promise((resolve, reject) => {
      this.queue.push({ texts, resolve, reject })
      this.flush()
    })
  }

  private flush(): void {
    if (!this.ready || this.pending || !this.queue.length) return
    this.pending = this.queue.shift()!
    this.proc!.stdin!.write(JSON.stringify({ texts: this.pending.texts }) + '\n')
  }

  get dimension(): number { return this.dim }

  stop(): void {
    this.proc?.kill()
    this.proc = null
    this.ready = false
  }
}

export const embedder = new EmbedderProcess()
