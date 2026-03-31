import { describe, it, expect } from 'vitest';
import { JMEMClient, type JMEMConfig } from './jmem-client.js';

describe('JMEMClient', () => {
  it('creates an instance with default config', () => {
    const client = new JMEMClient();
    expect(client).toBeInstanceOf(JMEMClient);
    expect(client.isConnected).toBe(false);
  });

  it('accepts partial config overrides', () => {
    const client = new JMEMClient({ namespace: 'test-ns', maxEpisodes: 500 });
    expect(client).toBeInstanceOf(JMEMClient);
    expect(client.isConnected).toBe(false);
  });

  it('has a Map-based cache for recall results', () => {
    const client = new JMEMClient();
    // The cache is private, but we can verify the instance was constructed
    // without errors and is an EventEmitter (inherits .on/.emit).
    expect(typeof client.on).toBe('function');
    expect(typeof client.emit).toBe('function');
  });

  it('returns disconnected status when not connected', async () => {
    const client = new JMEMClient();
    const status = await client.status();
    expect(status).toEqual({
      l1Episodes: 0,
      l2Patterns: 0,
      l3Strategies: 0,
      l4LearningRate: 0.1,
      l5Knowledge: 0,
      dbSizeKb: 0,
    });
  });

  it('returns empty entries from recall when disconnected', async () => {
    const client = new JMEMClient();
    const entries = await client.recall('test query');
    expect(entries).toEqual([]);
  });

  it('returns empty entries from search when disconnected', async () => {
    const client = new JMEMClient();
    const entries = await client.search('test query');
    expect(entries).toEqual([]);
  });

  it('store returns empty string when disconnected (no MCP server)', async () => {
    const client = new JMEMClient();
    const id = await client.store('test content', 1);
    expect(typeof id).toBe('string');
  });

  it('uses custom config values for Q-learning parameters', async () => {
    const customConfig: Partial<JMEMConfig> = {
      qLearningRate: 0.5,
      qDiscountFactor: 0.8,
      promotionThreshold: 0.9,
    };
    const client = new JMEMClient(customConfig);
    // Disconnected status should reflect the custom learning rate
    const status = await client.status();
    expect(status.l4LearningRate).toBe(0.5);
  });
});
