/**
 * Claude API Client — Direct Anthropic SDK integration for Aussie Agents.
 *
 * Provides real Claude API calls with graceful fallback to simulated
 * responses when no API key is available. Supports both simple ask
 * and tool-use patterns.
 */

import Anthropic from '@anthropic-ai/sdk';
import { readFileSync, existsSync } from 'node:fs';
import { join } from 'node:path';
import { homedir } from 'node:os';
import { getLogger } from '../utils/logger.js';

const log = getLogger('claude-client');

const MODEL = 'claude-sonnet-4-20250514';

/**
 * Load API key from ~/.pfaa/credentials.json if it exists.
 */
function loadSavedApiKey(): string | undefined {
  try {
    const credPath = join(homedir(), '.pfaa', 'credentials.json');
    if (existsSync(credPath)) {
      const creds = JSON.parse(readFileSync(credPath, 'utf-8'));
      return creds.anthropicApiKey || undefined;
    }
  } catch {
    // Ignore read errors
  }
  return undefined;
}

// ── Types ────────────────────────────────────────────────────────────

export interface Tool {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface ToolUseBlock {
  type: 'tool_use';
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface TextBlock {
  type: 'text';
  text: string;
}

export interface ToolCallResult {
  text: string;
  toolCalls: ToolUseBlock[];
  stopReason: string;
  inputTokens: number;
  outputTokens: number;
}

// ── Client ───────────────────────────────────────────────────────────

export class ClaudeClient {
  private client: Anthropic | null = null;
  private apiKey: string | undefined;

  constructor(apiKey?: string) {
    this.apiKey = apiKey || process.env['ANTHROPIC_API_KEY'] || loadSavedApiKey();

    if (this.apiKey) {
      try {
        this.client = new Anthropic({ apiKey: this.apiKey });
        log.info('Claude API client initialized (live mode)');
      } catch (err) {
        log.warn('Failed to initialize Anthropic SDK', {
          error: err instanceof Error ? err.message : String(err),
        });
        this.client = null;
      }
    } else {
      log.info('No API key found — running in simulated mode');
    }
  }

  /** Whether a live API connection is available. */
  get isAvailable(): boolean {
    return this.client !== null;
  }

  /**
   * Send a simple prompt to Claude and get a text response.
   * Falls back to simulated output when no API key is configured.
   */
  async ask(systemPrompt: string, userMessage: string): Promise<string> {
    if (!this.client) {
      return this.simulateAsk(systemPrompt, userMessage);
    }

    try {
      const response = await this.client.messages.create({
        model: MODEL,
        max_tokens: 4096,
        system: systemPrompt,
        messages: [{ role: 'user', content: userMessage }],
      });

      const textBlocks = response.content.filter(
        (block): block is Anthropic.TextBlock => block.type === 'text',
      );

      const text = textBlocks.map((b) => b.text).join('\n');

      log.debug('Claude response received', {
        inputTokens: response.usage.input_tokens,
        outputTokens: response.usage.output_tokens,
        stopReason: response.stop_reason,
      });

      return text;
    } catch (err) {
      log.error('Claude API error, falling back to simulation', {
        error: err instanceof Error ? err.message : String(err),
      });
      return this.simulateAsk(systemPrompt, userMessage);
    }
  }

  /**
   * Send a prompt with tool definitions and get structured results.
   * Falls back to simulated output when no API key is configured.
   */
  async askWithTools(
    systemPrompt: string,
    userMessage: string,
    tools: Tool[],
  ): Promise<ToolCallResult> {
    if (!this.client) {
      return this.simulateToolCall(systemPrompt, userMessage, tools);
    }

    try {
      const anthropicTools: Anthropic.Messages.Tool[] = tools.map((t) => ({
        name: t.name,
        description: t.description,
        input_schema: t.input_schema as Anthropic.Messages.Tool.InputSchema,
      }));

      const response = await this.client.messages.create({
        model: MODEL,
        max_tokens: 4096,
        system: systemPrompt,
        messages: [{ role: 'user', content: userMessage }],
        tools: anthropicTools,
      });

      const textBlocks = response.content.filter(
        (block): block is Anthropic.TextBlock => block.type === 'text',
      );
      const toolBlocks = response.content.filter(
        (block): block is Anthropic.Messages.ToolUseBlock => block.type === 'tool_use',
      );

      return {
        text: textBlocks.map((b) => b.text).join('\n'),
        toolCalls: toolBlocks.map((b) => ({
          type: 'tool_use' as const,
          id: b.id,
          name: b.name,
          input: b.input as Record<string, unknown>,
        })),
        stopReason: response.stop_reason || 'end_turn',
        inputTokens: response.usage.input_tokens,
        outputTokens: response.usage.output_tokens,
      };
    } catch (err) {
      log.error('Claude API tool call error, falling back to simulation', {
        error: err instanceof Error ? err.message : String(err),
      });
      return this.simulateToolCall(systemPrompt, userMessage, tools);
    }
  }

  // ── Simulation Fallbacks ──────────────────────────────────────────

  private simulateAsk(systemPrompt: string, userMessage: string): string {
    log.debug('Using simulated response (no API key)');
    return (
      `[Simulated] Based on the prompt: "${userMessage.slice(0, 80)}..."\n\n` +
      `Analysis complete. This is a simulated response because no ANTHROPIC_API_KEY ` +
      `is configured. Set your API key to get real Claude responses:\n\n` +
      `  export ANTHROPIC_API_KEY=sk-ant-...\n` +
      `  pfaa config set-api-key <key>\n`
    );
  }

  private simulateToolCall(
    _systemPrompt: string,
    userMessage: string,
    tools: Tool[],
  ): ToolCallResult {
    log.debug('Using simulated tool call (no API key)');
    return {
      text:
        `[Simulated] Would process: "${userMessage.slice(0, 80)}..." ` +
        `with ${tools.length} tools available. Configure ANTHROPIC_API_KEY for live results.`,
      toolCalls: [],
      stopReason: 'end_turn',
      inputTokens: 0,
      outputTokens: 0,
    };
  }
}
