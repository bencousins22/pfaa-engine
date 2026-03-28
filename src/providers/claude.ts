/**
 * Claude provider — uses @anthropic-ai/sdk for streaming tool use.
 * Supports the latest Claude 4.x models with extended thinking.
 */

import Anthropic from '@anthropic-ai/sdk'
import type { BaseProvider, CompleteOpts, CompleteResult, StreamWithToolsResult, ToolDefinition, Message } from './base.js'

export class ClaudeProvider implements BaseProvider {
  private client: Anthropic
  private model: string

  constructor(opts: { model?: string }) {
    this.client = new Anthropic()
    this.model = opts.model ?? 'claude-sonnet-4-6'
  }

  async complete(opts: CompleteOpts): Promise<CompleteResult> {
    const resp = await this.client.messages.create({
      model: this.model,
      system: opts.system,
      messages: opts.messages as Anthropic.MessageParam[],
      max_tokens: opts.maxTokens ?? 4096,
    })
    const content = resp.content[0]?.type === 'text' ? resp.content[0].text : ''
    return {
      content,
      inputTokens: resp.usage.input_tokens,
      outputTokens: resp.usage.output_tokens,
    }
  }

  async *streamWithTools(opts: {
    system: string
    messages: Message[]
    tools: ToolDefinition[]
    maxTokens: number
  }): StreamWithToolsResult {
    const stream = this.client.messages.stream({
      model: this.model,
      system: opts.system,
      messages: opts.messages as Anthropic.MessageParam[],
      tools: opts.tools as Anthropic.Tool[],
      max_tokens: opts.maxTokens,
    })

    let currentToolUse: { id: string; name: string; inputJson: string } | null = null

    for await (const event of stream) {
      if (event.type === 'content_block_start') {
        const block = (event as any).content_block
        if (block?.type === 'tool_use') {
          currentToolUse = { id: block.id, name: block.name, inputJson: '' }
        }
      }
      if (event.type === 'content_block_delta') {
        const delta = (event as any).delta
        if (delta?.type === 'text_delta') {
          yield { type: 'text', text: delta.text }
        }
        if (delta?.type === 'input_json_delta' && currentToolUse) {
          currentToolUse.inputJson += delta.partial_json
        }
      }
      if (event.type === 'content_block_stop' && currentToolUse) {
        yield {
          type: 'tool_use',
          id: currentToolUse.id,
          name: currentToolUse.name,
          input: JSON.parse(currentToolUse.inputJson || '{}'),
        }
        currentToolUse = null
      }
      if (event.type === 'message_delta') {
        const delta = (event as any).delta
        yield { type: 'stop', stopReason: delta?.stop_reason ?? 'end_turn' }
      }
    }
  }

  async summarise(text: string): Promise<string> {
    const resp = await this.complete({
      system: 'Summarise the following conversation history concisely, preserving all key decisions, code written, and facts established.',
      messages: [{ role: 'user', content: text }],
      maxTokens: 2048,
    })
    return resp.content
  }
}
