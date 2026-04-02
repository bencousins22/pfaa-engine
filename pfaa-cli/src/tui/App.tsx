/**
 * PFAA TUI App — Main application shell with real-time streaming agent display
 *
 * Layout:
 *   ╭─────────────────────────────────╮
 *   │  AUSSIE AGENTS (gradient)       │  ← Banner
 *   │  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
 *   │  v1.0 │ 44 Tools │ 17 MCP │ .. │
 *   ├─────────────────────────────────┤
 *   │  ◆ PFAA                         │  ← Messages
 *   │    Welcome to PFAA...           │
 *   │                                 │
 *   │  ▸ You                          │
 *   │    analyze this codebase        │
 *   │                                 │
 *   │  ◆ PFAA [ANALYZER]              │
 *   │    ╭─ grep [VAPOR] ── DONE ──╮  │  ← Tool blocks
 *   │    │ ▸ pattern: "TODO"       │  │
 *   │    │ ╰─ Found 23 matches     │  │
 *   │    ╰─────────────────────────╯  │
 *   │    ## Analysis Complete          │  ← Markdown
 *   │    Found **23** issues...       │
 *   ├─────────────────────────────────┤
 *   │  pfaa ▸ _                       │  ← Input
 *   ├─────────────────────────────────┤
 *   │ ◇ VAPOR │ SIM │ sonnet │ 0 tok │  ← Status bar
 *   ╰─────────────────────────────────╯
 *
 * Streaming architecture:
 *   1. User submits input
 *   2. ConversationEngine.query() returns an async generator of StreamEvents
 *   3. Each event updates the UI in real-time:
 *      - text_delta      → append to assistant message (streaming text)
 *      - tool_use_start  → add ToolCall block with spinner
 *      - tool_input_delta→ update tool args display
 *      - tool_use_end    → finalize tool input
 *      - tool_result     → mark tool completed/failed, show result
 *      - thinking_delta  → show thinking indicator
 *      - message_start   → create new assistant message (multi-turn)
 *      - message_end     → finalize, update token/cost stats
 *      - error           → display error
 *      - status          → update status bar
 */

import React, { useCallback, useRef } from 'react';
import { Box, Text, useApp as useInkApp, useInput, useStdout } from 'ink';
import { AppProvider, useApp } from './context.js';
import { AltScreen, Banner, MessageList, InputPrompt, StatusBar } from './components/index.js';
import { ConversationEngine } from './engine.js';
import { getToolDefinitions } from './tools.js';
import type { PFAABridge } from '../bridge/pfaa-bridge.js';
import type { AgentOrchestrator } from '../agents/orchestrator.js';
import type { JMEMClient } from '../memory/jmem-client.js';
import { EventType } from '../types.js';
import type { ToolCall } from './context.js';

// ── Help Panel (bordered) ────────────────────────────────────────────

