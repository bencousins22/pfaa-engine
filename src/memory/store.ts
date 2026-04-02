/**
 * Aussie Agents Memory Store — jmem-compatible MCP memory with Qdrant backend.
 *
 * Features (matching jmem-mcp-server patterns):
 *   - Semantic search via sentence-transformers embeddings
 *   - Memory areas (main, solutions, fragments, per-project)
 *   - Fact types (episodic, semantic, procedural, foresight, profile, reflexion)
 *   - Utility scoring with Q-learning decay
 *   - Soft delete via valid_to timestamps
 *   - Trust scoring for multi-agent memory sharing
 *   - Full CRUD: store, recall, list, forget, stats
 *
 * Degrades gracefully when Qdrant is unavailable.
 */

import { randomUUID } from 'crypto'
import { embedder } from './embedder-process.js'

/** Typed wrapper for Qdrant REST API JSON responses. */
interface QdrantResponse {
  result?: Record<string, unknown> | unknown[]
  status?: string
  time?: number
}

export type FactType = 'episodic' | 'semantic' | 'procedural' | 'foresight' | 'profile' | 'reflexion'
export type Visibility = 'private' | 'project' | 'shared' | 'broadcast'

export interface MemoryMetadata {
  id: string
  area: string
  content: string
  query: string
  timestamp: number
  valid_from: number
  valid_to: number | null
  fact_type: FactType
  confidence: number
  utility_score: number
  retrieval_count: number
  success_count: number
  failure_count: number
  source_agent: string
  trust_score: number
  visibility: Visibility
  tags: string[]
}

export interface MemoryPoint {
  id: string
  content: string
  metadata: Partial<MemoryMetadata>
  score?: number
}

export interface MemoryStats {
  total: number
  byArea: Record<string, number>
  byType: Record<string, number>
  available: boolean
}

const COLLECTION = 'pfaa_memory'
const EMBED_DIM = 768

export class MemoryStore {
  private qdrantUrl: string
  private available: boolean | null = null

  constructor(qdrantUrl?: string) {
    this.qdrantUrl = qdrantUrl ?? 'http://localhost:6333'
  }

  // ── Store a memory ──────────────────────────────────────────────
  async store(
    content: string,
    response: string,
    opts: Partial<MemoryMetadata> = {},
  ): Promise<string | null> {
    if (!await this.checkAvailable()) return null

    try {
      const id = opts.id ?? randomUUID()
      const [vector] = await this.embed([content])
      const now = Date.now() / 1000

      await this.qdrantRequest('PUT', `/collections/${COLLECTION}/points`, {
        points: [{
          id,
          vector,
          payload: {
            id,
            content: response.slice(0, 2000),
            query: content.slice(0, 500),
            timestamp: now,
            valid_from: now,
            valid_to: null,
            area: opts.area ?? 'main',
            fact_type: opts.fact_type ?? 'episodic',
            confidence: opts.confidence ?? 1.0,
            utility_score: 0.5,
            retrieval_count: 0,
            success_count: 0,
            failure_count: 0,
            source_agent: opts.source_agent ?? 'pfaa',
            trust_score: 1.0,
            visibility: opts.visibility ?? 'private',
            tags: opts.tags ?? [],
          } satisfies MemoryMetadata,
        }],
      })

      return id
    } catch {
      return null
    }
  }

