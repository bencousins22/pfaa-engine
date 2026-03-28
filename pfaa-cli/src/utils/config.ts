/**
 * Configuration Manager — Enterprise config with environment variable support.
 *
 * Loads configuration from:
 * 1. ~/.pfaa/config.yaml (user config)
 * 2. .pfaa.yaml (project config)
 * 3. Environment variables (PFAA_*)
 * 4. CLI flags (highest priority)
 */

import { existsSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';
import type {
  EnterpriseConfig,
  MemoryConfig,
  Python315Config,
  CacheConfig,
} from '../types.js';

export interface PFAAConfig {
  // Core
  model: string;
  maxConcurrentAgents: number;
  timeoutMs: number;
  workingDir: string;

  // Python 3.15
  python: Python315Config;

  // Memory (JMEM)
  memory: MemoryConfig;

  // Enterprise
  enterprise: EnterpriseConfig;

  // CLI
  verbose: boolean;
  color: boolean;
  stream: boolean;
}

const DEFAULT_CONFIG: PFAAConfig = {
  model: 'claude-sonnet-4-6',
  maxConcurrentAgents: 8,
  timeoutMs: 120_000,
  workingDir: process.cwd(),

  python: {
    interpreterPath: 'python3.15',
    useLazyImports: true,
    useFrozenDict: true,
    useKqueueSubprocess: true,
    freeThreading: false,
  },

  memory: {
    layers: 5,
    persistence: 'sqlite',
    storagePath: join(homedir(), '.pfaa', 'memory.db'),
    maxEpisodes: 10_000,
    learningRate: 0.01,
  },

  enterprise: {
    auth: {
      provider: 'apikey',
      permissions: [],
    },
    audit: {
      enabled: true,
      logPath: join(homedir(), '.pfaa', 'audit', 'pfaa-audit.jsonl'),
      retentionDays: 90,
      redactSecrets: true,
    },
    rateLimit: {
      maxRequestsPerMinute: 60,
      maxTokensPerMinute: 1_000_000,
      maxConcurrentAgents: 8,
      burstAllowance: 10,
    },
    cache: {
      enabled: true,
      strategy: 'adaptive',
      maxEntries: 1_000,
      ttlMs: 300_000,
      analysisCache: true,
    },
  },

  verbose: false,
  color: true,
  stream: true,
};

export function loadConfig(overrides: Partial<PFAAConfig> = {}): PFAAConfig {
  let config = { ...DEFAULT_CONFIG };

  // 1. User config (~/.pfaa/config.yaml)
  const userConfigPath = join(homedir(), '.pfaa', 'config.yaml');
  if (existsSync(userConfigPath)) {
    try {
      const raw = readFileSync(userConfigPath, 'utf-8');
      // Simple YAML-like parsing for flat keys
      const parsed = parseSimpleYaml(raw);
      config = deepMerge(config, parsed);
    } catch {
      // Ignore parse errors, use defaults
    }
  }

  // 2. Project config (.pfaa.yaml)
  const projectConfigPath = join(process.cwd(), '.pfaa.yaml');
  if (existsSync(projectConfigPath)) {
    try {
      const raw = readFileSync(projectConfigPath, 'utf-8');
      const parsed = parseSimpleYaml(raw);
      config = deepMerge(config, parsed);
    } catch {
      // Ignore
    }
  }

  // 3. Environment variables
  const envMap: Record<string, (val: string) => void> = {
    PFAA_MODEL: (v) => { config.model = v; },
    PFAA_MAX_AGENTS: (v) => { config.maxConcurrentAgents = parseInt(v, 10); },
    PFAA_TIMEOUT: (v) => { config.timeoutMs = parseInt(v, 10); },
    PFAA_PYTHON_PATH: (v) => { config.python.interpreterPath = v; },
    PFAA_MEMORY_PATH: (v) => { config.memory.storagePath = v; },
    PFAA_VERBOSE: (v) => { config.verbose = v === 'true' || v === '1'; },
    ANTHROPIC_API_KEY: (v) => { config.enterprise.auth.apiKey = v; },
    PFAA_TEAM_ID: (v) => { config.enterprise.auth.teamId = v; },
    PFAA_CACHE_ENABLED: (v) => { config.enterprise.cache.enabled = v === 'true'; },
    PFAA_FREE_THREADING: (v) => { config.python.freeThreading = v === 'true'; },
  };

  for (const [envKey, setter] of Object.entries(envMap)) {
    const val = process.env[envKey];
    if (val !== undefined) setter(val);
  }

  // 4. CLI overrides (highest priority)
  config = deepMerge(config, overrides);

  return config;
}

export function saveUserConfig(config: Partial<PFAAConfig>): void {
  const dir = join(homedir(), '.pfaa');
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  const path = join(dir, 'config.yaml');
  const yaml = toSimpleYaml(config);
  writeFileSync(path, yaml, 'utf-8');
}

export function initProjectConfig(): void {
  const path = join(process.cwd(), '.pfaa.yaml');
  if (existsSync(path)) return;

  const template = `# PFAA CLI — Project Configuration
model: claude-sonnet-4-6
maxConcurrentAgents: 8
timeoutMs: 120000

python:
  interpreterPath: python3.15
  useLazyImports: true
  useFrozenDict: true
  freeThreading: false

memory:
  layers: 5
  persistence: sqlite

enterprise:
  cache:
    enabled: true
    strategy: adaptive
`;
  writeFileSync(path, template, 'utf-8');
}

// ── Helpers ────────────────────────────────────────────────────────

function parseSimpleYaml(raw: string): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  const lines = raw.split('\n');
  const stack: { indent: number; obj: Record<string, unknown> }[] = [
    { indent: -1, obj: result },
  ];

  for (const line of lines) {
    const trimmed = line.trimEnd();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const indent = line.length - line.trimStart().length;
    const match = trimmed.match(/^(\s*)(\w[\w.]*)\s*:\s*(.*)$/);
    if (!match) continue;

    const [, , key, rawValue] = match;
    const value = rawValue.trim();

    // Pop stack to find parent
    while (stack.length > 1 && stack[stack.length - 1].indent >= indent) {
      stack.pop();
    }

    const parent = stack[stack.length - 1].obj;

    if (value === '' || value === undefined) {
      // Nested object
      const child: Record<string, unknown> = {};
      parent[key] = child;
      stack.push({ indent, obj: child });
    } else {
      // Leaf value
      parent[key] = parseValue(value);
    }
  }

  return result;
}

