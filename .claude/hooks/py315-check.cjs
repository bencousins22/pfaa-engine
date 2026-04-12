#!/usr/bin/env node
/**
 * PostToolUse hook — Python 3.15 suggestions after Write/Edit.
 *
 * Reads the tool input JSON from stdin, checks if the edited file
 * is a .py file, then reads the file from disk and suggests modern
 * Python 3.15 patterns:
 *
 *   - PEP 810: lazy imports for heavy modules (numpy, pandas, torch, etc.)
 *   - PEP 814: frozendict for UPPER_CASE dict constants
 *   - PEP 695: type parameter syntax (def func[T]() instead of TypeVar)
 *
 * Environment:
 *   ECC_HOOK_PROFILE=off  — skip this hook entirely
 */

'use strict';

const fs = require('fs');

// ── Early exit if hooks are disabled ─────────────────────
if (process.env.ECC_HOOK_PROFILE === 'off') {
  process.exit(0);
}

// ── Heavy modules that benefit from lazy imports ─────────
const HEAVY_MODULES = [
  'numpy', 'pandas', 'torch', 'tensorflow',
  'requests', 'httpx', 'sqlalchemy',
  'flask', 'fastapi', 'django',
  'pydantic', 'scipy', 'matplotlib',
  'boto3', 'celery',
];

// ── Read stdin (tool input JSON) ─────────────────────────
let data = '';
process.stdin.on('data', chunk => { data += chunk; });
process.stdin.on('end', () => {
  try {
    const inp = JSON.parse(data);
    const filePath = inp.tool_input?.file_path || '';

    // Only check Python files
    if (!filePath.endsWith('.py')) return;

    // Read the file content from disk
    const content = fs.readFileSync(filePath, 'utf8');
    const suggestions = [];

    // ── PEP 810: lazy imports for heavy modules ──────────
    if (content.includes('import ') && !content.includes('lazy import')) {
      const lines = content.split('\n');
      for (const line of lines) {
        const match = line.match(/^import\s+(\w+)/);
        if (match && HEAVY_MODULES.includes(match[1])) {
          suggestions.push('PEP 810: ' + line.trim() + ' → lazy ' + line.trim());
        }
      }
    }

    // ── PEP 814: frozendict for UPPER_CASE dict literals ─
    if (content.match(/^[A-Z_]+\s*=\s*\{/m) && !content.includes('frozendict')) {
      suggestions.push('PEP 814: UPPER_CASE dict could use frozendict');
    }

    // ── PEP 695: type parameter syntax ───────────────────
    if (content.includes('def ') && content.includes('TypeVar') && !content.match(/def\s+\w+\[/)) {
      suggestions.push('PEP 695: Use def func[T]() type param syntax');
    }

    // ── Output suggestions if any ────────────────────────
    if (suggestions.length > 0) {
      process.stdout.write(JSON.stringify({
        systemMessage: 'Py3.15: ' + suggestions.join('; ')
      }));
    }
  } catch {
    // Read failure or malformed input — silently ignore
  }
});
