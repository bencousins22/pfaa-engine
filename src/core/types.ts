/**
 * Core type definitions for the Aussie Agents enterprise CLI.
 */

import type { AuditLogger } from '../audit/logger.js'

export interface OrchestratorOptions {
  provider: string
  model?: string
  sandbox: boolean
  maxTokens: number
  compactThreshold: number
  workspace: string
  tools: string[]
  config: PFAAConfig
  audit: AuditLogger | null
  deferredTools?: boolean
}

export interface PFAAConfig {
  auditDir?: string
  qdrantUrl?: string
  pythonBin?: string
  maxIterations?: number
  maxParallelTeams?: number
  permissions?: {
    deny?: string[]
    requireConfirm?: string[]
    allowPaths?: string[]
  }
  tierModels?: Record<string, string>
}

export interface AgentEvent {
  type:
    | 'start' | 'text' | 'tool_call' | 'tool_result'
    | 'tool_blocked' | 'tool_error' | 'compacting'
    | 'compacted' | 'complete' | 'error' | 'memory_recall'
    | 'retry'
  [key: string]: unknown
}

export interface ExecutionPlan {
  steps: string[]
  estimatedTokens: number
}
