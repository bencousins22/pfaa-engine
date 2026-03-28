#!/usr/bin/env node
/**
 * PFAA CLI — run_cli.ts
 *
 * Exact replica of Agent Zero's run_cli.py terminal interface,
 * ported to Node.js with all PFAA enterprise features.
 *
 * Agent Zero color scheme:
 *   User prompt:    bg:#6C3483 font:white bold  (purple bg)
 *   Agent response: bg:#1D8348 font:white bold  (green bg)
 *   Agent stream:   font:#b3ffd9 italic         (mint green)
 *   Tool header:    bg:white font:#1B4F72 bold  (dark blue on white)
 *   Tool args:      font:#85C1E9 bold           (light blue)
 *   Tool response:  font:#85C1E9                (light blue)
 *   Errors:         font:red
 *   Warnings:       font:orange
 *   Hints:          font:#6C3483                (purple)
 *   Intervention:   bg:#6C3483 font:white bold
 *   Terminated:     bg:red font:white
 */

import readline from 'readline'
import chalk from 'chalk'
import { Orchestrator } from '../core/orchestrator.js'
import { loadConfig } from '../core/config.js'
import { AuditLogger } from '../audit/logger.js'
import type { PFAAConfig } from '../core/types.js'

// ── Agent Zero PrintStyle equivalents ───────────────────────────────
// These match the exact hex colors from agent-zero's PrintStyle calls

const style = {
  // User prompt header — bg:#6C3483 font:white bold padding:true
  userPrompt: (text: string) =>
    chalk.bgHex('#6C3483').white.bold(` ${text} `),

  // Agent response header — bg:#1D8348 font:white bold padding:true
  agentHeader: (text: string) =>
    chalk.bgHex('#1D8348').white.bold(` ${text} `),

  // Agent streaming text — font:#b3ffd9 italic
  agentStream: (text: string) =>
    chalk.hex('#b3ffd9').italic(text),

  // Agent "Generating" — bg:white font:green bold padding:true
  agentGenerating: (text: string) =>
    chalk.bgWhite.green.bold(` ${text} `),

  // Tool "Using tool" header — bg:white font:#1B4F72 bold padding:true
  toolHeader: (text: string) =>
    chalk.bgWhite.hex('#1B4F72').bold(` ${text} `),

  // Tool args key — font:#85C1E9 bold
  toolArgKey: (text: string) =>
    chalk.hex('#85C1E9').bold(text),

  // Tool args value — font:#85C1E9
  toolArgValue: (text: string) =>
    chalk.hex('#85C1E9')(text),

  // Tool response header — bg:white font:#1B4F72 bold padding:true
  toolResponseHeader: (text: string) =>
    chalk.bgWhite.hex('#1B4F72').bold(` ${text} `),

  // Tool response content — font:#85C1E9
  toolResponse: (text: string) =>
    chalk.hex('#85C1E9')(text),

  // Intervention — bg:#6C3483 font:white bold padding:true
  intervention: (text: string) =>
    chalk.bgHex('#6C3483').white.bold(` ${text} `),

  // Errors — font:red padding:true
  error: (text: string) =>
    chalk.red(text),

  // Warnings — font:orange padding:true
  warning: (text: string) =>
    chalk.hex('#FFA500')(text),

  // Hints — font:#6C3483
  hint: (text: string) =>
    chalk.hex('#6C3483')(text),

  // Context terminated — bg:red font:white padding:true
  terminated: (text: string) =>
    chalk.bgRed.white(` ${text} `),

  // Cleanup/compaction — bg:white font:orange bold
  cleanup: (text: string) =>
    chalk.bgWhite.hex('#FFA500').bold(` ${text} `),

  // Standard/info — font:blue
  info: (text: string) =>
    chalk.blue(text),

  // Success — font:green
  success: (text: string) =>
    chalk.green(text),

  // White text (plain output)
  white: (text: string) =>
    chalk.white(text),
}

// ── Session state ────────────────────────────────────────────────────
let interrupted = false
let streaming = false

