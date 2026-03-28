/**
 * Fetch tool — HTTP GET with content extraction.
 */

import type { Tool, ToolDefinition } from './base.js'

export class FetchTool implements Tool {
  definitions(): ToolDefinition[] {
    return [{
      name: 'web_fetch',
      description: 'Fetch content from a URL via HTTP GET. Returns up to 5000 chars of text.',
      input_schema: {
        type: 'object',
        properties: {
          url: { type: 'string', description: 'URL to fetch' },
          timeout: { type: 'number', description: 'Timeout in ms', default: 15000 },
        },
        required: ['url'],
      },
    }]
  }

  async execute(input: Record<string, any>): Promise<string> {
    try {
      const controller = new AbortController()
      const timer = setTimeout(() => controller.abort(), input.timeout ?? 15000)
      const resp = await fetch(input.url, { signal: controller.signal })
      clearTimeout(timer)
      const text = await resp.text()
      return text.slice(0, 5000)
    } catch (err: any) {
      return `Fetch error: ${err.message}`
    }
  }
}
