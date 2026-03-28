/**
 * Code execution tool — runs Python 3.15 in an isolated sandbox with REPL persistence.
 */

import type { Tool, ToolDefinition } from './base.js'
import { PythonSandbox } from '../sandbox/python.js'
import type { OrchestratorOptions } from '../core/types.js'

export class CodeTool implements Tool {
  private sandbox: PythonSandbox

  constructor(opts: OrchestratorOptions) {
    this.sandbox = new PythonSandbox({
      timeout: 60000,
      memoryLimitMb: 512,
      allowNetwork: false,
      persist: true,
      workspace: opts.workspace,
      pythonBin: opts.config?.pythonBin ?? 'python3',
    })
  }

  definitions(): ToolDefinition[] {
    return [{
      name: 'python',
      description: 'Execute Python 3.15 code in an isolated sandbox with persistent REPL state. Use for calculations, data processing, file manipulation, and testing logic.',
      input_schema: {
        type: 'object',
        properties: {
          code: { type: 'string', description: 'Python 3.15 code to execute' },
          session_id: { type: 'string', description: 'REPL session ID for state persistence' },
        },
        required: ['code'],
      },
    }]
  }

  async execute(input: Record<string, any>): Promise<string> {
    const result = await this.sandbox.execute(input.code, input.session_id)
    const parts: string[] = []
    if (result.stdout) parts.push(result.stdout)
    if (result.stderr) parts.push(`[stderr]: ${result.stderr}`)
    if (result.error) parts.push(`[error] ${result.error.type}: ${result.error.message}`)
    parts.push(`[runtime: ${result.durationMs}ms]`)
    return parts.join('\n')
  }
}
