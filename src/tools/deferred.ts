/**
 * Deferred tool loading — Anthropic's token-saving pattern.
 * Instead of sending all tool definitions upfront, send only a "tool_search" meta-tool.
 * The agent discovers tools on-demand by calling tool_search with a query.
 * Saves ~191K tokens. Opus accuracy: 49% → 74%.
 */

import type { Tool, ToolDefinition } from './base.js'

export class DeferredToolLoader implements Tool {
  private allDefs: ToolDefinition[]

  constructor(allDefs: ToolDefinition[]) {
    this.allDefs = allDefs
  }

  definitions(): ToolDefinition[] {
    return [{
      name: 'tool_search',
      description: 'Search for available tools by keyword. Use this to discover what tools are available before calling them. Returns tool names, descriptions, and input schemas.',
      input_schema: {
        type: 'object',
        properties: {
          query: { type: 'string', description: 'Search query — describe what you want to do' },
          max_results: { type: 'number', description: 'Max tools to return', default: 5 },
        },
        required: ['query'],
      },
    }]
  }

  async execute(input: Record<string, any>): Promise<string> {
    const query = (input.query as string).toLowerCase()
    const max = input.max_results ?? 5

    // Score each tool by keyword match against name + description
    const scored = this.allDefs.map(def => {
      const text = `${def.name} ${def.description}`.toLowerCase()
      const queryWords = query.split(/\s+/)
      const score = queryWords.filter(w => text.includes(w)).length / queryWords.length
      return { def, score }
    })
    .filter(s => s.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, max)

    if (!scored.length) {
      return `No tools match "${query}". Available tools: ${this.allDefs.map(d => d.name).join(', ')}`
    }

    const results = scored.map(s => ({
      name: s.def.name,
      description: s.def.description,
      input_schema: s.def.input_schema,
    }))

    return JSON.stringify(results, null, 2)
  }
}