  // ── Recall (semantic search) ────────────────────────────────────
  async recall(
    query: string,
    limit = 5,
    opts: { area?: string; fact_type?: FactType; threshold?: number } = {},
  ): Promise<MemoryPoint[]> {
    if (!await this.checkAvailable()) return []

    try {
      const [vector] = await this.embed([query])

      const filter: any = { must: [] }
      if (opts.area) filter.must.push({ key: 'area', match: { value: opts.area } })
      if (opts.fact_type) filter.must.push({ key: 'fact_type', match: { value: opts.fact_type } })
      // Only current memories (valid_to is null)
      filter.must.push({ key: 'valid_to', match: { value: null } })

      const resp = await this.qdrantRequest('POST', `/collections/${COLLECTION}/points/search`, {
        vector,
        limit,
        score_threshold: opts.threshold ?? 0.4,
        with_payload: true,
        filter: filter.must.length ? filter : undefined,
      })

      const results = (Array.isArray(resp.result) ? resp.result : []) as Record<string, unknown>[]

      // Update retrieval counts (Q-learning style)
      const ids = results.map((r: any) => String(r.id))
      if (ids.length) this.updateUtility(ids, 'retrieval').catch(() => {})

      return results.map((r: any) => ({
        id: String(r.id),
        content: String(r.payload?.content ?? ''),
        metadata: r.payload ?? {},
        score: r.score,
      }))
    } catch {
      return []
    }
  }

  // ── List all memories (paginated) ──────────────────────────────
  async list(
    opts: { area?: string; fact_type?: FactType; limit?: number; offset?: number } = {},
  ): Promise<MemoryPoint[]> {
    if (!await this.checkAvailable()) return []

    try {
      const filter: any = { must: [] }
      if (opts.area) filter.must.push({ key: 'area', match: { value: opts.area } })
      if (opts.fact_type) filter.must.push({ key: 'fact_type', match: { value: opts.fact_type } })
      filter.must.push({ key: 'valid_to', match: { value: null } })

      const resp = await this.qdrantRequest('POST', `/collections/${COLLECTION}/points/scroll`, {
        limit: opts.limit ?? 20,
        offset: opts.offset ?? null,
        with_payload: true,
        filter: filter.must.length ? filter : undefined,
      })

      const scrollResult = resp.result as Record<string, unknown> | undefined
      const points = (Array.isArray(scrollResult?.points) ? scrollResult.points : []) as Record<string, unknown>[]
      return points.map((r: any) => ({
        id: String(r.id),
        content: String(r.payload?.content ?? ''),
        metadata: r.payload ?? {},
      }))
    } catch {
      return []
    }
  }

  // ── Forget (soft delete — sets valid_to) ───────────────────────
  async forget(id: string): Promise<boolean> {
    if (!await this.checkAvailable()) return false
    try {
      await this.qdrantRequest('POST', `/collections/${COLLECTION}/points/payload`, {
        payload: { valid_to: Date.now() / 1000 },
        points: [id],
      })
      return true
    } catch {
      return false
    }
  }

  // ── Hard delete ────────────────────────────────────────────────
  async forgetHard(id: string): Promise<boolean> {
    if (!await this.checkAvailable()) return false
    try {
      await this.qdrantRequest('POST', `/collections/${COLLECTION}/points/delete`, {
        points: [id],
      })
      return true
    } catch {
      return false
    }
  }

  // ── Consolidate (promote high-Q memories) ──────────────────────
  async consolidate(opts: { minQ?: number; minRetrievals?: number } = {}): Promise<{
    promoted: number
    pruned: number
  }> {
    if (!await this.checkAvailable()) return { promoted: 0, pruned: 0 }

    const minQ = opts.minQ ?? 0.8
    const minRetrievals = opts.minRetrievals ?? 3
    let promoted = 0
    let pruned = 0

    try {
      const all = await this.list({ limit: 500 })

      for (const m of all) {
        const utility = (m.metadata.utility_score as number) ?? 0.5
        const retrievals = (m.metadata.retrieval_count as number) ?? 0
        const factType = (m.metadata.fact_type as string) ?? 'episodic'

        // Promote high-Q episodic memories to semantic
        if (factType === 'episodic' && utility >= minQ && retrievals >= minRetrievals) {
          await this.qdrantRequest('POST', `/collections/${COLLECTION}/points/payload`, {
            payload: { fact_type: 'semantic', confidence: utility },
            points: [m.id],
          })
          promoted++
        }

        // Soft-delete very low utility memories
        if (utility < 0.2 && retrievals > 5) {
          await this.forget(m.id)
          pruned++
        }
      }
    } catch { /* silent */ }

    return { promoted, pruned }
  }

