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
