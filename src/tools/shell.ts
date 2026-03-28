/**
 * Shell tool — execute bash commands with timeout.
 */

import type { Tool, ToolDefinition } from './base.js'
import { execa } from 'execa'

export class ShellTool implements Tool {
  constructor(private workspace: string) {}

  definitions(): ToolDefinition[] {
    return [{
      name: 'shell',
      description: 'Run a shell command. Returns stdout + stderr. Avoid destructive commands.',
      input_schema: {
        type: 'object',
        properties: {
          command: { type: 'string', description: 'Shell command to execute' },
          timeout: { type: 'number', description: 'Timeout in ms', default: 30000 },
        },
        required: ['command'],
      },
    }]
  }

  async execute(input: Record<string, any>): Promise<string> {
    try {
      const result = await execa('bash', ['-c', input.command], {
        cwd: this.workspace,
        timeout: input.timeout ?? 30000,
        all: true,
        reject: false,
      })
      return result.all ?? result.stdout ?? ''
    } catch (err: any) {
      return `Error: ${err.message}`
    }
  }
}
