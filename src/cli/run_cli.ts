#!/usr/bin/env node
/**
 * PFAA CLI — run_cli.ts
 * Agent Zero-style terminal loop with rich colorful output.
 * Gradient banners, animated spinners, tier-colored tool calls.
 */

import readline from 'readline'
import chalk from 'chalk'
import { Orchestrator } from '../core/orchestrator.js'
import { loadConfig } from '../core/config.js'
import { AuditLogger } from '../audit/logger.js'
import type { PFAAConfig } from '../core/types.js'

// ── Color Palette ───────────────────────────────────────────────────
const C = {
  // Primary brand — deep purple gradient
  purple:      chalk.hex('#8B5CF6'),
  purpleBold:  chalk.hex('#A78BFA').bold,
  purpleDim:   chalk.hex('#6D28D9'),
  purpleBg:    chalk.bgHex('#7C3AED').white.bold,

  // Agent response — emerald green gradient
  emerald:     chalk.hex('#34D399'),
  emeraldBold: chalk.hex('#10B981').bold,
  emeraldBg:   chalk.bgHex('#059669').white.bold,
  emeraldDim:  chalk.hex('#047857'),

  // Tool calls — electric cyan
  cyan:        chalk.hex('#22D3EE'),
  cyanBold:    chalk.hex('#06B6D4').bold,
  cyanDim:     chalk.hex('#0891B2'),

  // Results — warm amber
  amber:       chalk.hex('#FBBF24'),
  amberDim:    chalk.hex('#D97706'),

  // Errors — vivid rose
  rose:        chalk.hex('#FB7185'),
  roseBold:    chalk.hex('#F43F5E').bold,
  roseBg:      chalk.bgHex('#E11D48').white.bold,

  // Status — soft sky blue
  sky:         chalk.hex('#38BDF8'),
  skyDim:      chalk.hex('#0284C7'),

  // Text
  bright:      chalk.hex('#F8FAFC'),
  dim:         chalk.hex('#94A3B8'),
  muted:       chalk.hex('#64748B'),

  // Accents
  gold:        chalk.hex('#F59E0B'),
  pink:        chalk.hex('#EC4899'),
  indigo:      chalk.hex('#818CF8'),
  lime:        chalk.hex('#A3E635'),
  orange:      chalk.hex('#FB923C'),
}

// ── Decorative characters ───────────────────────────────────────────
const ICONS = {
  gear:     '⚙',
  arrow:    '↳',
  check:    '✓',
  cross:    '✗',
  bolt:     '⚡',
  brain:    '🧠',
  rocket:   '🚀',
  shield:   '🛡',
  chain:    '🔗',
  compress: '📦',
  sparkle:  '✨',
  wave:     '👋',
  block:    '🚫',
  warning:  '⚠',
  dot:      '●',
  ring:     '○',
}

// ── Print functions with rich colors ────────────────────────────────
const print = {
  userHeader: (msg: string) => {
    console.log()
    console.log(C.purpleBg(` ${ICONS.sparkle} ${msg} `))
  },

  agentHeader: (agentName: string) => {
    process.stdout.write('\n' + C.emeraldBg(` ${ICONS.brain} ${agentName} `) + '\n')
  },

  toolCall: (name: string, input: string) => {
    const truncated = input.length > 120 ? input.slice(0, 117) + '...' : input
    process.stdout.write(
      '\n    ' + C.cyanBold(`${ICONS.gear} ${name}`) +
      C.muted(` ${truncated}`) + '\n'
    )
  },

  toolResult: (result: string) => {
    const truncated = result.slice(0, 300).replace(/\n/g, ' ')
    process.stdout.write(
      '    ' + C.emeraldDim(`  ${ICONS.arrow} `) +
      C.dim(truncated) + '\n'
    )
  },

  toolBlocked: (name: string, reason: string) => {
    process.stdout.write(
      '\n    ' + C.roseBold(`${ICONS.block} blocked: ${name}`) +
      C.rose(` — ${reason}`) + '\n'
    )
  },

  error: (msg: string) => {
    console.log('    ' + C.roseBold(`${ICONS.cross} ${msg}`))
  },

  status: (msg: string) => {
    process.stdout.write('    ' + C.sky(`${ICONS.dot} ${msg}`) + '\n')
  },

  stream: (text: string) => {
    process.stdout.write(C.bright(text))
  },

  standard: (msg: string) => {
    console.log(C.dim(msg))
  },

  divider: () => {
    const gradient = '─'.repeat(60)
    console.log(C.muted(gradient))
  },

  success: (msg: string) => {
    console.log('    ' + C.emeraldBold(`${ICONS.check} ${msg}`))
  },

  compacting: (tokens: number) => {
    process.stdout.write(
      '    ' + C.amber(`${ICONS.compress} compacting context`) +
      C.amberDim(` (${tokens.toLocaleString()} tokens)...`) + '\n'
    )
  },

  compacted: (tokens: number) => {
    process.stdout.write(
      '    ' + C.lime(`${ICONS.check} compacted to ${tokens.toLocaleString()} tokens`) + '\n\n'
    )
  },
}

