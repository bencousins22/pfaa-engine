/**
 * Stream renderer — Aussie Agents PrintStyle output for pfaa run command.
 * Same hex colors, same padding behavior, same tool display format.
 */

import chalk from 'chalk'
import type { AgentEvent } from '../../core/types.js'
import { writeFile } from 'fs/promises'

// JMEM brand: emerald + gold
const agentText = chalk.hex('#00E676').italic
const toolHead = chalk.bgHex('#C9A73B').hex('#1a1a1a').bold
const toolKey = chalk.hex('#C9A73B').bold
const toolVal = chalk.hex('#4CAF50')
const agentHead = chalk.bgHex('#2E7D32').white.bold
const err = chalk.hex('#EF5350')
const warn = chalk.hex('#D4A017')
const cleanup = chalk.bgHex('#C9A73B').hex('#1a1a1a').bold
const ok = chalk.hex('#00E676')
const hint = chalk.hex('#2E7D32')
const dead = chalk.bgHex('#B71C1C').white

let lastEndline = true

function pad() {
  if (!lastEndline) { process.stdout.write('\n'); lastEndline = true }
  process.stdout.write('\n')
}

function print(text: string, end = '\n') {
  if (!lastEndline) process.stdout.write('\n')
  process.stdout.write(text + end)
  lastEndline = end.endsWith('\n')
}

function stream(text: string) {
  process.stdout.write(text)
  lastEndline = false
}

export class StreamRenderer {
  private output: string[] = []
  private opts: { json: boolean }
  private name: string

  constructor(opts: { json: boolean }, name = 'Aussie') {
    this.opts = opts
    this.name = name
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
        stream(agentText(event.content as string))
        this.output.push(event.content as string)
        break

      case 'tool_call': {
        pad()
        print(toolHead(` ${this.name}: Using tool '${event.toolName}': `))
        const input = event.toolInput as Record<string, unknown>
        if (input && typeof input === 'object') {
          for (const [k, v] of Object.entries(input)) {
            const vs = typeof v === 'string' ? v : JSON.stringify(v)
            stream(toolKey(`${k}: `))
            print(toolVal(vs.length > 500 ? vs.slice(0, 497) + '...' : vs))
          }
        }
        break
      }

      case 'tool_result':
        pad()
        print(toolHead(` ${this.name}: Response from tool '${event.toolName}': `))
        print(toolVal(String(event.result).slice(0, 2000)))
        break

      case 'tool_blocked':
        pad()
        print(err(`Error: Blocked: ${event.toolName} — ${event.reason}`))
        break

      case 'tool_error':
        pad()
        print(err(`Error: tool '${event.toolName}': ${event.error}`))
        break

      case 'compacting':
        pad()
        print(cleanup(` ${this.name}: Mid messages cleanup summary `))
        print(warn(`Compacting (${(event.tokensBefore as number).toLocaleString()} tokens)...`))
        break

      case 'compacted':
        print(ok(`Compacted to ${(event.tokensAfter as number).toLocaleString()} tokens`))
        break

      case 'complete':
        pad()
        print(agentHead(` ${this.name}: reponse: `))
        print(hint(`${event.iterations} iterations · ~${(event.tokenCount as number).toLocaleString()} tokens`))
        break

      case 'error':
        pad()
        print(dead(` ${this.name}: Error `))
        print(err(`Error: ${event.message}`))
        break
    }
  }

  async saveToFile(path: string): Promise<void> {
    await writeFile(path, this.output.join(''), 'utf8')
  }
}
