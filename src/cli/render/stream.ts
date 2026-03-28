/**
 * Stream renderer — formats agent events for terminal output.
 * Supports both human-readable and JSON output modes.
 */

import chalk from 'chalk'
import type { AgentEvent } from '../../core/types.js'
import { writeFile } from 'fs/promises'

export class StreamRenderer {
  private output: string[] = []
  private opts: { json: boolean }

  constructor(opts: { json: boolean }) {
    this.opts = opts
  }

  render(event: AgentEvent): void {
    if (this.opts.json) {
      process.stdout.write(JSON.stringify(event) + '\n')
      return
    }

    switch (event.type) {
      case 'start':
        process.stdout.write(chalk.gray(`\n[session: ${event.sessionId}]\n\n`))
        break
      case 'text':
        process.stdout.write(event.content as string)
        this.output.push(event.content as string)
        break
      case 'tool_call':
        process.stdout.write(
          chalk.cyan(`\n\n  ⚙ ${event.toolName}`) +
          chalk.gray(` ${JSON.stringify(event.toolInput)}\n`)
        )
        break
      case 'tool_result':
        process.stdout.write(chalk.gray(`    ↳ ${String(event.result).slice(0, 200)}\n\n`))
        break
      case 'tool_blocked':
        process.stdout.write(chalk.red(`\n  ✗ blocked: ${event.toolName} — ${event.reason}\n`))
        break
      case 'tool_error':
        process.stdout.write(chalk.red(`\n  ✗ error in ${event.toolName}: ${event.error}\n`))
        break
      case 'compacting':
        process.stdout.write(chalk.yellow(`\n  [compacting context: ${event.tokensBefore} tokens]\n`))
        break
      case 'compacted':
        process.stdout.write(chalk.yellow(`  [compacted to: ${event.tokensAfter} tokens]\n\n`))
        break
      case 'complete':
        process.stdout.write(
          chalk.green(`\n\n  done — ${event.iterations} iterations, ~${event.tokenCount} tokens\n`)
        )
        break
      case 'error':
        process.stdout.write(chalk.red(`\n  ✗ ${event.message}\n`))
        break
    }
  }

  async saveToFile(path: string): Promise<void> {
    await writeFile(path, this.output.join(''), 'utf8')
  }
}
