/**
 * Orchestrator — the central agentic loop.
 * Manages provider calls, tool dispatch, context compaction, and audit logging.
 * Mirrors Claude Code's agent loop but adds multi-provider support and permission gating.
 */

import type { OrchestratorOptions, AgentEvent, ExecutionPlan } from './types.js'
import { ClaudeProvider } from '../providers/claude.js'
import { GeminiProvider } from '../providers/gemini.js'
import { ClaudeAgentSDKProvider } from '../providers/claude-agent-sdk.js'
import { ToolRegistry } from '../tools/registry.js'
import { MemoryStore } from '../memory/store.js'
import { ContextManager } from './context.js'
import { PermissionGate } from '../audit/permissions.js'
import type { BaseProvider } from '../providers/base.js'

export class Orchestrator {
  private provider: BaseProvider
  private tools: ToolRegistry
  private memory: MemoryStore
  private context: ContextManager
  private gate: PermissionGate
  private opts: OrchestratorOptions
  private useDeferredTools: boolean
  private deferredSearchDone: boolean = false

  constructor(opts: OrchestratorOptions) {
    this.opts = opts
    this.useDeferredTools = opts.deferredTools ?? false
    this.provider = opts.provider === 'gemini'
      ? new GeminiProvider(opts)
      : opts.provider === 'claude-agent-sdk'
        ? new ClaudeAgentSDKProvider(opts)
        : new ClaudeProvider(opts)
    this.tools = new ToolRegistry(opts)
    this.memory = new MemoryStore(opts.config?.qdrantUrl)
    this.context = new ContextManager(opts.compactThreshold)
    this.gate = new PermissionGate(opts.config?.permissions ?? {})
  }

  async planTask(prompt: string): Promise<ExecutionPlan> {
    const systemPrompt = `You are a planning agent. Given a task, output a JSON array of step strings describing exactly what you will do. Be specific. Output ONLY valid JSON.`
    const resp = await this.provider.complete({
      system: systemPrompt,
      messages: [{ role: 'user', content: prompt }],
      maxTokens: 1024,
    })
    try {
      const steps: string[] = JSON.parse(resp.content)
      return { steps, estimatedTokens: resp.inputTokens + resp.outputTokens }
    } catch {
      return { steps: [resp.content], estimatedTokens: resp.inputTokens }
    }
  }

  async *run(prompt: string, runOpts: { dryRun?: boolean } = {}): AsyncGenerator<AgentEvent> {
    const memories = await this.memory.recall(prompt, 5)
    const memoryContext = memories.length
      ? `\n\nRelevant context from memory:\n${memories.map(m => `- ${m.content}`).join('\n')}`
      : ''

    const systemPrompt = this.buildSystemPrompt() + memoryContext
    this.context.init(systemPrompt)
    this.context.addMessage({ role: 'user', content: prompt })

    yield { type: 'start', sessionId: this.context.sessionId }

    let iterations = 0
    const maxIterations = this.opts.config?.maxIterations ?? 50

    while (iterations < maxIterations) {
      iterations++

      // Auto-compact before hitting threshold
      if (this.context.tokenCount > this.opts.compactThreshold * 0.9) {
        yield { type: 'compacting', tokensBefore: this.context.tokenCount }
        await this.context.compact(this.provider)
        yield { type: 'compacted', tokensAfter: this.context.tokenCount }
      }

      // In deferred mode, use only tool_search on the first iteration
      // until the agent has discovered the tools it needs
      const useDeferred = this.useDeferredTools && !this.deferredSearchDone
      const toolDefs = useDeferred
        ? this.tools.getDeferredDefinitions()
        : this.tools.getDefinitions()

      const response = this.provider.streamWithTools({
        system: this.context.system,
        messages: this.context.messages as any,
        tools: toolDefs,
        maxTokens: this.opts.maxTokens,
      })

      let hasToolUse = false

      for await (const chunk of response) {
        if (chunk.type === 'text' && chunk.text) {
          this.context.appendAssistantText(chunk.text)
          yield { type: 'text', content: chunk.text }
        }

        if (chunk.type === 'tool_use') {
          hasToolUse = true
          yield { type: 'tool_call', toolName: chunk.name, toolInput: chunk.input }

          const permitted = this.gate.check(chunk.name!, chunk.input as Record<string, any>)
          if (!permitted.allowed) {
            yield { type: 'tool_blocked', toolName: chunk.name, reason: permitted.reason }
            this.context.addToolResult(chunk.id!, `BLOCKED: ${permitted.reason}`)
            continue
          }

          if (runOpts.dryRun) {
            this.context.addToolResult(chunk.id!, '[dry-run: not executed]')
            continue
          }

          const tool = this.tools.get(chunk.name!)
          if (!tool) {
            this.context.addToolResult(chunk.id!, `Unknown tool: ${chunk.name}`)
            continue
          }

          try {
            const result = await tool.execute(chunk.input as Record<string, any>)
            this.context.addToolResult(chunk.id!, result)
            yield { type: 'tool_result', toolName: chunk.name, result }
            this.opts.audit?.logToolCall(chunk.name!, chunk.input as Record<string, any>, result)

            // After a tool_search call, switch to full definitions on next iteration
            if (chunk.name === 'tool_search') {
              this.deferredSearchDone = true
            }
          } catch (err: any) {
            const errMsg = `Error: ${err.message}`
            this.context.addToolResult(chunk.id!, errMsg)
            yield { type: 'tool_error', toolName: chunk.name, error: err.message }
          }
        }

        if (chunk.type === 'stop') {
          if (chunk.stopReason === 'end_turn' && !hasToolUse) {
            await this.memory.store(prompt, this.context.lastAssistantText())
            yield { type: 'complete', iterations, tokenCount: this.context.tokenCount }
            return
          }
          break // tool_use stop — loop continues for next iteration
        }
      }

      // If we got here without tool use, the model is done
      if (!hasToolUse) {
        await this.memory.store(prompt, this.context.lastAssistantText())
        yield { type: 'complete', iterations, tokenCount: this.context.tokenCount }
        return
      }
    }

    yield { type: 'error', message: `Max iterations (${maxIterations}) reached` }
  }

  private buildSystemPrompt(): string {
    return `You are PFAA — an enterprise autonomous agent for software development and automation.
You have access to a suite of tools and a Python 3.15 execution sandbox.
You are methodical, precise, and always prefer verified results over assumptions.
When writing or running code, use Python 3.15 idioms (match/case, improved type hints, asyncio.TaskGroup, etc.).
Always explain what you are doing before doing it.
If a task is ambiguous, clarify before acting.
Working directory: ${this.opts.workspace}`
  }
}
