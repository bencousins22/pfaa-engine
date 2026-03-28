#!/usr/bin/env node
/**
 * PFAA CLI — run_cli.ts
 *
 * Exact replica of Agent Zero's run_cli.py + agent.py terminal interface.
 * Same colors. Same flow. Same snappy feel.
 */

import readline from 'readline'
import chalk from 'chalk'
import { Orchestrator } from '../core/orchestrator.js'
import { loadConfig } from '../core/config.js'
import { AuditLogger } from '../audit/logger.js'
import type { PFAAConfig } from '../core/types.js'

// ── Agent Zero PrintStyle ───────────────────────────────────────────
// Exact hex codes from python/helpers/print_style.py

let lastEndline = true

function pad() {
  if (!lastEndline) { process.stdout.write('\n'); lastEndline = true }
  process.stdout.write('\n')
}

function print(text: string, end = '\n') {
  if (!lastEndline) { process.stdout.write('\n') }
  process.stdout.write(text + end)
  lastEndline = end.endsWith('\n')
}

function stream(text: string) {
  process.stdout.write(text)
  lastEndline = false
}

// bg:#6C3483 font:white bold
const userPrompt = (t: string) => chalk.bgHex('#6C3483').white.bold(` ${t} `)
// bg:#1D8348 font:white bold
const agentHeader = (t: string) => chalk.bgHex('#1D8348').white.bold(` ${t} `)
// bg:white font:green bold
const agentGen = (t: string) => chalk.bgWhite.green.bold(` ${t} `)
// font:#b3ffd9 italic
const agentText = (t: string) => chalk.hex('#b3ffd9').italic(t)
// bg:white font:#1B4F72 bold
const toolHead = (t: string) => chalk.bgWhite.hex('#1B4F72').bold(` ${t} `)
// font:#85C1E9 bold
const toolKey = (t: string) => chalk.hex('#85C1E9').bold(t)
// font:#85C1E9
const toolVal = (t: string) => chalk.hex('#85C1E9')(t)
// font:red
const error = (t: string) => chalk.red(t)
// font:orange
const warn = (t: string) => chalk.hex('#FFA500')(t)
// font:#6C3483
const hint = (t: string) => chalk.hex('#6C3483')(t)
// bg:red font:white
const dead = (t: string) => chalk.bgRed.white(` ${t} `)
// bg:white font:orange bold
const cleanup = (t: string) => chalk.bgWhite.hex('#FFA500').bold(` ${t} `)
// font:blue
const info = (t: string) => chalk.blue(t)
// font:green
const ok = (t: string) => chalk.green(t)

// ── State ────────────────────────────────────────────────────────────
let interrupted = false
let streaming = false

// ── Key capture (Agent Zero capture_keys thread) ─────────────────────
function captureKeys() {
  if (!process.stdin.isTTY) return
  readline.emitKeypressEvents(process.stdin)
  process.stdin.setRawMode(true)
  process.stdin.on('keypress', (_str, key) => {
    if (streaming && key && (key.name?.match(/^[a-z]$/) || key.name === 'space')) {
      interrupted = true
    }
    if (key?.ctrl && key.name === 'c') {
      if (streaming) { interrupted = true } else { process.exit(0) }
    }
  })
}

// ── Input ────────────────────────────────────────────────────────────
async function input(prompt: string, timeout?: number): Promise<string> {
  if (process.stdin.isTTY) try { process.stdin.setRawMode(false) } catch {}
  return new Promise(resolve => {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true })
    let t: ReturnType<typeof setTimeout> | null = null
    if (timeout) t = setTimeout(() => { rl.close(); resolve('') }, timeout * 1000)
    rl.question(prompt, a => { if (t) clearTimeout(t); rl.close(); resolve(a.trim()) })
  })
}

// ── Intervention (Agent Zero intervention()) ─────────────────────────
async function intervention(): Promise<string | null> {
  streaming = false
  pad()
  print(userPrompt(`User intervention ('e' to leave, empty to continue):`))
  const msg = await input('> ')
  if (msg.toLowerCase() === 'e') process.exit(0)
  streaming = true
  if (process.stdin.isTTY) try { process.stdin.setRawMode(true) } catch {}
  return msg || null
}

