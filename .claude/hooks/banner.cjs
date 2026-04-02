#!/usr/bin/env node
/**
 * SessionStart banner — pearl Aussie Agents startup display.
 * Dynamic counts from settings.json + JMEM stats + git branch.
 * Adapts to light/dark terminal backgrounds via COLORFGBG detection.
 */

const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const root = path.resolve(__dirname, '..', '..');

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

// ── Dynamic counts ────────────────────────────────────────
function getCounts() {
  let tools = 0, agents = 0, skills = 0, hooks = 0, mcp = 0;
  try {
    const settings = JSON.parse(fs.readFileSync(path.join(root, '.claude/settings.json'), 'utf8'));

    try {
      agents = fs.readdirSync(path.join(root, '.claude/agents')).filter(f => f.endsWith('.md')).length;
    } catch { agents = 10; }

    try {
      skills = fs.readdirSync(path.join(root, '.claude/skills')).filter(d => {
        try { return fs.statSync(path.join(root, '.claude/skills', d)).isDirectory(); } catch { return false; }
      }).length;
    } catch { skills = 27; }

    const hookTypes = settings.hooks || {};
    hooks = Object.keys(hookTypes).length;

    const mcpServers = settings.mcpServers || {};
    mcp = Object.keys(mcpServers).length;

    // Tools = skills + MCP tools (13 JMEM) + 8 native
    tools = skills + 13 + 8;
  } catch {
    tools = 44; agents = 10; skills = 27; hooks = 7; mcp = 1;
  }
  return { tools, agents, skills, hooks, mcp };
}

// ── JMEM stats ────────────────────────────────────────────
function getJmemStats() {
  try {
    const dbPath = path.join(require('os').homedir(), '.jmem/claude-code/memory.db');
    if (!fs.existsSync(dbPath)) return { memories: 0, avgQ: 0 };
    const out = execFileSync(
      'sqlite3', [dbPath, 'SELECT COUNT(*), ROUND(AVG(q_value),2) FROM memories;'],
      { timeout: 2000, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    ).trim();
    const [count, avgQ] = out.split('|');
    return { memories: parseInt(count) || 0, avgQ: parseFloat(avgQ) || 0 };
  } catch {
    return { memories: 0, avgQ: 0 };
  }
}

// ── Git branch ────────────────────────────────────────────
function getGitBranch() {
  try {
    return execFileSync(
      'git', ['rev-parse', '--abbrev-ref', 'HEAD'],
      { cwd: root, timeout: 2000, encoding: 'utf8', stdio: ['pipe', 'pipe', 'pipe'] }
    ).trim();
  } catch { return ''; }
}

// ── Cortex state ──────────────────────────────────────────
function getCortexState() {
  try {
    const state = JSON.parse(fs.readFileSync(path.join(root, '.claude/hooks/cortex_state.json'), 'utf8'));
    const pressure = state.pressure || 0;
    const sessions = state.episodes_this_session || 0;
    const lastDream = state.last_dream_at || 0;
    let dreamAgo = '';
    if (lastDream > 0) {
      const hours = ((Date.now() / 1000) - lastDream) / 3600;
      dreamAgo = hours < 1 ? `${Math.round(hours * 60)}m` : `${Math.round(hours)}h`;
    }
    return { pressure: pressure.toFixed(1), sessions, dreamAgo };
  } catch {
    return { pressure: '0.0', sessions: 0, dreamAgo: '' };
  }
}

// ── Gradient helpers ──────────────────────────────────────
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

// ── Build banner ──────────────────────────────────────────
const title = light
  ? gradient('AUSSIE AGENTS', [
      [100, 60, 120], [160, 50, 80], [90, 80, 160],
      [40, 110, 140], [140, 100, 40], [80, 70, 130],
    ])
  : gradient('AUSSIE AGENTS', [
      [255, 255, 255], [255, 228, 225], [230, 230, 250],
      [224, 247, 250], [255, 248, 225], [248, 248, 255],
    ]);

const line = light
  ? gradientLine('━', 60, [180, 170, 190], [140, 130, 160])
  : gradientLine('━', 60, [212, 212, 216], [192, 192, 192]);

const pill = (label, value, color) => {
  const [r, g, b] = color;
  return `${rgb(r, g, b, B + value)} ${rgb(r, g, b, label)}`;
};

const c = light
  ? {
      tools:  [30, 130, 90],   mcp:    [40, 90, 180],
      memory: [100, 70, 160],  hooks:  [180, 60, 70],
      agents: [160, 120, 40],  branch: [40, 110, 140],
      jmem:   [100, 70, 160],  cortex: [160, 50, 80],
      dot:    [160, 150, 170], hint:   [120, 110, 130],
    }
  : {
      tools:  [168, 230, 207], mcp:    [181, 212, 255],
      memory: [230, 230, 250], hooks:  [255, 228, 225],
      agents: [232, 213, 183], branch: [181, 212, 255],
      jmem:   [230, 230, 250], cortex: [255, 228, 225],
      dot:    [212, 212, 216], hint:   [142, 142, 147],
    };

const dot = `${rgb(...c.dot, '\u00b7')}`;

// Gather dynamic data
const counts = getCounts();
const jmem = getJmemStats();
const branch = getGitBranch();
const cortex = getCortexState();

// Line 1: core stats (dynamic counts)
const statsLine = [
  pill('tools', String(counts.tools), c.tools),
  pill('mcp', String(counts.mcp), c.mcp),
  pill('memory', '6L', c.memory),
  pill('hooks', String(counts.hooks), c.hooks),
  pill('agents', String(counts.agents), c.agents),
].join(`  ${dot}  `);

// Line 2: JMEM health + cortex + git branch
const detailParts = [];
if (jmem.memories > 0) {
  detailParts.push(rgb(...c.jmem, `JMEM: ${jmem.memories} memories`));
  detailParts.push(rgb(...c.jmem, `Q\u0304=${jmem.avgQ}`));
}
if (cortex.pressure !== '0.0') {
  detailParts.push(rgb(...c.cortex, `P:${cortex.pressure}`));
}
if (cortex.dreamAgo) {
  detailParts.push(rgb(...c.cortex, `dream:${cortex.dreamAgo} ago`));
}
if (cortex.sessions > 0) {
  detailParts.push(rgb(...c.cortex, `S#${cortex.sessions}`));
}
if (branch) {
  detailParts.push(rgb(...c.branch, `\u2387 ${branch}`));
}

const detailLine = detailParts.length > 0 ? detailParts.join(`  ${dot}  `) : '';

const hint = `${DIM}${ITALIC}${rgb(...c.hint, '/aussie-  for commands')}${R}`;

const parts = ['', `  ${title}`, `  ${line}`, `  ${statsLine}`];
if (detailLine) parts.push(`  ${detailLine}`);
parts.push(`  ${hint}`, '');

process.stdout.write(JSON.stringify({ systemMessage: parts.join('\n') }));
