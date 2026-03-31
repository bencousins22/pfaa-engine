/**
 * JMEM Client — Semantic Memory Integration via MCP.
 *
 * Connects to the JMEM MCP server for persistent semantic memory
 * across agent sessions. Implements the 5-layer cognitive model:
 *
 *   L1 Episodic → L2 Semantic → L3 Strategic → L4 Meta-Learning → L5 Emergent
 *
 * Uses Q-learning reinforcement for memory scoring and automatic
 * knowledge promotion (episode → concept → principle → skill).
 */

import { EventEmitter } from 'node:events';
import { getLogger } from '../utils/logger.js';
import type { MemoryEntry, MemoryLayer, MemoryStatus } from '../types.js';

const log = getLogger('jmem');

export interface JMEMConfig {
  serverUrl: string;
  serverCommand?: string;
  namespace: string;
  maxEpisodes: number;
  promotionThreshold: number;
  qLearningRate: number;
  qDiscountFactor: number;
}

const DEFAULT_JMEM_CONFIG: JMEMConfig = {
  serverUrl: process.env.JMEM_SERVER_URL || 'http://localhost:3100',
  serverCommand: 'python -m jmem.server',
  namespace: 'pfaa-cli',
  maxEpisodes: 10_000,
  promotionThreshold: 0.8,
  qLearningRate: 0.1,
  qDiscountFactor: 0.95,
};

/**
 * MCP tool call interface for JMEM server communication.
 */
interface MCPToolCall {
  name: string;
  arguments: Record<string, unknown>;
}

interface MCPToolResult {
  content: Array<{ type: string; text: string }>;
  isError?: boolean;
}

export class JMEMClient extends EventEmitter {
  private config: JMEMConfig;
  private connected = false;
  private cache = new Map<string, { entries: MemoryEntry[]; ts: number }>();
  private cacheMaxAge = 60_000; // 1 minute

  constructor(config: Partial<JMEMConfig> = {}) {
    super();
    this.config = { ...DEFAULT_JMEM_CONFIG, ...config };
  }

  async connect(): Promise<void> {
    log.info('Connecting to JMEM MCP server', {
      url: this.config.serverUrl,
      namespace: this.config.namespace,
    });

    // In MCP mode, the connection is managed by the MCP client.
    // Here we verify the server is reachable.
    try {
      const tools = await this.callMCP('jmem_status', {});
      this.connected = true;
      log.info('JMEM connected', { tools });
    } catch (err) {
      log.warn('JMEM server not available, using local fallback', {
        error: err instanceof Error ? err.message : String(err),
      });
      this.connected = false;
    }
  }

  get isConnected(): boolean {
    return this.connected;
  }

  // ── Core Memory Operations (17 JMEM MCP Tools) ─────────────────

  async store(
    content: string,
    layer: number = 1,
    metadata: Record<string, unknown> = {},
  ): Promise<string> {
    const result = await this.callMCP('jmem_store', {
      content,
      layer,
      namespace: this.config.namespace,
      metadata,
    });
    const id = this.extractText(result);
    log.debug('Stored memory', { id, layer });
    return id;
  }

  async recall(
    query: string,
    layer?: number,
    limit: number = 10,
  ): Promise<MemoryEntry[]> {
    // Check cache first
    const cacheKey = `${query}:${layer}:${limit}`;
    const cached = this.cache.get(cacheKey);
    if (cached && Date.now() - cached.ts < this.cacheMaxAge) {
      return cached.entries;
    }

    const result = await this.callMCP('jmem_recall', {
      query,
      layer,
      limit,
      namespace: this.config.namespace,
    });

    const entries = this.parseEntries(result);
    if (entries.length > 0) {
      this.cache.set(cacheKey, { entries, ts: Date.now() });
    }
    return entries;
  }

  async search(
    query: string,
    options: {
      layer?: number;
      minScore?: number;
      limit?: number;
    } = {},
  ): Promise<MemoryEntry[]> {
    const result = await this.callMCP('jmem_search', {
      query,
      ...options,
      namespace: this.config.namespace,
    });
    return this.parseEntries(result);
  }

  async reinforce(
    entryId: string,
    reward: number,
    context: string = '',
  ): Promise<void> {
    await this.callMCP('jmem_reinforce', {
      entry_id: entryId,
      reward,
      context,
      learning_rate: this.config.qLearningRate,
      discount_factor: this.config.qDiscountFactor,
    });
    log.debug('Reinforced memory', { entryId, reward });
  }

  async promote(entryId: string): Promise<void> {
    await this.callMCP('jmem_promote', {
      entry_id: entryId,
      namespace: this.config.namespace,
    });
    log.debug('Promoted memory', { entryId });
  }

  async forget(entryId: string): Promise<void> {
    await this.callMCP('jmem_forget', {
      entry_id: entryId,
      namespace: this.config.namespace,
    });
    this.cache.delete(entryId);
    log.debug('Forgot memory', { entryId });
  }

  async consolidate(): Promise<{
    promoted: number;
    pruned: number;
    merged: number;
  }> {
    const result = await this.callMCP('jmem_consolidate', {
      namespace: this.config.namespace,
      threshold: this.config.promotionThreshold,
    });
    const stats = JSON.parse(this.extractText(result));
    log.info('Memory consolidated', stats);
    return stats;
  }