// ── Chat loop (Agent Zero chat()) ────────────────────────────────────
async function chat(orc: Orchestrator, name: string) {
  while (true) {
    interrupted = false
    streaming = false

    // ── User prompt ──
    // PrintStyle(background_color="#6C3483", font_color="white", bold=True, padding=True)
    pad()
    print(userPrompt(`User message ('e' to leave):`))
    const msg = await input('> ')
    if (!msg) continue
    if (msg.toLowerCase() === 'e') break

    // ── Start streaming ──
    if (process.stdin.isTTY) try { process.stdin.setRawMode(true) } catch {}
    streaming = true

    // PrintStyle(bold=True, font_color="green", background_color="white", padding=True)
    pad()
    print(agentGen(`${name}: Generating`))

    // PrintStyle(italic=True, font_color="#b3ffd9", padding=False)
    // printer.print("Response: ")
    print(agentText('Response: '), '')

    try {
      for await (const event of orc.run(msg)) {
        if (interrupted) {
          const iv = await intervention()
          interrupted = false
          if (iv) stream(chalk.white(iv))
          continue
        }

        switch (event.type) {
          case 'start':
            break

          case 'text':
            // printer.stream(chunk) — italic mint green, no newline
            stream(agentText(event.content as string))
            break

          case 'tool_call': {
            // PrintStyle(font_color="#1B4F72", padding=True, background_color="white", bold=True)
            // .print(f"{name}: Using tool '{tool}':")
            pad()
            print(toolHead(`${name}: Using tool '${event.toolName}':`))
            const ti = event.toolInput as Record<string, unknown>
            if (ti && typeof ti === 'object') {
              for (const [k, v] of Object.entries(ti)) {
                const vs = typeof v === 'string' ? v : JSON.stringify(v)
                // PrintStyle(font_color="#85C1E9", bold=True).stream(key+": ")
                // PrintStyle(font_color="#85C1E9").stream(value)
                stream(toolKey(`${k}: `))
                print(toolVal(vs.length > 500 ? vs.slice(0, 497) + '...' : vs))
              }
            }
            break
          }

          case 'tool_result':
            // PrintStyle(font_color="#1B4F72", background_color="white", padding=True, bold=True)
            // .print(f"{name}: Response from tool '{tool}':")
            pad()
            print(toolHead(`${name}: Response from tool '${event.toolName}':`))
            // PrintStyle(font_color="#85C1E9").print(response.message)
            print(toolVal(String(event.result).slice(0, 2000)))
            // Resume streaming header
            print(agentText('Response: '), '')
            break

          case 'tool_blocked':
            pad()
            print(error(`Error: Blocked: ${event.toolName} — ${event.reason}`))
            break

          case 'tool_error':
            pad()
            print(error(`Error: tool '${event.toolName}': ${event.error}`))
            break

          case 'compacting':
            // PrintStyle(bold=True, font_color="orange", padding=True, background_color="white")
            pad()
            print(cleanup(`${name}: Mid messages cleanup summary`))
            print(warn(`Compacting context (${(event.tokensBefore as number).toLocaleString()} tokens)...`))
            break

          case 'compacted':
            print(ok(`Compacted to ${(event.tokensAfter as number).toLocaleString()} tokens`))
            break

          case 'complete':
            streaming = false
            // PrintStyle(font_color="white", background_color="#1D8348", bold=True, padding=True)
            // .print(f"{name}: reponse:")  (yes, typo is in Agent Zero source)
            pad()
            print(agentHeader(`${name}: reponse:`))
            print(hint(`${event.iterations} iterations · ~${(event.tokenCount as number).toLocaleString()} tokens`))
            break

          case 'error':
            streaming = false
            pad()
            print(dead(`Context terminated`))
            print(error(`Error: ${event.message}`))
            break
        }
      }
    } catch (err: any) {
      streaming = false
      pad()
      print(dead(`Context terminated`))
      print(error(`Error: ${err.message}`))
    }
    streaming = false
  }
}

// ── Main (Agent Zero __main__) ───────────────────────────────────────
async function main() {
  const args = process.argv.slice(2)
  const arg = (f: string, d: string) => { const i = args.indexOf(f); return i !== -1 ? args[i + 1] ?? d : d }
  const flag = (f: string) => args.includes(f)

  const provider = arg('--provider', process.env.PFAA_PROVIDER ?? 'claude')
  const model = arg('--model', process.env.PFAA_MODEL ?? '')
  const sandbox = flag('--sandbox')
  const configPath = arg('--config', './pfaa.config.json')
  const workspace = arg('--workspace', process.cwd())
  const name = arg('--name', 'Agent 0')

  // Agent Zero: print("Initializing framework...")
  print('Initializing framework...')

  const config = await loadConfig(configPath)

  // Agent Zero style: PrintStyle.info(), PrintStyle.success()
  print(info(`Info: provider=${provider} model=${model || (provider === 'gemini' ? 'gemini-2.5-pro' : 'claude-sonnet-4-6')}`))
  print(info(`Info: workspace=${workspace}${sandbox ? ' sandbox=python3(free-threaded)' : ''}`))
  print(ok('Success: Framework initialized'))

  const audit = new AuditLogger(config.auditDir)
  const orc = new Orchestrator({
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
  await chat(orc, name)

  pad()
  print(hint('Goodbye.'))
}

main().catch(err => {
  print(dead('Fatal error'))
  print(error(`Error: ${err.message}`))
  process.exit(1)
})