function HelpPanel({ width }: { width: number }) {
  const innerWidth = Math.min(width - 6, 68);
  const pad = (s: string, len: number) => s + ' '.repeat(Math.max(0, len - s.length));
  const hr = '\u2500'.repeat(innerWidth);

  const commands: [string, string][] = [
    ['run <goal>', 'Execute a natural language goal'],
    ['status', 'Show system status'],
    ['bench', 'Run performance benchmarks'],
    ['team <goal>', 'Spawn agent team'],
    ['swarm <goal>', 'Multi-agent parallel execution'],
    ['memory stats', 'JMEM memory status'],
    ['tools', 'List all tools'],
    ['learn', 'Force learning cycle'],
    ['explore', 'Phase exploration'],
    ['exec -c "code"', 'Run Python in sandbox'],
    ['self-build', 'Self-improvement cycle'],
  ];

  const shortcuts: [string, string][] = [
    ['Ctrl+C / Ctrl+D', 'Exit PFAA'],
    ['Ctrl+L', 'Clear messages'],
    ['Ctrl+U', 'Clear input line'],
    ['Esc', 'Cancel current operation'],
    ['Up/Down', 'Command history'],
    ['Tab', 'Command completion'],
  ];

  return (
    <Box flexDirection="column" paddingX={2} marginY={0}>
      <Text color="#2E7D32">{'\u256D' + hr + '\u256E'}</Text>
      <Text color="#2E7D32">{'\u2502'}<Text color="#FFD54F" bold>{pad(' PFAA Commands', innerWidth)}</Text>{'\u2502'}</Text>
      <Text color="#2E7D32">{'\u251C' + hr + '\u2524'}</Text>
      {commands.map(([cmd, desc], i) => (
        <Text key={`cmd-${i}`} color="#2E7D32">
          {'\u2502'}
          <Text color="#D4A017" bold>{pad(` ${cmd}`, 20)}</Text>
          <Text color="#E0E5DC">{pad(desc, innerWidth - 20)}</Text>
          {'\u2502'}
        </Text>
      ))}
      <Text color="#2E7D32">{'\u251C' + hr + '\u2524'}</Text>
      <Text color="#2E7D32">{'\u2502'}<Text color="#00BCD4" bold>{pad(' Keyboard Shortcuts', innerWidth)}</Text>{'\u2502'}</Text>
      <Text color="#2E7D32">{'\u251C' + hr + '\u2524'}</Text>
      {shortcuts.map(([key, desc], i) => (
        <Text key={`key-${i}`} color="#2E7D32">
          {'\u2502'}
          <Text color="#00BCD4" bold>{pad(` ${key}`, 20)}</Text>
          <Text color="#E0E5DC">{pad(desc, innerWidth - 20)}</Text>
          {'\u2502'}
        </Text>
      ))}
      <Text color="#2E7D32">{'\u2570' + hr + '\u256F'}</Text>
    </Box>
  );
}

const VERSION = '1.0.0';

// ── AppShell Props ──────────────────────────────────────────────────

interface AppShellProps {
  bridge: PFAABridge;
  orchestrator: AgentOrchestrator;
  memory: JMEMClient;
  isLive: boolean;
  model: string;
  apiKey?: string;
}

export function AppShell(props: AppShellProps) {
  return (
    <AppProvider
      bridge={props.bridge}
      orchestrator={props.orchestrator}
      memory={props.memory}
      isLive={props.isLive}
      model={props.model}
    >
      <AppContent
        model={props.model}
        apiKey={props.apiKey}
        isLive={props.isLive}
        bridge={props.bridge}
        orchestrator={props.orchestrator}
      />
    </AppProvider>
  );
}

// ── Main App Content ────────────────────────────────────────────────

interface AppContentProps {
  model: string;
  apiKey?: string;
  isLive: boolean;
  bridge: PFAABridge;
  orchestrator: AgentOrchestrator;
}

