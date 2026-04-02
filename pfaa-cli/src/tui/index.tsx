/**
 * PFAA TUI Entry Point — Launches the Ink-based interactive shell
 */

import React from 'react';
import { render } from 'ink';
import { AppShell } from './App.js';
import { loadConfig } from '../utils/config.js';
import { setLogLevel, LogLevel } from '../utils/logger.js';
import { createBridge } from '../bridge/pfaa-bridge.js';
import { AgentOrchestrator } from '../agents/orchestrator.js';
import { JMEMClient } from '../memory/jmem-client.js';
import { resolve } from 'node:path';

export interface TUIOptions {
  model?: string;
  live?: boolean;
  apiKey?: string;
  verbose?: boolean;
  python?: string;
}

export async function launchTUI(opts: TUIOptions = {}): Promise<void> {
  // Require a real TTY for the Ink TUI
  if (!process.stdin.isTTY) {
    console.error('PFAA interactive mode requires a terminal (TTY). Use `pfaa <command>` for non-interactive usage.');
    process.exit(1);
  }

  // Resolve API key: explicit option > environment variable > undefined
  const apiKey = opts.apiKey ?? process.env.ANTHROPIC_API_KEY;

  if (!apiKey) {
    // Check if Claude Code subscription tokens exist before warning
    let hasOAuth = false;
    try {
      const { execSync } = await import('node:child_process');
      const username = process.env['USER'] || (await import('node:os')).default.userInfo().username;
      const raw = execSync(
        `security find-generic-password -a "${username}" -s "Claude Code-credentials" -w 2>/dev/null`,
        { encoding: 'utf-8', timeout: 3000 },
      ).trim();
      if (raw && JSON.parse(raw)?.claudeAiOauth?.accessToken) hasOAuth = true;
    } catch { /* no keychain entry */ }

    if (!hasOAuth) {
      console.warn(
        '\x1b[33m\u26A0 No API key or Claude subscription found.\n' +
        '  Set ANTHROPIC_API_KEY, pass --api-key, or sign in with Claude Code first.\x1b[0m'
      );
    } else {
      console.log('\x1b[32m\u2713 Using Claude Code subscription (OAuth)\x1b[0m');
    }
  }

  const config = loadConfig({
    model: opts.model ?? 'claude-sonnet-4-6',
    maxConcurrentAgents: 8,
    timeoutMs: 120000,
    verbose: opts.verbose ?? false,
    color: true,
    python: { interpreterPath: opts.python ?? 'python3.15' },
    enterprise: { cache: { enabled: true } },
  });

  setLogLevel(opts.verbose ? LogLevel.DEBUG : LogLevel.WARN);

  const bridge = createBridge({
    pythonPath: config.python.interpreterPath,
    enginePath: resolve(process.cwd()),
    workingDir: process.cwd(),
    timeoutMs: config.timeoutMs,
    maxConcurrent: config.maxConcurrentAgents,
  });

  const orchestrator = new AgentOrchestrator(bridge, {
    live: opts.live ?? false,
    apiKey,
  });

  const memory = new JMEMClient();

  // Try to start bridge (non-blocking)
  try {
    await bridge.start();
  } catch {
    // Bridge may not be available — that's fine, we handle it in commands
  }

  const { waitUntilExit } = render(
    <AppShell
      bridge={bridge}
      orchestrator={orchestrator}
      memory={memory}
      isLive={opts.live ?? false}
      model={opts.model ?? 'claude-sonnet-4-6'}
      apiKey={apiKey}
    />,
    {
      exitOnCtrlC: false, // We handle Ctrl+C ourselves
    }
  );

  await waitUntilExit();

  // Cleanup
  try {
    await bridge.stop();
  } catch {
    // Best-effort cleanup
  }

  process.exit(0);
}
