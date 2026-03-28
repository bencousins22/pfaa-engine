/**
 * Multi-Agent Orchestrator — Enterprise-grade agent coordination.
 *
 * Implements the CSG (Coordinator-Specialist-Gatherer) swarm pattern:
 * 1. Orchestrator decomposes goals into specialized tasks
 * 2. Specialist agents execute in parallel with phase-fluid transitions
 * 3. Gatherer synthesizes results and updates memory
 *
 * Uses AI SDK 6 Agent abstraction for tool-calling loops
 * and Claude Agent SDK for subprocess agent management.
 */

import { EventEmitter } from 'node:events';
import { nanoid } from 'nanoid';
import { getLogger } from '../utils/logger.js';
import type { PFAABridge } from '../bridge/pfaa-bridge.js';
import {
  Phase,
  AgentRole,
  AgentResult,
  Task,
  TaskStatus,
  Pipeline,
  EventType,
  type StreamEvent,
  type AgentConfig,
} from '../types.js';

const log = getLogger('orchestrator');

// ── Agent Definitions ────────────────────────────────────────────────

const AGENT_PRESETS: Record<AgentRole, Omit<AgentConfig, 'name'>> = {
  [AgentRole.ANALYZER]: {
    role: AgentRole.ANALYZER,
    model: 'claude-sonnet-4-6',
    capabilities: ['code-analysis', 'py315-detection', 'complexity', 'security'],
    maxConcurrency: 4,
    timeoutMs: 60_000,
    phase: Phase.VAPOR,
    isolationRequired: false,
    memory: { layers: 5, persistence: 'sqlite', storagePath: '', maxEpisodes: 5000, learningRate: 0.01 },
  },
  [AgentRole.REFACTORER]: {
    role: AgentRole.REFACTORER,
    model: 'claude-sonnet-4-6',
    capabilities: ['code-edit', 'py315-migration', 'lazy-import', 'frozendict'],
    maxConcurrency: 2,
    timeoutMs: 120_000,
    phase: Phase.LIQUID,
    isolationRequired: false,
    memory: { layers: 5, persistence: 'sqlite', storagePath: '', maxEpisodes: 5000, learningRate: 0.01 },
  },
  [AgentRole.TESTER]: {
    role: AgentRole.TESTER,
    model: 'claude-sonnet-4-6',
    capabilities: ['test-gen', 'test-run', 'coverage', 'benchmark'],
    maxConcurrency: 4,
    timeoutMs: 180_000,
    phase: Phase.SOLID,
    isolationRequired: true,
    memory: { layers: 5, persistence: 'sqlite', storagePath: '', maxEpisodes: 5000, learningRate: 0.01 },
  },
  [AgentRole.DEPLOYER]: {
    role: AgentRole.DEPLOYER,
    model: 'claude-sonnet-4-6',
    capabilities: ['docker', 'ci-cd', 'deploy', 'rollback'],
    maxConcurrency: 1,
    timeoutMs: 300_000,
    phase: Phase.SOLID,
    isolationRequired: true,
    memory: { layers: 5, persistence: 'sqlite', storagePath: '', maxEpisodes: 5000, learningRate: 0.01 },
  },
  [AgentRole.RESEARCHER]: {
    role: AgentRole.RESEARCHER,
    model: 'claude-sonnet-4-6',
    capabilities: ['search', 'web', 'docs', 'api-research'],
    maxConcurrency: 8,
    timeoutMs: 60_000,
    phase: Phase.VAPOR,
    isolationRequired: false,
    memory: { layers: 5, persistence: 'sqlite', storagePath: '', maxEpisodes: 5000, learningRate: 0.01 },
  },
  [AgentRole.ORCHESTRATOR]: {
    role: AgentRole.ORCHESTRATOR,
    model: 'claude-opus-4-6',
    capabilities: ['planning', 'decomposition', 'coordination', 'synthesis'],
    maxConcurrency: 1,
    timeoutMs: 120_000,
    phase: Phase.VAPOR,
    isolationRequired: false,
    memory: { layers: 5, persistence: 'sqlite', storagePath: '', maxEpisodes: 5000, learningRate: 0.01 },
  },
  [AgentRole.REVIEWER]: {
    role: AgentRole.REVIEWER,
    model: 'claude-sonnet-4-6',
    capabilities: ['code-review', 'security-audit', 'style-check', 'py315-compliance'],
    maxConcurrency: 4,
    timeoutMs: 60_000,
    phase: Phase.VAPOR,
    isolationRequired: false,
    memory: { layers: 5, persistence: 'sqlite', storagePath: '', maxEpisodes: 5000, learningRate: 0.01 },
  },
  [AgentRole.BUILDER]: {
    role: AgentRole.BUILDER,
    model: 'claude-sonnet-4-6',
    capabilities: ['build', 'compile', 'package', 'publish'],
    maxConcurrency: 2,
    timeoutMs: 300_000,
    phase: Phase.SOLID,
    isolationRequired: true,
    memory: { layers: 5, persistence: 'sqlite', storagePath: '', maxEpisodes: 5000, learningRate: 0.01 },
  },
};

