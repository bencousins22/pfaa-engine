/**
 * Tool registry — manages available tools and their definitions.
 * Includes jmem memory tools (recall, store, feedback) by default.
 */

import type { OrchestratorOptions } from '../core/types.js'
import { FileTool } from './file.js'
import { ShellTool } from './shell.js'
import { FetchTool } from './fetch.js'
import { CodeTool } from './code.js'
import { MemoryTool } from './memory.js'
import { JMemTool } from './jmem.js'
import { DeferredToolLoader } from './deferred.js'
import type { Tool, ToolDefinition } from './base.js'

export class ToolRegistry {
  private tools: Map<string, Tool> = new Map()
  private deferredLoader: DeferredToolLoader | null = null

  constructor(opts: OrchestratorOptions) {
    const available: Record<string, Tool> = {
      file: new FileTool(opts.workspace),
      shell: new ShellTool(opts.workspace),
      fetch: new FetchTool(),
      code: new CodeTool(opts),
      memory: new MemoryTool(opts.config?.qdrantUrl),
      jmem: new JMemTool(opts.config?.pythonBin ?? 'python3'),
    }

    // Memory tools always enabled — they degrade gracefully if Qdrant is down
    const enabled = opts.tools ?? Object.keys(available)
    for (const name of enabled) {
      if (available[name]) this.tools.set(name, available[name])
    }
    // Always register memory tools — they degrade gracefully
    if (!this.tools.has('memory')) this.tools.set('memory', available.memory)
    if (!this.tools.has('jmem')) this.tools.set('jmem', available.jmem)
  }

  get(name: string): Tool | undefined {
    return this.tools.get(name)
  }

  getDefinitions(): ToolDefinition[] {
    return Array.from(this.tools.values()).flatMap(t => t.definitions())
  }

  getDeferredDefinitions(): ToolDefinition[] {
    if (!this.deferredLoader) {
      this.deferredLoader = new DeferredToolLoader(this.getDefinitions())
      this.tools.set('tool_search', this.deferredLoader)
    }
    return this.deferredLoader.definitions()
  }
}