// ── Keypress capture (mirrors Agent Zero's capture_keys thread) ─────
function captureKeys(): void {
  if (process.stdin.isTTY) {
    readline.emitKeypressEvents(process.stdin)
    process.stdin.setRawMode(true)
    process.stdin.on('keypress', (_str, key) => {
      if (streaming && key && (key.name?.match(/^[a-z]$/) || key.name === 'space')) {
        // Any alpha key or space during streaming triggers intervention
        // (same behavior as Agent Zero's capture_keys)
        interrupted = true
      }
      if (key?.ctrl && key.name === 'c') {
        if (streaming) {
          interrupted = true
        } else {
          process.exit(0)
        }
      }
    })
  }
}

// ── User input (mirrors Agent Zero's input with optional timeout) ───
async function getUserInput(prompt: string, timeout?: number): Promise<string> {
  if (process.stdin.isTTY) {
    try { process.stdin.setRawMode(false) } catch { /* ignore */ }
  }

  return new Promise((resolve) => {
    const rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: true,
    })

    let timer: ReturnType<typeof setTimeout> | null = null

    if (timeout) {
      timer = setTimeout(() => {
        rl.close()
        resolve('') // empty = auto-continue (like fw.msg_timeout)
      }, timeout * 1000)
    }

    rl.question(prompt, (answer) => {
      if (timer) clearTimeout(timer)
      rl.close()
      resolve(answer.trim())
    })
  })
}

// ── Intervention handler (mirrors Agent Zero's intervention()) ──────
async function handleIntervention(): Promise<string | null> {
  // Exact Agent Zero style: bg:#6C3483 font:white bold
  console.log()
  console.log(style.intervention(`User intervention ('e' to leave, empty to continue):`))

  const input = await getUserInput('> ')

  if (input.toLowerCase() === 'e') {
    process.exit(0)
  }

  return input || null
}

