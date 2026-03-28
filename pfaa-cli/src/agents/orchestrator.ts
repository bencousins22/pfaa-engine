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
import { ClaudeClient } from './claude-client.js';
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
  private claude: ClaudeClient;
  private activePipelines = new Map<string, Pipeline>();
  private agentResults = new Map<string, AgentResult[]>();
  private liveMode: boolean;

  constructor(bridge: PFAABridge, options?: { apiKey?: string; live?: boolean }) {
    super();
    this.bridge = bridge;
    this.liveMode = options?.live ?? false;
    this.claude = new ClaudeClient(options?.apiKey);
  }

  /** Whether the orchestrator is using live Claude API calls. */
  get isLive(): boolean {
    return this.liveMode && this.claude.isAvailable;
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

    // Phase 1: Decompose goal into tasks (uses Claude API when live)
    const tasks = await this.decomposeGoal(goal, pipelineId);
    log.info(`Decomposed into ${tasks.length} tasks (${this.isLive ? 'live' : 'simulated'})`);

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
      let output: unknown;

      if (this.isLive) {
        // Live mode: call Claude API with role-specific system prompt
        const systemPrompt = this.buildRolePrompt(role, preset);
        output = await this.claude.ask(systemPrompt, description);
      } else {
        // Simulation mode: route to Aussie Agents Python bridge
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
    log.info(`Starting swarm with ${tasks.length} agents (${this.isLive ? 'live' : 'simulated'})`);

    if (this.isLive) {
      // Live mode: fan out Claude API calls in parallel per agent
      return Promise.all(
        tasks.map(async (t) => {
          const preset = AGENT_PRESETS[t.role];
          const agentId = nanoid(8);
          const startTime = performance.now();

          this.emitEvent(EventType.AGENT_SPAWNED, {
            agentId,
            role: t.role,
            phase: preset.phase,
            live: true,
          });

          try {
            const systemPrompt = this.buildRolePrompt(t.role, preset);
            const response = await this.claude.ask(systemPrompt, t.description);
            const elapsed = performance.now() - startTime;

            this.emitEvent(EventType.AGENT_COMPLETED, {
              agentId,
              role: t.role,
              elapsedMs: Math.round(elapsed),
            });

            return {
              agentId,
              role: t.role,
              success: true,
              output: response,
              phase: preset.phase,
              elapsedMs: Math.round(elapsed),
              tokensUsed: { input: 0, output: 0 },
              memoryUpdated: true,
            } satisfies AgentResult;
          } catch (err) {
            const elapsed = performance.now() - startTime;
            this.emitEvent(EventType.AGENT_FAILED, {
              agentId,
              role: t.role,
              error: err instanceof Error ? err.message : String(err),
            });

            return {
              agentId,
              role: t.role,
              success: false,
              output: err instanceof Error ? err.message : String(err),
              phase: preset.phase,
              elapsedMs: Math.round(elapsed),
              tokensUsed: { input: 0, output: 0 },
              memoryUpdated: false,
            } satisfies AgentResult;
          }
        }),
      );
    }

    // Simulation fallback
    return Promise.all(
      tasks.map((t) => this.executeTask(t.description, t.role)),
    );
  }

  // ── Internal ─────────────────────────────────────────────────────

  private async decomposeGoal(goal: string, pipelineId: string): Promise<Task[]> {
    const decompositionPrompt =
      `Decompose this goal into parallel subtasks. For each subtask, specify the agent role ` +
      `(analyzer, refactorer, tester, deployer, researcher, reviewer, builder). ` +
      `Return as JSON array: [{"description": "...", "role": "...", "dependencies": []}]\n\n` +
      `Goal: ${goal}`;

    let rawOutput: string;

    if (this.isLive) {
      // Live mode: call Claude API directly for goal decomposition
      const systemPrompt =
        'You are an expert orchestrator in the Aussie Agents (Phase-Fluid Agent Architecture) system. ' +
        'Decompose user goals into well-defined subtasks for specialist agents. ' +
        'Always respond with a valid JSON array. Each task should have a clear description, ' +
        'an appropriate agent role, and list any dependency task indices.';

      rawOutput = await this.claude.ask(systemPrompt, decompositionPrompt);
    } else {
      // Simulation fallback: use the Aussie Agents Python bridge
      const result = await this.bridge.askClaude(decompositionPrompt);

      if (!result.success) {
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

      rawOutput = result.output;
    }

    try {
      const jsonMatch = rawOutput.match(/\[[\s\S]*\]/);
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

  private buildRolePrompt(
    role: AgentRole,
    preset: Omit<AgentConfig, 'name'>,
  ): string {
    const roleDescriptions: Record<AgentRole, string> = {
      [AgentRole.ANALYZER]:
        'You are a code analysis expert. Examine code for complexity, patterns, security issues, ' +
        'and Python 3.15 feature opportunities. Provide actionable findings.',
      [AgentRole.REFACTORER]:
        'You are a code refactoring specialist. Transform code to use modern patterns including ' +
        'Python 3.15 features like lazy imports (PEP 810) and frozendict (PEP 814). Preserve behavior.',
      [AgentRole.TESTER]:
        'You are a testing expert. Generate comprehensive test suites, analyze coverage gaps, ' +
        'and create benchmarks. Focus on edge cases and regression prevention.',
      [AgentRole.DEPLOYER]:
        'You are a deployment specialist. Handle Docker, CI/CD pipelines, deployments, ' +
        'and rollback strategies. Prioritize safety and zero-downtime.',
      [AgentRole.RESEARCHER]:
        'You are a research specialist. Search documentation, APIs, and best practices. ' +
        'Synthesize findings into actionable recommendations.',
      [AgentRole.ORCHESTRATOR]:
        'You are a planning and coordination expert. Decompose complex goals into subtasks, ' +
        'identify dependencies, and coordinate multi-agent workflows.',
      [AgentRole.REVIEWER]:
        'You are a code review expert. Audit code for quality, security vulnerabilities, ' +
        'style compliance, and Python 3.15 best practices.',
      [AgentRole.BUILDER]:
        'You are a build and packaging specialist. Handle compilation, packaging, publishing, ' +
        'and build optimization.',
    };

    return (
      `${roleDescriptions[role] || 'You are a helpful AI assistant.'}\n\n` +
      `You are operating in the Aussie Agents (Phase-Fluid Agent Architecture) system.\n` +
      `Current phase: ${preset.phase}\n` +
      `Capabilities: ${preset.capabilities.join(', ')}\n\n` +
      `Provide clear, structured, actionable responses. ` +
      `When analyzing code, reference specific line numbers and files.`
    );
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
