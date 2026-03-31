import { describe, it, expect, beforeEach } from 'vitest';
import { RateLimiter } from './rate-limiter.js';

describe('RateLimiter', () => {
  let limiter: RateLimiter;

  beforeEach(() => {
    limiter = new RateLimiter({
      maxRequestsPerMinute: 60,
      maxTokensPerMinute: 100_000,
      maxConcurrentAgents: 3,
      burstAllowance: 10,
    });
  });

  it('initializes with correct status', () => {
    const s = limiter.status();
    expect(s.requestsAvailable).toBeGreaterThanOrEqual(60);
    expect(s.tokensAvailable).toBeGreaterThanOrEqual(100_000);
    expect(s.activeAgents).toBe(0);
    expect(s.maxAgents).toBe(3);
    expect(s.queueLength).toBe(0);
  });

  it('acquireRequest decrements available requests', async () => {
    const before = limiter.status().requestsAvailable;
    await limiter.acquireRequest();
    const after = limiter.status().requestsAvailable;
    expect(after).toBeLessThan(before);
  });

  it('consumeTokens returns true when within budget', () => {
    expect(limiter.consumeTokens(1000)).toBe(true);
    const s = limiter.status();
    expect(s.tokensAvailable).toBeLessThan(100_000);
  });

  it('consumeTokens returns false when exceeding budget', () => {
    expect(limiter.consumeTokens(200_000)).toBe(false);
  });

  it('acquireAgent increments active count and returns disposable', async () => {
    const slot = await limiter.acquireAgent();
    expect(limiter.status().activeAgents).toBe(1);

    slot[Symbol.dispose]();
    expect(limiter.status().activeAgents).toBe(0);
  });

  it('acquireAgent respects max concurrency', async () => {
    const r1 = await limiter.acquireAgent();
    const r2 = await limiter.acquireAgent();
    const r3 = await limiter.acquireAgent();
    expect(limiter.status().activeAgents).toBe(3);

    // Fourth agent should queue — verify by checking queue in a race
    let fourthAcquired = false;
    const p4 = limiter.acquireAgent().then((r) => {
      fourthAcquired = true;
      return r;
    });

    // Give event loop a tick
    await new Promise((r) => setTimeout(r, 10));
    expect(fourthAcquired).toBe(false);
    expect(limiter.status().queueLength).toBe(1);

    // Release one — fourth should now acquire
    r1[Symbol.dispose]();
    const r4 = await p4;
    expect(fourthAcquired).toBe(true);
    expect(limiter.status().activeAgents).toBe(3);

    r2[Symbol.dispose](); r3[Symbol.dispose](); r4[Symbol.dispose]();
    expect(limiter.status().activeAgents).toBe(0);
  });
});
