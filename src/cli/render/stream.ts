/**
 * Stream renderer — formats agent events for terminal output.
 * Rich colorful display with gradient accents and icon decorations.
 */

import chalk from 'chalk'
import type { AgentEvent } from '../../core/types.js'
import { writeFile } from 'fs/promises'

// ── Color palette (shared with run_cli) ──────────────────────────────
const C = {
  purple:      chalk.hex('#8B5CF6'),
  emerald:     chalk.hex('#34D399'),
  emeraldBold: chalk.hex('#10B981').bold,
  emeraldDim:  chalk.hex('#047857'),
  cyan:        chalk.hex('#22D3EE'),
  cyanBold:    chalk.hex('#06B6D4').bold,
  amber:       chalk.hex('#FBBF24'),
  amberDim:    chalk.hex('#D97706'),
  rose:        chalk.hex('#FB7185'),
  roseBold:    chalk.hex('#F43F5E').bold,
  sky:         chalk.hex('#38BDF8'),
  bright:      chalk.hex('#F8FAFC'),
  dim:         chalk.hex('#94A3B8'),
  muted:       chalk.hex('#64748B'),
  lime:        chalk.hex('#A3E635'),
  indigo:      chalk.hex('#818CF8'),
}

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
        process.stdout.write(
          '\n  ' + C.purple('●') + C.dim(` session: `) + C.indigo(event.sessionId as string) + '\n\n'
        )
        break

      case 'text':
        process.stdout.write(C.bright(event.content as string))
        this.output.push(event.content as string)
        break

      case 'tool_call':
        process.stdout.write(
          '\n    ' + C.cyanBold(`⚙ ${event.toolName}`) +
          C.muted(` ${JSON.stringify(event.toolInput)}`) + '\n'
        )
        break

      case 'tool_result':
        process.stdout.write(
          '    ' + C.emeraldDim('  ↳ ') +
          C.dim(String(event.result).slice(0, 200)) + '\n\n'
        )
        break

      case 'tool_blocked':
        process.stdout.write(
          '\n    ' + C.roseBold(`🚫 blocked: ${event.toolName}`) +
          C.rose(` — ${event.reason}`) + '\n'
        )
        break

      case 'tool_error':
        process.stdout.write(
          '\n    ' + C.roseBold(`✗ ${event.toolName}`) +
          C.rose(`: ${event.error}`) + '\n'
        )
        break

      case 'compacting':
        process.stdout.write(
          '\n    ' + C.amber(`📦 compacting context`) +
          C.amberDim(` (${(event.tokensBefore as number).toLocaleString()} tokens)`) + '\n'
        )
        break

      case 'compacted':
        process.stdout.write(
          '    ' + C.lime(`✓ compacted to ${(event.tokensAfter as number).toLocaleString()} tokens`) + '\n\n'
        )
        break

      case 'complete':
        process.stdout.write(
          '\n  ' + C.muted('─'.repeat(56)) + '\n' +
          '    ' + C.emeraldBold('✓ done') +
          C.dim('  ·  ') +
          C.indigo(`${event.iterations} iterations`) +
          C.dim('  ·  ') +
          C.amber(`~${(event.tokenCount as number).toLocaleString()} tokens`) + '\n'
        )
        break

      case 'error':
        process.stdout.write(
          '\n    ' + C.roseBold(`✗ ${event.message}`) + '\n'
        )
        break
    }
  }

  async saveToFile(path: string): Promise<void> {
    await writeFile(path, this.output.join(''), 'utf8')
  }
}
