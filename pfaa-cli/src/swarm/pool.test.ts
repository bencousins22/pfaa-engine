import { describe, it, expect, beforeEach } from 'vitest';
import { ProcessPool, getPool } from './pool.js';

describe('ProcessPool', () => {
  it('can be constructed without arguments', () => {
    const pool = new ProcessPool();
    expect(pool).toBeInstanceOf(ProcessPool);
  });

  it('can be constructed with a custom pool size', () => {
    const pool = new ProcessPool(8);
    expect(pool).toBeInstanceOf(ProcessPool);
  });

  it('has dispatch method', () => {
    const pool = new ProcessPool();
    expect(typeof pool.dispatch).toBe('function');
  });

  it('has shutdown method', () => {
    const pool = new ProcessPool();
    expect(typeof pool.shutdown).toBe('function');
  });

  it('has warmUp method', () => {
    const pool = new ProcessPool();
    expect(typeof pool.warmUp).toBe('function');
  });

  it('size is 0 before warmUp', () => {
    const pool = new ProcessPool();
    expect(pool.size).toBe(0);
  });

  it('idleCount is 0 before warmUp', () => {
    const pool = new ProcessPool();
    expect(pool.idleCount).toBe(0);
  });

  it('pendingCount is 0 initially', () => {
    const pool = new ProcessPool();
    expect(pool.pendingCount).toBe(0);
  });

  it('is an EventEmitter (has on/emit)', () => {
    const pool = new ProcessPool();
    expect(typeof pool.on).toBe('function');
    expect(typeof pool.emit).toBe('function');
  });

  it('shutdown resolves on a fresh pool (no workers)', async () => {
    const pool = new ProcessPool();
    await expect(pool.shutdown()).resolves.toBeUndefined();
  });
});

describe('getPool (singleton)', () => {
  // getPool uses a module-level variable, so we need to test singleton behavior
  // within a single import context.

  it('returns a ProcessPool instance', () => {
    const pool = getPool();
    expect(pool).toBeInstanceOf(ProcessPool);
  });

  it('returns the same instance on repeated calls', () => {
    const pool1 = getPool();
    const pool2 = getPool();
    expect(pool1).toBe(pool2);
  });

  it('returns the same instance even with different size argument', () => {
    const pool1 = getPool(4);
    const pool2 = getPool(16);
    expect(pool1).toBe(pool2);
  });
});
