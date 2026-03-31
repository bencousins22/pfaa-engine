import { describe, it, expect, beforeEach, vi } from 'vitest';
import { AnalysisCache } from './cache.js';

describe('AnalysisCache', () => {
  let cache: AnalysisCache<string>;

  beforeEach(() => {
    cache = new AnalysisCache<string>({
      enabled: true,
      strategy: 'lru',
      maxEntries: 3,
      ttlMs: 10_000,
      analysisCache: true,
    });
  });

  it('stores and retrieves values', () => {
    cache.set('key1', 'value1');
    expect(cache.get('key1')).toBe('value1');
  });

  it('returns undefined for missing keys', () => {
    expect(cache.get('nonexistent')).toBeUndefined();
  });

  it('respects has()', () => {
    cache.set('key1', 'value1');
    expect(cache.has('key1')).toBe(true);
    expect(cache.has('missing')).toBe(false);
  });

  it('invalidates entries', () => {
    cache.set('key1', 'value1');
    expect(cache.invalidate('key1')).toBe(true);
    expect(cache.get('key1')).toBeUndefined();
  });

  it('clears all entries', () => {
    cache.set('a', '1');
    cache.set('b', '2');
    cache.clear();
    expect(cache.get('a')).toBeUndefined();
    expect(cache.get('b')).toBeUndefined();
    expect(cache.status().entries).toBe(0);
  });

  it('evicts LRU entry when at capacity', () => {
    cache.set('a', '1');
    cache.set('b', '2');
    cache.set('c', '3');
    // Access 'b' and 'c' so they're not LRU
    cache.get('b');
    cache.get('c');
    // Adding 'd' should evict 'a' (least recently used)
    cache.set('d', '4');
    expect(cache.get('a')).toBeUndefined();
    expect(cache.get('b')).toBe('2');
    expect(cache.get('d')).toBe('4');
  });

  it('expires entries after TTL', () => {
    vi.useFakeTimers();
    const shortCache = new AnalysisCache<string>({
      enabled: true,
      strategy: 'ttl',
      maxEntries: 10,
      ttlMs: 100,
      analysisCache: true,
    });

    shortCache.set('key', 'val');
    expect(shortCache.get('key')).toBe('val');

    vi.advanceTimersByTime(200);
    expect(shortCache.get('key')).toBeUndefined();
    vi.useRealTimers();
  });

  it('tracks hit/miss stats', () => {
    cache.set('a', '1');
    cache.get('a');       // hit
    cache.get('a');       // hit
    cache.get('missing'); // miss

    const s = cache.status();
    expect(s.hits).toBe(2);
    expect(s.misses).toBe(1);
    expect(s.hitRate).toBeCloseTo(2 / 3);
  });

  it('returns undefined when disabled', () => {
    const disabled = new AnalysisCache<string>({
      enabled: false,
      strategy: 'lru',
      maxEntries: 10,
      ttlMs: 10_000,
      analysisCache: true,
    });
    disabled.set('key', 'val');
    expect(disabled.get('key')).toBeUndefined();
  });

  describe('adaptive eviction', () => {
    it('evicts low-frequency entries first', () => {
      const adaptive = new AnalysisCache<string>({
        enabled: true,
        strategy: 'adaptive',
        maxEntries: 2,
        ttlMs: 60_000,
        analysisCache: true,
      });

      adaptive.set('hot', 'val');
      // Access many times to boost frequency
      adaptive.get('hot');
      adaptive.get('hot');
      adaptive.get('hot');

      adaptive.set('cold', 'val2');
      // Adding third should evict 'cold' (lower access frequency)
      adaptive.set('new', 'val3');
      expect(adaptive.get('hot')).toBe('val');
      expect(adaptive.get('new')).toBe('val3');
    });
  });
});
