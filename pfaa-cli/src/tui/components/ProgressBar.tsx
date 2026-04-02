/**
 * PFAA ProgressBar — Pearl shimmer gradient fill
 */

import React from 'react';
import { Box, Text } from 'ink';
import { theme } from '../theme.js';

interface ProgressBarProps {
  value: number;      // 0-1
  width?: number;
  label?: string;
  showPercent?: boolean;
}

export function ProgressBar({ value, width = 30, label, showPercent = true }: ProgressBarProps) {
  const clamped = Math.max(0, Math.min(1, value));
  const filled = Math.round(clamped * width);
  const empty = width - filled;

  // Pearl shimmer gradient: silver → white → soft rose → lavender → white
  let bar = '';
  for (let i = 0; i < filled; i++) {
    const t = filled > 1 ? i / (filled - 1) : 0;
    // Iridescent: silver(192,192,192) → white(248,248,255) → rose(255,228,225) → lavender(230,230,250) → white
    const phase = t * 3;
    let r: number, g: number, b: number;
    if (phase < 1) {
      const f = phase;
      r = Math.round(192 + (248 - 192) * f);
      g = Math.round(192 + (248 - 192) * f);
      b = Math.round(192 + (255 - 192) * f);
    } else if (phase < 2) {
      const f = phase - 1;
      r = Math.round(248 + (255 - 248) * f);
      g = Math.round(248 + (228 - 248) * f);
      b = Math.round(255 + (225 - 255) * f);
    } else {
      const f = phase - 2;
      r = Math.round(255 + (230 - 255) * f);
      g = Math.round(228 + (230 - 228) * f);
      b = Math.round(225 + (250 - 225) * f);
    }
    bar += `\x1b[38;2;${r};${g};${b}m█`;
  }
  bar += '\x1b[0m';

  const emptyBar = theme.dim('░'.repeat(empty));
  const pct = showPercent ? theme.bright(` ${Math.round(clamped * 100)}%`) : '';

  return (
    <Box gap={1}>
      {label && <Text>{theme.muted(label)}</Text>}
      <Text>{bar}{emptyBar}{pct}</Text>
    </Box>
  );
}

/** Pipeline progress — shows step-by-step completion */
interface PipelineProgressProps {
  steps: Array<{ name: string; status: 'pending' | 'running' | 'completed' | 'failed' }>;
}

export function PipelineProgress({ steps }: PipelineProgressProps) {
  return (
    <Box flexDirection="column" paddingLeft={2}>
      {steps.map((step, i) => {
        const icon = {
          pending:   theme.dim('○'),
          running:   theme.info('◉'),
          completed: theme.success('●'),
          failed:    theme.error('●'),
        }[step.status];

        const connector = i < steps.length - 1
          ? (step.status === 'completed' ? theme.success('│') : theme.dim('│'))
          : '';

        const nameColor = {
          pending:   theme.dim,
          running:   theme.info,
          completed: theme.text,
          failed:    theme.error,
        }[step.status];

        return (
          <Box key={i} flexDirection="column">
            <Text>{icon} {nameColor(step.name)}</Text>
            {connector && <Text>  {connector}</Text>}
          </Box>
        );
      })}
    </Box>
  );
}
