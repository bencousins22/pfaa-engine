/**
 * Stream renderer — Agent Zero PrintStyle-compatible output.
 * Uses the exact same color scheme as agent-zero's terminal interface.
 *
 * Color map:
 *   Tool header:     bg:white font:#1B4F72 bold
 *   Tool args/resp:  font:#85C1E9
 *   Agent stream:    font:#b3ffd9 italic
 *   Errors:          font:red
 *   Warnings:        font:orange
 *   Cleanup:         bg:white font:orange bold
 *   Success:         font:green
 *   Hints:           font:#6C3483
 */

import chalk from 'chalk'
import type { AgentEvent } from '../../core/types.js'
import { writeFile } from 'fs/promises'

const s = {
  agentStream:        chalk.hex('#b3ffd9').italic,
  toolHeader:         chalk.bgWhite.hex('#1B4F72').bold,
  toolArg:            chalk.hex('#85C1E9'),
  toolArgBold:        chalk.hex('#85C1E9').bold,
  toolResponse:       chalk.hex('#85C1E9'),
  agentResponse:      chalk.bgHex('#1D8348').white.bold,
  error:              chalk.red,
  warning:            chalk.hex('#FFA500'),
  cleanup:            chalk.bgWhite.hex('#FFA500').bold,
  success:            chalk.green,
  hint:               chalk.hex('#6C3483'),
  terminated:         chalk.bgRed.white,
  white:              chalk.white,
}

export class StreamRenderer {
  private output: string[] = []
  private opts: { json: boolean }
  private agentName: string

  constructor(opts: { json: boolean }, agentName = 'Agent 0') {
    this.opts = opts
    this.agentName = agentName
  }

  render(event: AgentEvent): void {
    if (this.opts.json) {
      process.stdout.write(JSON.stringify(event) + '\n')
      return
    }

    switch (event.type) {
      case 'start':
        break

      case 'text':
        process.stdout.write(s.agentStream(event.content as string))
        this.output.push(event.content as string)
        break

      case 'tool_call': {
        console.log()
        console.log(s.toolHeader(` ${this.agentName}: Using tool '${event.toolName}': `))
        const input = event.toolInput as Record<string, unknown>
        if (input && typeof input === 'object') {
          for (const [key, value] of Object.entries(input)) {
            const valStr = typeof value === 'string' ? value : JSON.stringify(value)
            process.stdout.write(s.toolArgBold(`${key}: `))
            process.stdout.write(s.toolArg(valStr.slice(0, 500)))
            console.log()
          }
        }
        break
      }

      case 'tool_result':
        console.log()
        console.log(s.toolHeader(` ${this.agentName}: Response from tool '${event.toolName}': `))
        console.log(s.toolResponse(String(event.result).slice(0, 1000)))
        break

      case 'tool_blocked':
        console.log()
        console.log(s.error(`Blocked: ${event.toolName} — ${event.reason}`))
        break

      case 'tool_error':
        console.log()
        console.log(s.error(`Error in tool '${event.toolName}': ${event.error}`))
        break

      case 'compacting':
        console.log()
        console.log(s.cleanup(` ${this.agentName}: Mid messages cleanup summary `))
        console.log(s.warning(`Compacting (${(event.tokensBefore as number).toLocaleString()} tokens)...`))
        break

      case 'compacted':
        console.log(s.success(`Compacted to ${(event.tokensAfter as number).toLocaleString()} tokens`))
        break

      case 'complete':
        console.log()
        console.log(s.agentResponse(` ${this.agentName}: response complete `))
        console.log(s.hint(`${event.iterations} iterations · ~${(event.tokenCount as number).toLocaleString()} tokens`))
        break

      case 'error':
        console.log()
        console.log(s.terminated(` ${this.agentName}: Error `))
        console.log(s.error(event.message as string))
        break
    }
  }

  async saveToFile(path: string): Promise<void> {
    await writeFile(path, this.output.join(''), 'utf8')
  }
}
