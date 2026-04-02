/**
 * PFAA MessageList — Scrollable message history with real-time streaming
 *
 * Shows completed messages from history, plus live streaming state at the bottom:
 * - streamingText: character-by-character text with cursor
 * - streamingToolUses: live tool call blocks with status
 * - Thinking indicator when in thinking mode
 * - Tool input streaming when accumulating tool arguments
 */

import React from 'react';
import { Box, Text } from 'ink';
import { useApp } from '../context.js';
import { MessageBubble } from './MessageBubble.js';
import { StreamingToolBlock } from './ToolCallBlock.js';
import { Spinner, StreamingDots } from './Spinner.js';

export function MessageList() {
  const { state } = useApp();
  const { messages, streamingMode, streamingText, streamingToolUses } = state;

  if (messages.length === 0 && streamingMode === 'idle') {
    return (
      <Box flexDirection="column" paddingX={2} paddingY={1}>
        <Text color="#F8F8FF" bold>Welcome to PFAA Interactive Shell</Text>
        <Text> </Text>
        <Text dimColor>  Type a natural language goal or command to get started.</Text>
        <Text dimColor>  Examples:</Text>
        <Text> </Text>
        <Text>    <Text color="#E8D5B7">{'\u25B8'}</Text> "analyze this codebase for security issues"</Text>
        <Text>    <Text color="#E8D5B7">{'\u25B8'}</Text> "run benchmarks"</Text>
        <Text>    <Text color="#E8D5B7">{'\u25B8'}</Text> "status"</Text>
        <Text>    <Text color="#E8D5B7">{'\u25B8'}</Text> "team optimize the database layer"</Text>
        <Text>    <Text color="#E8D5B7">{'\u25B8'}</Text> "memory stats"</Text>
        <Text> </Text>
        <Text dimColor>  Type "help" for all commands, "exit" to quit.</Text>
        <Text dimColor>  Press Ctrl+C to interrupt.</Text>
      </Box>
    );
  }

  // Show last N messages to keep viewport manageable
  const visible = messages.slice(-30);

  const isStreaming = streamingMode !== 'idle';

  return (
    <Box flexDirection="column" paddingX={1}>
      {/* Completed messages */}
      {visible.map((msg) => (
        <Box key={msg.id} marginY={0} flexDirection="column">
          <MessageBubble message={msg} />
          <Text> </Text>
        </Box>
      ))}

      {/* Live streaming section */}
      {isStreaming && (
        <Box flexDirection="column" marginY={0} paddingLeft={1}>
          {/* Assistant header for streaming content */}
          <Box gap={1}>
            <Text color="#F8F8FF" bold>{'\u25C6'} PFAA</Text>
            {streamingMode === 'thinking' && (
              <Spinner type="dots" label="Thinking" />
            )}
          </Box>

          {/* Thinking mode: show spinner with no text yet */}
          {streamingMode === 'thinking' && !streamingText && (
            <Box paddingLeft={3}>
              <Text dimColor>Analyzing your request</Text>
              <StreamingDots color="#D4D4D8" />
            </Box>
          )}

          {/* Responding mode: show streamed text with cursor */}
          {(streamingMode === 'responding' || streamingMode === 'requesting') && streamingText && (
            <Box paddingLeft={3} flexDirection="column">
              <Text>{streamingText}<Text color="#F8F8FF">{'\u258C'}</Text></Text>
            </Box>
          )}

          {/* Thinking mode with partial text */}
          {streamingMode === 'thinking' && streamingText && (
            <Box paddingLeft={3} flexDirection="column">
              <Text dimColor>{streamingText}</Text>
            </Box>
          )}

          {/* Responding with no text yet — show cursor */}
          {streamingMode === 'responding' && !streamingText && (
            <Box paddingLeft={3}>
              <Text color="#F8F8FF">{'\u258C'}</Text>
            </Box>
          )}

          {/* Tool input mode: show tool name + accumulating input */}
          {streamingMode === 'tool-input' && (
            <Box paddingLeft={3} flexDirection="column">
              {streamingText && (
                <Box flexDirection="column">
                  <Text>{streamingText}</Text>
                </Box>
              )}
            </Box>
          )}

          {/* Tool executing mode */}
          {streamingMode === 'tool-use' && streamingText && (
            <Box paddingLeft={3} flexDirection="column">
              <Text>{streamingText}</Text>
            </Box>
          )}

          {/* Live streaming tool use blocks */}
          {streamingToolUses.length > 0 && (
            <Box flexDirection="column" marginY={0}>
              {streamingToolUses.map((toolUse) => (
                <StreamingToolBlock key={toolUse.id} tool={toolUse} />
              ))}
            </Box>
          )}
        </Box>
      )}
    </Box>
  );
}
