#!/usr/bin/env node
/**
 * PFAA CLI — run_cli.ts
 * Agent Zero-style terminal loop with streaming agent output.
 * Purple user prompt, green agent responses, live tool calls.
 */

import readline from 'readline'
import chalk from 'chalk'
import { Orchestrator } from '../core/orchestrator.js'
import { loadConfig } from '../core/config.js'
import { AuditLogger } from '../audit/logger.js'
import type { PFAAConfig } from '../core/types.js'

// ── PrintStyle equivalents ──────────────────────────────────────────
const print = {
  userHeader: (msg: string) =>
    console.log('\n' + chalk.bgHex('#6C3483').white.bold(` ${msg} `)),
  agentHeader: (agentName: string) =>
    process.stdout.write('\n' + chalk.bgHex('#1D8348').white.bold(` ${agentName}: `) + '\n'),
  toolCall: (name: string, input: string) =>
    process.stdout.write(chalk.cyan(`\n    ⚙ ${name} `) + chalk.gray(input) + '\n'),
  toolResult: (result: string) =>
    process.stdout.write(chalk.gray(`      ↳ ${result.slice(0, 300).replace(/\n/g, ' ')}\n`)),
  error: (msg: string) =>
    console.log(chalk.red(`\n    ✗ ${msg}`)),
  status: (msg: string) =>
    process.stdout.write(chalk.yellow(`    [${msg}]\n`)),
  stream: (text: string) =>
    process.stdout.write(chalk.white(text)),
  standard: (msg: string) =>
    console.log(chalk.gray(msg)),
  divider: () =>
    console.log(chalk.gray('─'.repeat(60))),
}

// ── Session state ────────────────────────────────────────────────────
let interrupted = false

// ── Keypress intervention (mirrors Agent Zero's capture_keys) ────────
function captureKeys(): void {
  if (process.stdin.isTTY) {
    readline.emitKeypressEvents(process.stdin)
    process.stdin.setRawMode(true)
    process.stdin.on('keypress', (_str, key) => {
      if (key?.ctrl && key.name === 'c') {
        console.log(chalk.yellow('\n\n    Interrupted. Type \'e\' to exit or press Enter to continue.'))
        interrupted = true
      }
    })
  }
}

// ── User input with optional timeout ────────────────────────────────
async function getUserInput(prompt: string): Promise<string> {
  if (process.stdin.isTTY) {
    try { process.stdin.setRawMode(false) } catch { /* ignore */ }
  }

  return new Promise((resolve) => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true })
    rl.question(chalk.hex('#6C3483').bold(prompt), (answer) => {
      rl.close()
      resolve(answer.trim())
    })
  })
}

// ── Banner ───────────────────────────────────────────────────────────
function printBanner(provider: string, model: string, sandbox: boolean): void {
  console.log()
  console.log(chalk.hex('#6C3483').bold('╔══════════════════════════════════════════════════╗'))
  console.log(chalk.hex('#6C3483').bold('║') + chalk.white.bold('   PFAA — Platform for Autonomous Agents          ') + chalk.hex('#6C3483').bold('║'))
  console.log(chalk.hex('#6C3483').bold('╚══════════════════════════════════════════════════╝'))
  console.log(chalk.gray(`  provider : ${chalk.white(provider)}`))
  console.log(chalk.gray(`  model    : ${chalk.white(model)}`))
  console.log(chalk.gray(`  sandbox  : ${sandbox ? chalk.green('python3 (free-threaded)') : chalk.gray('off')}`))
  console.log(chalk.gray(`  type     : ${chalk.hex('#6C3483')('e')} ${chalk.gray('to exit')}  |  ${chalk.yellow('ctrl+c')} ${chalk.gray('to interrupt agent')}`))
  console.log()
}

// ── Main chat loop (mirrors Agent Zero's async chat()) ───────────────
async function chat(orchestrator: Orchestrator, agentName: string): Promise<void> {
  while (true) {
    interrupted = false

    print.userHeader(`User message ('e' to exit):`)
    const userInput = await getUserInput('› ')

    if (!userInput) continue
    if (userInput.toLowerCase() === 'e') {
      print.standard('\nGoodbye.')
      process.exit(0)
    }

    // Re-enable raw mode for interrupt capture during agent run
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
            print.standard(`    session: ${event.sessionId}\n`)
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
            print.error(`blocked: ${event.toolName} — ${event.reason}`)
            break
          case 'tool_error':
            print.error(`${event.toolName}: ${event.error}`)
            break
          case 'compacting':
            print.status(`compacting context (${event.tokensBefore} tokens)...`)
            break
          case 'compacted':
            print.status(`compacted to ${event.tokensAfter} tokens`)
            break
          case 'complete':
            process.stdout.write('\n')
            print.divider()
            print.standard(`    ${event.iterations} iterations · ~${event.tokenCount} tokens`)
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

  print.standard('Initializing PFAA...')

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
  console.error(chalk.red(err.message))
  process.exit(1)
})