function AppContent({ model, apiKey, isLive, bridge, orchestrator }: AppContentProps) {
  const app = useApp();
  const inkApp = useInkApp();
  const cancelRef = useRef(false);

  const { stdout } = useStdout();
  const termWidth = stdout?.columns ?? 80;

  // ── Conversation Engine (created once, stable ref) ──────────────

  const engineRef = useRef<ConversationEngine | null>(null);
  const engineFailedRef = useRef(false);

  if (!engineRef.current && !engineFailedRef.current) {
    try {
      const eng = new ConversationEngine({
        apiKey,
        model,
      });
      engineRef.current = eng;
      // Debug: log whether engine got a live client
      if (eng.isLive) {
        // eslint-disable-next-line no-console
        console.error('[PFAA] ConversationEngine: live client ready');
      } else {
        // eslint-disable-next-line no-console
        console.error('[PFAA] ConversationEngine: no live client (no API key or OAuth)');
      }
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('[PFAA] ConversationEngine init failed:', err);
      engineFailedRef.current = true;
    }
  }

  const engine = engineRef.current;

  // ── Session-level token tracking ────────────────────────────────

  const sessionTokensRef = useRef({ input: 0, output: 0 });

  // ── Global keyboard shortcuts ──────────────────────────────────

  useInput((_input, key) => {
    // Ctrl+C or Ctrl+D -- exit
    if (key.ctrl && (_input === 'c' || _input === 'd')) {
      engine?.abort();
      bridge.stop().catch(() => {});
      inkApp.exit();
      return;
    }
    // Ctrl+L -- clear messages
    if (key.ctrl && _input === 'l') {
      app.addMessage({ role: 'system', content: 'Screen cleared.' });
      return;
    }
    // Esc -- cancel current operation
    if (key.escape && app.state.isProcessing) {
      cancelRef.current = true;
      engine?.abort();
      app.setProcessing(false);
      app.addMessage({ role: 'system', content: 'Operation cancelled.' });
      return;
    }
  });

  // ── Stream handler: processes engine events into UI updates ─────

  const handleConversationStream = useCallback(async (input: string) => {
    if (!engine) return; // Should not happen -- caller checks engine.isLive
    app.setProcessing(true);
    app.setPhase('VAPOR');

    const startTime = Date.now();

    // Create initial assistant message (will be updated as stream comes in)
    let currentMsgId = app.addMessage({
      role: 'assistant',
      content: '',
      streaming: true,
    });

    // Track tool calls for the current message
    let currentToolCalls: ToolCall[] = [];
    // Track accumulated text for the current message
    let accumulatedText = '';
    // Map tool call IDs to indices for quick lookup
    const toolCallMap = new Map<string, number>();
    // Whether we are in a new message (after tool execution loop)
    let messageCount = 0;
    // Track thinking state
    let isThinking = false;

    try {
      for await (const event of engine.query(input)) {
        if (cancelRef.current) break;

        switch (event.type) {
          case 'message_start': {
            messageCount++;
            if (messageCount > 1) {
              // New assistant turn after tool execution -- finalize previous message
              app.updateMessage(currentMsgId, {
                content: accumulatedText,
                streaming: false,
                toolCalls: currentToolCalls.length > 0 ? [...currentToolCalls] : undefined,
              });

              // Start new assistant message
              accumulatedText = '';
              currentToolCalls = [];
              toolCallMap.clear();
              currentMsgId = app.addMessage({
                role: 'assistant',
                content: '',
                streaming: true,
              });
            }
            break;
          }

          case 'text_delta': {
            // Append text for streaming effect
            accumulatedText += event.text;
            app.appendToMessage(currentMsgId, event.text);
            if (isThinking) {
              isThinking = false;
              app.updateMessage(currentMsgId, { agentRole: undefined });
            }
            break;
          }

          case 'thinking_delta': {
            // Show thinking indicator on the message header
            if (!isThinking) {
              isThinking = true;
              app.updateMessage(currentMsgId, {
                agentRole: 'thinking...',
                streaming: true,
              });
            }
            break;
          }

          case 'tool_use_start': {
            // Add a new tool call block with running status and spinner
            const toolCall: ToolCall = {
              id: event.toolCallId,
              name: event.toolName,
              phase: 'VAPOR',
              status: 'running',
              startedAt: Date.now(),
              args: '',
            };
            const idx = currentToolCalls.length;
            currentToolCalls.push(toolCall);
            toolCallMap.set(event.toolCallId, idx);

            app.updateMessage(currentMsgId, {
              toolCalls: [...currentToolCalls],
              streaming: true,
            });
            break;
          }

          case 'tool_input_delta': {
            // Update tool call args display with streaming JSON input
            const idx = toolCallMap.get(event.toolCallId);
            if (idx !== undefined && currentToolCalls[idx]) {
              currentToolCalls[idx] = {
                ...currentToolCalls[idx],
                args: (currentToolCalls[idx].args || '') + event.partialJson,
              };
              app.updateMessage(currentMsgId, {
                toolCalls: [...currentToolCalls],
              });
            }
            break;
          }

          case 'tool_use_end': {
            // Tool input fully received -- format the input as readable args
            const idx = toolCallMap.get(event.toolCallId);
            if (idx !== undefined && currentToolCalls[idx]) {
              const inputStr = Object.entries(event.input)
                .map(([k, v]) => `${k}: ${typeof v === 'string' ? v : JSON.stringify(v)}`)
                .join(', ');
              currentToolCalls[idx] = {
                ...currentToolCalls[idx],
                args: inputStr || currentToolCalls[idx].args,
                status: 'running',
              };
              app.updateMessage(currentMsgId, {
                toolCalls: [...currentToolCalls],
              });
            }
            break;
          }

          case 'tool_result': {
            // Tool execution finished -- update status, show result
            const idx = toolCallMap.get(event.toolCallId);
            if (idx !== undefined && currentToolCalls[idx]) {
              const now = Date.now();
              currentToolCalls[idx] = {
                ...currentToolCalls[idx],
                status: event.isError ? 'failed' : 'completed',
                result: event.result.slice(0, 500),
                elapsedMs: now - currentToolCalls[idx].startedAt,
              };
              app.updateMessage(currentMsgId, {
                toolCalls: [...currentToolCalls],
              });
            }
            break;
          }

          case 'message_end': {
            // Update session-level token stats
            sessionTokensRef.current.input += event.inputTokens;
            sessionTokensRef.current.output += event.outputTokens;

            const totalTokens = sessionTokensRef.current.input + sessionTokensRef.current.output;
            app.updateStats({
              tokensUsed: totalTokens,
            });
            break;
          }

          case 'status': {
            // Update phase display based on what the engine is doing
            if (event.message.includes('tool')) {
              app.setPhase('SOLID');
            } else if (event.message.includes('Think')) {
              app.setPhase('VAPOR');
            }
            break;
          }

          case 'error': {
            // Display error inline in the assistant message
            app.updateMessage(currentMsgId, {
              content: accumulatedText
                ? accumulatedText + '\n\n**Error**: ' + event.message
                : '**Error**: ' + event.message,
              streaming: false,
              toolCalls: currentToolCalls.length > 0 ? [...currentToolCalls] : undefined,
            });
            break;
          }
        }
      }

      // Finalize the last message after stream ends
      if (!cancelRef.current) {
        app.updateMessage(currentMsgId, {
          content: accumulatedText,
          streaming: false,
          toolCalls: currentToolCalls.length > 0 ? [...currentToolCalls] : undefined,
        });
      }
    } catch (err) {
      if (!cancelRef.current) {
        app.updateMessage(currentMsgId, {
          content: `Error: ${err instanceof Error ? err.message : String(err)}`,
          streaming: false,
        });
      }
    } finally {
      app.setProcessing(false);
      app.setPhase('VAPOR');
      app.updateStats({ elapsedMs: Date.now() - startTime });
    }
  }, [app, engine]);

  // ── Input submission handler ───────────────────────────────────

  const handleSubmit = useCallback(async (input: string) => {
    cancelRef.current = false;

    // ── Built-in commands ─────────────────────────────────────────

    if (input === 'exit' || input === 'quit' || input === 'q') {
      engine?.abort();
      bridge.stop().catch(() => {});
      inkApp.exit();
      return;
    }

    if (input === 'clear') {
      app.addMessage({ role: 'system', content: 'Screen cleared.' });
      engine?.reset();
      return;
    }

    if (input === 'help' || input === '?') {
      app.addMessage({
        role: 'system',
        content: '__HELP_PANEL__',
      });
      return;
    }

    // ── Parse command prefix ─────────────────────────────────────

    const parts = input.split(/\s+/);
    const cmd = parts[0].toLowerCase();
    const args = parts.slice(1).join(' ');

    // ── Route built-in commands through the bridge ───────────────

    if (cmd === 'status') {
      await handleStatus(app, bridge);
      return;
    }
    if (cmd === 'bench' || cmd === 'benchmark') {
      await handleBench(app, bridge);
      return;
    }
    if (cmd === 'tools') {
      await handleTools(app, bridge);
      return;
    }
    if (cmd === 'memory') {
      await handleMemory(app, bridge, args);
      return;
    }
    if (cmd === 'learn') {
      await handleLearn(app, bridge);
      return;
    }
    if (cmd === 'team') {
      await handleTeam(app, bridge, args || 'general analysis');
      return;
    }
    if (cmd === 'swarm') {
      await handleSwarm(app, bridge, args || input);
      return;
    }
    if (cmd === 'explore') {
      await handleExplore(app, bridge);
      return;
    }
    if (cmd === 'self-build') {
      await handleSelfBuild(app, bridge);
      return;
    }

    // ── Default: natural language through ConversationEngine ─────
    // If the engine has a live API key, stream the response.
    // Otherwise fall back to bridge/orchestrator.

    // Add user message to display
    app.addMessage({ role: 'user', content: input });

    if (engine?.isLive) {
      await handleConversationStream(input);
    } else {
      // No live API -- fall back to bridge
      await handleRunViaBridge(app, bridge, orchestrator, input);
    }
  }, [app, inkApp, engine, bridge, orchestrator, handleConversationStream]);

  // ── Render ─────────────────────────────────────────────────────

  return (
    <AltScreen>
      <Box flexDirection="column" width={termWidth}>
        {/* Fixed header: Banner */}
        <Banner version={VERSION} />

        {/* Full-width separator */}
        <Box width={termWidth}>
          <Text color="#2E7D32">{'\u2500'.repeat(termWidth)}</Text>
        </Box>

        {/* Scrollable message area */}
        <Box flexDirection="column" flexGrow={1}>
          <MessageList />
          {/* Render help panel if last message is the sentinel */}
          {app.state.messages.length > 0 &&
            app.state.messages[app.state.messages.length - 1]?.content === '__HELP_PANEL__' && (
              <HelpPanel width={termWidth} />
            )}
        </Box>

        {/* Full-width separator */}
        <Box width={termWidth}>
          <Text color="#2E7D32">{'\u2500'.repeat(termWidth)}</Text>
        </Box>

        {/* Fixed input prompt */}
        <InputPrompt onSubmit={handleSubmit} />

        {/* Fixed status bar */}
        <StatusBar />
      </Box>
    </AltScreen>
  );
}

