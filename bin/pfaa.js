#!/usr/bin/env node

// Prefer compiled dist/ (npm install), fall back to src/ (dev mode)
import { existsSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const __dirname = dirname(fileURLToPath(import.meta.url))
const distEntry = join(__dirname, '..', 'dist', 'cli', 'index.js')
const srcEntry = join(__dirname, '..', 'src', 'cli', 'index.js')

if (existsSync(distEntry)) {
  await import(distEntry)
} else {
  await import(srcEntry)
}