// ── Main chat loop (exact Agent Zero run_cli.py chat() replica) ─────
async function chat(orchestrator: Orchestrator, agentName: string): Promise<void> {
  while (true) {
    interrupted = false

    // Get timeout from agent data (Agent Zero: context.agent0.get_data("timeout"))
    const timeout = undefined // No timeout by default, like Agent Zero

    if (!timeout) {
      // No timeout — wait forever for user input
      // Agent Zero: PrintStyle(background_color="#6C3483", font_color="white", bold=True, padding=True)
      //             .print(f"User message ('e' to leave):")
      console.log()
      console.log(style.userPrompt(`User message ('e' to leave):`))
      const userInput = await getUserInput('> ')

      if (!userInput) continue
      if (userInput.toLowerCase() === 'e') break

      // Re-enable raw mode for intervention capture during streaming
      if (process.stdin.isTTY) {
        try { process.stdin.setRawMode(true) } catch { /* ignore */ }
      }

      streaming = true

      // Agent Zero: PrintStyle(bold=True, font_color="green", background_color="white", padding=True)
      //             .print(f"{agent_name}: Generating")
      console.log()
      console.log(style.agentGenerating(`${agentName}: Generating`))

      try {
        for await (const event of orchestrator.run(userInput)) {
          // Check for user intervention (Agent Zero: any keypress during streaming)
          if (interrupted) {
            const interventionMsg = await handleIntervention()
            interrupted = false
            if (interventionMsg) {
              // Feed intervention message back — Agent Zero sets
              // context.streaming_agent.intervention_message
              // For now we just display it
              console.log(style.white(interventionMsg))
            }
            // Re-enable streaming capture
            if (process.stdin.isTTY) {
              try { process.stdin.setRawMode(true) } catch { /* ignore */ }
            }
            continue
          }

          switch (event.type) {
            case 'start':
              // Silent — Agent Zero doesn't print session IDs
              break

            case 'text':
              // Agent Zero: printer = PrintStyle(italic=True, font_color="#b3ffd9", padding=False)
              //             printer.stream(chunk)
              process.stdout.write(style.agentStream(event.content as string))
              break

            case 'tool_call': {
              // Agent Zero: PrintStyle(font_color="#1B4F72", padding=True, background_color="white", bold=True)
              //             .print(f"{agent_name}: Using tool '{tool_name}':")
              console.log()
              console.log(style.toolHeader(`${agentName}: Using tool '${event.toolName}':`))

              // Display tool args — Agent Zero shows each key:value
              const toolInput = event.toolInput as Record<string, unknown>
              if (toolInput && typeof toolInput === 'object') {
                for (const [key, value] of Object.entries(toolInput)) {
                  const valStr = typeof value === 'string' ? value : JSON.stringify(value)
                  // Agent Zero: PrintStyle(font_color="#85C1E9", bold=True).stream(key+": ")
                  //             PrintStyle(font_color="#85C1E9").stream(value)
                  process.stdout.write(style.toolArgKey(`${key}: `))
                  process.stdout.write(style.toolArgValue(valStr.slice(0, 500)))
                  console.log()
                }
              }
              break
            }

            case 'tool_result':
              // Agent Zero: PrintStyle(font_color="#1B4F72", background_color="white", padding=True, bold=True)
              //             .print(f"{agent_name}: Response from tool '{tool_name}':")
              console.log()
              console.log(style.toolResponseHeader(`${agentName}: Response from tool '${event.toolName}':`))
              // Agent Zero: PrintStyle(font_color="#85C1E9").print(response.message)
              console.log(style.toolResponse(String(event.result).slice(0, 1000)))
              break

            case 'tool_blocked':
              // Agent Zero: PrintStyle(font_color="red", padding=True)
              console.log()
              console.log(style.error(`Blocked: ${event.toolName} — ${event.reason}`))
              break

            case 'tool_error':
              // Agent Zero: PrintStyle(font_color="red", padding=True)
              console.log()
              console.log(style.error(`Error in tool '${event.toolName}': ${event.error}`))
              break

            case 'compacting':
              // Agent Zero: PrintStyle(bold=True, font_color="orange", padding=True, background_color="white")
              //             .print(f"{agent_name}: Mid messages cleanup summary")
              console.log()
              console.log(style.cleanup(`${agentName}: Mid messages cleanup summary`))
              console.log(style.warning(`Compacting context (${(event.tokensBefore as number).toLocaleString()} tokens)...`))
              break

            case 'compacted':
              console.log(style.success(`Compacted to ${(event.tokensAfter as number).toLocaleString()} tokens`))
              break

            case 'complete':
              streaming = false
              // Agent Zero: PrintStyle(font_color="white", background_color="#1D8348", bold=True, padding=True)
              //             .print(f"{agent_name}: response:")
              console.log()
              console.log(style.agentHeader(`${agentName}: response complete`))
              console.log(style.hint(
                `${event.iterations} iterations · ~${(event.tokenCount as number).toLocaleString()} tokens`
              ))
              break

            case 'error':
              streaming = false
              // Agent Zero: PrintStyle(font_color="white", background_color="red", padding=True)
              console.log()
              console.log(style.terminated(`${agentName}: Error`))
              console.log(style.error(event.message as string))
              break
          }
        }
      } catch (err: any) {
        streaming = false
        console.log()
        console.log(style.terminated(`${agentName}: Error`))
        console.log(style.error(err.message))
      }

      streaming = false
    }
  }

  // Exit message
  console.log()
  console.log(style.hint('Goodbye.'))
}

// ── Bootstrap (mirrors Agent Zero's __main__ block) ──────────────────
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
  const agentName = getArg('--name', 'Agent 0')

  // Agent Zero: print("Initializing framework...")
  console.log('Initializing framework...')

  let config: PFAAConfig = {}
  try {
    config = await loadConfig(configPath)
  } catch {
    // Silent — Agent Zero doesn't warn about missing config
  }

  // Show initialization info (Agent Zero style — simple prints)
  console.log(style.info(`Info: Provider: ${provider}`))
  console.log(style.info(`Info: Model: ${model || (provider === 'gemini' ? 'gemini-2.5-pro' : 'claude-sonnet-4-6')}`))
  if (sandbox) {
    console.log(style.info('Info: Python 3.15 sandbox enabled (PYTHON_GIL=0)'))
  }
  console.log(style.info(`Info: Workspace: ${workspace}`))
  console.log(style.success('Success: Framework initialized'))

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

  // Start key capture thread (mirrors Agent Zero's threading.Thread(target=capture_keys))
  captureKeys()

  // Start the chat (mirrors Agent Zero's asyncio.run(chat(context)))
  await chat(orchestrator, agentName)
}

run().catch(err => {
  console.log(style.terminated(`Fatal error`))
  console.error(style.error(err.message))
  process.exit(1)
})