// ── Bridge-based Command Handlers ────────────────────────────────────
// These handle built-in commands that go through the Python bridge
// or orchestrator rather than the ConversationEngine.

async function handleStatus(app: ReturnType<typeof useApp>, bridge: PFAABridge) {
  const msgId = app.addMessage({ role: 'assistant', content: '', streaming: true });
  app.setProcessing(true);

  try {
    await bridge.start();
    const status = await bridge.status();

    const toolCount = typeof status.tools === 'number' ? status.tools : 0;
    const content = [
      '## System Status',
      '',
      `**Engine**: ${toolCount} tools loaded`,
      `**Uptime**: ${status.uptime_ms ? (status.uptime_ms / 1000).toFixed(1) + 's' : 'N/A'}`,
      `**Memory**: L1=${status.l1Episodes ?? 0} episodes, L2=${status.l2Patterns ?? 0} patterns, L3=${status.l3Strategies ?? 0} strategies`,
      `**Mode**: ${app.state.isLive ? 'LIVE (Claude API)' : 'Simulated'}`,
      `**Model**: ${app.state.model}`,
    ].join('\n');

    app.updateMessage(msgId, { content, streaming: false });
    app.updateStats({
      toolCount,
      memoryCount: (status.l1Episodes ?? 0) + (status.l2Patterns ?? 0) + (status.l3Strategies ?? 0),
    });
  } catch (err) {
    app.updateMessage(msgId, {
      content: `Could not reach engine: ${err instanceof Error ? err.message : String(err)}.\nRunning in standalone mode.`,
      streaming: false,
    });
  } finally {
    app.setProcessing(false);
  }
}