  // ── Stats ──────────────────────────────────────────────────────
  async stats(): Promise<MemoryStats> {
    if (!await this.checkAvailable()) {
      return { total: 0, byArea: {}, byType: {}, available: false }
    }
    try {
      const resp = await this.qdrantRequest('GET', `/collections/${COLLECTION}`)
      const collectionResult = resp.result as Record<string, unknown> | undefined
      const total = (typeof collectionResult?.points_count === 'number' ? collectionResult.points_count : 0)

      // Get area/type breakdown from a sample
      const sample = await this.list({ limit: 1000 })
      const byArea: Record<string, number> = {}
      const byType: Record<string, number> = {}
      for (const m of sample) {
        const area = (m.metadata.area as string) ?? 'unknown'
        const type = (m.metadata.fact_type as string) ?? 'unknown'
        byArea[area] = (byArea[area] ?? 0) + 1
        byType[type] = (byType[type] ?? 0) + 1
      }

      return { total, byArea, byType, available: true }
    } catch {
      return { total: 0, byArea: {}, byType: {}, available: false }
    }
  }

  // ── Utility scoring (Q-learning) ───────────────────────────────
  async updateUtility(
    ids: string[],
    event: 'retrieval' | 'success' | 'failure',
  ): Promise<void> {
    if (!await this.checkAvailable()) return
    try {
      // Fetch current payloads
      const resp = await this.qdrantRequest('POST', `/collections/${COLLECTION}/points`, {
        ids,
        with_payload: true,
      })
      const points = (Array.isArray(resp.result) ? resp.result : []) as Record<string, unknown>[]

      for (const point of points) {
        const p = (point.payload ?? {}) as Record<string, unknown>
        const rc = (Number(p.retrieval_count) || 0) + (event === 'retrieval' ? 1 : 0)
        const sc = (Number(p.success_count) || 0) + (event === 'success' ? 1 : 0)
        const fc = (Number(p.failure_count) || 0) + (event === 'failure' ? 1 : 0)
        const total = sc + fc
        const utility = total > 0 ? (sc / total) * 0.8 + 0.5 * 0.2 : 0.5

        await this.qdrantRequest('POST', `/collections/${COLLECTION}/points/payload`, {
          payload: { retrieval_count: rc, success_count: sc, failure_count: fc, utility_score: utility },
          points: [String(point.id)],
        })
      }
    } catch { /* silent */ }
  }

  // ── Embedding ──────────────────────────────────────────────────
  private async embed(texts: string[]): Promise<number[][]> {
    try {
      if (!embedder.ready) {
        await embedder.start(process.env.PFAA_PYTHON ?? 'python3')
      }
      return await embedder.embed(texts)
    } catch {
      return texts.map(() => new Array(EMBED_DIM).fill(0))
    }
  }

  // ── Qdrant availability ────────────────────────────────────────
  private async checkAvailable(): Promise<boolean> {
    if (this.available !== null) return this.available
    try {
      await this.qdrantRequest('GET', '/collections')
      try {
        await this.qdrantRequest('GET', `/collections/${COLLECTION}`)
      } catch {
        await this.qdrantRequest('PUT', `/collections/${COLLECTION}`, {
          vectors: { size: EMBED_DIM, distance: 'Cosine' },
        })
      }
      this.available = true
    } catch {
      this.available = false
    }
    return this.available
  }

  private async qdrantRequest(method: string, path: string, body?: unknown): Promise<QdrantResponse> {
    const resp = await fetch(`${this.qdrantUrl}${path}`, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(5000),
    })
    if (!resp.ok) throw new Error(`Qdrant ${resp.status}`)
    return resp.json() as Promise<QdrantResponse>
  }
}
