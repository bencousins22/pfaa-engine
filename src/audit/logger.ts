/**
 * Tamper-evident audit logger — SHA-256 chained NDJSON per session.
 * Each entry includes a hash of the previous entry, creating an immutable chain.
 */

import { appendFile, mkdir } from 'fs/promises'
import { join } from 'path'
import { createHash, randomUUID } from 'crypto'

export interface AuditEntry {
  ts: string
  sessionId: string
  event: string
  data: Record<string, unknown>
  hash: string
}

export class AuditLogger {
  private sessionId = randomUUID()
  private entries: AuditEntry[] = []
  private auditDir: string
  private prevHash = ''

  constructor(auditDir: string = '.pfaa/audit') {
    this.auditDir = auditDir
  }

  logToolCall(tool: string, input: unknown, output: unknown): void {
    this.append('tool_call', { tool, input, output: String(output).slice(0, 500) })
  }

  logPermissionDenied(tool: string, reason: string): void {
    this.append('permission_denied', { tool, reason })
  }

  private append(event: string, data: Record<string, unknown>): void {
    const ts = new Date().toISOString()
    const payload = JSON.stringify({ ts, sessionId: this.sessionId, event, data, prev: this.prevHash })
    const hash = createHash('sha256').update(payload).digest('hex')
    const entry: AuditEntry = { ts, sessionId: this.sessionId, event, data, hash }
    this.prevHash = hash
    this.entries.push(entry)
  }

  async finalise(): Promise<void> {
    if (this.entries.length === 0) return
    await mkdir(this.auditDir, { recursive: true })
    const path = join(this.auditDir, `${this.sessionId}.ndjson`)
    const lines = this.entries.map(e => JSON.stringify(e)).join('\n')
    await appendFile(path, lines + '\n', 'utf8')
  }
}