async function handleBench(app: ReturnType<typeof useApp>, bridge: PFAABridge) {
  const startTime = Date.now();
  const msgId = app.addMessage({
    role: 'assistant',
    content: '',
    streaming: true,
    toolCalls: [
      { id: 'bench_1', name: 'benchmark', phase: 'SOLID', status: 'running', startedAt: startTime },
    ],
  });
  app.setProcessing(true);

  try {
    await bridge.start();
    const result = await bridge.benchmark();

    app.updateMessage(msgId, {
      streaming: false,
      content: '## Benchmark Results\n\n```json\n' + JSON.stringify(result, null, 2) + '\n```',
      toolCalls: [
        { id: 'bench_1', name: 'benchmark', phase: 'SOLID', status: 'completed', startedAt: startTime, elapsedMs: Date.now() - startTime },
      ],
    });
  } catch (err) {
    app.updateMessage(msgId, {
      streaming: false,
      content: `Benchmark error: ${err instanceof Error ? err.message : String(err)}`,
      toolCalls: [
        { id: 'bench_1', name: 'benchmark', phase: 'SOLID', status: 'failed', startedAt: startTime },
      ],
    });
  } finally {
    app.setProcessing(false);
    app.updateStats({ elapsedMs: Date.now() - startTime });
  }
}

