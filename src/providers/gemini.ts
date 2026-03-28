/**
 * Gemini provider — uses @google/generative-ai for streaming + function calling.
 * Supports Gemini 2.5 Pro with native tool use.
 */

import { GoogleGenerativeAI, type GenerativeModel } from '@google/generative-ai'
import type { BaseProvider, CompleteOpts, CompleteResult, StreamWithToolsResult, ToolDefinition, Message } from './base.js'

export class GeminiProvider implements BaseProvider {
  private model: GenerativeModel
  private modelName: string

  constructor(opts: { model?: string }) {
    const apiKey = process.env.GEMINI_API_KEY
    if (!apiKey) throw new Error('GEMINI_API_KEY environment variable required')
    const genai = new GoogleGenerativeAI(apiKey)
    this.modelName = opts.model ?? 'gemini-2.5-pro'
    this.model = genai.getGenerativeModel({ model: this.modelName })
  }

  async complete(opts: CompleteOpts): Promise<CompleteResult> {
    const chat = this.model.startChat({
      systemInstruction: opts.system,
      history: opts.messages.slice(0, -1).map(m => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: typeof m.content === 'string' ? m.content : JSON.stringify(m.content) }],
      })),
    })
    const last = opts.messages.at(-1)!
    const lastContent = typeof last.content === 'string' ? last.content : JSON.stringify(last.content)
    const result = await chat.sendMessage(lastContent)
    const text = result.response.text()
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

    const chat = this.model.startChat({
      systemInstruction: opts.system,
      tools: [{ functionDeclarations }] as any,
      history: opts.messages.slice(0, -1).map(m => ({
        role: m.role === 'assistant' ? 'model' : 'user',
        parts: [{ text: typeof m.content === 'string' ? m.content : JSON.stringify(m.content) }],
      })),
    })

    const last = opts.messages.at(-1)!
    const lastContent = typeof last.content === 'string' ? last.content : JSON.stringify(last.content)
    const result = await chat.sendMessageStream(lastContent)

    for await (const chunk of result.stream) {
      const text = chunk.text()
      if (text) yield { type: 'text', text }

      const calls = chunk.functionCalls()
      if (calls?.length) {
        for (const call of calls) {
          yield { type: 'tool_use', id: call.name, name: call.name, input: call.args as Record<string, unknown> }
        }
      }
    }

    yield { type: 'stop', stopReason: 'end_turn' }
  }

  async summarise(text: string): Promise<string> {
    const result = await this.model.generateContent(
      `Summarise this conversation concisely, preserving key decisions, code, and facts:\n\n${text}`
    )
    return result.response.text()
  }
}
