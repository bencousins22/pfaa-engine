/**
 * JMEM tools — wraps the jmem MCP server as agent tools.
 *
 * 5-layer cognitive memory: episode → concept → principle → skill
 * Q-learning reinforcement, Zettelkasten graph traversal, auto-consolidation.
 * Pure Python backend (SQLite FTS5 + TF-IDF, zero external deps).
 *
 * The agent gets 7 tools: recall, remember, consolidate, reflect, reward, evolve, status.
 */

import type { Tool, ToolDefinition } from './base.js'
import { execa } from 'execa'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

export class JMemTool implements Tool {
  private pythonBin: string

  constructor(pythonBin = 'python3') {
    this.pythonBin = pythonBin
  }

  definitions(): ToolDefinition[] {
    return [
      {
        name: 'jmem_recall',
        description: 'Search JMEM semantic memory using TF-IDF + Zettelkasten graph traversal. Returns memories ranked by relevance and Q-value. Memories are organized in a hierarchy: episode (facts) → concept (patterns) → principle (rules) → skill (capabilities). Higher-level memories have been reinforced through repeated successful use.',
        input_schema: {
          type: 'object',
          properties: {
            query: { type: 'string', description: 'Natural language search query' },
            top_k: { type: 'number', description: 'Max results (default 5)', default: 5 },
            graph_walk: { type: 'boolean', description: 'Follow Zettelkasten backlinks for related memories', default: true },
          },
          required: ['query'],
        },
      },
      {
        name: 'jmem_remember',
        description: 'Store important information in JMEM for cross-session persistence. Memories start as episodes and get automatically promoted to concepts, principles, and skills as they prove useful through Q-learning reinforcement.',
        input_schema: {
          type: 'object',
          properties: {
            content: { type: 'string', description: 'The information to remember' },
            context: { type: 'string', description: 'When/where this applies', default: '' },
            keywords: { type: 'array', items: { type: 'string' }, description: 'Keywords for clustering and retrieval' },
            tags: { type: 'array', items: { type: 'string' }, description: 'Tags for categorization' },
            level: { type: 'string', enum: ['episode', 'concept', 'principle', 'skill'], default: 'episode' },
          },
          required: ['content'],
        },
      },
      {
        name: 'jmem_reward',
        description: 'Reinforce a memory via Q-learning. Positive reward (0.0-1.0) increases Q-value, making the memory surface more in future searches. Negative reward decreases it. Strong signals (>0.85) update fast.',
        input_schema: {
          type: 'object',
          properties: {
            note_id: { type: 'string', description: 'ID of the memory to reinforce' },
            reward: { type: 'number', description: 'Reward signal: 0.0 (useless) to 1.0 (very useful)' },
            context: { type: 'string', description: 'Why this reward was given', default: '' },
          },
          required: ['note_id', 'reward'],
        },
      },
      {
        name: 'jmem_evolve',
        description: 'Update an existing memory in place — change content, add keywords, add tags, update context.',
        input_schema: {
          type: 'object',
          properties: {
            note_id: { type: 'string', description: 'ID of the memory to update' },
            content: { type: 'string', description: 'New content (replaces existing)' },
            add_keywords: { type: 'array', items: { type: 'string' }, description: 'Keywords to add' },
            add_tags: { type: 'array', items: { type: 'string' }, description: 'Tags to add' },
            context: { type: 'string', description: 'New context' },
          },
          required: ['note_id'],
        },
      },
      {
        name: 'jmem_consolidate',
        description: 'Run memory consolidation: link related memories via Zettelkasten, auto-promote high-Q episodes to concepts/principles/skills, synthesize keyword clusters, decay stale memories.',
        input_schema: { type: 'object', properties: {} },
      },
      {
        name: 'jmem_reflect',
        description: 'Full cognitive cycle — consolidation + health analysis. Returns: memory counts by level, Q-value distribution, learning health (excellent/healthy/needs_attention/critical), knowledge maturity.',
        input_schema: { type: 'object', properties: {} },
      },
      {
        name: 'jmem_status',
        description: 'JMEM health report: counts by level, average Q-value, linked/evolved counts, store backend info.',
        input_schema: { type: 'object', properties: {} },
      },
    ]
  }

  async execute(input: Record<string, any>): Promise<string> {
    // Determine which tool was called by checking input fields
    let toolName: string
    if ('query' in input) toolName = 'jmem_recall'
    else if ('content' in input && !('note_id' in input)) toolName = 'jmem_remember'
    else if ('reward' in input) toolName = 'jmem_reward'
    else if ('note_id' in input) toolName = 'jmem_evolve'
    else toolName = 'jmem_status'

    return this.callJMem(toolName, input)
  }

  private async callJMem(toolName: string, args: Record<string, any>): Promise<string> {
    const scriptPath = resolve(__dirname, '../../python/jmem/server.py')

    // Build a JSON-RPC request
    const request = {
      jsonrpc: '2.0',
      id: 1,
      method: 'tools/call',
      params: { name: toolName, arguments: args },
    }

    // We need to initialize first, then call the tool
    const initRequest = { jsonrpc: '2.0', id: 0, method: 'initialize', params: {} }
    const input = JSON.stringify(initRequest) + '\n' + JSON.stringify(request) + '\n'

    try {
      const result = await execa(this.pythonBin, ['-m', 'jmem'], {
        input,
        env: {
          ...process.env,
          PYTHONPATH: resolve(__dirname, '../../python'),
          JMEM_AGENT: 'pfaa',
        },
        timeout: 30000,
        maxBuffer: 10 * 1024 * 1024,
      })

      // Parse the last JSON-RPC response
      const lines = result.stdout.trim().split('\n')
      for (let i = lines.length - 1; i >= 0; i--) {
        try {
          const resp = JSON.parse(lines[i])
          if (resp.result?.content?.[0]?.text) {
            return resp.result.content[0].text
          }
          if (resp.result) {
            return JSON.stringify(resp.result, null, 2)
          }
        } catch { continue }
      }

      return result.stdout || 'No response from JMEM'
    } catch (err: any) {
      return `JMEM error: ${err.message}`
    }
  }
}
