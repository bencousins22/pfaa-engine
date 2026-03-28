/**
 * Claude Agent SDK provider — uses the native query() async generator.
 * Same engine Claude Code uses internally.
 *
 * Falls back to standard Claude provider if Agent SDK is not installed.
 *
 * Usage: pfaa --provider claude-agent-sdk run "fix the bug"
 */

import type { BaseProvider, CompleteOpts, CompleteResult, StreamWithToolsResult, ToolDefinition, Message } from './base.js'

export class ClaudeAgentSDKProvider implements BaseProvider {
  private model: string
  private available: boolean | null = null

  constructor(opts: { model?: string }) {
    this.model = opts.model ?? 'claude-sonnet-4-6'
  }

  private async checkAvailable(): Promise<boolean> {
    if (this.available !== null) return this.available
    try {
      // @ts-ignore — optional dependency
      await import('@anthropic-ai/claude-agent-sdk')
      this.available = true
    } catch {
      this.available = false
    }
    return this.available
  }

  async complete(opts: CompleteOpts): Promise<CompleteResult> {
    if (!await this.checkAvailable()) {
      // Fallback to standard SDK
      const { ClaudeProvider } = await import('./claude.js')
      const fallback = new ClaudeProvider({ model: this.model })
      return fallback.complete(opts)
    }

    const { query } = // @ts-ignore — optional dependency
      await import('@anthropic-ai/claude-agent-sdk')
    let output = ''

    for await (const message of query({
      prompt: typeof opts.messages.at(-1)?.content === 'string'
        ? opts.messages.at(-1)!.content as string
        : JSON.stringify(opts.messages.at(-1)?.content),
      options: {
        model: this.model,
        systemPrompt: opts.system,
        maxTurns: 1,
      },
    })) {
      if (typeof message === 'string') output += message
      else if (message && typeof message === 'object' && 'content' in message) {
        output += String((message as any).content ?? '')
      }
    }

    return { content: output, inputTokens: 0, outputTokens: 0 }
  }

  async *streamWithTools(opts: {
    system: string
    messages: Message[]
    tools: ToolDefinition[]
    maxTokens: number
  }): StreamWithToolsResult {
    if (!await this.checkAvailable()) {
      // Fallback to standard Claude streaming
      const { ClaudeProvider } = await import('./claude.js')
      const fallback = new ClaudeProvider({ model: this.model })
      yield* fallback.streamWithTools(opts)
      return
    }

    const { query } = // @ts-ignore — optional dependency
      await import('@anthropic-ai/claude-agent-sdk')

    const lastMessage = opts.messages.at(-1)
    const prompt = typeof lastMessage?.content === 'string'
      ? lastMessage.content
      : JSON.stringify(lastMessage?.content ?? '')

    // Map our tool definitions to Agent SDK allowed tools format
    const allowedTools = opts.tools.map(t => t.name)

    try {
      for await (const message of query({
        prompt,
        options: {
          model: this.model,
          systemPrompt: opts.system,
          allowedTools,
          maxTurns: 20,
        },
      })) {
        // The Agent SDK emits different message types
        if (typeof message === 'string') {
          yield { type: 'text', text: message }
        } else if (message && typeof message === 'object') {
          const msg = message as any

          // Text content
          if (msg.type === 'text' || msg.content) {
            yield { type: 'text', text: String(msg.content ?? msg.text ?? '') }
          }

          // Tool use
          if (msg.type === 'tool_use' || msg.tool_name) {
            yield {
              type: 'tool_use',
              id: msg.id ?? msg.tool_use_id ?? 'sdk',
              name: msg.tool_name ?? msg.name,
              input: msg.input ?? msg.arguments ?? {},
            }
          }
        }
      }
    } catch (err: any) {
      yield { type: 'text', text: `Agent SDK error: ${err.message}` }
    }

    yield { type: 'stop', stopReason: 'end_turn' }
  }

  async summarise(text: string): Promise<string> {
    const result = await this.complete({
      system: 'Summarise concisely, preserving key decisions, code, and facts.',
      messages: [{ role: 'user', content: text }],
      maxTokens: 2048,
    })
    return result.content
  }
}
