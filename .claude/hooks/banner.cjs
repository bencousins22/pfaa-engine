#!/usr/bin/env node
/**
 * SessionStart banner — modern, minimal Aussie Agents startup display.
 * Uses 24-bit ANSI color with smooth gradients.
 */

const R = '\x1b[0m';
const B = '\x1b[1m';
const DIM = '\x1b[2m';
const ITALIC = '\x1b[3m';

const rgb = (r, g, b, s) => `\x1b[38;2;${r};${g};${b}m${s}${R}`;
const bg = (r, g, b, s) => `\x1b[48;2;${r};${g};${b}m${s}${R}`;

// ── Gradient text ──────────────────────────────────────────
function gradient(text, stops) {
  let out = '';
  for (let i = 0; i < text.length; i++) {
    if (text[i] === ' ') { out += ' '; continue; }
    const t = text.length === 1 ? 0 : i / (text.length - 1);
    const idx = t * (stops.length - 1);
    const lo = Math.floor(idx);
    const hi = Math.min(lo + 1, stops.length - 1);
    const f = idx - lo;
    const r = Math.round(stops[lo][0] + (stops[hi][0] - stops[lo][0]) * f);
    const g = Math.round(stops[lo][1] + (stops[hi][1] - stops[lo][1]) * f);
    const b = Math.round(stops[lo][2] + (stops[hi][2] - stops[lo][2]) * f);
    out += `\x1b[1m\x1b[38;2;${r};${g};${b}m${text[i]}`;
  }
  return out + R;
}

// ── Gradient line ──────────────────────────────────────────
function gradientLine(char, len, from, to) {
  let out = '';
  for (let i = 0; i < len; i++) {
    const t = i / (len - 1);
    const r = Math.round(from[0] + (to[0] - from[0]) * t);
    const g = Math.round(from[1] + (to[1] - from[1]) * t);
    const b = Math.round(from[2] + (to[2] - from[2]) * t);
    out += `\x1b[38;2;${r};${g};${b}m${char}`;
  }
  return out + R;
}

// ── Build banner ───────────────────────────────────────────
const title = gradient('AUSSIE AGENTS', [
  [255, 180, 40],   // warm gold
  [255, 120, 50],   // orange
  [0, 220, 120],    // green
  [0, 200, 220],    // teal
  [80, 140, 255],   // blue
  [0, 230, 118],    // accent green
]);

const line = gradientLine('─', 52, [60, 60, 80], [40, 40, 55]);

// Stats with pill-style badges
const pill = (label, value, color) => {
  const [r, g, b] = color;
  return `${DIM}${rgb(r, g, b, B + value)}${DIM} ${rgb(r, g, b, label)}${R}`;
};

const stats = [
  pill('tools', '44', [0, 230, 118]),
  pill('mcp',   '17', [0, 200, 200]),
  pill('memory', '5L', [140, 100, 255]),
  pill('hooks',  '6',  [255, 100, 80]),
  pill('agents','10', [212, 160, 23]),
].join(`  ${DIM}\u00b7${R}  `);

const hint = `${DIM}${ITALIC}${rgb(80, 80, 100, '/aussie-  for commands')}${R}`;

const banner = [
  '',
  `  ${title}`,
  `  ${line}`,
  `  ${stats}`,
  `  ${hint}`,
  '',
].join('\n');

process.stdout.write(JSON.stringify({ systemMessage: banner }));
