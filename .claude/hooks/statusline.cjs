#!/usr/bin/env node
/**
 * Status line — pearl Aussie Agents indicator.
 * Adapts to light/dark terminal backgrounds.
 */

const R = '\x1b[0m';
const B = '\x1b[1m';

const rgb = (r, g, b, s) => `\x1b[38;2;${r};${g};${b}m${s}${R}`;

// Light/dark detection
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

const L = isLightBg();

const c = L
  ? { diamond: [160, 120, 40], name: [60, 50, 70], tools: [30, 130, 90], jmem: [40, 90, 180], mem: [100, 70, 160], q: [160, 120, 40], dot: [160, 150, 170] }
  : { diamond: [232, 213, 183], name: [248, 248, 255], tools: [168, 230, 207], jmem: [181, 212, 255], mem: [230, 230, 250], q: [232, 213, 183], dot: [212, 212, 216] };

const dot = rgb(...c.dot, '\u00b7');

process.stdout.write(
  `${rgb(...c.diamond, B + '\u25c6')} ${rgb(...c.name, 'Aussie')} ${dot} ${rgb(...c.tools, '44t')} ${dot} ${rgb(...c.jmem, 'JMEM')} ${rgb(...c.mem, '6L')} ${dot} ${rgb(...c.q, 'Q\u03b1')}`
);
