/**
 * Per-tier model routing — maps each pipeline tier to its optimal Claude model.
 *
 * Expensive reasoning tiers (intelligence, conversion) use Opus.
 * Throughput tiers (acquisition, enrichment, outreach, content) use Sonnet.
 * High-volume / low-latency tiers (scoring, nurture, operations) use Haiku.
 */

export const TIER_MODELS = {
  intelligence: 'claude-opus-4-6',
  acquisition: 'claude-sonnet-4-6',
  enrichment: 'claude-sonnet-4-6',
  scoring: 'claude-haiku-4-5-20251001',
  outreach: 'claude-sonnet-4-6',
  conversion: 'claude-opus-4-6',
  nurture: 'claude-haiku-4-5-20251001',
  content: 'claude-sonnet-4-6',
  operations: 'claude-haiku-4-5-20251001',
} satisfies Record<string, string>;

/** Known tier names. */
export type Tier = keyof typeof TIER_MODELS;

/** Look up the model for a tier, falling back to Sonnet. */
export function modelForTier(tier: string): string {
  if (tier in TIER_MODELS) {
    return TIER_MODELS[tier as Tier];
  }
  return 'claude-sonnet-4-6';
}
