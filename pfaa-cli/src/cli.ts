#!/usr/bin/env node
/**
 * PFAA CLI — Enterprise AI Agent CLI for Python 3.15
 *
 * A Claude Code-class CLI that orchestrates the Phase-Fluid Agent
 * Architecture with enterprise features: multi-agent swarms, JMEM
 * semantic memory, adaptive caching, audit logging, and full
 * Python 3.15 code analysis tooling.
 *
 * Architecture:
 *   Node.js CLI (this) → PFAA Python Engine (subprocess bridge)
 *                       → Claude Agent SDK (AI orchestration)
 *                       → JMEM MCP Server (semantic memory)
 *                       → AI SDK 6 (tool calling + streaming)
 *
 * Usage:
 *   pfaa run "analyze this codebase for security issues"
 *   pfaa agent swarm --roles analyzer,reviewer,tester
 *   pfaa py315 analyze ./src --suggest-lazy-imports
 *   pfaa memory status
 *   pfaa bench
 */

import { Command } from 'commander';
import { readFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { homedir } from 'node:os';
import { loadConfig, initProjectConfig, type PFAAConfig } from './utils/config.js';
import { getLogger, setLogLevel, LogLevel } from './utils/logger.js';
import { createBridge, type PFAABridge } from './bridge/pfaa-bridge.js';
import { AgentOrchestrator } from './agents/orchestrator.js';
import { JMEMClient } from './memory/jmem-client.js';
import { RateLimiter } from './enterprise/rate-limiter.js';
import { AnalysisCache } from './enterprise/cache.js';
import { Python315Tools } from './tools/python315.js';
import { Phase, AgentRole, EventType } from './types.js';

const VERSION = '1.0.0';
const BANNER = `
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗ ███████╗ █████╗  █████╗      ██████╗██╗     ██╗   ║
║   ██╔══██╗██╔════╝██╔══██╗██╔══██╗    ██╔════╝██║     ██║   ║
║   ██████╔╝█████╗  ███████║███████║    ██║     ██║     ██║   ║
║   ██╔═══╝ ██╔══╝  ██╔══██║██╔══██║    ██║     ██║     ██║   ║
║   ██║     ██║     ██║  ██║██║  ██║    ╚██████╗███████╗██║   ║
║   ╚═╝     ╚═╝     ╚═╝  ╚═╝╚═╝  ╚═╝     ╚═════╝╚══════╝╚═╝   ║
║                                                              ║
║   Phase-Fluid Agent Architecture — Enterprise CLI v${VERSION}      ║
║   Python 3.15 · Multi-Agent · JMEM Memory · AI SDK 6        ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
`;

const log = getLogger('cli');

// ── Global State ─────────────────────────────────────────────────────

let config: PFAAConfig;
let bridge: PFAABridge;
let orchestrator: AgentOrchestrator;
let memory: JMEMClient;
let rateLimiter: RateLimiter;
let cache: AnalysisCache;
let py315: Python315Tools;

// ── CLI Setup ────────────────────────────────────────────────────────

const program = new Command();

program
  .name('pfaa')
  .version(VERSION)
  .description('Enterprise AI CLI — Phase-Fluid Agent Architecture for Python 3.15')
  .option('-v, --verbose', 'Enable verbose logging')
  .option('-q, --quiet', 'Suppress all output except results')
  .option('--no-color', 'Disable colored output')
  .option('--no-cache', 'Disable analysis caching')
  .option('--model <model>', 'Claude model to use', 'claude-sonnet-4-6')
  .option('--max-agents <n>', 'Max concurrent agents', '8')
  .option('--timeout <ms>', 'Global timeout in milliseconds', '120000')
  .option('--python <path>', 'Python 3.15 interpreter path', 'python3.15')
  .option('--config <path>', 'Path to config file')
  .hook('preAction', async (thisCommand) => {
    const opts = thisCommand.opts();
    config = loadConfig({
      model: opts.model,
      maxConcurrentAgents: parseInt(opts.maxAgents),
      timeoutMs: parseInt(opts.timeout),
      verbose: opts.verbose,
      color: opts.color !== false,
      python: { interpreterPath: opts.python } as any,
      enterprise: {
        cache: { enabled: opts.cache !== false } as any,
      } as any,
    });

    if (config.verbose) setLogLevel(LogLevel.DEBUG);
    if (opts.quiet) setLogLevel(LogLevel.ERROR);

    // Initialize subsystems
    bridge = createBridge({
      pythonPath: config.python.interpreterPath,
      enginePath: resolve(process.cwd()),
      workingDir: process.cwd(),
      timeoutMs: config.timeoutMs,
      maxConcurrent: config.maxConcurrentAgents,
    });

    orchestrator = new AgentOrchestrator(bridge);
    memory = new JMEMClient();
    rateLimiter = new RateLimiter(config.enterprise.rateLimit);
    cache = new AnalysisCache(config.enterprise.cache);
    py315 = new Python315Tools(config.python);

    // Wire up event streaming
    orchestrator.on('event', (event: any) => {
      if (config.verbose) {
        log.debug(`[${event.type}]`, event.data);
      }
    });
  });

// ── Command: run ─────────────────────────────────────────────────────

program
  .command('run <goal>')
  .description('Execute a natural language goal using the agent swarm')
  .option('-p, --parallel', 'Force parallel execution', true)
  .option('-r, --roles <roles>', 'Agent roles to use (comma-separated)')
  .option('--dry-run', 'Show plan without executing')
  .option('--stream', 'Stream results in real-time', true)
  .action(async (goal: string, opts) => {
    console.log(colorize('cyan', `\n⚡ PFAA — Executing goal...\n`));
    console.log(colorize('dim', `  Goal: ${goal}`));
    console.log(colorize('dim', `  Model: ${config.model}`));
    console.log(colorize('dim', `  Max Agents: ${config.maxConcurrentAgents}\n`));

    const startTime = performance.now();

    try {
      await bridge.start();
      await memory.connect();

      // Get context from JMEM before execution
      const context = await memory.getContext(goal);
      if (context.relevant.length > 0) {
        console.log(colorize('magenta', `  📚 Found ${context.relevant.length} relevant memories\n`));
      }

      await rateLimiter.acquireRequest();

      const result = await orchestrator.executeGoal(goal);
      const elapsed = performance.now() - startTime;

      // Display results
      console.log(colorize('green', '\n✅ Goal completed\n'));
      console.log(boxify(result.summary, 'Results'));

      // Show pipeline details
      const { pipeline, results } = result;
      console.log(colorize('dim', `\n  Pipeline: ${pipeline.tasks.length} tasks`));
      for (const task of pipeline.tasks) {
        const icon = task.status === 'completed' ? '✓' : '✗';
        const color = task.status === 'completed' ? 'green' : 'red';
        console.log(colorize(color, `    ${icon} [${task.agent}] ${task.description.slice(0, 60)}`));
      }

      console.log(colorize('dim', `\n  Total time: ${Math.round(elapsed)}ms`));

      // Learn from results
      await memory.learnFromPipeline(
        goal,
        results.map((r) => ({
          action: r.role,
          success: r.success,
          elapsedMs: r.elapsedMs,
        })),
      );

      log.audit('goal:executed', { goal, elapsed: Math.round(elapsed), tasks: pipeline.tasks.length });
    } catch (err) {
      console.error(colorize('red', `\n❌ Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    } finally {
      await bridge.stop();
    }
  });

// ── Command: agent ───────────────────────────────────────────────────

const agentCmd = program
  .command('agent')
  .description('Manage and run specialized agents');

agentCmd
  .command('swarm <goal>')
  .description('Execute a goal with a multi-agent swarm')
  .option('-r, --roles <roles>', 'Comma-separated agent roles', 'analyzer,reviewer,tester')
  .option('-c, --concurrency <n>', 'Max concurrent agents', '4')
  .action(async (goal: string, opts) => {
    const roles = opts.roles.split(',').map((r: string) => r.trim() as AgentRole);
    console.log(colorize('cyan', `\n🐝 Swarm: ${roles.length} agents\n`));

    try {
      await bridge.start();
      const tasks = roles.map((role: AgentRole) => ({ description: goal, role }));
      const results = await orchestrator.swarm(tasks);

      for (const r of results) {
        const icon = r.success ? '✓' : '✗';
        const color = r.success ? 'green' : 'red';
        console.log(colorize(color, `  ${icon} [${r.role}] ${r.elapsedMs}ms — ${r.phase} phase`));
      }

      const succeeded = results.filter((r) => r.success).length;
      console.log(colorize('dim', `\n  ${succeeded}/${results.length} agents succeeded`));
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    } finally {
      await bridge.stop();
    }
  });

agentCmd
  .command('exec <description>')
  .description('Run a single specialized agent')
  .option('-r, --role <role>', 'Agent role', 'analyzer')
  .action(async (description: string, opts) => {
    try {
      await bridge.start();
      const result = await orchestrator.executeTask(description, opts.role as AgentRole);

      console.log(colorize(result.success ? 'green' : 'red',
        `\n${result.success ? '✓' : '✗'} [${result.role}] ${result.elapsedMs}ms — ${result.phase} phase`));

      if (result.output) {
        console.log(boxify(
          typeof result.output === 'string' ? result.output : JSON.stringify(result.output, null, 2),
          `${result.role} output`,
        ));
      }
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    } finally {
      await bridge.stop();
    }
  });

agentCmd
  .command('list')
  .description('List available agent roles and their capabilities')
  .action(() => {
    const roles = Object.values(AgentRole);
    console.log(colorize('cyan', '\n📋 Available Agent Roles\n'));

    const roleInfo: Record<string, { phase: string; capabilities: string[] }> = {
      analyzer: { phase: 'VAPOR', capabilities: ['code-analysis', 'py315-detection', 'complexity', 'security'] },
      refactorer: { phase: 'LIQUID', capabilities: ['code-edit', 'py315-migration', 'lazy-import', 'frozendict'] },
      tester: { phase: 'SOLID', capabilities: ['test-gen', 'test-run', 'coverage', 'benchmark'] },
      deployer: { phase: 'SOLID', capabilities: ['docker', 'ci-cd', 'deploy', 'rollback'] },
      researcher: { phase: 'VAPOR', capabilities: ['search', 'web', 'docs', 'api-research'] },
      orchestrator: { phase: 'VAPOR', capabilities: ['planning', 'decomposition', 'coordination'] },
      reviewer: { phase: 'VAPOR', capabilities: ['code-review', 'security-audit', 'py315-compliance'] },
      builder: { phase: 'SOLID', capabilities: ['build', 'compile', 'package', 'publish'] },
    };

    for (const role of roles) {
      const info = roleInfo[role] || { phase: '?', capabilities: [] };
      console.log(colorize('yellow', `  ${role.padEnd(14)}`),
        colorize('dim', `[${info.phase}]`),
        info.capabilities.join(', '));
    }
    console.log();
  });

// ── Command: py315 ───────────────────────────────────────────────────

const py315Cmd = program
  .command('py315')
  .description('Python 3.15 code analysis and optimization tools');

py315Cmd
  .command('analyze <path>')
  .description('Analyze Python files for 3.15 features and opportunities')
  .option('--suggest-lazy-imports', 'Suggest PEP 810 lazy import conversions')
  .option('--suggest-frozendict', 'Suggest PEP 814 frozendict usage')
  .option('--json', 'Output as JSON')
  .action((path: string, opts) => {
    const fullPath = resolve(path);
    console.log(colorize('cyan', `\n🐍 Python 3.15 Analysis: ${path}\n`));

    const analysis = py315.analyzeFile(fullPath);

    if (opts.json) {
      console.log(JSON.stringify(analysis, null, 2));
      return;
    }

    // Features found
    if (analysis.py315Features.length > 0) {
      console.log(colorize('green', `  ✅ Python 3.15 Features (${analysis.py315Features.length}):\n`));
      for (const f of analysis.py315Features) {
        console.log(`    L${f.line}: ${colorize('yellow', f.pep)} — ${f.usage}`);
      }
    }

    // Issues
    if (analysis.issues.length > 0) {
      console.log(colorize('yellow', `\n  ⚠ Issues (${analysis.issues.length}):\n`));
      for (const issue of analysis.issues) {
        const color = issue.severity === 'error' ? 'red' : issue.severity === 'warning' ? 'yellow' : 'dim';
        console.log(`    L${issue.line}: ${colorize(color, `[${issue.severity}]`)} ${issue.message}`);
      }
    }

    // Suggestions
    if (analysis.suggestions.length > 0) {
      console.log(colorize('magenta', `\n  💡 Suggestions (${analysis.suggestions.length}):\n`));
      for (const s of analysis.suggestions) {
        console.log(`    L${s.line}: ${colorize('dim', s.original)} → ${colorize('green', s.suggested)}`);
        console.log(colorize('dim', `           ${s.reason}`));
      }
    }

    console.log(colorize('dim', `\n  Complexity: ${analysis.complexity}`));
    console.log();
  });

py315Cmd
  .command('check')
  .description('Check Python 3.15 runtime availability')
  .action(async () => {
    console.log(colorize('cyan', '\n🐍 Python 3.15 Runtime Check\n'));

    const result = await py315.checkRuntime();

    if (result.available) {
      console.log(colorize('green', `  ✅ Python ${result.version} available`));
      console.log(colorize('dim', `  Path: ${result.path}`));
      console.log(colorize('dim', `  GIL: ${result.gilEnabled ? 'enabled' : 'disabled (free-threading)'}`));
      console.log(colorize('dim', `  Features: ${result.features.join(', ') || 'none detected'}`));
    } else {
      console.log(colorize('red', '  ❌ Python 3.15 not found'));
      console.log(colorize('dim', '  Install: https://www.python.org/downloads/'));
      console.log(colorize('dim', `  Tried: ${config.python.interpreterPath}`));
    }
    console.log();
  });

py315Cmd
  .command('lazy-imports <path>')
  .description('Suggest PEP 810 lazy import conversions')
  .action((path: string) => {
    const suggestions = py315.suggestLazyImports(resolve(path));
    console.log(colorize('cyan', `\n📦 Lazy Import Suggestions: ${path}\n`));

    if (suggestions.length === 0) {
      console.log(colorize('green', '  ✅ No lazy import opportunities found\n'));
      return;
    }

    for (const s of suggestions) {
      console.log(`  L${s.line}: ${colorize('red', s.original)} → ${colorize('green', s.suggested)}`);
      console.log(colorize('dim', `         ${s.reason}\n`));
    }
  });

// ── Command: memory ──────────────────────────────────────────────────

const memoryCmd = program
  .command('memory')
  .description('JMEM semantic memory operations');

memoryCmd
  .command('status')
  .description('Show memory status across all 5 cognitive layers')
  .action(async () => {
    await memory.connect();
    const status = await memory.status();
    console.log(colorize('cyan', '\n🧠 JMEM Memory Status\n'));
    console.log(`  L1 Episodic:     ${colorize('green', String(status.l1Episodes))} episodes`);
    console.log(`  L2 Semantic:     ${colorize('green', String(status.l2Patterns))} patterns`);
    console.log(`  L3 Strategic:    ${colorize('green', String(status.l3Strategies))} strategies`);
    console.log(`  L4 Meta-Learn:   ${colorize('yellow', status.l4LearningRate.toFixed(3))} rate`);
    console.log(`  L5 Emergent:     ${colorize('magenta', String(status.l5Knowledge))} knowledge items`);
    console.log(`  DB Size:         ${status.dbSizeKb} KB`);
    console.log();
  });

memoryCmd
  .command('recall <query>')
  .description('Recall relevant memories for a query')
  .option('-l, --layer <n>', 'Memory layer (1-5)')
  .option('-n, --limit <n>', 'Max results', '10')
  .action(async (query: string, opts) => {
    await memory.connect();
    const entries = await memory.recall(query, opts.layer ? parseInt(opts.layer) : undefined, parseInt(opts.limit));
    console.log(colorize('cyan', `\n🔍 Memory Recall: "${query}"\n`));

    if (entries.length === 0) {
      console.log(colorize('dim', '  No matching memories found.\n'));
      return;
    }

    for (const entry of entries) {
      console.log(`  [L${entry.layer}] Score: ${entry.score.toFixed(2)}`);
      console.log(colorize('dim', `  ${entry.content.slice(0, 120)}`));
      console.log();
    }
  });

memoryCmd
  .command('consolidate')
  .description('Run memory consolidation — promote validated knowledge')
  .action(async () => {
    console.log(colorize('cyan', '\n🔄 Consolidating memory...\n'));
    await memory.connect();
    const stats = await memory.consolidate();
    console.log(`  Promoted: ${colorize('green', String(stats.promoted))}`);
    console.log(`  Pruned:   ${colorize('red', String(stats.pruned))}`);
    console.log(`  Merged:   ${colorize('yellow', String(stats.merged))}`);
    console.log();
  });

// ── Command: tools ───────────────────────────────────────────────────

program
  .command('tools')
  .description('List all available PFAA tools')
  .action(async () => {
    try {
      await bridge.start();
      const tools = await bridge.listTools();
      console.log(colorize('cyan', `\n🛠  PFAA Tools (${tools.length} registered)\n`));

      for (const tool of tools) {
        const phaseColor = tool.phase === 'VAPOR' ? 'cyan' : tool.phase === 'LIQUID' ? 'yellow' : 'red';
        console.log(`  ${tool.name.padEnd(20)} ${colorize(phaseColor, tool.phase.padEnd(8))} ${tool.description}`);
      }
      console.log();
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
    } finally {
      await bridge.stop();
    }
  });

// ── Command: bench ───────────────────────────────────────────────────

program
  .command('bench')
  .description('Run PFAA performance benchmarks')
  .action(async () => {
    console.log(colorize('cyan', '\n⏱  Running PFAA Benchmarks...\n'));

    try {
      await bridge.start();
      const results = await bridge.benchmark();
      console.log(boxify(JSON.stringify(results, null, 2), 'Benchmark Results'));
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
    } finally {
      await bridge.stop();
    }
  });

// ── Command: status ──────────────────────────────────────────────────

program
  .command('status')
  .description('Show full system status')
  .action(async () => {
    console.log(BANNER);

    // Python runtime
    const pyResult = await py315.checkRuntime();
    console.log(colorize('cyan', '  Runtime'));
    console.log(`    Python:  ${pyResult.available ? colorize('green', pyResult.version) : colorize('red', 'not found')}`);
    console.log(`    Node:    ${colorize('green', process.version)}`);
    console.log(`    Model:   ${colorize('yellow', config.model)}`);
    console.log(`    GIL:     ${pyResult.gilEnabled ? 'enabled' : colorize('green', 'free-threading')}`);

    // Cache
    const cacheStatus = cache.status();
    console.log(colorize('cyan', '\n  Cache'));
    console.log(`    Entries: ${cacheStatus.entries}/${cacheStatus.maxEntries}`);
    console.log(`    Hit Rate: ${(cacheStatus.hitRate * 100).toFixed(1)}%`);

    // Rate limiter
    const rlStatus = rateLimiter.status();
    console.log(colorize('cyan', '\n  Rate Limits'));
    console.log(`    Requests: ${rlStatus.requestsAvailable} available`);
    console.log(`    Agents:   ${rlStatus.activeAgents}/${rlStatus.maxAgents}`);

    // Memory
    try {
      await memory.connect();
      const memStatus = await memory.status();
      console.log(colorize('cyan', '\n  JMEM Memory'));
      console.log(`    Episodes:   ${memStatus.l1Episodes}`);
      console.log(`    Patterns:   ${memStatus.l2Patterns}`);
      console.log(`    Strategies: ${memStatus.l3Strategies}`);
      console.log(`    Knowledge:  ${memStatus.l5Knowledge}`);
    } catch {
      console.log(colorize('cyan', '\n  JMEM Memory'));
      console.log(colorize('dim', '    Not connected'));
    }

    console.log();
  });

// ── Command: init ────────────────────────────────────────────────────

program
  .command('init')
  .description('Initialize PFAA configuration in current project')
  .action(() => {
    initProjectConfig();
    console.log(colorize('green', '\n✅ Created .pfaa.yaml in current directory\n'));
    console.log(colorize('dim', '  Edit this file to configure PFAA for your project.'));
    console.log(colorize('dim', '  Run `pfaa status` to verify your setup.\n'));
  });

// ── Command: ask ─────────────────────────────────────────────────────

program
  .command('ask <prompt>')
  .description('Ask Claude a question via the PFAA bridge')
  .option('-m, --model <model>', 'Claude model')
  .action(async (prompt: string, opts) => {
    try {
      await bridge.start();
      await rateLimiter.acquireRequest();

      console.log(colorize('dim', '\n  Asking Claude...\n'));
      const result = await bridge.askClaude(prompt, opts.model);

      if (result.success) {
        console.log(boxify(result.output, `Claude (${opts.model || config.model}) — ${Math.round(result.elapsedMs)}ms`));
      } else {
        console.error(colorize('red', `  Error: ${result.output}`));
      }
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
    } finally {
      await bridge.stop();
    }
  });

// ── Command: self-build ──────────────────────────────────────────────

program
  .command('self-build')
  .description('Run a self-improvement cycle — the engine builds itself')
  .option('--apply', 'Auto-apply validated changes')
  .action(async (opts) => {
    console.log(colorize('cyan', '\n🔧 Running self-build cycle...\n'));

    try {
      await bridge.start();
      const result = await bridge.selfBuild(opts.apply);
      console.log(boxify(JSON.stringify(result, null, 2), 'Self-Build Results'));
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
    } finally {
      await bridge.stop();
    }
  });

// ── Utility Functions ────────────────────────────────────────────────

type Color = 'red' | 'green' | 'yellow' | 'cyan' | 'magenta' | 'dim' | 'white';

function colorize(color: Color, text: string): string {
  if (config && !config.color) return text;

  const codes: Record<Color, string> = {
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    cyan: '\x1b[36m',
    magenta: '\x1b[35m',
    dim: '\x1b[2m',
    white: '\x1b[37m',
  };

  return `${codes[color] || ''}${text}\x1b[0m`;
}

function boxify(content: string, title: string): string {
  const lines = content.split('\n');
  const maxLen = Math.max(title.length + 4, ...lines.map((l) => l.length + 4));
  const border = '─'.repeat(maxLen);

  return [
    `  ┌${border}┐`,
    `  │ ${title.padEnd(maxLen - 2)} │`,
    `  ├${border}┤`,
    ...lines.map((l) => `  │ ${l.padEnd(maxLen - 2)} │`),
    `  └${border}┘`,
  ].join('\n');
}

// ── Entry Point ──────────────────────────────────────────────────────

program.parse(process.argv);

// Show banner if no command provided
if (process.argv.length <= 2) {
  console.log(BANNER);
  program.outputHelp();
}
