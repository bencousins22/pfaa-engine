/**
 * PFAA Status Bar — Persistent bottom bar showing phase, streaming mode,
 * model, tokens, cost, elapsed time, tool count, memory count, and turn count.
 *
 * Layout:
 *   ╭──────────────────────────────────────────────────────────────────────╮
 *   │ ◇ VAPOR │ RESPONDING... │ sonnet │ 1.2K tok │ $0.02 │ 3.2s │ T3 M12 │
 *   ╰──────────────────────────────────────────────────────────────────────╯
 */

import React from 'react';
import { Box, Text, useStdout } from 'ink';
import { useApp } from '../context.js';
import { StreamingDots } from './Spinner.js';

/** Rough cost estimation per 1K tokens (blended input+output for Sonnet) */
const COST_PER_1K_TOKENS: Record<string, number> = {
  'claude-sonnet-4-6': 0.009,
  'claude-sonnet-4-20250514': 0.009,
  'claude-opus-4-6': 0.045,
  'claude-opus-4-20250514': 0.045,
  'claude-haiku-3-5': 0.002,
};

function estimateCost(tokens: number, model: string): string {
  const rate = COST_PER_1K_TOKENS[model] ?? 0.009;
  const cost = (tokens / 1000) * rate;
  if (cost < 0.001) return '--';
  if (cost < 0.01) return `~$${cost.toFixed(4)}`;
  if (cost < 1) return `~$${cost.toFixed(3)}`;
  return `~$${cost.toFixed(2)}`;
}

function formatCost(cost: number): string {
  if (cost <= 0) return '--';
  if (cost < 0.01) return `$${cost.toFixed(4)}`;
  if (cost < 1) return `$${cost.toFixed(3)}`;
  return `$${cost.toFixed(2)}`;
}

function formatElapsed(ms: number): string {
  if (ms <= 0) return '--';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60000);
  const secs = Math.round((ms % 60000) / 1000);
  return `${mins}m${secs}s`;
}

function formatTokens(n: number): string {
  if (n <= 0) return '--';
  if (n < 1000) return `${n}`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`;
  return `${(n / 1_000_000).toFixed(2)}M`;
}

/** Map streaming mode to display label and color — pearl tones */
function modeDisplay(mode: string): { label: string; color: string } {
  switch (mode) {
    case 'thinking':
      return { label: 'THINKING', color: '#FFE4B5' };
    case 'responding':
      return { label: 'RESPONDING', color: '#F8F8FF' };
    case 'requesting':
      return { label: 'REQUESTING', color: '#B5D4FF' };
    case 'tool-input':
      return { label: 'TOOL INPUT', color: '#E8D5B7' };
    case 'tool-use':
      return { label: 'TOOL USE', color: '#E6E6FA' };
    case 'idle':
    default:
      return { label: 'IDLE', color: '#8E8E93' };
  }
}

export function StatusBar() {
  const { state } = useApp();
  const { stdout } = useStdout();
  const {
    currentPhase,
    model,
    tokensUsed,
    elapsedMs,
    isLive,
    toolCount,
    memoryCount,
    streamingMode,
    totalCost,
    turnCount,
  } = state;

  const termWidth = stdout?.columns ?? 80;
  const elapsed = formatElapsed(elapsedMs);
  const tokens = formatTokens(tokensUsed);
  const costFromTokens = estimateCost(tokensUsed, model);
  const costDisplay = totalCost > 0 ? formatCost(totalCost) : costFromTokens;

  // Short model name for display
  const shortModel = model
    .replace('claude-', '')
    .replace(/-\d{8}$/, '')
    .replace('-4-6', '');

  // Phase indicator color — soft pearl iridescence
  const phaseColors: Record<string, string> = {
    VAPOR: '#B5D4FF',
    LIQUID: '#FFE4B5',
    SOLID: '#FFB5B5',
  };
  const phaseColor = phaseColors[currentPhase] ?? '#B5D4FF';

  // Streaming mode indicator
  const { label: modeLabel, color: modeColor } = modeDisplay(streamingMode);
  const isActive = streamingMode !== 'idle';

  return (
    <Box flexDirection="column" width={termWidth}>
      {/* Top border */}
      <Box paddingX={0}>
        <Text color="#D4D4D8">
          {'\u256D' + '\u2500'.repeat(Math.max(0, termWidth - 2)) + '\u256E'}
        </Text>
      </Box>

      {/* Status content */}
      <Box paddingX={0} justifyContent="space-between" width={termWidth}>
        <Text color="#D4D4D8">{'\u2502'}</Text>

        <Box flexGrow={1} justifyContent="space-between" paddingX={1}>
          {/* Left group: phase, streaming mode, model */}
          <Box gap={1}>
            <Text color={phaseColor}>{'\u25C7'}</Text>
            <Text color={phaseColor} bold>{currentPhase}</Text>
            <Text color="#D4D4D8">{'\u2502'}</Text>

            {/* Streaming mode indicator */}
            {isActive ? (
              <Box>
                <Text color={modeColor} bold> {modeLabel} </Text>
                <StreamingDots color={modeColor} />
              </Box>
            ) : (
              <Text color={modeColor}> {modeLabel} </Text>
            )}

            <Text color="#D4D4D8">{'\u2502'}</Text>

            {isLive ? (
              <Text color="#A8E6CF" bold> LIVE </Text>
            ) : (
              <Text color="#8E8E93"> SIM  </Text>
            )}
            <Text color="#D4D4D8">{'\u2502'}</Text>
            <Text dimColor>{shortModel}</Text>
          </Box>

          {/* Right group: tokens, cost, elapsed, turns, tools, memory */}
          <Box gap={1}>
            <Text color="#E8D5B7">{'\u25B8'} {tokens} tok</Text>
            <Text color="#D4D4D8">{'\u2502'}</Text>
            <Text color="#A1A1A6">{costDisplay}</Text>
            <Text color="#D4D4D8">{'\u2502'}</Text>
            <Text color="#B5D4FF">{'\u23F1'} {elapsed}</Text>
            <Text color="#D4D4D8">{'\u2502'}</Text>
            <Text color="#E6E6FA">T{turnCount}</Text>
            <Text color="#D4D4D8">{'\u2502'}</Text>
            <Text dimColor>{toolCount}T</Text>
            <Text color="#E6E6FA">{memoryCount}M</Text>
          </Box>
        </Box>

        <Text color="#D4D4D8">{'\u2502'}</Text>
      </Box>

      {/* Bottom border */}
      <Box paddingX={0}>
        <Text color="#D4D4D8">
          {'\u2570' + '\u2500'.repeat(Math.max(0, termWidth - 2)) + '\u256F'}
        </Text>
      </Box>
    </Box>
  );
}