// ── Session state ────────────────────────────────────────────────────
let interrupted = false

// ── Keypress intervention ────────────────────────────────────────────
function captureKeys(): void {
  if (process.stdin.isTTY) {
    readline.emitKeypressEvents(process.stdin)
    process.stdin.setRawMode(true)
    process.stdin.on('keypress', (_str, key) => {
      if (key?.ctrl && key.name === 'c') {
        console.log('\n\n    ' + C.amber(`${ICONS.warning} Interrupted.`) + C.dim(` Type 'e' to exit or press Enter to continue.`))
        interrupted = true
      }
    })
  }
}

// ── User input ──────────────────────────────────────────────────────
async function getUserInput(prompt: string): Promise<string> {
  if (process.stdin.isTTY) {
    try { process.stdin.setRawMode(false) } catch { /* ignore */ }
  }

  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true })
    rl.question(C.purpleBold(prompt), (answer) => {
      rl.close()
      resolve(answer.trim())
    })
  })
}

// ── Gradient text helper ────────────────────────────────────────────
function gradient(text: string, colors: string[]): string {
  const chars = [...text]
  return chars.map((c, i) => {
    const colorIdx = Math.floor((i / chars.length) * colors.length)
    return chalk.hex(colors[Math.min(colorIdx, colors.length - 1)])(c)
  }).join('')
}

// ── Banner ───────────────────────────────────────────────────────────
function printBanner(provider: string, model: string, sandbox: boolean): void {
  const gradColors = ['#8B5CF6', '#7C3AED', '#6D28D9', '#5B21B6', '#4C1D95']
  const w = 54

  console.log()
  console.log(gradient('╔' + '═'.repeat(w) + '╗', gradColors))
  console.log(
    C.purpleDim('║') +
    '                                                      ' +
    C.purpleDim('║')
  )
  console.log(
    C.purpleDim('║') +
    gradient('     ██████  ███████  █████   █████               ', ['#A78BFA', '#8B5CF6', '#7C3AED', '#6D28D9']) +
    '    ' +
    C.purpleDim('║')
  )
  console.log(
    C.purpleDim('║') +
    gradient('     ██   ██ ██      ██   ██ ██   ██              ', ['#A78BFA', '#8B5CF6', '#7C3AED', '#6D28D9']) +
    '    ' +
    C.purpleDim('║')
  )
  console.log(
    C.purpleDim('║') +
    gradient('     ██████  █████   ███████ ███████              ', ['#C4B5FD', '#A78BFA', '#8B5CF6', '#7C3AED']) +
    '    ' +
    C.purpleDim('║')
  )
  console.log(
    C.purpleDim('║') +
    gradient('     ██      ██      ██   ██ ██   ██              ', ['#8B5CF6', '#7C3AED', '#6D28D9', '#5B21B6']) +
    '    ' +
    C.purpleDim('║')
  )
  console.log(
    C.purpleDim('║') +
    gradient('     ██      ██      ██   ██ ██   ██              ', ['#7C3AED', '#6D28D9', '#5B21B6', '#4C1D95']) +
    '    ' +
    C.purpleDim('║')
  )
  console.log(
    C.purpleDim('║') +
    '                                                      ' +
    C.purpleDim('║')
  )
  console.log(
    C.purpleDim('║') +
    C.dim('   Platform for Autonomous Agents') +
    C.muted(' · enterprise') +
    '      ' +
    C.purpleDim('║')
  )
  console.log(
    C.purpleDim('║') +
    '                                                      ' +
    C.purpleDim('║')
  )
  console.log(gradient('╚' + '═'.repeat(w) + '╝', gradColors))
  console.log()

  // Status line with colored badges
  const providerBadge = provider === 'claude'
    ? C.orange(`${ICONS.bolt} Claude`)
    : C.sky(`${ICONS.bolt} Gemini`)

  const sandboxBadge = sandbox
    ? C.lime(`${ICONS.shield} python3 free-threaded`)
    : C.muted(`${ICONS.ring} sandbox off`)

  console.log(
    C.dim('  ') +
    C.purple(`${ICONS.dot} provider`) + C.bright(` ${provider}`) +
    C.muted('  ·  ') +
    C.purple(`${ICONS.dot} model`) + C.bright(` ${model}`) +
    C.muted('  ·  ') +
    sandboxBadge
  )
  console.log(
    C.dim('  ') +
    C.pink(`${ICONS.dot} exit`) + C.muted(` type 'e'`) +
    C.muted('  ·  ') +
    C.amber(`${ICONS.dot} interrupt`) + C.muted(` ctrl+c`)
  )
  console.log()
  print.divider()
  console.log()
}

