/**
 * Adaptive Analysis Cache — Smart caching for code analysis results.
 *
 * Strategies:
 * - LRU: Least recently used eviction
 * - TTL: Time-based expiration
 * - Adaptive: Combines both + frequency-based retention
 *
 * Caches expensive operations like code analysis, AST parsing,
 * and Claude API responses to avoid redundant work.
 */

import { createHash } from 'node:crypto';
import { getLogger } from '../utils/logger.js';
import type { CacheConfig } from '../types.js';

const log = getLogger('cache');

interface CacheEntry<T> {
  key: string;
  value: T;
  createdAt: number;
  accessedAt: number;
  accessCount: number;
  size: number;
  ttlMs: number;
}

export class AnalysisCache<T = unknown> {
  private entries = new Map<string, CacheEntry<T>>();
  private config: CacheConfig;
  private hits = 0;
  private misses = 0;

  constructor(config: CacheConfig) {
    this.config = config;
  }

  get(key: string): T | undefined {
    if (!this.config.enabled) return undefined;

    const entry = this.entries.get(this.hash(key));
    if (!entry) {
      this.misses++;
      return undefined;
    }

    // TTL check
    if (Date.now() - entry.createdAt > entry.ttlMs) {
      this.entries.delete(this.hash(key));
      this.misses++;
      return undefined;
    }

    entry.accessedAt = Date.now();
    entry.accessCount++;
    this.hits++;
    return entry.value;
  }

  set(key: string, value: T, ttlMs?: number): void {
    if (!this.config.enabled) return;

    const hash = this.hash(key);

    // Evict if at capacity
    if (this.entries.size >= this.config.maxEntries && !this.entries.has(hash)) {
      this.evict();
    }

    const size = JSON.stringify(value).length;

    this.entries.set(hash, {
      key,
      value,
      createdAt: Date.now(),
      accessedAt: Date.now(),
      accessCount: 1,
      size,
      ttlMs: ttlMs || this.config.ttlMs,
    });
  }

  has(key: string): boolean {
    const entry = this.entries.get(this.hash(key));
    if (!entry) return false;
    if (Date.now() - entry.createdAt > entry.ttlMs) {
      this.entries.delete(this.hash(key));
      return false;
    }
    return true;
  }

  invalidate(key: string): boolean {
    return this.entries.delete(this.hash(key));
  }

  clear(): void {
    this.entries.clear();
    this.hits = 0;
    this.misses = 0;
  }

  status(): {
    entries: number;
    maxEntries: number;
    hitRate: number;
    hits: number;
    misses: number;
    totalSizeKb: number;
  } {
    const total = this.hits + this.misses;
    const totalSize = Array.from(this.entries.values())
      .reduce((sum, e) => sum + e.size, 0);

    return {
      entries: this.entries.size,
      maxEntries: this.config.maxEntries,
      hitRate: total > 0 ? this.hits / total : 0,
      hits: this.hits,
      misses: this.misses,
      totalSizeKb: Math.round(totalSize / 1024),
    };
  }

  private evict(): void {
    if (this.config.strategy === 'lru') {
      this.evictLRU();
    } else if (this.config.strategy === 'ttl') {
      this.evictExpired();
    } else {
      // Adaptive: remove expired first, then LRU with frequency weighting
      this.evictExpired();
      if (this.entries.size >= this.config.maxEntries) {
        this.evictAdaptive();
      }
    }
  }

  private evictLRU(): void {
    let oldest: string | null = null;
    let oldestTime = Infinity;

    for (const [hash, entry] of this.entries) {
      if (entry.accessedAt < oldestTime) {
        oldestTime = entry.accessedAt;
        oldest = hash;
      }
    }

    if (oldest) this.entries.delete(oldest);
  }

  private evictExpired(): void {
    const now = Date.now();
    for (const [hash, entry] of this.entries) {
      if (now - entry.createdAt > entry.ttlMs) {
        this.entries.delete(hash);
      }
    }
  }

  private evictAdaptive(): void {
    // Score = accessCount / age. Lower score = evict first.
    const now = Date.now();
    let lowest: string | null = null;
    let lowestScore = Infinity;

    for (const [hash, entry] of this.entries) {
      const ageMs = Math.max(1, now - entry.createdAt);
      const score = entry.accessCount / (ageMs / 1000);
      if (score < lowestScore) {
        lowestScore = score;
        lowest = hash;
      }
    }

    if (lowest) this.entries.delete(lowest);
  }

  private hash(key: string): string {
    return createHash('sha256').update(key).digest('hex').slice(0, 16);
  }
}
