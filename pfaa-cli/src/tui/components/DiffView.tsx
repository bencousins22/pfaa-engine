/**
 * PFAA DiffView — Syntax-highlighted unified diff display
 */

import React from 'react';
import { Box, Text } from 'ink';
import { theme } from '../theme.js';

interface DiffViewProps {
  filename: string;
  hunks: DiffHunk[];
}

interface DiffHunk {
  header: string;
  lines: DiffLine[];
}

interface DiffLine {
  type: 'add' | 'remove' | 'context';
  content: string;
  oldLine?: number;
  newLine?: number;
}

export function DiffView({ filename, hunks }: DiffViewProps) {
  return (
    <Box flexDirection="column" borderStyle="round" borderColor="#D4D4D8" paddingX={1} marginLeft={2}>
      {/* File header */}
      <Box>
        <Text>{theme.shimmer.bold('  ')} {theme.bright(filename)}</Text>
      </Box>

      {hunks.map((hunk, i) => (
        <Box key={i} flexDirection="column">
          {/* Hunk header */}
          <Text>{theme.info(hunk.header)}</Text>

          {/* Lines */}
          {hunk.lines.map((line, j) => {
            const lineNum = line.type === 'remove'
              ? theme.dim(`${(line.oldLine ?? '').toString().padStart(4)} `)
              : line.type === 'add'
                ? theme.dim(`${(line.newLine ?? '').toString().padStart(4)} `)
                : theme.dim(`${(line.oldLine ?? '').toString().padStart(4)} `);

            if (line.type === 'add') {
              return (
                <Text key={j}>
                  {lineNum}{theme.success('+ ')}{theme.success(line.content)}
                </Text>
              );
            }
            if (line.type === 'remove') {
              return (
                <Text key={j}>
                  {lineNum}{theme.error('- ')}{theme.error(line.content)}
                </Text>
              );
            }
            return (
              <Text key={j}>
                {lineNum}{theme.dim('  ')}{theme.dim(line.content)}
              </Text>
            );
          })}
        </Box>
      ))}
    </Box>
  );
}

/** Parse a unified diff string into DiffView props */
export function parseDiff(diffStr: string): { filename: string; hunks: DiffHunk[] } {
  const lines = diffStr.split('\n');
  let filename = 'unknown';
  const hunks: DiffHunk[] = [];
  let currentHunk: DiffHunk | null = null;
  let oldLine = 0;
  let newLine = 0;

  for (const line of lines) {
    if (line.startsWith('--- ')) {
      filename = line.slice(4).replace(/^a\//, '');
      continue;
    }
    if (line.startsWith('+++ ')) {
      filename = line.slice(4).replace(/^b\//, '');
      continue;
    }
    if (line.startsWith('@@')) {
      const match = line.match(/@@ -(\d+),?\d* \+(\d+),?\d* @@(.*)/);
      oldLine = match ? parseInt(match[1]) : 0;
      newLine = match ? parseInt(match[2]) : 0;
      currentHunk = { header: line, lines: [] };
      hunks.push(currentHunk);
      continue;
    }
    if (!currentHunk) continue;

    if (line.startsWith('+')) {
      currentHunk.lines.push({ type: 'add', content: line.slice(1), newLine: newLine++ });
    } else if (line.startsWith('-')) {
      currentHunk.lines.push({ type: 'remove', content: line.slice(1), oldLine: oldLine++ });
    } else {
      currentHunk.lines.push({ type: 'context', content: line.slice(1), oldLine: oldLine++, newLine: newLine++ });
    }
  }

  return { filename, hunks };
}
