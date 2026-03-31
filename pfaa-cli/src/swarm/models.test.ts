import { describe, it, expect } from 'vitest';
import { TIER_MODELS, modelForTier } from './models.js';

describe('TIER_MODELS', () => {
  it('maps intelligence to Opus', () => {
    expect(TIER_MODELS['intelligence']).toBe('claude-opus-4-6');
  });

  it('maps acquisition to Sonnet', () => {
    expect(TIER_MODELS['acquisition']).toBe('claude-sonnet-4-6');
  });

  it('maps scoring to Haiku', () => {
    expect(TIER_MODELS['scoring']).toBe('claude-haiku-4-5-20251001');
  });

  it('has 9 tiers defined', () => {
    expect(Object.keys(TIER_MODELS)).toHaveLength(9);
  });
});

describe('modelForTier', () => {
  it('returns Opus for intelligence tier', () => {
    expect(modelForTier('intelligence')).toBe('claude-opus-4-6');
  });

  it('returns Haiku for operations tier', () => {
    expect(modelForTier('operations')).toBe('claude-haiku-4-5-20251001');
  });

  it('falls back to Sonnet for unknown tiers', () => {
    expect(modelForTier('unknown')).toBe('claude-sonnet-4-6');
    expect(modelForTier('')).toBe('claude-sonnet-4-6');
  });
});
