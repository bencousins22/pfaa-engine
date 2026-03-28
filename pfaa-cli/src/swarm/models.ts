/**
 * Per-tier model routing — maps each pipeline tier to its optimal Claude model.
 *
 * Expensive reasoning tiers (intelligence, conversion) use Opus.
 * Throughput tiers (acquisition, enrichment, outreach, content) use Sonnet.
 * High-volume / low-latency tiers (scoring, nurture, operations) use Haiku.
 */

export const TIER_MODELS: Record<string, string> = {
  intelligence: 'claude-opus-4-6',
  acquisition: 'claude-sonnet-4-6',
  enrichment: 'claude-sonnet-4-6',
  scoring: 'claude-haiku-4-5-20251001',
  outreach: 'claude-sonnet-4-6',
  conversion: 'claude-opus-4-6',
  nurture: 'claude-haiku-4-5-20251001',
  content: 'claude-sonnet-4-6',
  operations: 'claude-haiku-4-5-20251001',
};

/** Look up the model for a tier, falling back to Sonnet. */
export function modelForTier(tier: string): string {
  return TIER_MODELS[tier] ?? 'claude-sonnet-4-6';
}
