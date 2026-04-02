/**
 * A0 Bridge — connects PFAA agents with Agent Zero v1.5+.
 *
 * Capabilities:
 * - Create A0 plugins from PFAA skills
 * - Bidirectional A2A communication
 * - Memory sync between JMEM and A0's vector memory
 */

import { AgentZeroClient, type A0Response } from './client.js'

export interface A0BridgeConfig {
  a0Url: string
  a0ApiKey: string
  timeout?: number
}

export interface PluginManifest {
  name: string
  title: string
  description: string
  version: string
}

export interface A2AMessage {
  from: string
  to: string
  type: 'task' | 'result' | 'memory_sync' | 'status'
  content: string
  metadata?: Record<string, unknown>
}

export class A0Bridge {
  private client: AgentZeroClient

  constructor(config: A0BridgeConfig) {
    this.client = new AgentZeroClient(
      config.a0Url,
      config.a0ApiKey,
      config.timeout,
    )
  }

  async isAvailable(): Promise<boolean> {
    try {
      await this.client.health()
      return true
    } catch {
      return false
    }
  }

  /** Send a task to Agent Zero and wait for the response. */
  async delegateTask(
    task: string,
    context?: string,
    contextId?: string,
  ): Promise<A0Response> {
    const prompt = context ? `Context: ${context}\n\nTask: ${task}` : task
    return this.client.message(prompt, { contextId })
  }

  /** Send a task and poll until Agent Zero finishes. */
  async delegateAndWait(
    task: string,
    context?: string,
    contextId?: string,
  ): Promise<string> {
    const prompt = context ? `Context: ${context}\n\nTask: ${task}` : task
    return this.client.messageAndWait(prompt, contextId)
  }

  /** Generate an A0 plugin manifest from a PFAA skill definition. */
  generatePluginManifest(
    skillName: string,
    description: string,
  ): PluginManifest {
    return {
      name: `pfaa_${skillName.replace(/-/g, '_')}`,
      title: `PFAA: ${skillName}`,
      description,
      version: '1.0.0',
    }
  }

  /** Sync a JMEM memory to Agent Zero via message. */
  async syncMemory(
    content: string,
    level: string,
    contextId?: string,
  ): Promise<void> {
    const prompt = `Store this knowledge in your memory:\n\nLevel: ${level}\nContent: ${content}`
    await this.client.message(prompt, { contextId })
  }

  /** Get the underlying client for direct API access. */
  getClient(): AgentZeroClient {
    return this.client
  }
}
