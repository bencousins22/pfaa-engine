/**
 * Memory tools — jmem-compatible memory_recall and memory_store.
 * Uses sentence-transformers (all-mpnet-base-v2) for embeddings,
 * same model as the Aussie Agents EMBEDDING_MODEL.
 *
 * Q-learning utility scoring:
 *   - Each recall increments retrieval_count
 *   - Agent can mark memories as success/failure
 *   - utility_score = (success_rate * 0.8) + (0.5 * 0.2) baseline
 */

import type { Tool, ToolDefinition } from './base.js'
import { MemoryStore, type FactType } from '../memory/store.js'

export class MemoryTool implements Tool {
  private store: MemoryStore

  constructor(qdrantUrl?: string) {
    this.store = new MemoryStore(qdrantUrl)
  }

  definitions(): ToolDefinition[] {
    return [
      {
        name: 'memory_recall',
        description: 'Search long-term memory using semantic similarity (sentence-transformers/all-mpnet-base-v2 embeddings → Qdrant). Returns relevant past interactions, learned facts, and stored knowledge. Use this to recall context from previous sessions.',
        input_schema: {
          type: 'object',
          properties: {
            query: { type: 'string', description: 'Semantic search query' },
            limit: { type: 'number', description: 'Max results (default 5)', default: 5 },
            area: { type: 'string', description: 'Memory area filter (main, solutions, fragments, or project name)' },
            fact_type: {
              type: 'string',
              description: 'Fact type filter',
              enum: ['episodic', 'semantic', 'procedural', 'foresight', 'profile', 'reflexion'],
            },
          },
          required: ['query'],
        },
      },
      {
        name: 'memory_store',
        description: 'Store important information in long-term memory for future recall. Use this to save key decisions, learned patterns, user preferences, and important facts that should persist across sessions.',
        input_schema: {
          type: 'object',
          properties: {
            content: { type: 'string', description: 'The information to remember' },
            area: { type: 'string', description: 'Memory area (main, solutions, fragments)', default: 'main' },
            fact_type: {
              type: 'string',
              description: 'Type of fact being stored',
              enum: ['episodic', 'semantic', 'procedural', 'foresight', 'profile', 'reflexion'],
              default: 'semantic',
            },
            tags: {
              type: 'array',
              items: { type: 'string' },
              description: 'Tags for categorization',
            },
          },
          required: ['content'],
        },
      },
      {
        name: 'memory_feedback',
        description: 'Provide feedback on a recalled memory to improve future retrieval. Mark memories as useful (success) or not useful (failure) to train the Q-learning utility scorer.',
        input_schema: {
          type: 'object',
          properties: {
            memory_id: { type: 'string', description: 'ID of the memory to rate' },
            useful: { type: 'boolean', description: 'Was this memory useful?' },
          },
          required: ['memory_id', 'useful'],
        },
      },
      {
        name: 'memory_stats',
        description: 'Get statistics about the memory store — total count, breakdown by area and fact type, availability status.',
        input_schema: {
          type: 'object',
          properties: {},
        },
      },
      {
        name: 'memory_consolidate',
        description: 'Promote high-quality episodic memories to semantic knowledge and prune low-value memories. Uses Q-learning scores to determine promotion eligibility.',
        input_schema: {
          type: 'object',
          properties: {
            min_q: { type: 'number', description: 'Minimum utility score for promotion (default 0.8)', default: 0.8 },
            min_retrievals: { type: 'number', description: 'Minimum retrieval count for promotion (default 3)', default: 3 },
          },
        },
      },
    ]
  }

  async execute(input: Record<string, any>): Promise<string> {
    // Route by which fields are present
    if ('query' in input) return this.recall(input)
    if ('memory_id' in input && 'useful' in input) return this.feedback(input)
    if ('min_q' in input || 'min_retrievals' in input) return this.consolidate(input)
    if ('content' in input) return this.store_(input)
    if (Object.keys(input).length === 0) return this.stats()
    return 'Unknown memory operation'
  }

  private async recall(input: Record<string, any>): Promise<string> {
    const results = await this.store.recall(
      input.query,
      input.limit ?? 5,
      {
        area: input.area,
        fact_type: input.fact_type as FactType,
      },
    )

    if (!results.length) return 'No relevant memories found.'

    const lines = results.map(r => {
      const score = r.score ? `${(r.score * 100).toFixed(0)}%` : '?'
      const area = (r.metadata.area as string) ?? '?'
      const type = (r.metadata.fact_type as string) ?? '?'
      const utility = ((r.metadata.utility_score as number) ?? 0).toFixed(2)
      return `[${score} match, area=${area}, type=${type}, utility=${utility}, id=${r.id.slice(0, 8)}]\n${r.content}`
    })

    return `Found ${results.length} memories:\n\n${lines.join('\n\n')}`
  }

  private async store_(input: Record<string, any>): Promise<string> {
    const id = await this.store.store(
      input.content,
      input.content,
      {
        area: input.area ?? 'main',
        fact_type: (input.fact_type as FactType) ?? 'semantic',
        tags: input.tags ?? [],
      },
    )

    if (id) {
      return `Memory stored (id=${id.slice(0, 8)}, area=${input.area ?? 'main'}, type=${input.fact_type ?? 'semantic'})`
    }
    return 'Failed to store memory (Qdrant may be unavailable)'
  }

  private async feedback(input: Record<string, any>): Promise<string> {
    const event = input.useful ? 'success' : 'failure'
    await this.store.updateUtility([input.memory_id], event)
    return `Memory ${input.memory_id.slice(0, 8)} marked as ${event}. Utility score updated.`
  }

  private async stats(): Promise<string> {
    const s = await this.store.stats()
    if (!s.available) return 'Memory store unavailable (Qdrant not reachable)'

    const areas = Object.entries(s.byArea).map(([k, v]) => `  ${k}: ${v}`).join('\n') || '  (none)'
    const types = Object.entries(s.byType).map(([k, v]) => `  ${k}: ${v}`).join('\n') || '  (none)'

    return `Memory Stats:\n  Total: ${s.total}\n  Available: ${s.available}\n\nBy Area:\n${areas}\n\nBy Type:\n${types}`
  }

  private async consolidate(input: Record<string, any>): Promise<string> {
    const result = await this.store.consolidate({
      minQ: input.min_q,
      minRetrievals: input.min_retrievals,
    })
    return `Consolidation complete: ${result.promoted} memories promoted (episodic → semantic), ${result.pruned} low-value memories pruned.`
  }
}
