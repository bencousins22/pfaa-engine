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
const green = s => rgb(0, 230, 118, s);
const gold = s => rgb(212, 160, 23, s);
const purple = s => rgb(140, 100, 255, s);
const dot = `${DIM}\u00b7${R}`;

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

  let parts = [green(`${B}\u2713${R} `) + green('ready')];
  if (newSkills > 0) parts.push(gold(`+${newSkills} skill${newSkills > 1 ? 's' : ''}`));
  if (newAgents > 0) parts.push(gold(`+${newAgents} agent${newAgents > 1 ? 's' : ''}`));
  if (uniq.length > 0) parts.push(purple(`py3.15: ${uniq.join(', ')}`));

  process.stdout.write(JSON.stringify({ systemMessage: parts.join(` ${dot} `) }));
} catch (e) {
  process.stdout.write(JSON.stringify({ systemMessage: green('\u2713 done') }));
}
