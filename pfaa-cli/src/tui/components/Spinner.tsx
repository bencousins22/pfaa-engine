/**
 * PFAA Spinner — Animated loading indicator with label
 * Only active when visible (doesn't trigger global re-renders when unused)
 */

import React, { useState, useEffect } from 'react';
import { Text } from 'ink';

const DOTS = ['\u280B', '\u2819', '\u2839', '\u2838', '\u283C', '\u2834', '\u2826', '\u2827', '\u2807', '\u280F'];
const FRAMES = ['\u25D0', '\u25D3', '\u25D1', '\u25D2'];

interface SpinnerProps {
  label?: string;
  type?: 'dots' | 'circle';
  color?: string;
}

export function Spinner({ label, type = 'dots', color = '#E8D5B7' }: SpinnerProps) {
  const [frame, setFrame] = useState(0);
  const frames = type === 'circle' ? FRAMES : DOTS;

  useEffect(() => {
    const interval = setInterval(() => {
      setFrame(f => (f + 1) % frames.length);
    }, 100);
    return () => clearInterval(interval);
  }, [frames.length]);

  return (
    <Text>
      <Text color={color}>{frames[frame]}</Text>
      {label ? <Text dimColor> {label}</Text> : null}
    </Text>
  );
}

/**
 * StreamingDots — Animated ellipsis that cycles through ., .., ...
 * Used to indicate ongoing streaming activity.
 */
export function StreamingDots({ color = '#D4D4D8' }: { color?: string }) {
  const [count, setCount] = useState(1);

  useEffect(() => {
    const interval = setInterval(() => {
      setCount(c => (c % 3) + 1);
    }, 400);
    return () => clearInterval(interval);
  }, []);

  return <Text color={color}>{'.'.repeat(count)}{' '.repeat(3 - count)}</Text>;
}