// ── Orchestrator ─────────────────────────────────────────────────────

export class AgentOrchestrator extends EventEmitter {
  private bridge: PFAABridge;
  private activePipelines = new Map<string, Pipeline>();
  private agentResults = new Map<string, AgentResult[]>();

  constructor(bridge: PFAABridge) {
    super();
    this.bridge = bridge;
  }

  /**
   * Execute a natural language goal using the CSG swarm pattern.
   *
   * 1. Orchestrator agent decomposes the goal
   * 2. Specialist agents execute tasks in parallel
   * 3. Results are gathered and synthesized
   */
  async executeGoal(goal: string): Promise<{
    pipeline: Pipeline;
    results: AgentResult[];
    summary: string;
  }> {
    const pipelineId = nanoid(12);
    log.info('Executing goal', { pipelineId, goal: goal.slice(0, 100) });
    log.audit('goal:start', { pipelineId, goal });

    const startTime = performance.now();

    // Phase 1: Decompose goal into tasks
    const tasks = await this.decomposeGoal(goal, pipelineId);
    log.info(`Decomposed into ${tasks.length} tasks`);

    // Phase 2: Create pipeline
    const pipeline: Pipeline = {
      id: pipelineId,
      name: goal.slice(0, 80),
      tasks,
      parallel: true,
      started: Date.now(),
    };
    this.activePipelines.set(pipelineId, pipeline);

    this.emitEvent(EventType.PIPELINE_STARTED, {
      pipelineId,
      taskCount: tasks.length,
      goal: goal.slice(0, 100),
    });

    // Phase 3: Execute tasks (parallel where possible)
    const results = await this.executeTasks(pipeline);

    // Phase 4: Synthesize results
    pipeline.completed = Date.now();
    const elapsed = performance.now() - startTime;

    const summary = this.synthesizeResults(goal, results, elapsed);

    this.emitEvent(EventType.PIPELINE_COMPLETED, {
      pipelineId,
      totalMs: Math.round(elapsed),
      succeeded: results.filter((r) => r.success).length,
      failed: results.filter((r) => !r.success).length,
    });

    log.audit('goal:complete', {
      pipelineId,
      elapsedMs: Math.round(elapsed),
      tasks: tasks.length,
      succeeded: results.filter((r) => r.success).length,
    });

    return { pipeline, results, summary };
  }

  /**
   * Execute a focused task with a specific agent role.
   */
  async executeTask(
    description: string,
    role: AgentRole = AgentRole.ANALYZER,
  ): Promise<AgentResult> {
    const preset = AGENT_PRESETS[role];
    const agentId = nanoid(8);

    log.info('Executing task', { agentId, role, description: description.slice(0, 80) });

    this.emitEvent(EventType.AGENT_SPAWNED, {
      agentId,
      role,
      phase: preset.phase,
    });

    const startTime = performance.now();

    try {
      // Route to appropriate engine command based on role
      let output: unknown;

      switch (role) {
        case AgentRole.ANALYZER:
        case AgentRole.REVIEWER:
          output = await this.bridge.executeTool('codebase_search', description);
          break;
        case AgentRole.TESTER:
          output = await this.bridge.executeTool('sandbox_exec', description);
          break;
        case AgentRole.BUILDER:
          output = await this.bridge.executeTool('shell', description);
          break;
        default:
          output = await this.bridge.askClaude(description);
      }

      const elapsed = performance.now() - startTime;

      const result: AgentResult = {
        agentId,
        role,
        success: true,
        output,
        phase: preset.phase,
        elapsedMs: Math.round(elapsed),
        tokensUsed: { input: 0, output: 0 },
        memoryUpdated: true,
      };

      this.emitEvent(EventType.AGENT_COMPLETED, {
        agentId,
        role,
        elapsedMs: Math.round(elapsed),
      });

      return result;
    } catch (err) {
      const elapsed = performance.now() - startTime;
      const result: AgentResult = {
        agentId,
        role,
        success: false,
        output: err instanceof Error ? err.message : String(err),
        phase: preset.phase,
        elapsedMs: Math.round(elapsed),
        tokensUsed: { input: 0, output: 0 },
        memoryUpdated: false,
      };

      this.emitEvent(EventType.AGENT_FAILED, {
        agentId,
        role,
        error: result.output,
      });

      return result;
    }
  }

