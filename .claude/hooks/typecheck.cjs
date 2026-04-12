#!/usr/bin/env node
/**
 * PostToolUse hook — TypeScript type-check after Write/Edit.
 *
 * Reads the tool input JSON from stdin, checks if the edited file
 * is a .ts or .tsx file, and runs `npx tsc --noEmit` to report errors.
 *
 * Environment:
 *   ECC_HOOK_PROFILE=off  — skip this hook entirely
 *
 * Expects CWD to be pfaa-cli/ (set via settings.json command prefix).
 */

'use strict';

const { execSync } = require('child_process');

// ── Early exit if hooks are disabled ─────────────────────
if (process.env.ECC_HOOK_PROFILE === 'off') {
  process.exit(0);
}

// ── Read stdin (tool input JSON) ─────────────────────────
let data = '';
process.stdin.on('data', chunk => { data += chunk; });
process.stdin.on('end', () => {
  try {
    const inp = JSON.parse(data);
    const filePath = inp.tool_input?.file_path || '';

    // Only run on TypeScript files
    if (!filePath.match(/\.(ts|tsx)$/)) {
      return;
    }

    // Run tsc --noEmit and report result
    try {
      execSync('npx tsc --noEmit 2>&1', { timeout: 15000 });
      process.stdout.write(JSON.stringify({
        systemMessage: 'TypeScript: OK'
      }));
    } catch (_e) {
      process.stdout.write(JSON.stringify({
        systemMessage: 'TypeScript errors found — check with: npx tsc --noEmit'
      }));
    }
  } catch {
    // Malformed input — silently ignore
  }
});
