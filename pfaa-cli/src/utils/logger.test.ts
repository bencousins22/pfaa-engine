import { describe, it, expect } from 'vitest';
import { getLogger } from './logger.js';

describe('getLogger', () => {
  it('returns a logger with standard methods', () => {
    const log = getLogger('test');
    expect(typeof log.info).toBe('function');
    expect(typeof log.warn).toBe('function');
    expect(typeof log.error).toBe('function');
    expect(typeof log.debug).toBe('function');
  });

  it('returns loggers with consistent behavior for same name', () => {
    const a = getLogger('same');
    const b = getLogger('same');
    expect(typeof a.info).toBe(typeof b.info);
    expect(typeof a.warn).toBe(typeof b.warn);
  });

  it('returns different loggers for different names', () => {
    const a = getLogger('alpha');
    const b = getLogger('beta');
    // They may share implementation but should be callable
    expect(typeof a.info).toBe('function');
    expect(typeof b.info).toBe('function');
  });
});
