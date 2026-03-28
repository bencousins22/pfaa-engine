/**
 * Base provider interface for AI model providers.
 * Supports Claude + Gemini with streaming tool use.
 */

export interface Message {
  role: 'user' | 'assistant'
  content: string | ContentBlock[]
}

export interface ContentBlock {
  type: string
  [key: string]: unknown
}

export interface CompleteOpts {
  system: string
  messages: Message[]
  maxTokens?: number
}

export interface CompleteResult {
  content: string
  inputTokens: number
  outputTokens: number
}

export interface StreamChunk {
  type: 'text' | 'tool_use' | 'stop'
  text?: string
  id?: string
  name?: string
  input?: Record<string, unknown>
  stopReason?: string
}

export type StreamWithToolsResult = AsyncGenerator<StreamChunk, void, unknown>

export interface BaseProvider {
  complete(opts: CompleteOpts): Promise<CompleteResult>
  streamWithTools(opts: {
    system: string
    messages: Message[]
    tools: ToolDefinition[]
    maxTokens: number
  }): StreamWithToolsResult
  summarise(text: string): Promise<string>
}

export interface ToolDefinition {
  name: string
  description: string
  input_schema: Record<string, unknown>
}