async function handleTools(app: ReturnType<typeof useApp>, bridge: PFAABridge) {
  const msgId = app.addMessage({ role: 'assistant', content: '', streaming: true });
  app.setProcessing(true);

  try {
    await bridge.start();
    const tools = await bridge.listTools();

    const grouped: Record<string, typeof tools> = {};
    for (const t of tools) {
      const phase = t.phase || 'UNKNOWN';
      if (!grouped[phase]) grouped[phase] = [];
      grouped[phase].push(t);
    }

    let content = '## Registered Tools\n\n';
    for (const [phase, list] of Object.entries(grouped)) {
      content += `### ${phase} (${list.length})\n`;
      for (const t of list) {
        content += `- **${t.name}** --- ${t.description || 'no description'}\n`;
      }
      content += '\n';
    }

    app.updateMessage(msgId, { content, streaming: false });
    app.updateStats({ toolCount: tools.length });
  } catch (err) {
    // Fallback: show built-in tool definitions from engine
    const builtInTools = getToolDefinitions();
    let content = '## Available Tools (Built-in)\n\n';
    for (const t of builtInTools) {
      content += `- **${t.name}** --- ${t.description.slice(0, 80)}\n`;
    }
    content += `\n*Bridge not available: ${err instanceof Error ? err.message : String(err)}*`;
    app.updateMessage(msgId, { content, streaming: false });
  } finally {
    app.setProcessing(false);
  }
}

async function handleMemory(app: ReturnType<typeof useApp>, bridge: PFAABridge, args: string) {
  const msgId = app.addMessage({ role: 'assistant', content: '', streaming: true });
  app.setProcessing(true);

  try {
    await bridge.start();
    const status = await bridge.status();
    const mem = await bridge.getMemory();

    let content = '## JMEM Memory Status\n\n';
    content += `- **L1 Episodic**: ${status.l1Episodes ?? 0} entries\n`;
    content += `- **L2 Semantic**: ${status.l2Patterns ?? 0} patterns\n`;
    content += `- **L3 Strategic**: ${status.l3Strategies ?? 0} strategies\n`;

    if (mem.knowledge && Object.keys(mem.knowledge).length > 0) {
      content += '\n### Recent Knowledge\n';
      const entries = Array.isArray(mem.knowledge) ? mem.knowledge : Object.values(mem.knowledge);
      for (const k of entries.slice(0, 5)) {
        content += `- ${typeof k === 'string' ? k : JSON.stringify(k).slice(0, 80)}\n`;
      }
    }

    app.updateMessage(msgId, { content, streaming: false });
  } catch (err) {
    app.updateMessage(msgId, {
      content: `Memory unavailable: ${err instanceof Error ? err.message : String(err)}`,
      streaming: false,
    });
  } finally {
    app.setProcessing(false);
  }
}

