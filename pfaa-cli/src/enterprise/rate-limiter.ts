/**
 * Enterprise Rate Limiter — Token bucket with burst allowance.
 *
 * Prevents runaway costs by limiting:
 * - Requests per minute (API calls)
 * - Tokens per minute (LLM throughput)
 * - Concurrent agents (resource protection)
 */

import { getLogger } from '../utils/logger.js';
import type { RateLimitConfig } from '../types.js';

const log = getLogger('rate-limiter');

interface Bucket {
  tokens: number;
  lastRefill: number;
  rate: number;
  max: number;
}

export class RateLimiter {
  private requestBucket: Bucket;
  private tokenBucket: Bucket;
  private activeAgents = 0;
  private maxAgents: number;
  private waitQueue: Array<() => void> = [];

  constructor(config: RateLimitConfig) {
    this.requestBucket = {
      tokens: config.maxRequestsPerMinute + config.burstAllowance,
      lastRefill: Date.now(),
      rate: config.maxRequestsPerMinute / 60_000, // per ms
      max: config.maxRequestsPerMinute + config.burstAllowance,
    };

    this.tokenBucket = {
      tokens: config.maxTokensPerMinute,
      lastRefill: Date.now(),
      rate: config.maxTokensPerMinute / 60_000,
      max: config.maxTokensPerMinute,
    };

    this.maxAgents = config.maxConcurrentAgents;
  }

  /**
   * Wait until a request slot is available.
   */
  async acquireRequest(): Promise<void> {
    this.refill(this.requestBucket);

    if (this.requestBucket.tokens < 1) {
      const waitMs = Math.ceil((1 - this.requestBucket.tokens) / this.requestBucket.rate);
      log.debug(`Rate limited, waiting ${waitMs}ms`);
      await this.sleep(waitMs);
      this.refill(this.requestBucket);
    }

    this.requestBucket.tokens -= 1;
  }

  /**
   * Consume token budget (call after receiving response).
   */
  consumeTokens(count: number): boolean {
    this.refill(this.tokenBucket);

    if (this.tokenBucket.tokens < count) {
      log.warn('Token rate limit exceeded', {
        requested: count,
        available: Math.floor(this.tokenBucket.tokens),
      });
      return false;
    }

    this.tokenBucket.tokens -= count;
    return true;
  }

  /**
   * Acquire an agent slot. Waits if at capacity.
   */
  async acquireAgent(): Promise<() => void> {
    while (this.activeAgents >= this.maxAgents) {
      await new Promise<void>((resolve) => {
        this.waitQueue.push(resolve);
      });
    }

    this.activeAgents++;
    log.debug('Agent acquired', {
      active: this.activeAgents,
      max: this.maxAgents,
    });

    // Return release function
    return () => {
      this.activeAgents--;
      const next = this.waitQueue.shift();
      if (next) next();
    };
  }

  status(): {
    requestsAvailable: number;
    tokensAvailable: number;
    activeAgents: number;
    maxAgents: number;
    queueLength: number;
  } {
    this.refill(this.requestBucket);
    this.refill(this.tokenBucket);

    return {
      requestsAvailable: Math.floor(this.requestBucket.tokens),
      tokensAvailable: Math.floor(this.tokenBucket.tokens),
      activeAgents: this.activeAgents,
      maxAgents: this.maxAgents,
      queueLength: this.waitQueue.length,
    };
  }

  private refill(bucket: Bucket): void {
    const now = Date.now();
    const elapsed = now - bucket.lastRefill;
    bucket.tokens = Math.min(
      bucket.max,
      bucket.tokens + elapsed * bucket.rate,
    );
    bucket.lastRefill = now;
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
}
