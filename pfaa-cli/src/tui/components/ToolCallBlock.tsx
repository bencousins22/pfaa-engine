/**
 * PFAA ToolCallBlock — Tool execution display with streaming support
 *
 * Supports both finalized ToolCall (from messages) and live StreamingToolUse:
 *   streaming  -> tool name + live input JSON accumulation with spinner
 *   executing  -> tool name + args + executing spinner
 *   completed  -> bordered panel with green border + result
 *   failed     -> bordered panel with red border + error
 */

import React from 'react';
import { Box, Text } from 'ink';
import { Spinner, StreamingDots } from './Spinner.js';
import type { ToolCall, StreamingToolUse } from '../context.js';

const MAX_RESULT_LENGTH = 500;

function truncate(text: string, max: number): string {
  if (text.length <= max) return text;
  return text.slice(0, max) + `\n... (truncated, ${text.length - max} more chars)`;
}

function formatElapsed(ms?: number): string {
  if (!ms || ms <= 0) return '';
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const mins = Math.floor(ms / 60000);
  const secs = Math.round((ms % 60000) / 1000);
  return `${mins}m${secs}s`;
}

// ── StreamingToolBlock ────────────────────────────────────────────

interface StreamingToolBlockProps {
  tool: StreamingToolUse;
}

export function StreamingToolBlock({ tool }: StreamingToolBlockProps) {
  const elapsed = formatElapsed(tool.elapsedMs);

  // Streaming: accumulating input JSON
  if (tool.status === 'streaming') {
    return (
      <Box flexDirection="column" paddingLeft={2} marginY={0}>
        <Box gap={1}>
          <Spinner type="dots" color="#E8D5B7" />
          <Text color="#E8D5B7" bold>{tool.name}</Text>
          <Text backgroundColor="#B5D4FF" color="#2C2C2E"> STREAMING </Text>
        </Box>
        {tool.unparsedInput && (
          <Box paddingLeft={4}>
            <Text dimColor>{truncate(tool.unparsedInput, 200)}</Text>
            <StreamingDots color="#D4D4D8" />
          </Box>
        )}
      </Box>
    );
  }

  // Executing: input is complete, waiting for result
  if (tool.status === 'executing') {
    return (
      <Box flexDirection="column" paddingLeft={2} marginY={0}>
        <Box gap={1}>
          <Spinner type="dots" color="#B5D4FF" />
          <Text color="#E8D5B7" bold>{tool.name}</Text>
          <Text backgroundColor="#B5D4FF" color="#2C2C2E"> EXECUTING </Text>
          {elapsed ? <Text dimColor>{elapsed}</Text> : null}
        </Box>
        {tool.unparsedInput && (
          <Box paddingLeft={4}>
            <Text dimColor>{truncate(tool.unparsedInput, 200)}</Text>
          </Box>
        )}
      </Box>
    );
  }

  // Completed: bordered green panel
  if (tool.status === 'completed') {
    return (
      <Box
        flexDirection="column"
        borderStyle="round"
        borderColor="#A8E6CF"
        paddingX={1}
        marginLeft={2}
        marginY={0}
      >
        <Box justifyContent="space-between">
          <Box gap={1}>
            <Text color="#A8E6CF">{'\u2713'}</Text>
            <Text color="#E8D5B7" bold>{tool.name}</Text>
            <Text backgroundColor="#A8E6CF" color="#2C2C2E"> DONE </Text>
          </Box>
          {elapsed ? <Text dimColor>{elapsed}</Text> : null}
        </Box>
        {tool.unparsedInput && (
          <Box paddingLeft={2}>
            <Text dimColor>{'\u25B8'} {truncate(tool.unparsedInput, 200)}</Text>
          </Box>
        )}
        {tool.result && (
          <Box paddingLeft={2} flexDirection="column">
            <Text dimColor>{'\u2570\u2500'} </Text>
            <Text>{truncate(tool.result, MAX_RESULT_LENGTH)}</Text>
          </Box>
        )}
      </Box>
    );
  }

  // Failed: bordered red panel
  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor="#FFB5B5"
      paddingX={1}
      marginLeft={2}
      marginY={0}
    >
      <Box justifyContent="space-between">
        <Box gap={1}>
          <Text color="#FFB5B5">{'\u2717'}</Text>
          <Text color="#E8D5B7" bold>{tool.name}</Text>
          <Text backgroundColor="#FFB5B5" color="#2C2C2E"> FAIL </Text>
        </Box>
        {elapsed ? <Text dimColor>{elapsed}</Text> : null}
      </Box>
      {tool.unparsedInput && (
        <Box paddingLeft={2}>
          <Text dimColor>{'\u25B8'} {truncate(tool.unparsedInput, 200)}</Text>
        </Box>
      )}
      {tool.result && (
        <Box paddingLeft={2} flexDirection="column">
          <Text color="#FFB5B5">{truncate(tool.result, MAX_RESULT_LENGTH)}</Text>
        </Box>
      )}
    </Box>
  );
}