async function handleLearn(app: ReturnType<typeof useApp>, bridge: PFAABridge) {
  const msgId = app.addMessage({ role: 'assistant', content: '', streaming: true });
  app.setProcessing(true);

  try {
    await bridge.start();
    const result = await bridge.forceLearn();
    app.updateMessage(msgId, {
      content: `## Learning Cycle Complete\n\nExtracted **${result?.learned ?? 0}** new patterns from episodes.`,
      streaming: false,
    });
  } catch (err) {
    app.updateMessage(msgId, {
      content: `Learning error: ${err instanceof Error ? err.message : String(err)}`,
      streaming: false,
    });
  } finally {
    app.setProcessing(false);
  }
}

async function handleSwarm(app: ReturnType<typeof useApp>, bridge: PFAABridge, goal: string) {
  const msgId = app.addMessage({
    role: 'assistant',
    content: 'Spawning agent swarm...',
    streaming: true,
    agentRole: 'SWARM',
  });
  app.setProcessing(true);

  try {
    await bridge.start();
    const result = await bridge.spawnTeam(goal);
    app.updateMessage(msgId, {
      content: '## Swarm Results\n\n```json\n' + JSON.stringify(result, null, 2) + '\n```',
      streaming: false,
    });
  } catch (err) {
    app.updateMessage(msgId, {
      content: `Swarm error: ${err instanceof Error ? err.message : String(err)}`,
      streaming: false,
    });
  } finally {
    app.setProcessing(false);
  }
}

async function handleTeam(app: ReturnType<typeof useApp>, bridge: PFAABridge, goal: string) {
  return handleSwarm(app, bridge, goal);
}

async function handleExplore(app: ReturnType<typeof useApp>, bridge: PFAABridge) {
  const msgId = app.addMessage({ role: 'assistant', content: '', streaming: true });
  app.setProcessing(true);

  try {
    await bridge.start();
    const result = await bridge.explore();
    app.updateMessage(msgId, {
      content: '## Phase Exploration\n\n```json\n' + JSON.stringify(result, null, 2) + '\n```',
      streaming: false,
    });
  } catch (err) {
    app.updateMessage(msgId, {
      content: `Explore error: ${err instanceof Error ? err.message : String(err)}`,
      streaming: false,
    });
  } finally {
    app.setProcessing(false);
  }
}

async function handleSelfBuild(app: ReturnType<typeof useApp>, bridge: PFAABridge) {
  const msgId = app.addMessage({
    role: 'assistant',
    content: 'Running self-improvement cycle...',
    streaming: true,
    agentRole: 'BUILDER',
  });
  app.setProcessing(true);

  try {
    await bridge.start();
    const result = await bridge.selfBuild(false);
    app.updateMessage(msgId, {
      content: '## Self-Build Results\n\n```json\n' + JSON.stringify(result, null, 2) + '\n```',
      streaming: false,
    });
  } catch (err) {
    app.updateMessage(msgId, {
      content: `Self-build error: ${err instanceof Error ? err.message : String(err)}`,
      streaming: false,
    });
  } finally {
    app.setProcessing(false);
  }
}

/**
 * Fallback handler for natural language when ConversationEngine has no API key.
 * Tries the orchestrator, then bridge, then shows a helpful message.
 */
