/**
 * Context manager — tracks conversation state, token estimates, and auto-compaction.
 * Mirrors Claude Code's auto-compact context windows.
 */

import { randomUUID } from 'crypto'
import type { BaseProvider } from '../providers/base.js'

interface Message {
  role: 'user' | 'assistant'
  content: string | unknown[]
}

export class ContextManager {
  readonly sessionId = randomUUID()
  system = ''
  messages: Message[] = []
  tokenCount = 0

  constructor(private compactThreshold: number) {}

  init(system: string): void {
    this.system = system
    this.tokenCount = Math.ceil(system.length / 4)
  }

  addMessage(msg: Message): void {
    this.messages.push(msg)
    this.tokenCount += Math.ceil(JSON.stringify(msg).length / 4)
  }

  appendAssistantText(text: string): void {
    const last = this.messages.at(-1)
    if (last?.role === 'assistant' && typeof last.content === 'string') {
      last.content += text
    } else {
      this.messages.push({ role: 'assistant', content: text })
    }
    this.tokenCount += Math.ceil(text.length / 4)
  }

  addToolResult(toolUseId: string, result: string): void {
    this.messages.push({
      role: 'user',
      content: [{ type: 'tool_result', tool_use_id: toolUseId, content: result }],
    })
    this.tokenCount += Math.ceil(result.length / 4)
  }

  lastAssistantText(): string {
    for (let i = this.messages.length - 1; i >= 0; i--) {
      const m = this.messages[i]
      if (m.role === 'assistant' && typeof m.content === 'string') return m.content
    }
    return ''
  }

  async compact(provider: BaseProvider): Promise<void> {
    if (this.messages.length <= 6) return
    const head = this.messages.slice(0, 2)
    const tail = this.messages.slice(-4)
    const middle = this.messages.slice(2, -4)
    const summary = await provider.summarise(
      middle.map(m =>
        `${m.role}: ${typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}`
      ).join('\n')
    )
    this.messages = [
      ...head,
      { role: 'user', content: `[Context summary]\n${summary}` },
      ...tail,
    ]
    this.tokenCount = Math.ceil(JSON.stringify(this.messages).length / 4)
  }
}
