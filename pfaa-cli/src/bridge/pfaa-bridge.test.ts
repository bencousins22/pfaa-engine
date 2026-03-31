import { describe, it, expect } from 'vitest';
import { PFAABridge, createBridge, type BridgeConfig } from './pfaa-bridge.js';

const stubConfig: BridgeConfig = {
  pythonPath: '/usr/bin/python3',
  enginePath: '/tmp/fake-engine',
  workingDir: '/tmp',
  timeoutMs: 5_000,
  maxConcurrent: 4,
  startupTimeoutMs: 30_000,
};

describe('PFAABridge', () => {
  it('accepts a BridgeConfig via constructor', () => {
    const bridge = new PFAABridge(stubConfig);
    expect(bridge).toBeInstanceOf(PFAABridge);
  });

  it('isRunning is false before start()', () => {
    const bridge = new PFAABridge(stubConfig);
    expect(bridge.isRunning).toBe(false);
  });

  it('exposes status as a function', () => {
    const bridge = new PFAABridge(stubConfig);
    expect(typeof bridge.status).toBe('function');
  });

  it('exposes listTools as a function', () => {
    const bridge = new PFAABridge(stubConfig);
    expect(typeof bridge.listTools).toBe('function');
  });

  it('exposes executeTool as a function', () => {
    const bridge = new PFAABridge(stubConfig);
    expect(typeof bridge.executeTool).toBe('function');
  });

  it('exposes runGoal as a function', () => {
    const bridge = new PFAABridge(stubConfig);
    expect(typeof bridge.runGoal).toBe('function');
  });

  it('status rejects when bridge is not started', async () => {
    const bridge = new PFAABridge(stubConfig);
    await expect(bridge.status()).rejects.toThrow('Bridge not started');
  });

  it('listTools rejects when bridge is not started', async () => {
    const bridge = new PFAABridge(stubConfig);
    await expect(bridge.listTools()).rejects.toThrow('Bridge not started');
  });

  it('executeTool rejects when bridge is not started', async () => {
    const bridge = new PFAABridge(stubConfig);
    await expect(bridge.executeTool('some_tool')).rejects.toThrow('Bridge not started');
  });

  it('is an EventEmitter (has on/emit)', () => {
    const bridge = new PFAABridge(stubConfig);
    expect(typeof bridge.on).toBe('function');
    expect(typeof bridge.emit).toBe('function');
  });
});

describe('BridgeConfig interface shape', () => {
  it('requires all fields', () => {
    const config: BridgeConfig = {
      pythonPath: 'python3',
      enginePath: '/engine',
      workingDir: '/work',
      timeoutMs: 1000,
      maxConcurrent: 2,
      startupTimeoutMs: 30_000,
    };
    expect(config.pythonPath).toBe('python3');
    expect(config.enginePath).toBe('/engine');
    expect(config.workingDir).toBe('/work');
    expect(config.timeoutMs).toBe(1000);
    expect(config.maxConcurrent).toBe(2);
  });
});

describe('createBridge', () => {
  it('returns a PFAABridge instance with defaults', () => {
    const bridge = createBridge();
    expect(bridge).toBeInstanceOf(PFAABridge);
  });

  it('accepts partial overrides', () => {
    const bridge = createBridge({ timeoutMs: 999 });
    expect(bridge).toBeInstanceOf(PFAABridge);
    expect(bridge.isRunning).toBe(false);
  });
});
