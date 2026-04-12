#!/usr/bin/env node
/**
 * PostToolUse hook — console.log detection after Write/Edit.
 *
 * Reads the tool input JSON from stdin, checks if the edited file
 * is a .ts/.tsx file (excluding test/spec files), and warns if
 * console.log statements are found in the written/edited content.
 *
 * Environment:
 *   ECC_HOOK_PROFILE=off  — skip this hook entirely
 */

'use strict';

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

    // Only check TypeScript files that are NOT test/spec files
    if (!filePath.match(/\.(ts|tsx)$/)) return;
    if (filePath.match(/\.(test|spec)\./)) return;

    // Extract the content that was written or edited
    const content = inp.tool_result?.content
      || inp.tool_input?.new_string
      || inp.tool_input?.content
      || '';

    // Count non-comment console.log statements
    const lines = content.split('\n');
    const hits = lines.filter(line => {
      const trimmed = line.trim();
      return /console\.log/.test(trimmed)
        && !trimmed.startsWith('//')
        && !trimmed.startsWith('*');
    }).length;

    if (hits > 0) {
      process.stdout.write(JSON.stringify({
        systemMessage: `Warning: ${hits} console.log statement(s) in ${filePath} (not in test file)`
      }));
    }
  } catch {
    // Malformed input — silently ignore
  }
});
