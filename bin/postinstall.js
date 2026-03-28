#!/usr/bin/env node

/**
 * PFAA postinstall — checks Python availability and optionally installs deps.
 * Runs after `npm install @aussie-agents/pfaa` or `npx @aussie-agents/pfaa`.
 */

import { execSync } from 'child_process'
import { existsSync } from 'fs'
import { dirname, join } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = join(__dirname, '..')

const GREEN = '\x1b[32m'
const YELLOW = '\x1b[33m'
const PURPLE = '\x1b[35m'
const DIM = '\x1b[2m'
const RESET = '\x1b[0m'

function run(cmd) {
  try {
    return execSync(cmd, { encoding: 'utf8', timeout: 10000, stdio: 'pipe' }).trim()
  } catch {
    return null
  }
}

console.log()
console.log(`${PURPLE}  PFAA${RESET} — Platform for Autonomous Agents`)
console.log()

// Check Python
const python = run('python3 --version') || run('python --version')
if (python) {
  console.log(`${GREEN}  ✓${RESET} ${python}`)
} else {
  console.log(`${YELLOW}  ⚠ Python not found. Python 3.12+ required for:${RESET}`)
  console.log(`${DIM}    - JMEM cognitive memory (jmem engine)`)
  console.log(`    - 9-tier agent swarm`)
  console.log(`    - Python code sandbox${RESET}`)
}

// Check if jmem is accessible
const jmemPath = join(root, 'python', 'jmem', 'engine.py')
if (existsSync(jmemPath)) {
  console.log(`${GREEN}  ✓${RESET} JMEM engine found`)
} else {
  console.log(`${YELLOW}  ⚠ JMEM engine not found at ${jmemPath}${RESET}`)
}

// Check optional sentence-transformers
const sbert = run('python3 -c "import sentence_transformers; print(sentence_transformers.__version__)"')
if (sbert) {
  console.log(`${GREEN}  ✓${RESET} sentence-transformers ${sbert}`)
} else {
  console.log(`${DIM}  ○ sentence-transformers not installed (optional — for Qdrant memory)${RESET}`)
  console.log(`${DIM}    Install with: pip install sentence-transformers${RESET}`)
}

// Check optional Qdrant
const qdrant = run('curl -s -o /dev/null -w "%{http_code}" http://localhost:6333/collections 2>/dev/null')
if (qdrant === '200') {
  console.log(`${GREEN}  ✓${RESET} Qdrant running on :6333`)
} else {
  console.log(`${DIM}  ○ Qdrant not running (optional — JMEM uses SQLite by default)${RESET}`)
  console.log(`${DIM}    Start with: docker run -p 6333:6333 qdrant/qdrant${RESET}`)
}

console.log()
console.log(`${GREEN}  Ready!${RESET} Run with:`)
console.log()
console.log(`${DIM}    npx @aussie-agents/pfaa              ${RESET}${PURPLE}# Agent Zero-style interactive CLI${RESET}`)
console.log(`${DIM}    npx @aussie-agents/pfaa run "task"    ${RESET}${PURPLE}# One-shot task execution${RESET}`)
console.log(`${DIM}    npx @aussie-agents/pfaa exec -c "..." ${RESET}${PURPLE}# Python sandbox${RESET}`)
console.log(`${DIM}    npx @aussie-agents/pfaa swarm "task"  ${RESET}${PURPLE}# 9-tier agent swarm${RESET}`)
console.log(`${DIM}    npx @aussie-agents/pfaa memory stats  ${RESET}${PURPLE}# JMEM memory health${RESET}`)
console.log()