function parseValue(v: string): unknown {
  if (v === 'true') return true;
  if (v === 'false') return false;
  if (v === 'null') return null;
  if (/^-?\d+$/.test(v)) return parseInt(v, 10);
  if (/^-?\d+\.\d+$/.test(v)) return parseFloat(v);
  if (v.startsWith('"') && v.endsWith('"')) return v.slice(1, -1);
  if (v.startsWith("'") && v.endsWith("'")) return v.slice(1, -1);
  return v;
}

function toSimpleYaml(obj: Record<string, unknown>, indent = 0): string {
  let out = '';
  const prefix = '  '.repeat(indent);
  for (const [k, v] of Object.entries(obj)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      out += `${prefix}${k}:\n`;
      out += toSimpleYaml(v as Record<string, unknown>, indent + 1);
    } else {
      out += `${prefix}${k}: ${v}\n`;
    }
  }
  return out;
}

function deepMerge(target: any, source: any): any {
  const result = { ...target };
  for (const key of Object.keys(source)) {
    if (
      source[key] &&
      typeof source[key] === 'object' &&
      !Array.isArray(source[key]) &&
      target[key] &&
      typeof target[key] === 'object'
    ) {
      result[key] = deepMerge(target[key], source[key]);
    } else if (source[key] !== undefined) {
      result[key] = source[key];
    }
  }
  return result;
}
