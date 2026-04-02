#!/usr/bin/env node
/**
 * Status line — pearl Aussie Agents indicator with live counts.
 * Adapts to light/dark terminal backgrounds.
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const root = path.resolve(__dirname, '..', '..');

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
  ? { diamond: [160, 120, 40], name: [60, 50, 70], tools: [30, 130, 90], jmem: [40, 90, 180], mem: [100, 70, 160], q: [160, 120, 40], branch: [40, 110, 140], dot: [160, 150, 170] }
  : { diamond: [232, 213, 183], name: [248, 248, 255], tools: [168, 230, 207], jmem: [181, 212, 255], mem: [230, 230, 250], q: [232, 213, 183], branch: [181, 212, 255], dot: [212, 212, 216] };

const dot = rgb(...c.dot, '\u00b7');

// Dynamic tool count — Python + TS + MCP + native
let toolCount = 92;
try {
  let pyTools = 0;
  const coreDir = path.join(root, 'agent_setup_cli/core');
  for (const f of fs.readdirSync(coreDir)) {
    if (f.endsWith('.py')) {
      const content = fs.readFileSync(path.join(coreDir, f), 'utf8');
      const matches = content.match(/def tool_/g);
      if (matches) pyTools += matches.length;
    }
  }
  const tsTools = fs.readdirSync(path.join(root, 'src/tools')).filter(f => f.endsWith('.ts')).length;
  toolCount = pyTools + tsTools + 13 + 8;
} catch {}

// JMEM memory count — try daemon first
let memCount = '';
try {
  const { jmemRequest } = require('./jmem-client.cjs');
  const daemonResult = jmemRequest('status', {});
  if (daemonResult && daemonResult.total_memories != null) {
    memCount = `${daemonResult.total_memories}m`;
  } else {
    // Fallback to sqlite3
    const dbPath = path.join(require('os').homedir(), '.jmem/claude-code/memory.db');
    if (fs.existsSync(dbPath)) {
      const out = execFileSync(
        'sqlite3', [dbPath, "SELECT COUNT(*) FROM documents;"],
        { timeout: 1500, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
      ).trim();
      const n = parseInt(out);
      if (n > 0) memCount = `${n}m`;
    }
  }
} catch {}

// Git branch
let branch = '';
try {
  branch = execFileSync(
    'git', ['rev-parse', '--abbrev-ref', 'HEAD'],
    { cwd: root, timeout: 1500, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
  ).trim();
} catch {}

// Build statusline
const parts = [
  `${rgb(...c.diamond, B + '\u25c6')}`,
  `${rgb(...c.name, 'Aussie')}`,
  dot,
  `${rgb(...c.tools, toolCount + 't')}`,
  dot,
  `${rgb(...c.jmem, 'JMEM')} ${rgb(...c.mem, '6L')}`,
];

if (memCount) {
  parts.push(dot, `${rgb(...c.mem, memCount)}`);
}

parts.push(dot, `${rgb(...c.q, 'Q\u03b1')}`);

if (branch) {
  parts.push(dot, `${rgb(...c.branch, branch)}`);
}

process.stdout.write(parts.join(' '));
