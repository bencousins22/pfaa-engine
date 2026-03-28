/**
 * Aussie Agents CLI — Core Type Definitions
 *
 * Enterprise-grade types for the Phase-Fluid Agent Architecture CLI.
 * Designed for Python 3.15 code capabilities with full type safety.
 */

// ── Phase-Fluid Execution Model ──────────────────────────────────────

export enum Phase {
  VAPOR = 'VAPOR',    // async coroutine — I/O-bound
  LIQUID = 'LIQUID',  // OS thread — CPU-bound
  SOLID = 'SOLID',    // subprocess — isolation
}

export enum PhaseTransition {
  CONDENSE = 'condense',     // VAPOR → LIQUID
  EVAPORATE = 'evaporate',   // LIQUID → VAPOR
  FREEZE = 'freeze',         // LIQUID → SOLID
  MELT = 'melt',             // SOLID → LIQUID
  SUBLIMATE = 'sublimate',   // VAPOR → SOLID
  DEPOSIT = 'deposit',       // SOLID → VAPOR
}

// ── Agent Types ──────────────────────────────────────────────────────

export interface AgentConfig {
  name: string;
  role: AgentRole;
  model: string;
  capabilities: string[];
  maxConcurrency: number;
  timeoutMs: number;
  phase: Phase;
  isolationRequired: boolean;
  memory: MemoryConfig;
}

export enum AgentRole {
  ANALYZER = 'analyzer',
  REFACTORER = 'refactorer',
  TESTER = 'tester',
  DEPLOYER = 'deployer',
  RESEARCHER = 'researcher',
  ORCHESTRATOR = 'orchestrator',
  REVIEWER = 'reviewer',
  BUILDER = 'builder',
}

export interface AgentResult {
  agentId: string;
  role: AgentRole;
  success: boolean;
  output: unknown;
  phase: Phase;
  elapsedMs: number;
  tokensUsed: { input: number; output: number };
  cost?: number;
  memoryUpdated: boolean;
}

// ── Tool Types ───────────────────────────────────────────────────────

export interface ToolDefinition {
  name: string;
  description: string;
  phase: Phase;
  isolated: boolean;
  inputSchema: Record<string, unknown>;
  capabilities: string[];
}

export interface ToolResult {
  tool: string;
  success: boolean;
  result: unknown;
  phaseUsed: Phase;
  elapsedUs: number;
}

// ── Memory (JMEM Integration) ────────────────────────────────────────

export interface MemoryConfig {
  layers: number;
  persistence: 'sqlite' | 'qdrant' | 'memory';
  storagePath: string;
  maxEpisodes: number;
  learningRate: number;
}

export enum MemoryLayer {
  L1_EPISODIC = 1,
  L2_SEMANTIC = 2,
  L3_STRATEGIC = 3,
  L4_META_LEARNING = 4,
  L5_EMERGENT = 5,
}

export interface MemoryEntry {
  id: string;
  layer: MemoryLayer;
  content: string;
  embedding?: number[];
  score: number;
  timestamp: number;
  source: string;
  metadata: Record<string, unknown>;
}

export interface MemoryStatus {
  l1Episodes: number;
  l2Patterns: number;
  l3Strategies: number;
  l4LearningRate: number;
  l5Knowledge: number;
  dbSizeKb: number;
}

// ── Enterprise Features ──────────────────────────────────────────────

export interface EnterpriseConfig {
  auth: AuthConfig;
  audit: AuditConfig;
  rateLimit: RateLimitConfig;
  cache: CacheConfig;
}

export interface AuthConfig {
  provider: 'apikey' | 'oauth' | 'saml';
  apiKey?: string;
  teamId?: string;
  permissions: Permission[];
}

export enum Permission {
  READ = 'read',
  WRITE = 'write',
  EXECUTE = 'execute',
  DEPLOY = 'deploy',
  ADMIN = 'admin',
}

export interface AuditConfig {
  enabled: boolean;
  logPath: string;
  retentionDays: number;
  redactSecrets: boolean;
}

export interface RateLimitConfig {
  maxRequestsPerMinute: number;
  maxTokensPerMinute: number;
  maxConcurrentAgents: number;
  burstAllowance: number;
}

export interface CacheConfig {
  enabled: boolean;
  strategy: 'lru' | 'ttl' | 'adaptive';
  maxEntries: number;
  ttlMs: number;
  analysisCache: boolean;
}

// ── Task & Pipeline ──────────────────────────────────────────────────

export interface Task {
  id: string;
  description: string;
  agent: AgentRole;
  dependencies: string[];
  status: TaskStatus;
  result?: AgentResult;
  retries: number;
  maxRetries: number;
}

export enum TaskStatus {
  PENDING = 'pending',
  RUNNING = 'running',
  COMPLETED = 'completed',
  FAILED = 'failed',
  RETRYING = 'retrying',
  CANCELLED = 'cancelled',
}

export interface Pipeline {
  id: string;
  name: string;
  tasks: Task[];
  parallel: boolean;
  started: number;
  completed?: number;
}

// ── Streaming Events ─────────────────────────────────────────────────

export enum EventType {
  AGENT_SPAWNED = 'agent:spawned',
  AGENT_PHASE_CHANGE = 'agent:phase_change',
  AGENT_COMPLETED = 'agent:completed',
  AGENT_FAILED = 'agent:failed',
  TOOL_STARTED = 'tool:started',
  TOOL_COMPLETED = 'tool:completed',
  MEMORY_UPDATED = 'memory:updated',
  PIPELINE_STARTED = 'pipeline:started',
  PIPELINE_COMPLETED = 'pipeline:completed',
  TOKEN_STREAM = 'token:stream',
  SYSTEM_STATUS = 'system:status',
}

export interface StreamEvent {
  type: EventType;
  timestamp: number;
  agentId?: string;
  data: Record<string, unknown>;
}

// ── Python 3.15 Specific ─────────────────────────────────────────────

export interface Python315Config {
  interpreterPath: string;
  useLazyImports: boolean;
  useFrozenDict: boolean;
  useKqueueSubprocess: boolean;
  freeThreading: boolean;
  venvPath?: string;
}

export interface CodeAnalysis {
  file: string;
  language: string;
  py315Features: Py315Feature[];
  complexity: number;
  issues: CodeIssue[];
  suggestions: CodeSuggestion[];
}

export interface Py315Feature {
  feature: string;
  pep: string;
  line: number;
  usage: string;
}

export interface CodeIssue {
  severity: 'error' | 'warning' | 'info';
  line: number;
  message: string;
  rule: string;
}

export interface CodeSuggestion {
  type: 'performance' | 'security' | 'style' | 'py315';
  line: number;
  original: string;
  suggested: string;
  reason: string;
}
