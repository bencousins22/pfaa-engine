/**
 * Tool registry — manages available tools and their definitions.
 */

import type { OrchestratorOptions } from '../core/types.js'
import { FileTool } from './file.js'
import { ShellTool } from './shell.js'
import { FetchTool } from './fetch.js'
import { CodeTool } from './code.js'
import type { Tool, ToolDefinition } from './base.js'

export class ToolRegistry {
  private tools: Map<string, Tool> = new Map()

  constructor(opts: OrchestratorOptions) {
    const available: Record<string, Tool> = {
      file: new FileTool(opts.workspace),
      shell: new ShellTool(opts.workspace),
      fetch: new FetchTool(),
      code: new CodeTool(opts),
    }

    const enabled = opts.tools ?? Object.keys(available)
    for (const name of enabled) {
      if (available[name]) this.tools.set(name, available[name])
    }
  }

  get(name: string): Tool | undefined {
    return this.tools.get(name)
  }

  getDefinitions(): ToolDefinition[] {
    return Array.from(this.tools.values()).flatMap(t => t.definitions())
  }
}
