#!/usr/bin/env node
/**
 * SessionStart banner — pearl Aussie Agents startup display.
 * Adapts to light/dark terminal backgrounds via COLORFGBG detection.
 */

const R = '\x1b[0m';
const B = '\x1b[1m';
const DIM = '\x1b[2m';
const ITALIC = '\x1b[3m';

const rgb = (r, g, b, s) => `\x1b[38;2;${r};${g};${b}m${s}${R}`;

// ── Light/dark detection ──────────────────────────────────
function isLightBg() {
  const cfg = process.env.COLORFGBG;
  if (cfg) {
    const parts = cfg.split(';');
    const bg = parseInt(parts[parts.length - 1], 10);
    if (!isNaN(bg) && bg >= 8) return true;
  }
  const vsc = process.env.VSCODE_THEME_KIND;
  if (vsc === 'vscode-light' || vsc === 'vscode-high-contrast-light') return true;
  if ((process.env.ITERM_PROFILE || '').toLowerCase().includes('light')) return true;
  return false;
}

const light = isLightBg();

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

// ── Build banner — adaptive pearl ─────────────────────────
const title = light
  ? gradient('AUSSIE AGENTS', [
      [100, 60, 120],    // deep plum
      [160, 50, 80],     // rose
      [90, 80, 160],     // purple
      [40, 110, 140],    // teal
      [140, 100, 40],    // amber
      [80, 70, 130],     // indigo
    ])
  : gradient('AUSSIE AGENTS', [
      [255, 255, 255],   // pure white
      [255, 228, 225],   // misty rose
      [230, 230, 250],   // lavender
      [224, 247, 250],   // light cyan
      [255, 248, 225],   // lemon chiffon
      [248, 248, 255],   // ghost white
    ]);

const line = light
  ? gradientLine('━', 52, [180, 170, 190], [140, 130, 160])
  : gradientLine('━', 52, [212, 212, 216], [192, 192, 192]);

// Stats — pill badges with adaptive colors
const pill = (label, value, color) => {
  const [r, g, b] = color;
  return `${rgb(r, g, b, B + value)} ${rgb(r, g, b, label)}`;
};

// Light mode: deeper, saturated versions; dark mode: soft pastels
const colors = light
  ? {
      tools:  [30, 130, 90],     // deep mint
      mcp:    [40, 90, 180],     // rich blue
      memory: [100, 70, 160],    // deep lavender
      hooks:  [180, 60, 70],     // deep rose
      agents: [160, 120, 40],    // deep amber
      dot:    [160, 150, 170],   // warm gray
      hint:   [120, 110, 130],   // muted plum
    }
  : {
      tools:  [168, 230, 207],   // soft mint
      mcp:    [181, 212, 255],   // soft sky
      memory: [230, 230, 250],   // soft lavender
      hooks:  [255, 228, 225],   // soft rose
      agents: [232, 213, 183],   // soft shimmer
      dot:    [212, 212, 216],   // silver
      hint:   [142, 142, 147],   // muted
    };

const dot = `${rgb(...colors.dot, '\u00b7')}`;

const stats = [
  pill('tools', '44', colors.tools),
  pill('mcp',   '17', colors.mcp),
  pill('memory', '6L', colors.memory),
  pill('hooks',  '7',  colors.hooks),
  pill('agents','10', colors.agents),
].join(`  ${dot}  `);

const hint = `${DIM}${ITALIC}${rgb(...colors.hint, '/aussie-  for commands')}${R}`;

const banner = [
  '',
  `  ${title}`,
  `  ${line}`,
  `  ${stats}`,
  `  ${hint}`,
  '',
].join('\n');

process.stdout.write(JSON.stringify({ systemMessage: banner }));