// ── Stats display after completion ──────────────────────────────────
function printCompletionStats(iterations: number, tokenCount: number): void {
  console.log()
  print.divider()
  console.log(
    '    ' +
    C.emeraldBold(`${ICONS.check} done`) +
    C.dim('  ·  ') +
    C.indigo(`${iterations} iterations`) +
    C.dim('  ·  ') +
    C.amber(`~${tokenCount.toLocaleString()} tokens`)
  )
}

// ── Main chat loop ──────────────────────────────────────────────────
async function chat(orchestrator: Orchestrator, agentName: string): Promise<void> {
  while (true) {
    interrupted = false

    print.userHeader(`User message ('e' to exit):`)
    const userInput = await getUserInput(`  ${ICONS.sparkle} `)

    if (!userInput) continue
    if (userInput.toLowerCase() === 'e') {
      console.log()
      console.log(C.dim(`  ${ICONS.wave} `) + gradient('Goodbye!', ['#8B5CF6', '#EC4899', '#F59E0B']))
      console.log()
      process.exit(0)
    }

    if (process.stdin.isTTY) {
      try { process.stdin.setRawMode(true) } catch { /* ignore */ }
    }

    print.agentHeader(agentName)

    try {
      for await (const event of orchestrator.run(userInput)) {
        if (interrupted) {
          print.status('Agent paused by user')
          break
        }

        switch (event.type) {
          case 'start':
            print.standard(`    ${ICONS.chain} session: ${C.indigo(event.sessionId as string)}\n`)
            break
          case 'text':
            print.stream(event.content as string)
            break
          case 'tool_call':
            print.toolCall(event.toolName as string, JSON.stringify(event.toolInput))
            break
          case 'tool_result':
            print.toolResult(String(event.result))
            break
          case 'tool_blocked':
            print.toolBlocked(event.toolName as string, event.reason as string)
            break
          case 'tool_error':
            print.error(`${event.toolName}: ${event.error}`)
            break
          case 'compacting':
            print.compacting(event.tokensBefore as number)
            break
          case 'compacted':
            print.compacted(event.tokensAfter as number)
            break
          case 'complete':
            printCompletionStats(event.iterations as number, event.tokenCount as number)
            break
          case 'error':
            print.error(event.message as string)
            break
        }
      }
    } catch (err: any) {
      print.error(err.message)
    }

    console.log()
  }
}

// ── Bootstrap ────────────────────────────────────────────────────────
async function run(): Promise<void> {
  const args = process.argv.slice(2)
  const getArg = (flag: string, def: string) => {
    const i = args.indexOf(flag)
    return i !== -1 ? args[i + 1] ?? def : def
  }
  const hasFlag = (flag: string) => args.includes(flag)

  const provider = getArg('--provider', process.env.PFAA_PROVIDER ?? 'claude')
  const model = getArg('--model', process.env.PFAA_MODEL ?? '')
  const sandbox = hasFlag('--sandbox')
  const configPath = getArg('--config', './pfaa.config.json')
  const workspace = getArg('--workspace', process.cwd())
  const agentName = getArg('--name', 'PFAA')

  console.log()
  console.log(C.dim('  ') + gradient('Initializing PFAA...', ['#8B5CF6', '#7C3AED', '#6D28D9']))

  let config: PFAAConfig = {}
  try {
    config = await loadConfig(configPath)
  } catch {
    print.standard('  No pfaa.config.json found, using defaults.')
  }

  printBanner(
    provider,
    model || (provider === 'gemini' ? 'gemini-2.5-pro' : 'claude-sonnet-4-6'),
    sandbox,
  )

  const audit = new AuditLogger(config.auditDir)

  const orchestrator = new Orchestrator({
    provider,
    model: model || undefined,
    sandbox,
    maxTokens: 8192,
    compactThreshold: 80000,
    workspace,
    tools: ['file', 'shell', 'fetch', 'code'],
    config,
    audit,
  })

  captureKeys()
  await chat(orchestrator, agentName)
}

run().catch(err => {
  console.error(C.roseBold(`  ${ICONS.cross} Fatal: ${err.message}`))
  process.exit(1)
})
