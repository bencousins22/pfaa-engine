/**
 * Gemini provider — uses @google/genai v1.46+ (the current official SDK).
 * NOTE: @google/generative-ai is DEPRECATED as of Aug 2025.
 * Supports Gemini 2.5 Pro/Flash with native function calling.
 */

import { GoogleGenAI } from '@google/genai'
import type { BaseProvider, CompleteOpts, CompleteResult, StreamWithToolsResult, ToolDefinition, Message } from './base.js'

export class GeminiProvider implements BaseProvider {
  private ai: GoogleGenAI
  private modelName: string

  constructor(opts: { model?: string }) {
    const apiKey = process.env.GEMINI_API_KEY
    if (!apiKey) throw new Error('GEMINI_API_KEY environment variable required')
    this.ai = new GoogleGenAI({ apiKey })
    this.modelName = opts.model ?? 'gemini-2.5-pro'
  }

  async complete(opts: CompleteOpts): Promise<CompleteResult> {
    const contents = opts.messages.map(m => ({
      role: m.role === 'assistant' ? 'model' : 'user',
      parts: [{ text: typeof m.content === 'string' ? m.content : JSON.stringify(m.content) }],
    }))

    const response = await this.ai.models.generateContent({
      model: this.modelName,
      contents,
      config: {
        systemInstruction: opts.system,
        maxOutputTokens: opts.maxTokens ?? 4096,
      },
    })

    const text = response.text ?? ''
    return { content: text, inputTokens: 0, outputTokens: 0 }
  }

  async *streamWithTools(opts: {
    system: string
    messages: Message[]
    tools: ToolDefinition[]
    maxTokens: number
  }): StreamWithToolsResult {
    const functionDeclarations = opts.tools.map(t => ({
      name: t.name,
      description: t.description,
      parameters: t.input_schema,
    }))

    const contents = opts.messages.map(m => ({
      role: m.role === 'assistant' ? 'model' : 'user',
      parts: [{ text: typeof m.content === 'string' ? m.content : JSON.stringify(m.content) }],
    }))

    const response = await this.ai.models.generateContentStream({
      model: this.modelName,
      contents,
      config: {
        systemInstruction: opts.system,
        tools: [{ functionDeclarations }] as any,
        maxOutputTokens: opts.maxTokens,
      },
    })

    for await (const chunk of response) {
      const text = chunk.text
      if (text) yield { type: 'text', text }

      const calls = chunk.functionCalls
      if (calls?.length) {
        for (const call of calls) {
          yield { type: 'tool_use', id: call.name!, name: call.name!, input: (call.args ?? {}) as Record<string, unknown> }
        }
      }
    }

    yield { type: 'stop', stopReason: 'end_turn' }
  }

  async summarise(text: string): Promise<string> {
    const response = await this.ai.models.generateContent({
      model: this.modelName,
      contents: `Summarise this conversation concisely, preserving key decisions, code, and facts:\n\n${text}`,
    })
    return response.text ?? ''
  }
}
