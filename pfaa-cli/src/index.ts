/**
 * Aussie Agents CLI — Programmatic API
 *
 * Use this module to embed the Aussie Agents CLI capabilities in other
 * Node.js applications. All subsystems are available:
 *
 *   import { createBridge, AgentOrchestrator, JMEMClient } from '@pfaa/cli';
 */

// Core types
export * from './types.js';

// Bridge
export { PFAABridge, createBridge, type BridgeConfig } from './bridge/pfaa-bridge.js';

// Agents
export { AgentOrchestrator } from './agents/orchestrator.js';

// Memory
export { JMEMClient, type JMEMConfig } from './memory/jmem-client.js';

// Enterprise
export { RateLimiter } from './enterprise/rate-limiter.js';
export { AnalysisCache } from './enterprise/cache.js';

// Tools
export { Python315Tools } from './tools/python315.js';

// Utils
export { getLogger, setLogLevel, LogLevel, Logger } from './utils/logger.js';
export { loadConfig, saveUserConfig, initProjectConfig, type PFAAConfig } from './utils/config.js';