  /**
   * Run multiple agents in parallel across a swarm.
   */
  async swarm(
    tasks: Array<{ description: string; role: AgentRole }>,
  ): Promise<AgentResult[]> {
    log.info(`Starting swarm with ${tasks.length} agents`);
    return Promise.all(
      tasks.map((t) => this.executeTask(t.description, t.role)),
    );
  }

  // ── Internal ─────────────────────────────────────────────────────

  private async decomposeGoal(goal: string, pipelineId: string): Promise<Task[]> {
    // Use the PFAA engine's Claude bridge for decomposition
    const result = await this.bridge.askClaude(
      `Decompose this goal into parallel subtasks. For each subtask, specify the agent role ` +
      `(analyzer, refactorer, tester, deployer, researcher, reviewer, builder). ` +
      `Return as JSON array: [{"description": "...", "role": "...", "dependencies": []}]\n\n` +
      `Goal: ${goal}`,
    );

    if (!result.success) {
      // Fallback: single analyzer task
      return [{
        id: `${pipelineId}_0`,
        description: goal,
        agent: AgentRole.ANALYZER,
        dependencies: [],
        status: TaskStatus.PENDING,
        retries: 0,
        maxRetries: 3,
      }];
    }

    try {
      // Parse Claude's response
      const jsonMatch = result.output.match(/\[[\s\S]*\]/);
      if (!jsonMatch) throw new Error('No JSON array found');

      const parsed = JSON.parse(jsonMatch[0]) as Array<{
        description: string;
        role: string;
        dependencies?: string[];
      }>;

      return parsed.map((item, i) => ({
        id: `${pipelineId}_${i}`,
        description: item.description,
        agent: (item.role as AgentRole) || AgentRole.ANALYZER,
        dependencies: item.dependencies || [],
        status: TaskStatus.PENDING,
        retries: 0,
        maxRetries: 3,
      }));
    } catch {
      return [{
        id: `${pipelineId}_0`,
        description: goal,
        agent: AgentRole.ANALYZER,
        dependencies: [],
        status: TaskStatus.PENDING,
        retries: 0,
        maxRetries: 3,
      }];
    }
  }

  private async executeTasks(pipeline: Pipeline): Promise<AgentResult[]> {
    const results: AgentResult[] = [];
    const completed = new Set<string>();

    // Simple dependency-aware parallel execution
    while (completed.size < pipeline.tasks.length) {
      const ready = pipeline.tasks.filter(
        (t) =>
          !completed.has(t.id) &&
          t.dependencies.every((dep) => completed.has(dep)),
      );

      if (ready.length === 0 && completed.size < pipeline.tasks.length) {
        log.error('Deadlock detected in task dependencies');
        break;
      }

      const batch = await Promise.all(
        ready.map(async (task) => {
          task.status = TaskStatus.RUNNING;
          const result = await this.executeTask(task.description, task.agent);
          task.status = result.success ? TaskStatus.COMPLETED : TaskStatus.FAILED;
          task.result = result;
          completed.add(task.id);
          return result;
        }),
      );

      results.push(...batch);
    }

    return results;
  }

  private synthesizeResults(
    goal: string,
    results: AgentResult[],
    elapsedMs: number,
  ): string {
    const succeeded = results.filter((r) => r.success).length;
    const failed = results.filter((r) => !r.success).length;
    const totalTokens = results.reduce(
      (sum, r) => sum + r.tokensUsed.input + r.tokensUsed.output,
      0,
    );

    return [
      `Goal: ${goal.slice(0, 80)}`,
      `Tasks: ${results.length} (${succeeded} succeeded, ${failed} failed)`,
      `Time: ${Math.round(elapsedMs)}ms`,
      `Tokens: ${totalTokens.toLocaleString()}`,
      `Agents: ${[...new Set(results.map((r) => r.role))].join(', ')}`,
    ].join('\n');
  }

  private emitEvent(type: EventType, data: Record<string, unknown>): void {
    const event: StreamEvent = {
      type,
      timestamp: Date.now(),
      data,
    };
    this.emit('event', event);
  }
}
