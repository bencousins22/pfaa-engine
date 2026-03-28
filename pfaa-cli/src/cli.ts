#!/usr/bin/env node
/**
 * @aussie-agents/pfaa — Phase-Fluid Agent Architecture CLI
 *
 * 48 tools · 5-layer memory · multi-agent swarms · Python 3.15
 *
 * Usage:
 *   pfaa run "analyze this codebase"         # Goal execution
 *   pfaa exec -c "print(1+1)"                # Python sandbox
 *   pfaa swarm "find security issues"         # 9-tier agent swarm
 *   pfaa tool shell "ls -la"                  # Single tool
 *   pfaa scatter grep "TODO" "FIXME" "HACK"   # Fan-out tool
 *   pfaa pipeline shell:ls glob:*.py          # Sequential pipeline
 *   pfaa memory stats                         # JMEM health
 *   pfaa team "optimize database"             # Spawn agent team
 *   pfaa explore --rounds 200                 # Phase exploration
 *   pfaa learn                                # Force learning cycle
 *   pfaa self-build --apply                   # Self-improvement
 *   pfaa status                               # Full system status
 */

import { Command } from 'commander';
import { readFileSync, existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { homedir } from 'node:os';
import { createInterface } from 'node:readline';
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

/** JMEM-branded banner — emerald green + gold on dark */
function renderBanner(): string {
  const R = '\x1b[0m';

  // JMEM brand palette (from screenshot)
  const GOLD    = '\x1b[38;2;201;167;59m';   // #C9A73B — muted gold
  const GOLDBR  = '\x1b[38;2;212;160;23m';   // #D4A017 — bright gold
  const GREEN   = '\x1b[38;2;0;230;118m';    // #00E676 — emerald bright
  const GREEND  = '\x1b[38;2;76;175;80m';    // #4CAF50 — emerald mid
  const GREENDD = '\x1b[38;2;46;125;50m';    // #2E7D32 — emerald dark
  const DIM     = '\x1b[38;2;90;100;85m';    // muted grey-green
  const WHITE   = '\x1b[38;2;220;225;215m';  // warm white

  // Gradient line: gold → emerald
  const lineW = 60;
  let gradLine = '';
  for (let i = 0; i < lineW; i++) {
    const t = i / lineW;
    const r = Math.round(201 * (1 - t));
    const g = Math.round(167 + (230 - 167) * t);
    const b = Math.round(59 + (118 - 59) * t);
    gradLine += `\x1b[38;2;${r};${g};${b}m━`;
  }

  // Per-character gradient for "AUSSIE AGENTS"
  const title = 'AUSSIE  AGENTS';
  const titleStops: [number, number, number][] = [
    [255, 200, 40],   // gold
    [255, 160, 20],   // amber
    [255, 120, 40],   // orange
    [220, 80, 120],   // coral
    [0, 200, 100],    // emerald
    [0, 230, 118],    // bright green
    [0, 220, 160],    // teal
    [0, 200, 200],    // cyan
    [0, 180, 220],    // sky
    [40, 160, 255],   // blue
    [100, 140, 255],  // indigo
    [0, 230, 118],    // back to green
    [0, 200, 100],    // emerald
    [0, 180, 80],     // dark green
  ];
  let colorTitle = '  \x1b[1m';
  for (let i = 0; i < title.length; i++) {
    if (title[i] === ' ') { colorTitle += ' '; continue; }
    const t = i / (title.length - 1);
    const idx = t * (titleStops.length - 1);
    const lo = Math.floor(idx);
    const hi = Math.min(lo + 1, titleStops.length - 1);
    const f = idx - lo;
    const cr = Math.round(titleStops[lo][0] + (titleStops[hi][0] - titleStops[lo][0]) * f);
    const cg = Math.round(titleStops[lo][1] + (titleStops[hi][1] - titleStops[lo][1]) * f);
    const cb = Math.round(titleStops[lo][2] + (titleStops[hi][2] - titleStops[lo][2]) * f);
    colorTitle += `\x1b[38;2;${cr};${cg};${cb}m${title[i]}`;
  }
  colorTitle += R;

  // Wider rainbow gradient separator
  const lineW2 = 70;
  let rainbowLine = '';
  const rainbowStops: [number, number, number][] = [
    [255, 200, 40], [255, 140, 30], [255, 80, 80], [220, 60, 160],
    [140, 60, 240], [60, 120, 255], [0, 200, 200], [0, 230, 118], [0, 180, 80],
  ];
  for (let i = 0; i < lineW2; i++) {
    const t = i / lineW2;
    const idx = t * (rainbowStops.length - 1);
    const lo = Math.floor(idx);
    const hi = Math.min(lo + 1, rainbowStops.length - 1);
    const f = idx - lo;
    const cr = Math.round(rainbowStops[lo][0] + (rainbowStops[hi][0] - rainbowStops[lo][0]) * f);
    const cg = Math.round(rainbowStops[lo][1] + (rainbowStops[hi][1] - rainbowStops[lo][1]) * f);
    const cb = Math.round(rainbowStops[lo][2] + (rainbowStops[hi][2] - rainbowStops[lo][2]) * f);
    rainbowLine += `\x1b[38;2;${cr};${cg};${cb}m━`;
  }

  return [
    '',
    colorTitle,
    `  ${rainbowLine}${R}`,
    `  ${DIM}v${VERSION}${R}  ${GREENDD}│${R}  \x1b[38;2;255;200;40m\x1b[1m44${R} \x1b[38;2;255;160;20mTools${R}  ${GREENDD}│${R}  \x1b[38;2;0;200;200m\x1b[1m17${R} \x1b[38;2;0;180;180mMCP${R}  ${GREENDD}│${R}  \x1b[38;2;140;60;240m\x1b[1m5${R}\x1b[38;2;120;80;200m-Layer Memory${R}  ${GREENDD}│${R}  \x1b[38;2;255;80;80m\x1b[1m6${R} \x1b[38;2;220;60;60mHooks${R}  ${GREENDD}│${R}  ${GREEN}\x1b[1mPy${R}${GREEND} 3.15${R}`,
    '',
  ].join('\n');
}

const log = getLogger('cli');

// ── Global State ─────────────────────────────────────────────────────

let config: PFAAConfig;
let bridge: PFAABridge;
let orchestrator: AgentOrchestrator;
let memory: JMEMClient;
let rateLimiter: RateLimiter;
let cache: AnalysisCache;
let py315: Python315Tools;

// ═════════════════════════════════════════════════════════════════════
// RENDERING ENGINE — Aussie Agents colors + Rich-style tables & panels
// ═════════════════════════════════════════════════════════════════════

const R = '\x1b[0m';  // reset

// ── 256-color / hex helpers ──────────────────────────────────────────

function rgb(r: number, g: number, b: number): string {
  return `\x1b[38;2;${r};${g};${b}m`;
}

function bgRgb(r: number, g: number, b: number): string {
  return `\x1b[48;2;${r};${g};${b}m`;
}

function hex(h: string): string {
  const n = parseInt(h.replace('#', ''), 16);
  return rgb((n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF);
}

function bgHex(h: string): string {
  const n = parseInt(h.replace('#', ''), 16);
  return bgRgb((n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF);
}

// ── Aussie Agents PrintStyle — JMEM brand: emerald + gold ───────────

const AZ = {
  // User prompt: gold background, dark text
  userPrompt:  (t: string) => `${bgHex('#D4A017')}${hex('#1a1a1a')}\x1b[1m ${t} ${R}`,
  // Agent header: emerald background, white text
  agentHeader: (t: string) => `${bgHex('#2E7D32')}\x1b[37m\x1b[1m ${t} ${R}`,
  // Agent generating: dark bg, bright emerald text
  agentGen:    (t: string) => `${bgHex('#1a2e1a')}${hex('#00E676')}\x1b[1m ${t} ${R}`,
  // Agent streaming text: bright emerald italic
  agentText:   (t: string) => `${hex('#00E676')}\x1b[3m${t}${R}`,
  // Tool header: gold bg, dark text
  toolHead:    (t: string) => `${bgHex('#C9A73B')}${hex('#1a1a1a')}\x1b[1m ${t} ${R}`,
  // Key/value: gold keys, emerald values
  toolKey:     (t: string) => `${hex('#C9A73B')}\x1b[1m${t}${R}`,
  toolVal:     (t: string) => `${hex('#4CAF50')}${t}${R}`,
  // Status colors
  error:       (t: string) => `${hex('#EF5350')}${t}${R}`,
  warning:     (t: string) => `${hex('#D4A017')}${t}${R}`,
  hint:        (t: string) => `${hex('#2E7D32')}${t}${R}`,
  info:        (t: string) => `${hex('#4CAF50')}${t}${R}`,
  success:     (t: string) => `${hex('#00E676')}${t}${R}`,
  dim:         (t: string) => `${hex('#5A6A5A')}${t}${R}`,
  dead:        (t: string) => `${bgHex('#B71C1C')}\x1b[37m ${t} ${R}`,
  cleanup:     (t: string) => `${bgHex('#C9A73B')}${hex('#1a1a1a')}\x1b[1m ${t} ${R}`,
};

// ── Simple color shorthand (backward compat) ────────────────────────

type Color = 'red' | 'green' | 'yellow' | 'cyan' | 'magenta' | 'dim' | 'white';

function colorize(color: Color, text: string): string {
  if (config && !config.color) return text;
  const codes: Record<Color, string> = {
    red: '\x1b[31m', green: '\x1b[32m', yellow: '\x1b[33m',
    cyan: '\x1b[36m', magenta: '\x1b[35m', dim: '\x1b[2m', white: '\x1b[37m',
  };
  return `${codes[color] || ''}${text}${R}`;
}

// ── Rich-style Table ─────────────────────────────────────────────────

interface TableColumn {
  header: string;
  style?: Color;
  width?: number;
  align?: 'left' | 'right';
}

function table(title: string, columns: TableColumn[], rows: string[][]): string {
  const B = '\x1b[38;2;46;125;50m'; // JMEM emerald dark borders

  // Calculate column widths
  const widths = columns.map((col, i) =>
    Math.max(col.header.length, col.width || 0, ...rows.map((r) => stripAnsi(r[i] || '').length)));
  const totalW = widths.reduce((a, b) => a + b, 0) + (columns.length - 1) * 3 + 4;

  const hLine = (l: string, m: string, r: string) =>
    `  ${B}${l}${widths.map((w) => '─'.repeat(w + 2)).join(m)}${r}${R}`;

  const fmtRow = (cells: string[], styles?: (Color | undefined)[]) =>
    `  ${B}│${R}${cells.map((cell, i) => {
      const stripped = stripAnsi(cell);
      const pad = widths[i] - stripped.length;
      const padded = columns[i].align === 'right'
        ? ' '.repeat(pad) + cell
        : cell + ' '.repeat(pad);
      const styled = styles?.[i] ? colorize(styles[i]!, padded) : padded;
      return ` ${styled} `;
    }).join(`${B}│${R}`)}${B}│${R}`;

  const titlePad = Math.max(0, totalW - stripAnsi(title).length - 4);
  const lines = [
    hLine('┌', '┬', '┐'),
    `  ${B}│${R} \x1b[38;2;212;160;23m\x1b[1m${title}${R}${' '.repeat(titlePad)} ${B}│${R}`,
    hLine('├', '┼', '┤'),
    fmtRow(columns.map((c) => c.header), columns.map((c) => c.style || 'cyan')),
    hLine('├', '┼', '┤'),
    ...rows.map((r) => fmtRow(r, columns.map((c) => c.style))),
    hLine('└', '┴', '┘'),
  ];
  return lines.join('\n');
}

function stripAnsi(s: string): string {
  return s.replace(/\x1b\[[0-9;]*m/g, '');
}

// ── Rich-style Panel ─────────────────────────────────────────────────

function panel(content: string, title: string, borderColor: Color = 'cyan'): string {
  const B = borderColor === 'cyan' ? '\x1b[38;2;46;125;50m'          // emerald dark
    : borderColor === 'magenta' ? '\x1b[38;2;46;125;50m'           // emerald dark
    : borderColor === 'yellow' ? '\x1b[38;2;170;130;30m'           // muted gold
    : borderColor === 'green' ? '\x1b[38;2;76;175;80m'             // emerald mid
    : borderColor === 'red' ? '\x1b[38;2;200;60;60m'               // red
    : '\x1b[38;2;55;65;50m';                                       // dark grey-green

  const lines = content.split('\n');
  const titleLen = stripAnsi(title).length;
  const maxLen = Math.max(titleLen + 4, ...lines.map((l) => stripAnsi(l).length + 4));
  const border = '─'.repeat(maxLen);
  return [
    `  ${B}┌${border}┐${R}`,
    `  ${B}│${R} ${title}${' '.repeat(maxLen - titleLen - 2)} ${B}│${R}`,
    `  ${B}├${border}┤${R}`,
    ...lines.map((l) => {
      const pad = maxLen - stripAnsi(l).length - 2;
      return `  ${B}│${R} ${l}${' '.repeat(Math.max(0, pad))} ${B}│${R}`;
    }),
    `  ${B}└${border}┘${R}`,
  ].join('\n');
}

// ── Bar Chart ────────────────────────────────────────────────────────

function bar(value: number, max: number, width: number = 30): string {
  const filled = Math.round((value / Math.max(max, 1)) * width);
  const empty = width - filled;
  // Gradient bar: bright emerald → dark forest
  let result = '';
  for (let i = 0; i < filled; i++) {
    const t = filled > 1 ? i / (filled - 1) : 0;
    const r = Math.round(0);
    const g = Math.round(230 - t * 110);
    const b = Math.round(118 - t * 68);
    result += `\x1b[38;2;${r};${g};${b}m█`;
  }
  result += `\x1b[38;2;35;45;35m${'░'.repeat(empty)}${R}`;  // very dark green-grey
  return result;
}

// ── Boxify (backward compat alias) ───────────────────────────────────

function boxify(content: string, title: string): string {
  return panel(content, title);
}

// ── Interactive Input ────────────────────────────────────────────────

function prompt(msg: string): Promise<string> {
  return new Promise((resolve) => {
    const rl = createInterface({ input: process.stdin, output: process.stdout, terminal: true });
    rl.question(msg, (answer) => { rl.close(); resolve(answer.trim()); });
  });
}

// ── Bridge Lifecycle ─────────────────────────────────────────────────

async function withBridge<T>(fn: () => Promise<T>): Promise<T> {
  try {
    await bridge.start();
    return await fn();
  } finally {
    await bridge.stop();
  }
}

// ── CLI Setup ────────────────────────────────────────────────────────

const program = new Command();

program
  .name('pfaa')
  .version(VERSION)
  .description('@aussie-agents/pfaa — Phase-Fluid Agent Architecture CLI (48 tools · 5-layer memory · Python 3.15)')
  .option('-v, --verbose', 'Enable verbose logging')
  .option('-q, --quiet', 'Suppress all output except results')
  .option('--no-color', 'Disable colored output')
  .option('--no-cache', 'Disable analysis caching')
  .option('--json', 'Output as JSON where supported')
  .option('--model <model>', 'Claude model to use', 'claude-sonnet-4-6')
  .option('--max-agents <n>', 'Max concurrent agents', '8')
  .option('--timeout <ms>', 'Global timeout in milliseconds', '120000')
  .option('--python <path>', 'Python interpreter path', 'python3.15')
  .option('--live', 'Use live Claude API (requires ANTHROPIC_API_KEY)')
  .option('--api-key <key>', 'Anthropic API key (overrides env var)')
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

    // Quiet by default — only show warnings unless verbose
    if (opts.quiet) {
      setLogLevel(LogLevel.ERROR);
    } else if (config.verbose) {
      setLogLevel(LogLevel.DEBUG);
    } else {
      setLogLevel(LogLevel.WARN);
    }

    bridge = createBridge({
      pythonPath: config.python.interpreterPath,
      enginePath: resolve(process.cwd()),
      workingDir: process.cwd(),
      timeoutMs: config.timeoutMs,
      maxConcurrent: config.maxConcurrentAgents,
    });

    orchestrator = new AgentOrchestrator(bridge, {
      live: opts.live,
      apiKey: opts.apiKey,
    });
    memory = new JMEMClient();
    rateLimiter = new RateLimiter(config.enterprise.rateLimit);
    cache = new AnalysisCache(config.enterprise.cache);
    py315 = new Python315Tools(config.python);

    orchestrator.on('event', (event: any) => {
      if (config.verbose) log.debug(`[${event.type}]`, event.data);
    });
  });

// ═════════════════════════════════════════════════════════════════════
// CORE COMMANDS
// ═════════════════════════════════════════════════════════════════════

// ── run ──────────────────────────────────────────────────────────────

program
  .command('run <goal>')
  .description('Execute a natural language goal using the agent swarm')
  .option('-r, --roles <roles>', 'Agent roles to use (comma-separated)')
  .option('--dry-run', 'Show plan without executing')
  .action(async (goal: string, opts) => {
    console.log(colorize('cyan', `\n⚡ Aussie Agents — Executing goal...\n`));
    console.log(colorize('dim', `  Goal: ${goal}`));
    console.log(colorize('dim', `  Model: ${config.model}`));
    console.log(colorize(orchestrator.isLive ? 'green' : 'yellow',
      `  Mode: ${orchestrator.isLive ? 'LIVE (Claude API)' : 'SIMULATED'}\n`));

    const startTime = performance.now();
    try {
      await bridge.start();
      await memory.connect();

      const context = await memory.getContext(goal);
      if (context.relevant.length > 0) {
        console.log(colorize('magenta', `  📚 Found ${context.relevant.length} relevant memories\n`));
      }

      await rateLimiter.acquireRequest();
      const result = await orchestrator.executeGoal(goal);
      const elapsed = performance.now() - startTime;

      console.log(colorize('green', '\n✅ Goal completed\n'));
      console.log(boxify(result.summary, 'Results'));

      const { pipeline, results } = result;
      console.log(colorize('dim', `\n  Pipeline: ${pipeline.tasks.length} tasks`));
      for (const task of pipeline.tasks) {
        const icon = task.status === 'completed' ? '✓' : '✗';
        const c = task.status === 'completed' ? 'green' : 'red';
        console.log(colorize(c as Color, `    ${icon} [${task.agent}] ${task.description.slice(0, 60)}`));
      }

      console.log(colorize('dim', `\n  Total time: ${Math.round(elapsed)}ms`));

      await memory.learnFromPipeline(
        goal,
        results.map((r) => ({ action: r.role, success: r.success, elapsedMs: r.elapsedMs })),
      );
      log.audit('goal:executed', { goal, elapsed: Math.round(elapsed), tasks: pipeline.tasks.length });
    } catch (err) {
      console.error(colorize('red', `\n❌ Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    } finally {
      await bridge.stop();
    }
  });

// ── exec ─────────────────────────────────────────────────────────────

program
  .command('exec')
  .description('Execute Python code in a sandboxed subprocess')
  .option('-c, --code <code>', 'Python code to execute')
  .option('-f, --file <path>', 'Python file to execute')
  .option('-t, --timeout <ms>', 'Timeout in milliseconds', '30000')
  .action(async (opts) => {
    const code = opts.code || (opts.file ? readFileSync(resolve(opts.file), 'utf-8') : null);
    if (!code) {
      console.error(colorize('red', 'Error: Provide -c <code> or -f <file>'));
      process.exitCode = 1;
      return;
    }

    try {
      await withBridge(async () => {
        const result = await bridge.executeTool('sandbox_exec', code);
        if (result.success) {
          console.log(typeof result.result === 'string' ? result.result : JSON.stringify(result.result, null, 2));
        } else {
          console.error(colorize('red', `Error: ${JSON.stringify(result.result)}`));
          process.exitCode = 1;
        }
      });
    } catch (err) {
      // Fallback: run directly with python
      const result = await py315.runScript(code, parseInt(opts.timeout));
      if (result.stdout) console.log(result.stdout);
      if (result.stderr) console.error(result.stderr);
      process.exitCode = result.exitCode;
    }
  });

// ── swarm ────────────────────────────────────────────────────────────

program
  .command('swarm <goal>')
  .description('Execute a goal with a multi-agent swarm')
  .option('-r, --roles <roles>', 'Comma-separated agent roles', 'analyzer,refactorer,tester,reviewer,researcher,builder,deployer,orchestrator')
  .option('-c, --concurrency <n>', 'Max concurrent agents', '8')
  .action(async (goal: string, opts) => {
    const roles = opts.roles.split(',').map((r: string) => r.trim() as AgentRole);
    console.log(colorize('cyan', `\n🐝 Swarm: ${roles.length} agents\n`));
    console.log(colorize('dim', `  Goal: ${goal}`));
    console.log(colorize(orchestrator.isLive ? 'green' : 'yellow',
      `  Mode: ${orchestrator.isLive ? 'LIVE (Claude API)' : 'SIMULATED'}\n`));

    try {
      await bridge.start();
      const tasks = roles.map((role: AgentRole) => ({ description: goal, role }));
      const results = await orchestrator.swarm(tasks);

      for (const r of results) {
        const icon = r.success ? '✓' : '✗';
        const c = r.success ? 'green' : 'red';
        console.log(colorize(c as Color, `  ${icon} [${r.role}] ${r.elapsedMs}ms — ${r.phase} phase`));
        if (r.output && typeof r.output === 'string') {
          const preview = r.output.split('\n')[0].slice(0, 80);
          console.log(colorize('dim', `    ${preview}`));
        }
      }

      const succeeded = results.filter((r) => r.success).length;
      console.log(colorize('dim', `\n  ${succeeded}/${results.length} agents succeeded\n`));
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    } finally {
      await bridge.stop();
    }
  });

// ── tool ─────────────────────────────────────────────────────────────

program
  .command('tool <name> [args...]')
  .description('Execute a single Aussie Agents tool by name (e.g. shell, grep, compute)')
  .action(async (name: string, args: string[]) => {
    try {
      await withBridge(async () => {
        const result = await bridge.executeTool(name, ...args);
        const phaseColor = result.phaseUsed === ('VAPOR' as any) ? 'cyan' : result.phaseUsed === ('LIQUID' as any) ? 'yellow' : 'red';
        console.log(colorize(phaseColor as Color, `[${result.phaseUsed}] ${result.elapsedUs}μs`));

        if (typeof result.result === 'string') {
          console.log(result.result);
        } else {
          console.log(JSON.stringify(result.result, null, 2));
        }
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ── scatter ──────────────────────────────────────────────────────────

program
  .command('scatter <tool> <inputs...>')
  .description('Fan-out a tool across multiple inputs in parallel')
  .action(async (tool: string, inputs: string[]) => {
    console.log(colorize('cyan', `\n⚡ Scatter: ${tool} × ${inputs.length} inputs\n`));

    try {
      await withBridge(async () => {
        const results = await bridge.scatter(tool, inputs);
        for (const r of results) {
          const icon = r.success ? '✓' : '✗';
          const c = r.success ? 'green' : 'red';
          console.log(colorize(c as Color, `  ${icon} [${r.phaseUsed}] ${r.elapsedUs}μs`));
          if (typeof r.result === 'string') {
            console.log(colorize('dim', `    ${r.result.toString().split('\n')[0].slice(0, 80)}`));
          }
        }

        const succeeded = results.filter((r) => r.success).length;
        console.log(colorize('dim', `\n  ${succeeded}/${results.length} succeeded\n`));
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ── pipeline ─────────────────────────────────────────────────────────

program
  .command('pipeline <steps...>')
  .description('Execute tools sequentially (format: tool:arg1,arg2)')
  .action(async (steps: string[]) => {
    console.log(colorize('cyan', `\n🔗 Pipeline: ${steps.length} stages\n`));

    const parsed = steps.map((s) => {
      const [tool, ...rest] = s.split(':');
      const args = rest.join(':').split(',').filter(Boolean);
      return { tool, args };
    });

    try {
      await withBridge(async () => {
        const results = await bridge.pipeline(parsed);
        for (const r of results) {
          const icon = r.success ? '✓' : '✗';
          const c = r.success ? 'green' : 'red';
          console.log(colorize(c as Color, `  ${icon} ${r.tool} [${r.phase}] ${r.elapsed_us}μs`));
          if (r.result && typeof r.result === 'string') {
            console.log(colorize('dim', `    ${r.result.split('\n')[0].slice(0, 80)}`));
          }
        }
        console.log();
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ── team ─────────────────────────────────────────────────────────────

program
  .command('team <goal>')
  .description('Spawn the full Aussie Agents team (6 or 10 agents)')
  .option('-m, --mode <mode>', 'Team mode: basic (6 agents) or remix (10 agents)', 'basic')
  .action(async (goal: string, opts) => {
    const agentCount = opts.mode === 'remix' ? 10 : 6;
    console.log(colorize('cyan', `\n🤖 Team: ${agentCount} agents (${opts.mode} mode)\n`));
    console.log(colorize('dim', `  Goal: ${goal}\n`));

    try {
      await withBridge(async () => {
        const result = await bridge.spawnTeam(goal, opts.mode);
        console.log(boxify(JSON.stringify(result, null, 2), `Team Results (${opts.mode})`));
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ── generate ─────────────────────────────────────────────────────────

program
  .command('generate <description>')
  .description('Generate code using Claude via the Aussie Agents bridge')
  .option('-l, --language <lang>', 'Language', 'python')
  .option('-o, --output <path>', 'Write to file')
  .action(async (description: string, opts) => {
    console.log(AZ.agentGen(` Aussie: Generating ${opts.language} code `));
    console.log();

    try {
      await withBridge(async () => {
        const result = await bridge.generateCode(description, opts.language, opts.output);
        if (result.success) {
          console.log(result.code);
          if (result.file) {
            console.log(AZ.success(`\nWritten to ${result.file}`));
          }
        } else {
          console.error(AZ.error(`Error: ${result.code}`));
          process.exitCode = 1;
        }
      });
    } catch (err) {
      console.error(AZ.error(`Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ── explore ──────────────────────────────────────────────────────────

program
  .command('explore')
  .description('Run epsilon-greedy phase exploration across all tools')
  .option('-r, --rounds <n>', 'Exploration rounds', '200')
  .option('-e, --epsilon <n>', 'Exploration rate (0-1)', '0.3')
  .action(async (opts) => {
    const rounds = parseInt(opts.rounds);
    const epsilon = parseFloat(opts.epsilon);
    console.log(colorize('cyan', `\n🔬 Phase Exploration: ${rounds} rounds, ε=${epsilon}\n`));

    try {
      await withBridge(async () => {
        const result = await bridge.explore(rounds, epsilon);
        console.log(boxify(JSON.stringify(result, null, 2), 'Exploration Results'));
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ── learn ────────────────────────────────────────────────────────────

program
  .command('learn')
  .description('Force a learning cycle — extract patterns from episodes')
  .action(async () => {
    console.log(colorize('cyan', '\n🧠 Forcing learning cycle...\n'));

    try {
      await withBridge(async () => {
        await bridge.forceLearn();
        const mem = await bridge.getMemory() as any;

        // Handle both array and dict shapes from the Python bridge
        const status = mem.status || {};
        const patterns = mem.patterns || {};
        const strategies = mem.strategies || {};
        const patternCount = Array.isArray(patterns) ? patterns.length : Object.keys(patterns).length;
        const strategyCount = Array.isArray(strategies) ? strategies.length : Object.keys(strategies).length;
        const episodeCount = status.l1_episodes || 0;

        console.log(AZ.success(`  Learning complete\n`));
        console.log(`  ${AZ.toolKey('L1 Episodes:  ')} ${colorize('green', String(episodeCount))}`);
        console.log(`  ${AZ.toolKey('L2 Patterns:  ')} ${colorize('green', String(patternCount))}`);
        console.log(`  ${AZ.toolKey('L3 Strategies:')} ${colorize('yellow', String(strategyCount))}`);

        if (patternCount > 0) {
          const patternEntries = Array.isArray(patterns) ? patterns : Object.entries(patterns).map(([tool, p]: [string, any]) => ({ tool, ...p }));
          console.log(AZ.info('\n  Top patterns:\n'));
          for (const p of patternEntries.slice(0, 8)) {
            const name = p.tool || p.name || '?';
            const phase = p.best_phase || '?';
            const avg = Math.round(p.avg_us || p.avg_latency_us || 0);
            const conf = (p.confidence || 0).toFixed(2);
            const phaseColor = phase === 'VAPOR' ? 'cyan' : phase === 'LIQUID' ? 'yellow' : 'red';
            console.log(`    ${name.padEnd(20)} ${colorize(phaseColor as Color, phase.padEnd(7))} ${String(avg).padStart(8)}μs  conf=${conf}`);
          }
        }

        if (strategyCount > 0) {
          const stratEntries = Array.isArray(strategies) ? strategies : Object.entries(strategies).map(([tool, s]: [string, any]) => ({ tool, ...s }));
          console.log(AZ.info('\n  Phase optimizations:\n'));
          for (const s of stratEntries) {
            const from = s.default || s.from_phase || '?';
            const to = s.override || s.to_phase || '?';
            const speedup = s.speedup_factor ? `${s.speedup_factor.toFixed(1)}x` : (s.speedup || '?');
            console.log(`    ${s.tool}: ${colorize('red', from)} → ${colorize('green', to)} (${speedup})`);
          }
        }
        console.log();
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ── ask ──────────────────────────────────────────────────────────────

program
  .command('ask <prompt>')
  .description('Ask Claude a question')
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

// ═════════════════════════════════════════════════════════════════════
// AGENT SUBCOMMANDS
// ═════════════════════════════════════════════════════════════════════

const agentCmd = program.command('agent').description('Manage and run specialized agents');

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

    const rows = Object.values(AgentRole).map((role) => {
      const info = roleInfo[role] || { phase: '?', capabilities: [] };
      const phaseColor = info.phase === 'VAPOR' ? 'cyan' : info.phase === 'LIQUID' ? 'yellow' : 'red';
      return [role, colorize(phaseColor as Color, info.phase), info.capabilities.join(', ')];
    });

    console.log('\n' + table('Agent Roles', [
      { header: 'Role', style: 'yellow', width: 14 },
      { header: 'Phase', width: 7 },
      { header: 'Capabilities', style: 'dim', width: 50 },
    ], rows));
    console.log();
  });

// ═════════════════════════════════════════════════════════════════════
// MEMORY SUBCOMMANDS
// ═════════════════════════════════════════════════════════════════════

const memoryCmd = program.command('memory').description('JMEM semantic memory operations');

memoryCmd
  .command('stats')
  .description('Show memory status across all 5 cognitive layers')
  .action(async () => {
    // Try Aussie Agents engine memory first, fall back to JMEM MCP
    try {
      await bridge.start();
      const mem = await bridge.getMemory();
      const maxEp = Math.max(mem.episodes, 1);

      const statusContent = [
        `${AZ.toolKey('L1 Episodes:  ')} ${colorize('green', String(mem.episodes).padStart(6))}  ${bar(mem.episodes, maxEp, 20)}`,
        `${AZ.toolKey('L2 Patterns:  ')} ${colorize('green', String(mem.patterns.length).padStart(6))}  ${bar(mem.patterns.length, maxEp, 20)}`,
        `${AZ.toolKey('L3 Strategies:')} ${colorize('yellow', String(mem.strategies.length).padStart(6))}  ${bar(mem.strategies.length, Math.max(mem.patterns.length, 1), 20)}`,
      ].join('\n');

      console.log('\n' + panel(statusContent, '🧠 Aussie Agents Memory Status'));

      if (mem.patterns.length > 0) {
        const patternRows = mem.patterns.slice(0, 12).map((p) => [
          p.tool,
          colorize(p.best_phase === 'VAPOR' ? 'cyan' : p.best_phase === 'LIQUID' ? 'yellow' : 'red', p.best_phase),
          `${Math.round(p.avg_latency_us)}`,
          bar(p.confidence, 1, 10) + ` ${p.confidence.toFixed(2)}`,
        ]);

        console.log('\n' + table('L2 — Learned Patterns', [
          { header: 'Tool', style: 'cyan', width: 20 },
          { header: 'Best Phase', width: 10 },
          { header: 'Avg μs', style: 'green', width: 8, align: 'right' },
          { header: 'Confidence', width: 20 },
        ], patternRows));
      }

      if (mem.strategies.length > 0) {
        const stratRows = mem.strategies.map((s) => [
          s.tool,
          colorize('red', s.from_phase),
          colorize('green', s.to_phase),
          colorize('yellow', s.speedup),
        ]);

        console.log('\n' + table('L3 — Phase Optimization Strategies', [
          { header: 'Tool', style: 'cyan', width: 18 },
          { header: 'Default', width: 8 },
          { header: 'Override', width: 8 },
          { header: 'Speedup', style: 'yellow', width: 10 },
        ], stratRows));
      }

      if (mem.knowledge.length > 0) {
        console.log('\n' + panel(
          mem.knowledge.slice(0, 5).map((k) =>
            `${AZ.hint(`[${k.pattern}]`)} freq=${k.frequency}`
          ).join('\n'),
          '🔮 L5 — Emergent Knowledge',
          'magenta',
        ));
      }
      console.log();
      await bridge.stop();
    } catch {
      // Fall back to JMEM MCP
      await memory.connect();
      const status = await memory.status();
      const max = Math.max(status.l1Episodes, status.l2Patterns, status.l3Strategies, status.l5Knowledge, 1);

      const content = [
        `${AZ.toolKey('L1 Episodic:  ')} ${String(status.l1Episodes).padStart(5)}  ${bar(status.l1Episodes, max, 20)}`,
        `${AZ.toolKey('L2 Semantic:  ')} ${String(status.l2Patterns).padStart(5)}  ${bar(status.l2Patterns, max, 20)}`,
        `${AZ.toolKey('L3 Strategic: ')} ${String(status.l3Strategies).padStart(5)}  ${bar(status.l3Strategies, max, 20)}`,
        `${AZ.toolKey('L4 Meta-Learn:')} ${status.l4LearningRate.toFixed(3).padStart(5)}  ${bar(status.l4LearningRate, 1, 20)}`,
        `${AZ.toolKey('L5 Emergent:  ')} ${String(status.l5Knowledge).padStart(5)}  ${bar(status.l5Knowledge, max, 20)}`,
        `${AZ.toolKey('DB Size:      ')} ${status.dbSizeKb} KB`,
      ].join('\n');

      console.log('\n' + panel(content, '🧠 JMEM Memory Status'));
      console.log();
    }
  });

// Keep "status" as alias for "stats"
memoryCmd
  .command('status')
  .description('Alias for memory stats')
  .action(async () => {
    await program.parseAsync(['node', 'pfaa', 'memory', 'stats']);
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

memoryCmd
  .command('dump')
  .description('Dump full memory state (patterns, strategies, knowledge)')
  .action(async () => {
    try {
      await withBridge(async () => {
        const mem = await bridge.getMemory();
        console.log(JSON.stringify(mem, null, 2));
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ═════════════════════════════════════════════════════════════════════
// PYTHON 3.15 TOOLS
// ═════════════════════════════════════════════════════════════════════

const py315Cmd = program.command('py315').description('Python 3.15 code analysis and optimization tools');

py315Cmd
  .command('analyze <path>')
  .description('Analyze Python files for 3.15 features and opportunities')
  .option('--json', 'Output as JSON')
  .action((path: string, opts) => {
    const fullPath = resolve(path);
    console.log(colorize('cyan', `\n🐍 Python 3.15 Analysis: ${path}\n`));

    const analysis = py315.analyzeFile(fullPath);

    if (opts.json) {
      console.log(JSON.stringify(analysis, null, 2));
      return;
    }

    if (analysis.py315Features.length > 0) {
      console.log(colorize('green', `  ✅ Python 3.15 Features (${analysis.py315Features.length}):\n`));
      for (const f of analysis.py315Features) {
        console.log(`    L${f.line}: ${colorize('yellow', f.pep)} — ${f.usage}`);
      }
    }

    if (analysis.issues.length > 0) {
      console.log(colorize('yellow', `\n  ⚠ Issues (${analysis.issues.length}):\n`));
      for (const issue of analysis.issues) {
        const c = issue.severity === 'error' ? 'red' : issue.severity === 'warning' ? 'yellow' : 'dim';
        console.log(`    L${issue.line}: ${colorize(c as Color, `[${issue.severity}]`)} ${issue.message}`);
      }
    }

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

// ═════════════════════════════════════════════════════════════════════
// SYSTEM COMMANDS
// ═════════════════════════════════════════════════════════════════════

program
  .command('tools')
  .description('List all registered Aussie Agents tools (48 tools across 3 phases)')
  .action(async () => {
    try {
      await bridge.start();
      const tools = await bridge.listTools();

      const rows = tools
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((t) => {
          const phaseColor = t.phase === 'VAPOR' ? 'cyan' : t.phase === 'LIQUID' ? 'yellow' : 'red';
          return [
            t.name,
            colorize(phaseColor as Color, t.phase),
            t.capabilities?.join(', ') || '',
            t.description,
          ];
        });

      console.log('\n' + table(`Aussie Agents Tools (${tools.length} registered)`, [
        { header: 'Name', style: 'cyan', width: 20 },
        { header: 'Phase', width: 7 },
        { header: 'Capabilities', style: 'dim', width: 20 },
        { header: 'Description', style: 'white', width: 40 },
      ], rows));
      console.log();
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
    } finally {
      await bridge.stop();
    }
  });

program
  .command('bench')
  .description('Run Aussie Agents performance benchmarks (7 tests)')
  .action(async () => {
    console.log(colorize('cyan', '\n⏱  Running Aussie Agents Benchmarks...\n'));
    try {
      await withBridge(async () => {
        const results = await bridge.benchmark();
        console.log(boxify(JSON.stringify(results, null, 2), 'Benchmark Results'));
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
    }
  });

program
  .command('status')
  .description('Show full system status')
  .action(async () => {
    setLogLevel(LogLevel.FATAL); // suppress all noise during status display
    console.log(renderBanner());

    const pyResult = await py315.checkRuntime();

    // Runtime panel
    const runtimeLines = [
      `${AZ.toolKey('Python:  ')} ${pyResult.available ? `\x1b[38;2;0;255;136m${pyResult.version}${R}` : colorize('red', 'not found')}`,
      `${AZ.toolKey('Node:    ')} \x1b[38;2;0;255;136m${process.version}${R}`,
      `${AZ.toolKey('Model:   ')} \x1b[38;2;255;180;30m${config.model}${R}`,
      `${AZ.toolKey('Claude:  ')} ${orchestrator.isLive ? `\x1b[38;2;0;255;136m\x1b[1mLIVE${R}` : `\x1b[38;2;255;180;30mSIMULATED${R}`}`,
      `${AZ.toolKey('GIL:     ')} ${pyResult.gilEnabled ? 'enabled' : `\x1b[38;2;0;255;136mfree-threading${R}`}`,
    ];
    console.log(panel(runtimeLines.join('\n'), '\x1b[38;2;0;230;118m\x1b[1m Runtime \x1b[0m', 'cyan'));

    // Engine panel
    try {
      await bridge.start();
      const tools = await bridge.listTools();
      const phases = { VAPOR: 0, LIQUID: 0, SOLID: 0 };
      for (const t of tools) (phases as any)[t.phase]++;

      const engineLines = [
        `${AZ.toolKey('Tools:   ')} \x1b[38;2;0;255;136m\x1b[1m${tools.length}${R} registered`,
        `${AZ.toolKey('VAPOR:   ')} \x1b[38;2;0;200;255m${phases.VAPOR}${R}  ${AZ.toolKey('LIQUID: ')} \x1b[38;2;255;220;50m${phases.LIQUID}${R}  ${AZ.toolKey('SOLID: ')} \x1b[38;2;255;80;80m${phases.SOLID}${R}`,
        `${AZ.toolKey('Phases:  ')} ${bar(phases.VAPOR, tools.length, 8)} ${bar(phases.LIQUID, tools.length, 6)} ${bar(phases.SOLID, tools.length, 10)}`,
      ];
      console.log(panel(engineLines.join('\n'), '\x1b[38;2;212;160;23m\x1b[1m Engine \x1b[0m', 'yellow'));
      await bridge.stop();
    } catch {
      console.log(panel(colorize('dim', 'Not available (install Aussie Agents Python engine)'), '\x1b[38;2;212;160;23m\x1b[1m Engine \x1b[0m', 'dim'));
    }

    // Enterprise panel
    const cacheStatus = cache.status();
    const rlStatus = rateLimiter.status();
    const entLines = [
      `${AZ.toolKey('Cache:     ')} ${cacheStatus.entries}/${cacheStatus.maxEntries} entries  ${bar(cacheStatus.hitRate, 1, 10)} ${(cacheStatus.hitRate * 100).toFixed(0)}% hit`,
      `${AZ.toolKey('Requests:  ')} \x1b[38;2;0;255;136m${rlStatus.requestsAvailable}${R} available`,
      `${AZ.toolKey('Agents:    ')} ${rlStatus.activeAgents}/${rlStatus.maxAgents}  ${bar(rlStatus.activeAgents, rlStatus.maxAgents, 10)}`,
    ];
    console.log(panel(entLines.join('\n'), '\x1b[38;2;201;167;59m\x1b[1m Enterprise \x1b[0m', 'magenta'));

    // Memory panel — suppress bridge teardown noise
    const origStdoutWrite = process.stdout.write.bind(process.stdout);
    process.stdout.write = (chunk: any, ...args: any[]) => {
      const s = typeof chunk === 'string' ? chunk : chunk.toString();
      if (s.includes('WARN') && (s.includes('bridge') || s.includes('jmem'))) return true;
      return origStdoutWrite(chunk, ...args);
    };
    try {
      await memory.connect();
      const ms = await memory.status();
      const max = Math.max(ms.l1Episodes, ms.l2Patterns, ms.l3Strategies, ms.l5Knowledge, 1);
      const memLines = [
        `${AZ.toolKey('L1 Episodes:   ')} ${String(ms.l1Episodes).padStart(4)}  ${bar(ms.l1Episodes, max, 15)}`,
        `${AZ.toolKey('L2 Patterns:   ')} ${String(ms.l2Patterns).padStart(4)}  ${bar(ms.l2Patterns, max, 15)}`,
        `${AZ.toolKey('L3 Strategies: ')} ${String(ms.l3Strategies).padStart(4)}  ${bar(ms.l3Strategies, max, 15)}`,
        `${AZ.toolKey('L4 Learn Rate: ')} ${ms.l4LearningRate.toFixed(3).padStart(4)}  ${bar(ms.l4LearningRate, 1, 15)}`,
        `${AZ.toolKey('L5 Knowledge:  ')} ${String(ms.l5Knowledge).padStart(4)}  ${bar(ms.l5Knowledge, max, 15)}`,
        `${AZ.toolKey('DB Size:       ')} ${ms.dbSizeKb} KB`,
      ];
      console.log(panel(memLines.join('\n'), '\x1b[38;2;0;230;118m\x1b[1m JMEM Memory \x1b[0m', 'magenta'));
    } catch {
      console.log(panel(colorize('dim', 'Not connected'), '\x1b[38;2;0;230;118m\x1b[1m JMEM Memory \x1b[0m', 'dim'));
    }
    process.stdout.write = origStdoutWrite;

    // Hooks & Skills panel
    const GOLDBR  = '\x1b[38;2;212;160;23m';
    const GREEN   = '\x1b[38;2;0;230;118m';
    const GREEND  = '\x1b[38;2;76;175;80m';
    const hooksLines = [
      `${AZ.toolKey('Skills:     ')} \x1b[38;2;0;255;136m\x1b[1m10${R} registered  ${AZ.dim('/aussie-*')}`,
      `${AZ.toolKey('Agents:     ')} \x1b[38;2;0;255;136m\x1b[1m3${R}  (lead, rewriter, validator)`,
      `${AZ.toolKey('Hooks:      ')} \x1b[38;2;0;255;136m\x1b[1m6${R}  (PreToolUse, PostToolUse, SessionStart, Stop, PreCompact, PostCompact)`,
      `${AZ.toolKey('MCP Tools:  ')} \x1b[38;2;0;255;136m\x1b[1m17${R} JMEM (recall, remember, consolidate, reflect, reward, evolve, status)`,
    ];
    console.log(panel(hooksLines.join('\n'), `${GOLDBR}\x1b[1m Aussie Agents \x1b[0m`, 'yellow'));

    console.log();
  });

program
  .command('self-build')
  .description('Run a self-improvement cycle — the engine builds itself')
  .option('--apply', 'Auto-apply validated changes')
  .action(async (opts) => {
    console.log(colorize('cyan', '\n🔧 Running self-build cycle...\n'));
    try {
      await withBridge(async () => {
        const result = await bridge.selfBuild(opts.apply);
        console.log(boxify(JSON.stringify(result, null, 2), 'Self-Build Results'));
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
    }
  });

program
  .command('init')
  .description('Initialize Aussie Agents configuration in current project')
  .action(() => {
    initProjectConfig();
    console.log(colorize('green', '\n✅ Created .pfaa.yaml in current directory\n'));
    console.log(colorize('dim', '  Edit this file to configure Aussie Agents for your project.'));
    console.log(colorize('dim', '  Run `pfaa status` to verify your setup.\n'));
  });

// ── checkpoints ──────────────────────────────────────────────────────

program
  .command('checkpoints')
  .description('List saved goal checkpoints (resumable goals)')
  .action(async () => {
    try {
      await withBridge(async () => {
        const checkpoints = await bridge.listCheckpoints();
        console.log(colorize('cyan', `\n📌 Saved Checkpoints (${checkpoints.length})\n`));

        if (checkpoints.length === 0) {
          console.log(colorize('dim', '  No checkpoints found.\n'));
          return;
        }

        for (const cp of checkpoints) {
          const icon = cp.status === 'completed' ? '✓' : cp.status === 'failed' ? '✗' : '⏸';
          const c = cp.status === 'completed' ? 'green' : cp.status === 'failed' ? 'red' : 'yellow';
          console.log(colorize(c as Color, `  ${icon} ${cp.goal_id.slice(0, 8)}`), `${cp.goal.slice(0, 60)}`);
          console.log(colorize('dim', `    ${cp.completed}/${cp.subtasks} subtasks — ${cp.status}`));
        }
        console.log();
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
    }
  });

program
  .command('resume <goal-id>')
  .description('Resume a saved goal from checkpoint')
  .action(async (goalId: string) => {
    console.log(colorize('cyan', `\n▶ Resuming goal: ${goalId}\n`));
    try {
      await withBridge(async () => {
        const result = await bridge.resumeGoal(goalId);
        console.log(colorize(result.success ? 'green' : 'red',
          `${result.success ? '✅ Goal completed' : '❌ Goal failed'}`));
        if (result.output) {
          console.log(boxify(
            typeof result.output === 'string' ? result.output : JSON.stringify(result.output, null, 2),
            'Result',
          ));
        }
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ═════════════════════════════════════════════════════════════════════
// CONFIG SUBCOMMANDS
// ═════════════════════════════════════════════════════════════════════

const configCmd = program.command('config').description('Manage Aussie Agents configuration');

configCmd
  .command('set-api-key <key>')
  .description('Save your Anthropic API key for live Claude API calls')
  .action(async (key: string) => {
    const { writeFileSync, mkdirSync } = await import('node:fs');
    const configDir = join(homedir(), '.pfaa');
    const configFile = join(configDir, 'credentials.json');

    mkdirSync(configDir, { recursive: true });
    const credentials = existsSync(configFile)
      ? JSON.parse(readFileSync(configFile, 'utf-8'))
      : {};
    credentials.anthropicApiKey = key;
    writeFileSync(configFile, JSON.stringify(credentials, null, 2), { mode: 0o600 });

    console.log(colorize('green', '\n✅ API key saved to ~/.pfaa/credentials.json\n'));
    console.log(colorize('dim', '  Use --live flag to enable Claude API calls.\n'));
  });

configCmd
  .command('show')
  .description('Show current configuration')
  .action(() => {
    const configFile = join(homedir(), '.pfaa', 'credentials.json');
    const hasKey = existsSync(configFile) && (() => {
      try {
        const creds = JSON.parse(readFileSync(configFile, 'utf-8'));
        return !!creds.anthropicApiKey;
      } catch { return false; }
    })();
    const envKey = !!process.env['ANTHROPIC_API_KEY'];

    console.log(colorize('cyan', '\n📋 Aussie Agents Configuration\n'));
    console.log(`  API Key (file):  ${hasKey ? colorize('green', 'configured') : colorize('dim', 'not set')}`);
    console.log(`  API Key (env):   ${envKey ? colorize('green', 'set') : colorize('dim', 'not set')}`);
    console.log(`  Model:           ${config?.model || 'claude-sonnet-4-6'}`);
    console.log(`  Python:          ${config?.python?.interpreterPath || 'python3.15'}`);
    console.log(`  Config dir:      ~/.pfaa/`);
    console.log();
  });

// ═════════════════════════════════════════════════════════════════════
// INTERACTIVE MODE (Aussie Agents chat loop)
// ═════════════════════════════════════════════════════════════════════

program
  .command('chat')
  .description('Interactive Aussie Agents-style chat loop')
  .option('-n, --name <name>', 'Agent name', 'Aussie')
  .action(async (opts) => {
    console.log(renderBanner());
    console.log(AZ.agentHeader(`${opts.name}: Ready`));
    console.log(AZ.hint(`  Model: ${config.model} | Mode: ${orchestrator.isLive ? 'LIVE' : 'SIMULATED'}`));
    console.log();

    try {
      await bridge.start();
    } catch { /* bridge optional for chat */ }

    while (true) {
      console.log();
      console.log(AZ.userPrompt(`User message ('e' to leave):`));
      const msg = await prompt('> ');
      if (!msg) continue;
      if (msg.toLowerCase() === 'e') break;

      console.log();
      console.log(AZ.agentGen(`${opts.name}: Generating`));
      process.stdout.write(AZ.agentText('Response: '));

      try {
        await rateLimiter.acquireRequest();

        if (orchestrator.isLive) {
          const result = await orchestrator.executeGoal(msg);
          console.log();
          console.log();
          console.log(AZ.agentText(result.summary));

          for (const task of result.pipeline.tasks) {
            const icon = task.status === 'completed' ? '✓' : '✗';
            console.log();
            console.log(AZ.toolHead(`${opts.name}: Task '${task.agent}':`));
            console.log(AZ.toolVal(`  ${icon} ${task.description.slice(0, 80)}`));
          }
        } else {
          // Simulated mode — route through bridge if available
          try {
            const result = await bridge.askClaude(msg);
            console.log();
            console.log();
            if (result.success) {
              console.log(AZ.agentText(result.output));
            } else {
              console.log(AZ.error(result.output));
            }
          } catch {
            console.log();
            console.log();
            console.log(AZ.agentText('[Simulated] ' + msg.slice(0, 100)));
          }
        }

        console.log();
        console.log(AZ.agentHeader(`${opts.name}: response complete`));
      } catch (err) {
        console.log();
        console.log(AZ.dead('Context terminated'));
        console.log(AZ.error(`Error: ${err instanceof Error ? err.message : String(err)}`));
      }
    }

    await bridge.stop();
    console.log();
    console.log(AZ.hint('Goodbye.'));
  });

// ── warmup ───────────────────────────────────────────────────────────

program
  .command('warmup')
  .description('Profile every tool once to populate memory with baseline data')
  .action(async () => {
    console.log(colorize('cyan', '\n🔥 Warming up all tools...\n'));

    try {
      await bridge.start();
      const tools = await bridge.listTools();

      // Default safe args per tool
      const WARMUP_ARGS: Record<string, string[]> = {
        compute: ['sqrt(42)'],
        hash_data: ['warmup'],
        grep: ['def ', '.', '*.py'],
        line_count: ['.'],
        json_parse: ['{"a":1}'],
        regex_extract: ['test123', '\\d+'],
        read_file: ['/dev/null'],
        glob_search: ['*.py', '.'],
        system_info: [],
        disk_usage: ['.'],
        env_get: ['HOME'],
        file_stats: ['.'],
        shell: ['echo warmup'],
        sandbox_exec: ["print('ok')"],
        git_status: [],
        git_log: ['.', '3'],
        git_diff: [],
        git_branch: [],
        dns_lookup: ['localhost'],
      };

      const rows: string[][] = [];
      let succeeded = 0;

      for (const tool of tools) {
        const args = WARMUP_ARGS[tool.name] || [];
        try {
          const result = await bridge.executeTool(tool.name, ...args);
          succeeded++;
          const phaseColor = result.phaseUsed === ('VAPOR' as any) ? 'cyan' : result.phaseUsed === ('LIQUID' as any) ? 'yellow' : 'red';
          rows.push([
            '✓',
            tool.name,
            tool.phase,
            String(result.phaseUsed),
            `${result.elapsedUs}`,
          ]);
          console.log(
            colorize('green', '  ✓ ') +
            tool.name.padEnd(22) +
            colorize(phaseColor as Color, String(result.phaseUsed).padEnd(8)) +
            colorize('dim', `${result.elapsedUs}μs`),
          );
        } catch (e) {
          rows.push(['✗', tool.name, tool.phase, 'ERROR', '0']);
          console.log(
            colorize('red', '  ✗ ') +
            tool.name.padEnd(22) +
            colorize('red', 'ERROR'),
          );
        }
      }

      // Force learning after warmup
      try { await bridge.forceLearn(); } catch {}

      console.log(colorize('green', `\n  ✅ Warmup complete: ${succeeded}/${tools.length} tools profiled\n`));
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
    } finally {
      await bridge.stop();
    }
  });

// ── tool-search ─────────────────────────────────────────────────────

program
  .command('tool-search <query>')
  .description('Search for tools by name or description (deferred tool discovery)')
  .option('-l, --limit <n>', 'Max results to return', '5')
  .action(async (query: string, opts) => {
    const limit = parseInt(opts.limit) || 5;
    console.log(colorize('cyan', `\n⚡ Tool Search: "${query}" (limit ${limit})\n`));

    try {
      await withBridge(async () => {
        const tools = await bridge.searchTools(query, limit);
        if (tools.length === 0) {
          console.log(colorize('yellow', '  No tools found matching that query.\n'));
          return;
        }

        for (const t of tools) {
          const phaseColor = t.phase === 'VAPOR' ? 'cyan' : t.phase === 'LIQUID' ? 'yellow' : 'red';
          console.log(colorize('green', `  ${t.name}`));
          console.log(colorize(phaseColor as Color, `    Phase: ${t.phase}`));
          console.log(colorize('dim', `    ${t.description || '(no description)'}`));
          if (t.capabilities && t.capabilities.length > 0) {
            console.log(colorize('dim', `    Capabilities: ${t.capabilities.join(', ')}`));
          }
          console.log('');
        }
        console.log(colorize('dim', `  ${tools.length} tool(s) found\n`));
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ═════════════════════════════════════════════════════════════════════
// SESSION PERSISTENCE
// ═════════════════════════════════════════════════════════════════════

program
  .command('sessions')
  .description('List saved sessions')
  .action(async () => {
    try {
      await withBridge(async () => {
        const result = await bridge.loadSession();
        const sessions = (result as any).sessions || [];
        if (sessions.length === 0) {
          console.log(colorize('dim', '\n  No saved sessions found.\n'));
          return;
        }
        console.log(colorize('cyan', '\n  Saved Sessions\n'));
        for (const s of sessions) {
          const ts = s.timestamp ? new Date(s.timestamp * 1000).toISOString() : 'unknown';
          console.log(colorize('green', `    ${s.id}`));
          console.log(colorize('dim', `      Time: ${ts}  Goals: ${s.goals ?? 0}`));
        }
        console.log('');
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

program
  .command('session-save')
  .description('Save current session state')
  .option('--id <sessionId>', 'Session ID (default: session_<timestamp>)')
  .action(async (opts) => {
    try {
      await withBridge(async () => {
        const sessionId = opts.id || `session_${Date.now()}`;
        const state: Record<string, unknown> = {
          goals_count: 0,
          tools_used: [],
          goals_executed: [],
          memories_stored: 0,
          l2_patterns_count: 0,
          l3_strategies_count: 0,
        };

        // Try to populate from live memory status
        try {
          const memStatus = await bridge.status();
          if (memStatus) {
            state.l2_patterns_count = (memStatus as any).l2Patterns ?? 0;
            state.l3_strategies_count = (memStatus as any).l3Strategies ?? 0;
            state.memories_stored = (memStatus as any).l1Episodes ?? 0;
          }
        } catch {
          // Memory status unavailable, save with defaults
        }

        const result = await bridge.saveSession(sessionId, state);
        console.log(colorize('green', `\n  Session saved: ${sessionId}`));
        console.log(colorize('dim', `  Path: ${result.saved}\n`));
      });
    } catch (err) {
      console.error(colorize('red', `Error: ${err instanceof Error ? err.message : String(err)}`));
      process.exitCode = 1;
    }
  });

// ═════════════════════════════════════════════════════════════════════
// ENTRY POINT
// ═════════════════════════════════════════════════════════════════════

if (process.argv.length <= 2) {
  console.log(renderBanner());
  program.outputHelp();
} else {
  program.parse(process.argv);
}
