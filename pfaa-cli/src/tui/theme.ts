/**
 * PFAA TUI Theme — Pearl White Glossy palette
 * Luminous whites, soft iridescence, ultra-smooth aesthetic
 */

import chalk from 'chalk';

export const theme = {
  // Pearl tones
  pearl:      chalk.hex('#F8F8FF'),
  pearlWarm:  chalk.hex('#FAF0E6'),
  pearlCool:  chalk.hex('#F0F0FF'),
  silver:     chalk.hex('#C0C0C0'),
  platinum:   chalk.hex('#E5E4E2'),
  ivory:      chalk.hex('#FFFFF0'),
  shimmer:    chalk.hex('#E8D5B7'),

  // Iridescent accents
  irisRose:   chalk.hex('#FFE4E1'),
  irisLav:    chalk.hex('#E6E6FA'),
  irisSky:    chalk.hex('#E0F7FA'),
  irisGold:   chalk.hex('#FFF8E1'),

  // Semantic
  success:    chalk.hex('#A8E6CF'),
  error:      chalk.hex('#FFB5B5'),
  warning:    chalk.hex('#FFE4B5'),
  info:       chalk.hex('#B5D4FF'),
  dim:        chalk.hex('#8E8E93'),
  muted:      chalk.hex('#A1A1A6'),
  text:       chalk.hex('#F8F8FF'),
  bright:     chalk.hex('#FFFFFF'),

  // Backgrounds (for chalk.bgHex)
  bg: {
    pearl:   chalk.bgHex('#F8F8FF').hex('#2C2C2E'),
    silver:  chalk.bgHex('#E5E4E2').hex('#2C2C2E'),
    error:   chalk.bgHex('#FFB5B5').hex('#2C2C2E'),
    panel:   chalk.bgHex('#1C1C1E').hex('#F8F8FF'),
    input:   chalk.bgHex('#2C2C2E').hex('#F8F8FF'),
    accent:  chalk.bgHex('#E8D5B7').hex('#2C2C2E'),
  },

  // Phase colors — soft iridescent variants
  phase: {
    VAPOR:  chalk.hex('#B5D4FF'),
    LIQUID: chalk.hex('#FFE4B5'),
    SOLID:  chalk.hex('#FFB5B5'),
  } as Record<string, ReturnType<typeof chalk.hex>>,

  // Status badge colors — pearl tones
  badge: {
    pending:   chalk.bgHex('#D4D4D8').hex('#2C2C2E'),
    running:   chalk.bgHex('#B5D4FF').hex('#2C2C2E'),
    completed: chalk.bgHex('#A8E6CF').hex('#2C2C2E'),
    failed:    chalk.bgHex('#FFB5B5').hex('#2C2C2E'),
  },

  // Box drawing characters — refined thin style
  box: {
    topLeft:     '╭',
    topRight:    '╮',
    bottomLeft:  '╰',
    bottomRight: '╯',
    horizontal:  '─',
    vertical:    '│',
    teeRight:    '├',
    teeLeft:     '┤',
    cross:       '┼',
    dot:         '·',
    bullet:      '●',
    arrow:       '▸',
    arrowDown:   '▾',
    check:       '✓',
    cross_:      '✗',
    spinner:     '◆',
    diamond:     '◇',
  },

  // Gradient stops — pearl iridescent shimmer
  gradientStops: ['#FFFFFF', '#FFE4E1', '#E6E6FA', '#E0F7FA', '#FFF8E1', '#F8F8FF', '#FFFFFF'],
} as const;

/** Create a horizontal gradient line */
export function gradientLine(width: number, stops?: readonly string[]): string {
  const colors = stops ?? ['#E5E4E2', '#F8F8FF', '#E6E6FA', '#F8F8FF', '#E5E4E2'];
  const parseHex = (h: string) => {
    const n = parseInt(h.replace('#', ''), 16);
    return [(n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF] as [number, number, number];
  };

  const parsed = colors.map(parseHex);
  let line = '';
  for (let i = 0; i < width; i++) {
    const t = i / (width - 1);
    const segLen = parsed.length - 1;
    const seg = Math.min(Math.floor(t * segLen), segLen - 1);
    const f = (t * segLen) - seg;
    const [r1, g1, b1] = parsed[seg];
    const [r2, g2, b2] = parsed[seg + 1];
    const r = Math.round(r1 + (r2 - r1) * f);
    const g = Math.round(g1 + (g2 - g1) * f);
    const b = Math.round(b1 + (b2 - b1) * f);
    line += chalk.rgb(r, g, b)('━');
  }
  return line;
}

/** Create gradient text */
export function gradientText(text: string, stops?: readonly string[]): string {
  const colors = stops ?? theme.gradientStops;
  const parseHex = (h: string) => {
    const n = parseInt(h.replace('#', ''), 16);
    return [(n >> 16) & 0xFF, (n >> 8) & 0xFF, n & 0xFF] as [number, number, number];
  };

  const parsed = colors.map(parseHex);
  let result = '';
  const chars = [...text]; // handle unicode
  for (let i = 0; i < chars.length; i++) {
    if (chars[i] === ' ') { result += ' '; continue; }
    const t = chars.length > 1 ? i / (chars.length - 1) : 0;
    const segLen = parsed.length - 1;
    const seg = Math.min(Math.floor(t * segLen), segLen - 1);
    const f = (t * segLen) - seg;
    const [r1, g1, b1] = parsed[seg];
    const [r2, g2, b2] = parsed[seg + 1];
    const r = Math.round(r1 + (r2 - r1) * f);
    const g = Math.round(g1 + (g2 - g1) * f);
    const b = Math.round(b1 + (b2 - b1) * f);
    result += chalk.rgb(r, g, b).bold(chars[i]);
  }
  return result;
}