  async status(): Promise<MemoryStatus> {
    if (!this.connected) {
      return {
        l1Episodes: 0,
        l2Patterns: 0,
        l3Strategies: 0,
        l4LearningRate: this.config.qLearningRate,
        l5Knowledge: 0,
        dbSizeKb: 0,
      };
    }

    const result = await this.callMCP('jmem_status', {
      namespace: this.config.namespace,
    });
    return JSON.parse(this.extractText(result));
  }

  // ── Context-Aware Memory ─────────────────────────────────────────

  /**
   * Record an agent action with full context for learning.
   */
  async recordAction(
    action: string,
    result: unknown,
    context: {
      agent: string;
      tool?: string;
      phase?: string;
      elapsedMs?: number;
      success: boolean;
    },
  ): Promise<string> {
    const content = JSON.stringify({
      action,
      result: typeof result === 'string' ? result.slice(0, 500) : result,
      ...context,
      timestamp: Date.now(),
    });

    const entryId = await this.store(content, 1, {
      type: 'action',
      agent: context.agent,
      tool: context.tool,
      success: context.success,
    });

    // Auto-reinforce based on success
    const reward = context.success ? 1.0 : -0.5;
    await this.reinforce(entryId, reward, action);

    return entryId;
  }

  /**
   * Get relevant context before executing a task.
   */
  async getContext(
    task: string,
    limit: number = 5,
  ): Promise<{
    relevant: MemoryEntry[];
    strategies: MemoryEntry[];
    knowledge: MemoryEntry[];
  }> {
    const [relevant, strategies, knowledge] = await Promise.all([
      this.recall(task, 1, limit),     // L1: episodic
      this.recall(task, 3, 3),         // L3: strategic
      this.recall(task, 5, 3),         // L5: emergent
    ]);

    return { relevant, strategies, knowledge };
  }

  /**
   * Learn from a completed pipeline — batch memory update.
   */
  async learnFromPipeline(
    goal: string,
    results: Array<{ action: string; success: boolean; elapsedMs: number }>,
  ): Promise<void> {
    // Store each result as L1 episode
    for (const r of results) {
      await this.store(
        JSON.stringify(r),
        1,
        { goal, type: 'pipeline_result' },
      );
    }

    // Consolidate to promote patterns to higher layers
    const stats = await this.consolidate();
    log.info('Pipeline learning complete', {
      goal: goal.slice(0, 60),
      results: results.length,
      ...stats,
    });
  }

  // ── Internal ─────────────────────────────────────────────────────

  private async callMCP(
    toolName: string,
    args: Record<string, unknown>,
  ): Promise<MCPToolResult> {
    if (!this.connected && toolName !== 'jmem_status') {
      // Return empty result for non-status calls when disconnected
      return { content: [{ type: 'text', text: '[]' }] };
    }

    // In production, this would use the MCP client transport.
    // For now, simulate via HTTP to the JMEM server.
    // Retry with exponential backoff for transient failures.
    const MAX_RETRIES = 3;
    const BASE_DELAY_MS = 200;

    for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
      try {
        const response = await fetch(`${this.config.serverUrl}/mcp/tool`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: toolName, arguments: args }),
          signal: AbortSignal.timeout(10_000),
        });

        // Retry on server errors (5xx)
        if (response.status >= 500 && attempt < MAX_RETRIES) {
          const delay = BASE_DELAY_MS * 2 ** attempt;
          log.debug(`JMEM ${toolName} returned ${response.status}, retrying in ${delay}ms`, {
            attempt: attempt + 1,
          });
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }

        if (!response.ok) {
          throw new Error(`JMEM MCP call failed: ${response.status}`);
        }

        return await response.json() as MCPToolResult;
      } catch (err) {
        const isRetryable =
          err instanceof TypeError || // fetch network error (connection refused)
          (err instanceof DOMException && err.name === 'TimeoutError') ||
          (err instanceof Error && err.message.includes('ECONNREFUSED'));

        if (isRetryable && attempt < MAX_RETRIES) {
          const delay = BASE_DELAY_MS * 2 ** attempt;
          log.debug(`JMEM ${toolName} failed (attempt ${attempt + 1}), retrying in ${delay}ms`, {
            error: err instanceof Error ? err.message : String(err),
          });
          await new Promise((r) => setTimeout(r, delay));
          continue;
        }

        if (toolName === 'jmem_status') throw err;
        log.debug(`JMEM call failed: ${toolName}`, {
          error: err instanceof Error ? err.message : String(err),
          attempts: attempt + 1,
        });
        return { content: [{ type: 'text', text: '[]' }] };
      }
    }

    // Unreachable, but satisfies TypeScript return type
    return { content: [{ type: 'text', text: '[]' }] };
  }

  private extractText(result: MCPToolResult): string {
    const textContent = result.content?.find((c) => c.type === 'text');
    return textContent?.text || '';
  }

  private parseEntries(result: MCPToolResult): MemoryEntry[] {
    try {
      const text = this.extractText(result);
      return JSON.parse(text) as MemoryEntry[];
    } catch {
      return [];
    }
  }
}
