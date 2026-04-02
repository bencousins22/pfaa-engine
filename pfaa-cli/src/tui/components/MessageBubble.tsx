/**
 * PFAA MessageBubble — Renders a single message with role-based styling
 */

import React from 'react';
import { Box, Text } from 'ink';
import { Spinner } from './Spinner.js';
import { ToolCallBlock } from './ToolCallBlock.js';
import type { Message } from '../context.js';

interface MessageBubbleProps {
  message: Message;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const { role, content, streaming, toolCalls, agentRole } = message;

  if (role === 'user') {
    return (
      <Box flexDirection="column" marginY={0} paddingLeft={1}>
        <Box gap={1}>
          <Text color="#E8D5B7" bold>▸ You</Text>
        </Box>
        <Box paddingLeft={3}>
          <Text>{content}</Text>
        </Box>
      </Box>
    );
  }

  if (role === 'system') {
    // Skip sentinel values rendered elsewhere (e.g. HelpPanel)
    if (content.startsWith('__') && content.endsWith('__')) return null;
    return (
      <Box paddingLeft={2} marginY={0} flexDirection="column">
        <MarkdownText text={content} />
      </Box>
    );
  }

  if (role === 'assistant') {
    return (
      <Box flexDirection="column" marginY={0} paddingLeft={1}>
        {/* Header */}
        <Box gap={1}>
          <Text color="#F8F8FF" bold>◆ PFAA</Text>
          {agentRole && <Text dimColor>[{agentRole}]</Text>}
          {streaming && <Spinner type="dots" label="thinking" />}
        </Box>

        {/* Tool calls */}
        {toolCalls && toolCalls.length > 0 && (
          <Box flexDirection="column" marginY={0}>
            {toolCalls.map(tc => (
              <ToolCallBlock key={tc.id} tool={tc} />
            ))}
          </Box>
        )}

        {/* Content */}
        {content && (
          <Box paddingLeft={3} flexDirection="column">
            <MarkdownText text={content} />
          </Box>
        )}

        {/* Streaming cursor */}
        {streaming && !content && (
          <Box paddingLeft={3}>
            <Text color="#F8F8FF">▌</Text>
          </Box>
        )}
      </Box>
    );
  }

  return (
    <Box paddingLeft={2}>
      <Text dimColor>{content}</Text>
    </Box>
  );
}

/**
 * Simple terminal markdown rendering using Ink <Text> color props
 */
function MarkdownText({ text }: { text: string }) {
  const lines = text.split('\n');
  const rendered: React.ReactNode[] = [];

  let inCodeBlock = false;
  let codeBuffer: string[] = [];
  let codeLang = '';

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Code block toggle
    if (line.startsWith('```')) {
      if (!inCodeBlock) {
        inCodeBlock = true;
        codeLang = line.slice(3).trim();
        codeBuffer = [];
        continue;
      } else {
        inCodeBlock = false;
        rendered.push(
          <Box key={`code-${i}`} flexDirection="column" borderStyle="round" borderColor="#D4D4D8" paddingX={1} marginY={0}>
            {codeLang && <Text dimColor>  {codeLang}</Text>}
            {codeBuffer.map((cl, j) => (
              <Text key={`cl-${i}-${j}`} color="#F8F8FF">{cl}</Text>
            ))}
          </Box>
        );
        continue;
      }
    }

    if (inCodeBlock) {
      codeBuffer.push(line);
      continue;
    }

    // Headers
    if (line.startsWith('### ')) {
      rendered.push(<Text key={`h3-${i}`} color="#E8D5B7" bold>{line.slice(4)}</Text>);
      continue;
    }
    if (line.startsWith('## ')) {
      rendered.push(<Text key={`h2-${i}`} color="#FFFFFF" bold>{line.slice(3)}</Text>);
      continue;
    }
    if (line.startsWith('# ')) {
      rendered.push(<Text key={`h1-${i}`} color="#FFFFFF" bold underline>{line.slice(2)}</Text>);
      continue;
    }

    // List items
    if (line.match(/^\s*[-*]\s/)) {
      const content_ = line.replace(/^\s*[-*]\s/, '');
      rendered.push(
        <Text key={`li-${i}`}>  <Text color="#F8F8FF">•</Text> {content_}</Text>
      );
      continue;
    }

    // Numbered list
    if (line.match(/^\s*\d+\.\s/)) {
      const match = line.match(/^(\s*)(\d+)\.\s(.*)/);
      if (match) {
        rendered.push(
          <Text key={`ol-${i}`}>  <Text color="#E8D5B7">{match[2]}.</Text> {match[3]}</Text>
        );
        continue;
      }
    }

    // Horizontal rule
    if (line.match(/^---+$/)) {
      rendered.push(<Text key={`hr-${i}`} dimColor>{'─'.repeat(40)}</Text>);
      continue;
    }

    // Blockquote
    if (line.startsWith('> ')) {
      rendered.push(
        <Text key={`bq-${i}`} dimColor>  │ <Text italic>{line.slice(2)}</Text></Text>
      );
      continue;
    }

    // Empty line
    if (!line.trim()) {
      rendered.push(<Text key={`empty-${i}`}> </Text>);
      continue;
    }

    // Normal text — apply inline formatting
    rendered.push(<Text key={`txt-${i}`}>{line}</Text>);
  }

  return <>{rendered}</>;
}
