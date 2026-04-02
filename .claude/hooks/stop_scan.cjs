#!/usr/bin/env node
/**
 * Stop hook — scan for unregistered skills/agents & Py3.15 features.
 */

const fs = require('fs');
const path = require('path');

const R = '\x1b[0m';
const B = '\x1b[1m';
const DIM = '\x1b[2m';
const rgb = (r, g, b, s) => `\x1b[38;2;${r};${g};${b}m${s}${R}`;

// Light/dark detection
const _cfg = process.env.COLORFGBG || '';
const _vsc = process.env.VSCODE_THEME_KIND || '';
const _iterm = (process.env.ITERM_PROFILE || '').toLowerCase();
const L = (_cfg && parseInt(_cfg.split(';').pop(), 10) >= 8)
  || _vsc === 'vscode-light' || _vsc === 'vscode-high-contrast-light'
  || _iterm.includes('light');

const mint = L ? s => rgb(30, 130, 90, s) : s => rgb(168, 230, 207, s);
const shimmer = L ? s => rgb(160, 120, 40, s) : s => rgb(232, 213, 183, s);
const iris = L ? s => rgb(100, 70, 160, s) : s => rgb(230, 230, 250, s);
const dot = L ? `${rgb(160, 150, 170, '\u00b7')}` : `${rgb(212, 212, 216, '\u00b7')}`;

const root = '/Users/borris/Desktop/pfaa-engine';

try {
  let newSkills = 0, newAgents = 0, pyFeatures = [];

  const settings = JSON.parse(fs.readFileSync(path.join(root, '.claude/settings.json'), 'utf8'));
  const skillDirs = fs.readdirSync(path.join(root, '.claude/skills'))
    .filter(d => {
      try { return fs.statSync(path.join(root, '.claude/skills', d)).isDirectory(); }
      catch { return false; }
    });
  const agentFiles = fs.readdirSync(path.join(root, '.claude/agents'))
    .filter(f => f.endsWith('.md'));

  const regSkills = Object.keys(settings.skills || {}).length;
  const regAgents = Object.keys(settings.agents || {}).length;
  if (skillDirs.length > regSkills) newSkills = skillDirs.length - regSkills;
  if (agentFiles.length > regAgents) newAgents = agentFiles.length - regAgents;

  // Py3.15 feature scan — walk recent .py files via fs only (no shell)
  const featureMap = {
    'lazy import': 'lazy_import',
    'frozendict': 'frozendict',
    'TaskGroup': 'taskgroup',
  };

  function scanDir(dir, depth) {
    if (depth > 3) return;
    try {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === 'node_modules' || entry.name === '__pycache__' || entry.name.startsWith('.')) continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) scanDir(full, depth + 1);
        else if (entry.name.endsWith('.py') && pyFeatures.length < 20) {
          try {
            const c = fs.readFileSync(full, 'utf8');
            for (const [pattern, label] of Object.entries(featureMap)) {
              if (c.includes(pattern)) pyFeatures.push(label);
            }
            if (c.includes('match ') && c.includes('case ')) pyFeatures.push('match_case');
            if (c.includes('def ') && c.includes('TypeVar') && !c.match(/def\s+\w+\[/)) pyFeatures.push('pep695');
          } catch {}
        }
      }
    } catch {}
  }
  scanDir(root, 0);

  const uniq = [...new Set(pyFeatures)];

  let parts = [mint(`${B}\u2713${R} `) + mint('ready')];
  if (newSkills > 0) parts.push(shimmer(`+${newSkills} skill${newSkills > 1 ? 's' : ''}`));
  if (newAgents > 0) parts.push(shimmer(`+${newAgents} agent${newAgents > 1 ? 's' : ''}`));
  if (uniq.length > 0) parts.push(iris(`py3.15: ${uniq.join(', ')}`));

  // Silent — work done, no output to avoid UI clutter
} catch (e) {
  // Silent
}
