/**
 * Memory store — sentence-transformers embeddings via Python subprocess -> Qdrant.
 * Mirrors Agent Zero's QdrantMemoryStore with utility scoring.
 * Degrades gracefully when Qdrant is unavailable.
 */

import { randomUUID } from 'crypto'
import { EmbedderProcess, embedder } from './embedder-process.js'

export interface MemoryPoint {
  id: string
  content: string
  metadata: Record<string, unknown>
  score?: number
}

const COLLECTION = 'pfaa_memory'
const EMBED_DIM = 768

export class MemoryStore {
  private qdrantUrl: string
  private available: boolean | null = null

  constructor(qdrantUrl?: string) {
    this.qdrantUrl = qdrantUrl ?? 'http://localhost:6333'
  }

  async store(content: string, response: string): Promise<string | null> {
    if (!await this.checkAvailable()) return null

    try {
      const id = randomUUID()
      const [vector] = await this.embed([content])
      const now = Date.now() / 1000

      await this.qdrantRequest('PUT', `/collections/${COLLECTION}/points`, {
        points: [{
          id,
          vector,
          payload: {
            content: response.slice(0, 2000),
            query: content.slice(0, 500),
            timestamp: now,
            area: 'main',
            fact_type: 'episodic',
            utility_score: 0.5,
            retrieval_count: 0,
          },
        }],
      })

      return id
    } catch {
      return null
    }
  }

  async recall(query: string, limit = 5): Promise<MemoryPoint[]> {
    if (!await this.checkAvailable()) return []

    try {
      const [vector] = await this.embed([query])

      const resp = await this.qdrantRequest('POST', `/collections/${COLLECTION}/points/search`, {
        vector,
        limit,
        score_threshold: 0.4,
        with_payload: true,
      })

      const results = (resp as any).result ?? []
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

  private async embed(texts: string[]): Promise<number[][]> {
    try {
      if (!embedder.ready) {
        await embedder.start(process.env.PFAA_PYTHON ?? 'python3')
      }
      return await embedder.embed(texts)
    } catch {
      // Fallback: zero vectors (memory will still work, just no semantic search)
      return texts.map(() => new Array(EMBED_DIM).fill(0))
    }
  }

  private async checkAvailable(): Promise<boolean> {
    if (this.available !== null) return this.available

    try {
      await this.qdrantRequest('GET', '/collections')
      // Ensure collection exists
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

  private async qdrantRequest(method: string, path: string, body?: unknown): Promise<unknown> {
    const url = `${this.qdrantUrl}${path}`
    const resp = await fetch(url, {
      method,
      headers: body ? { 'Content-Type': 'application/json' } : {},
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(5000),
    })
    if (!resp.ok) throw new Error(`Qdrant ${resp.status}`)
    return resp.json()
  }
}
