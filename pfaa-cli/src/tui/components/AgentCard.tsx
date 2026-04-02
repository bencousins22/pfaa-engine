/**
 * PFAA AgentCard — Pearl glossy agent status card
 */

import React from 'react';
import { Box, Text } from 'ink';
import { theme } from '../theme.js';
import { Spinner } from './Spinner.js';

interface AgentCardProps {
  name: string;
  role: string;
  phase: string;
  status: 'idle' | 'running' | 'completed' | 'failed';
  task?: string;
  elapsedMs?: number;
}

export function AgentCard({ name, role, phase, status, task, elapsedMs }: AgentCardProps) {
  const phaseColor = theme.phase[phase] ?? theme.info;
  const borderColor = {
    idle:      '#D4D4D8',
    running:   '#B5D4FF',
    completed: '#A8E6CF',
    failed:    '#FFB5B5',
  }[status];

  const statusIcon = {
    idle:      theme.dim('◇'),
    running:   '',
    completed: theme.success('◆'),
    failed:    theme.error('◆'),
  }[status];

  return (
    <Box
      borderStyle="round"
      borderColor={borderColor}
      paddingX={1}
      flexDirection="column"
      width={36}
    >
      <Box justifyContent="space-between">
        <Box gap={1}>
          {status === 'running' ? <Spinner type="circle" /> : <Text>{statusIcon}</Text>}
          <Text>{theme.bright.bold(name)}</Text>
        </Box>
        <Text>{phaseColor(`[${phase}]`)}</Text>
      </Box>

      <Text>{theme.muted(role)}</Text>

      {task && (
        <Text>{theme.dim('▸ ')}{theme.text(task.slice(0, 30))}</Text>
      )}

      {elapsedMs !== undefined && (
        <Text>{theme.dim(`  ${elapsedMs}ms`)}</Text>
      )}
    </Box>
  );
}

/** Agent swarm grid — multiple agents displayed in a grid */
export function AgentGrid({ agents }: { agents: AgentCardProps[] }) {
  // Display in rows of 3
  const rows: AgentCardProps[][] = [];
  for (let i = 0; i < agents.length; i += 3) {
    rows.push(agents.slice(i, i + 3));
  }

  return (
    <Box flexDirection="column" gap={0}>
      {rows.map((row, i) => (
        <Box key={i} gap={1}>
          {row.map((agent, j) => (
            <AgentCard key={j} {...agent} />
          ))}
        </Box>
      ))}
    </Box>
  );
}
