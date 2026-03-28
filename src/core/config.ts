/**
 * Configuration loader for PFAA.
 * Reads pfaa.config.json and merges with environment variables.
 */

import { readFile } from 'fs/promises'
import type { PFAAConfig } from './types.js'

const DEFAULTS: PFAAConfig = {
  auditDir: '.pfaa/audit',
  qdrantUrl: 'http://localhost:6333',
  pythonBin: 'python3',
  maxIterations: 50,
  maxParallelTeams: 9,
  permissions: {
    deny: [],
    requireConfirm: ['shell'],
    allowPaths: ['./src', './tests', './docs'],
  },
  tierModels: {
    intelligence: 'claude-opus-4-6',
    acquisition: 'claude-sonnet-4-6',
    enrichment: 'claude-sonnet-4-6',
    scoring: 'claude-haiku-4-5-20251001',
    outreach: 'claude-sonnet-4-6',
    conversion: 'claude-opus-4-6',
    nurture: 'claude-haiku-4-5-20251001',
    content: 'claude-sonnet-4-6',
    operations: 'claude-haiku-4-5-20251001',
  },
}

export async function loadConfig(configPath: string): Promise<PFAAConfig> {
  try {
    const raw = await readFile(configPath, 'utf8')
    const parsed = JSON.parse(raw)
    return { ...DEFAULTS, ...parsed }
  } catch {
    return { ...DEFAULTS }
  }
}
