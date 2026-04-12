/**
 * Secret Detection Cache — avoids rescanning identical commands.
 *
 * Maintains a Set of previously-seen command hashes. Only performs the
 * full pattern scan when a command hash is new. Returns the scan result
 * (blocking decision or null) so the calling hook can act on it.
 *
 * Usage from another hook or inline script:
 *
 *   const { checkCommand } = require('./.claude/hooks/secret-cache.cjs');
 *   const result = checkCommand(commandString);
 *   // result is null (safe) or { decision: 'block', reason: '...' }
 *
 * The cache persists for the lifetime of the Node process. Because
 * Claude Code hooks run as short-lived processes, a file-backed cache
 * (~/.pfaa/secret-scan-cache.json) is also maintained so repeated
 * sessions benefit from prior scans.
 */

'use strict';

const crypto = require('crypto');
const fs = require('fs');
const os = require('os');
const path = require('path');

// -- Secret patterns to detect -------------------------------------------
// Patterns are base64-encoded to prevent this file itself from triggering
// the secret detection hook. They are decoded at runtime.

const _ENCODED_PATTERNS = [
  'c2stYW50LQ==',
  'c2stcHJvai0=',
  'Z2hwXw==',
  'Z2hzXw==',
  'Z2hvXw==',
  'QUtJQQ==',
  'QUl6YQ==',
  'eG94Yi0=',
  'eG94cC0=',
  'cGF0Xw==',
  'cGFzc3dvcmQ9',
  'c2VjcmV0PQ==',
  'YXBpX2tleT0=',
  'YXBpa2V5PQ==',
  'dG9rZW49',
  'bW9uZ29kYjovLw==',
  'cG9zdGdyZXM6Ly8=',
  'bXlzcWw6Ly8=',
];

const SECRET_PATTERNS = _ENCODED_PATTERNS.map(
  (b) => Buffer.from(b, 'base64').toString('utf8')
);

// -- File-backed cache ---------------------------------------------------

const CACHE_DIR = path.join(os.homedir(), '.pfaa');
const CACHE_FILE = path.join(CACHE_DIR, 'secret-scan-cache.json');
const MAX_CACHE_SIZE = 10000; // Prevent unbounded growth

/**
 * Load the persisted cache from disk. Returns a plain object mapping
 * hash -> scan result (null means "safe", string means "blocked reason").
 */
function _loadCache() {
  try {
    const raw = fs.readFileSync(CACHE_FILE, 'utf8');
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed;
    }
  } catch {
    // File missing or corrupt — start fresh
  }
  return {};
}

/**
 * Persist the cache to disk. Silently ignores write errors (non-critical).
 */
function _saveCache(cache) {
  try {
    fs.mkdirSync(CACHE_DIR, { recursive: true });
    fs.writeFileSync(CACHE_FILE, JSON.stringify(cache) + '\n');
  } catch {
    // Best-effort persistence
  }
}

// In-memory cache (populated from disk on first load)
let _memCache = null;

function _getCache() {
  if (_memCache === null) {
    _memCache = _loadCache();
  }
  return _memCache;
}

// -- Core API ------------------------------------------------------------

/**
 * Hash a command string using SHA-256 (first 16 hex chars for compactness).
 */
function hashCommand(command) {
  return crypto.createHash('sha256').update(command).digest('hex').slice(0, 16);
}

/**
 * Scan a command string against all secret patterns.
 * Returns null if safe, or the matched pattern string if a secret is found.
 */
function scanPatterns(command) {
  const lower = command.toLowerCase();
  for (const pattern of SECRET_PATTERNS) {
    if (lower.includes(pattern.toLowerCase())) {
      return pattern;
    }
  }
  return null;
}

/**
 * Check a command for secrets, using the hash cache to skip re-scanning
 * previously seen commands.
 *
 * @param {string} command - The shell command to check.
 * @returns {null|{decision: string, reason: string}} - null if safe,
 *   or a blocking decision object.
 */
function checkCommand(command) {
  if (!command) return null;

  const hash = hashCommand(command);
  const cache = _getCache();

  // Cache hit — return cached result without rescanning
  if (hash in cache) {
    const cached = cache[hash];
    if (cached === null) return null;
    return { decision: 'block', reason: 'Secret detected in command: ' + cached };
  }

  // Cache miss — perform full scan
  const match = scanPatterns(command);

  // Evict oldest entries if cache is too large (simple FIFO via key order)
  const keys = Object.keys(cache);
  if (keys.length >= MAX_CACHE_SIZE) {
    const toRemove = keys.slice(0, keys.length - MAX_CACHE_SIZE + 1);
    for (const k of toRemove) {
      delete cache[k];
    }
  }

  // Store result: null for safe, pattern string for blocked
  cache[hash] = match; // null or the matched pattern
  _saveCache(cache);

  if (match) {
    return { decision: 'block', reason: 'Secret detected in command: ' + match };
  }
  return null;
}

// -- Exports -------------------------------------------------------------

module.exports = {
  checkCommand,
  hashCommand,
  scanPatterns,
  SECRET_PATTERNS,
};

// -- Standalone execution (when called directly as a hook) ---------------
// Reads JSON from stdin (Claude Code hook protocol) and outputs a blocking
// decision if a secret is found.

if (require.main === module) {
  if (process.env.ECC_HOOK_PROFILE === 'off') {
    process.exit(0);
  }

  let data = '';
  process.stdin.on('data', (chunk) => { data += chunk; });
  process.stdin.on('end', () => {
    try {
      const input = JSON.parse(data);
      const cmd = (input.tool_input && input.tool_input.command) || '';
      const result = checkCommand(cmd);
      if (result) {
        process.stdout.write(JSON.stringify(result));
      }
    } catch {
      // Parse error — let the command through (fail-open for hook errors)
    }
  });
}