// ── ToolCallBlock (finalized, from message history) ──────────────

interface ToolCallBlockProps {
  tool: ToolCall;
}

export function ToolCallBlock({ tool }: ToolCallBlockProps) {
  const elapsed = formatElapsed(tool.elapsedMs);

  // Inline mode for pending
  if (tool.status === 'pending') {
    return (
      <Box paddingLeft={2}>
        <Text dimColor>{'\u25CB'} </Text>
        <Text color="#E8D5B7">{tool.name}</Text>
        <Text color="#B5D4FF"> [{tool.phase}]</Text>
        <Text dimColor> waiting...</Text>
      </Box>
    );
  }

  // Running with spinner
  if (tool.status === 'running') {
    return (
      <Box flexDirection="column" paddingLeft={2}>
        <Box gap={1}>
          <Spinner type="dots" />
          <Text color="#E8D5B7" bold>{tool.name}</Text>
          <Text color="#B5D4FF"> [{tool.phase}]</Text>
          <Text backgroundColor="#B5D4FF" color="#2C2C2E"> RUNNING </Text>
        </Box>
        {tool.args && (
          <Box paddingLeft={4}>
            <Text dimColor>{tool.args.slice(0, 120)}</Text>
          </Box>
        )}
      </Box>
    );
  }

  // Block mode for completed/failed
  const borderColor = tool.status === 'completed' ? '#A8E6CF' : '#FFB5B5';
  const statusBadge = tool.status === 'completed'
    ? <Text backgroundColor="#A8E6CF" color="#2C2C2E"> DONE </Text>
    : <Text backgroundColor="#FFB5B5" color="#2C2C2E"> FAIL </Text>;

  const statusIcon = tool.status === 'completed'
    ? <Text color="#A8E6CF">{'\u2713'}</Text>
    : <Text color="#FFB5B5">{'\u2717'}</Text>;

  return (
    <Box
      flexDirection="column"
      borderStyle="round"
      borderColor={borderColor}
      paddingX={1}
      marginLeft={2}
      marginY={0}
    >
      {/* Header */}
      <Box justifyContent="space-between">
        <Box gap={1}>
          {statusIcon}
          <Text color="#E8D5B7" bold>{tool.name}</Text>
          <Text color="#B5D4FF">[{tool.phase}]</Text>
          {statusBadge}
        </Box>
        {elapsed ? <Text dimColor>{elapsed}</Text> : null}
      </Box>

      {/* Args */}
      {tool.args && (
        <Box paddingLeft={2}>
          <Text dimColor>{'\u25B8'} {tool.args.slice(0, 200)}</Text>
        </Box>
      )}

      {/* Result */}
      {tool.result && (
        <Box paddingLeft={2} flexDirection="column">
          <Text dimColor>{'\u2570\u2500'} </Text>
          <Text>{truncate(tool.result, MAX_RESULT_LENGTH)}</Text>
        </Box>
      )}
    </Box>
  );
}

/** Compact summary for multiple tool calls */
export function ToolCallSummary({ tools }: { tools: ToolCall[] }) {
  const completed = tools.filter(t => t.status === 'completed').length;
  const failed = tools.filter(t => t.status === 'failed').length;
  const running = tools.filter(t => t.status === 'running').length;

  return (
    <Box paddingLeft={2} gap={2}>
      {completed > 0 && <Text color="#A8E6CF">{completed} {'\u2713'}</Text>}
      {running > 0 && <Text color="#B5D4FF">{running} {'\u25CF'}</Text>}
      {failed > 0 && <Text color="#FFB5B5">{failed} {'\u2717'}</Text>}
      <Text dimColor>({tools.length} tool calls)</Text>
    </Box>
  );
}