async function handleRunViaBridge(
  app: ReturnType<typeof useApp>,
  bridge: PFAABridge,
  orchestrator: AgentOrchestrator,
  goal: string,
) {
  const msgId = app.addMessage({
    role: 'assistant',
    content: '',
    streaming: true,
    agentRole: 'ORCHESTRATOR',
  });
  app.setProcessing(true);
  app.setPhase('VAPOR');

  const startTime = Date.now();

  // Track tool calls from orchestrator events
  const toolCalls: ToolCall[] = [];

  const eventHandler = (event: any) => {
    if (event.type === EventType.AGENT_SPAWNED) {
      toolCalls.push({
        id: event.data.agentId || `tc_${toolCalls.length}`,
        name: event.data.role || 'agent',
        phase: event.data.phase || 'VAPOR',
        status: 'running',
        startedAt: Date.now(),
      });
      app.updateMessage(msgId, { toolCalls: [...toolCalls] });
    } else if (event.type === EventType.AGENT_COMPLETED) {
      const tc = toolCalls.find(t => t.id === event.data.agentId);
      if (tc) {
        tc.status = 'completed';
        tc.elapsedMs = event.data.elapsedMs;
        app.updateMessage(msgId, { toolCalls: [...toolCalls] });
      }
    } else if (event.type === EventType.AGENT_FAILED) {
      const tc = toolCalls.find(t => t.id === event.data.agentId);
      if (tc) {
        tc.status = 'failed';
        tc.result = event.data.error;
        app.updateMessage(msgId, { toolCalls: [...toolCalls] });
      }
    }
    app.addEvent(event);
  };

  orchestrator.on('event', eventHandler);

  try {
    // Try live orchestrator first (needs Claude API key)
    if (orchestrator.isLive) {
      const result = await orchestrator.executeGoal(goal);
      app.updateMessage(msgId, {
        content: result.summary || 'Goal completed.',
        streaming: false,
        toolCalls: [...toolCalls],
      });
    } else {
      // Try bridge mode -- start bridge if needed
      let bridgeAvailable = false;
      try {
        if (!bridge.isRunning) await bridge.start();
        bridgeAvailable = bridge.isRunning;
      } catch {
        // Bridge not available
      }

      if (bridgeAvailable) {
        try {
          const result = await bridge.runGoal(goal);
          const output = typeof result.output === 'string' ? result.output : JSON.stringify(result.output ?? result, null, 2);
          app.updateMessage(msgId, { content: output, streaming: false });
        } catch {
          // Fallback to askClaude via bridge
          try {
            const result = await bridge.askClaude(goal);
            app.updateMessage(msgId, { content: result.output || 'No response.', streaming: false });
          } catch {
            app.updateMessage(msgId, {
              content: 'Bridge error. Try a specific command like `status` or `tools`.',
              streaming: false,
            });
          }
        }
      } else {
        // No bridge, no live API -- show helpful message
        const noApiKey = app.state.isLive;
        app.updateMessage(msgId, {
          content: noApiKey
            ? '## No API Key Found\n\nYou passed `--live` but no Anthropic API key was found.\n\nSet it with:\n```\nexport ANTHROPIC_API_KEY=sk-ant-...\n```\n\nOr pass it directly:\n```\npfaa --live --api-key sk-ant-...\n```'
            : '## Engine Not Available\n\nThe Python bridge is not running. Start it with:\n```\npython3.15 -m pfaa\n```\n\nOr use live Claude API mode:\n```\npfaa --live\n```',
          streaming: false,
        });
      }
    }
  } catch (err) {
    app.updateMessage(msgId, {
      content: `Error: ${err instanceof Error ? err.message : String(err)}`,
      streaming: false,
    });
  } finally {
    orchestrator.removeListener('event', eventHandler);
    app.setProcessing(false);
    app.updateStats({ elapsedMs: Date.now() - startTime });
  }
}
