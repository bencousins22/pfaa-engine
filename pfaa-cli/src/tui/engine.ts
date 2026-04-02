/**
 * ConversationEngine — Streaming conversation engine for PFAA CLI.
 *
 * This is the core of the interactive CLI. It manages multi-turn conversations
 * with Claude via the Anthropic SDK, streaming responses as typed events through
 * an async generator. The engine handles the full agentic loop:
 *
 *   1. Send user message + conversation history to Claude
 *   2. Stream SSE events, yielding typed StreamEvents to the caller
 *   3. Accumulate tool_use blocks during streaming
 *   4. After message_stop with stop_reason=tool_use: execute tools locally
 *   5. Append tool_result messages and loop back to step 1
 *   6. Repeat until end_turn or max turns reached
 *
 * Tool execution runs on the local machine: Read, Write, Edit use Node fs;
 * Bash uses child_process; Glob uses Node 22+ fs.globSync with shell fallback;
 * Grep uses ripgrep (rg) with grep fallback.
 */

import Anthropic from '@anthropic-ai/sdk';
import {
  readFileSync,
  writeFileSync,
  existsSync,
  mkdirSync,
  statSync,
  globSync,
} from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { homedir, platform, release, arch, hostname } from 'node:os';
import { execSync } from 'node:child_process';
import { getLogger } from '../utils/logger.js';

const log = getLogger('engine');

// ── Stream Event Types ──────────────────────────────────────────────

export interface TextDeltaEvent {
  type: 'text_delta';
  text: string;
  timestamp: number;
}

export interface ThinkingDeltaEvent {
  type: 'thinking_delta';
  text: string;
  timestamp: number;
}

export interface ToolUseStartEvent {
  type: 'tool_use_start';
  toolUseId: string;
  toolCallId: string;
  toolName: string;
  timestamp: number;
}

export interface ToolInputDeltaEvent {
  type: 'tool_input_delta';
  toolUseId: string;
  toolCallId: string;
  partialJson: string;
  timestamp: number;
}

export interface ToolUseEndEvent {
  type: 'tool_use_end';
  toolUseId: string;
  toolCallId: string;
  toolName: string;
  input: Record<string, unknown>;
  timestamp: number;
}

export interface ToolResultEvent {
  type: 'tool_result';
  toolUseId: string;
  toolCallId: string;
  toolName: string;
  result: string;
  isError: boolean;
  durationMs: number;
  timestamp: number;
}

export interface MessageStartEvent {
  type: 'message_start';
  messageId: string;
  model: string;
  timestamp: number;
}

export interface MessageEndEvent {
  type: 'message_end';
  stopReason: string;
  inputTokens: number;
  outputTokens: number;
  timestamp: number;
}

export interface StatusEvent {
  type: 'status';
  message: string;
  timestamp: number;
}

export interface ErrorEvent {
  type: 'error';
  error: string;
  message: string;
  code?: string;
  retryable: boolean;
  timestamp: number;
}

export type StreamEvent =
  | TextDeltaEvent
  | ThinkingDeltaEvent
  | ToolUseStartEvent
  | ToolInputDeltaEvent
  | ToolUseEndEvent
  | ToolResultEvent
  | MessageStartEvent
  | MessageEndEvent
  | StatusEvent
  | ErrorEvent;

// ── Content Block Types ─────────────────────────────────────────────

export interface TextBlock {
  type: 'text';
  text: string;
}

export interface ToolUseBlock {
  type: 'tool_use';
  id: string;
  name: string;
  input: Record<string, unknown>;
}

export interface ToolResultBlock {
  type: 'tool_result';
  tool_use_id: string;
  content: string;
  is_error?: boolean;
}

export interface ThinkingBlock {
  type: 'thinking';
  thinking: string;
}

export type ContentBlock = TextBlock | ToolUseBlock | ToolResultBlock | ThinkingBlock;

export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: ContentBlock[] | string;
}

// ── Tool Definition & Handler ───────────────────────────────────────

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export type ToolHandler = (
  input: Record<string, unknown>,
  signal?: AbortSignal,
) => Promise<string>;

/** Legacy tool executor signature (used by App.tsx). */
export type ToolExecutor = (
  name: string,
  input: Record<string, unknown>,
  signal?: AbortSignal,
) => Promise<{ result: string; isError: boolean }>;

// ── Token Usage ─────────────────────────────────────────────────────

export interface TokenUsage {
  inputTokens: number;
  outputTokens: number;
}

// ── Engine Options ──────────────────────────────────────────────────

export interface ConversationEngineOptions {
  apiKey?: string;
  model?: string;
  tools?: ToolDefinition[];
  customHandlers?: Map<string, ToolHandler>;
  /** Legacy tool executor (wraps into per-tool handlers). Used by App.tsx. */
  toolExecutor?: ToolExecutor;
  systemPrompt?: string;
  maxTokens?: number;
  maxTurns?: number;
  cwd?: string;
}

// ── Credential Loading ──────────────────────────────────────────────

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

/**
 * Load Claude Code OAuth token from macOS Keychain or fallback file.
 * Claude Code stores subscription tokens under "Claude Code-credentials".
 * Returns { accessToken, refreshToken } or null.
 */
function loadClaudeCodeOAuthToken(): { accessToken: string; refreshToken?: string } | null {
  // 1. Check env var (used by CCR/remote)
  if (process.env['CLAUDE_CODE_OAUTH_TOKEN']) {
    return { accessToken: process.env['CLAUDE_CODE_OAUTH_TOKEN'] };
  }

  // 2. Read from macOS Keychain
  try {
    const { execSync } = require('node:child_process');
    const username = process.env['USER'] || require('node:os').userInfo().username;
    const raw = execSync(
      `security find-generic-password -a "${username}" -s "Claude Code-credentials" -w 2>/dev/null`,
      { encoding: 'utf-8', timeout: 5000 },
    ).trim();

    if (raw) {
      const data = JSON.parse(raw);
      const oauth = data?.claudeAiOauth;
      if (oauth?.accessToken) {
        log.info('Loaded OAuth token from macOS Keychain (Claude Code subscription)');
        return { accessToken: oauth.accessToken, refreshToken: oauth.refreshToken };
      }
    }
  } catch {
    // Keychain not available or no entry
  }

  // 3. Fallback: read from ~/.claude/.credentials.json
  try {
    const credPath = join(homedir(), '.claude', '.credentials.json');
    if (existsSync(credPath)) {
      const data = JSON.parse(readFileSync(credPath, 'utf-8'));
      const oauth = data?.claudeAiOauth;
      if (oauth?.accessToken) {
        log.info('Loaded OAuth token from ~/.claude/.credentials.json');
        return { accessToken: oauth.accessToken, refreshToken: oauth.refreshToken };
      }
    }
  } catch {
    // Ignore
  }

  return null;
}

// ── System Prompt Builder ───────────────────────────────────────────

export function buildSystemPrompt(cwd: string): string {
  const date = new Date().toISOString().split('T')[0];
  const os = `${platform()} ${release()} (${arch()})`;
  const shell = process.env['SHELL'] || '/bin/zsh';
  const user = process.env['USER'] || process.env['USERNAME'] || 'unknown';

  return [
    'You are PFAA (Phase-Fluid Agent Architecture), an expert AI coding assistant.',
    'You help users with coding, analysis, debugging, file operations, and system tasks.',
    '',
    'Environment:',
    `- Date: ${date}`,
    `- OS: ${os}`,
    `- Shell: ${shell}`,
    `- User: ${user}`,
    `- Hostname: ${hostname()}`,
    `- Working directory: ${cwd}`,
    `- Node.js: ${process.version}`,
    '',
    'Guidelines:',
    '- Be concise and precise. Avoid filler.',
    '- Use tools to gather information before answering when needed.',
    '- Always use absolute paths for file operations.',
    '- When running bash commands, prefer non-destructive operations.',
    '- For complex tasks, plan before executing.',
    '- Format code and structured data with markdown.',
    '- If a file read is large, use offset/limit to read relevant sections.',
    '- For edits, ensure old_string is unique in the file or use replace_all.',
    '- Never run destructive git commands (push --force, reset --hard) without being asked.',
  ].join('\n');
}

// ── Built-in Tool Definitions ───────────────────────────────────────

const BUILTIN_TOOLS: ToolDefinition[] = [
  {
    name: 'Read',
    description:
      'Read a file from the filesystem. Returns contents with line numbers (cat -n format). ' +
      'Use offset and limit to read portions of large files. Can read any text file.',
    input_schema: {
      type: 'object',
      properties: {
        file_path: {
          type: 'string',
          description: 'Absolute path to the file to read.',
        },
        offset: {
          type: 'number',
          description: 'Line number to start reading from (1-based). Default: 1.',
        },
        limit: {
          type: 'number',
          description: 'Maximum number of lines to read. Default: 2000.',
        },
      },
      required: ['file_path'],
    },
  },
  {
    name: 'Write',
    description:
      'Write content to a file. Creates parent directories if needed. Overwrites existing files. ' +
      'Prefer Edit for modifying existing files.',
    input_schema: {
      type: 'object',
      properties: {
        file_path: {
          type: 'string',
          description: 'Absolute path to the file to write.',
        },
        content: {
          type: 'string',
          description: 'The full content to write.',
        },
      },
      required: ['file_path', 'content'],
    },
  },
  {
    name: 'Edit',
    description:
      'Perform exact string replacement in a file. old_string must match exactly (including ' +
      'whitespace and indentation). If old_string is not unique, provide more context or use ' +
      'replace_all. old_string and new_string must be different.',
    input_schema: {
      type: 'object',
      properties: {
        file_path: {
          type: 'string',
          description: 'Absolute path to the file to edit.',
        },
        old_string: {
          type: 'string',
          description: 'The exact text to find and replace.',
        },
        new_string: {
          type: 'string',
          description: 'The replacement text.',
        },
        replace_all: {
          type: 'boolean',
          description: 'Replace all occurrences. Default: false.',
        },
      },
      required: ['file_path', 'old_string', 'new_string'],
    },
  },
  {
    name: 'Bash',
    description:
      'Execute a bash command and return stdout/stderr. Commands run in the working directory. ' +
      'Use absolute paths. Timeout defaults to 120 seconds (max 600s).',
    input_schema: {
      type: 'object',
      properties: {
        command: {
          type: 'string',
          description: 'The bash command to execute.',
        },
        timeout: {
          type: 'number',
          description: 'Timeout in milliseconds. Default: 120000, max: 600000.',
        },
        cwd: {
          type: 'string',
          description: 'Working directory for the command. Default: engine cwd.',
        },
      },
      required: ['command'],
    },
  },
  {
    name: 'Glob',
    description:
      'Find files matching a glob pattern. Returns absolute file paths, one per line. ' +
      'Supports patterns like "**/*.ts", "src/**/*.{js,jsx}".',
    input_schema: {
      type: 'object',
      properties: {
        pattern: {
          type: 'string',
          description: 'Glob pattern to match (e.g. "**/*.ts").',
        },
        path: {
          type: 'string',
          description: 'Directory to search in. Default: engine cwd.',
        },
      },
      required: ['pattern'],
    },
  },
  {
    name: 'Grep',
    description:
      'Search file contents using regex. Uses ripgrep (rg) if available, otherwise grep. ' +
      'Returns matching file paths (default), matching lines with context, or match counts.',
    input_schema: {
      type: 'object',
      properties: {
        pattern: {
          type: 'string',
          description: 'Regex pattern to search for.',
        },
        path: {
          type: 'string',
          description: 'File or directory to search. Default: engine cwd.',
        },
        glob: {
          type: 'string',
          description: 'Glob filter for files (e.g. "*.ts", "*.{js,jsx}").',
        },
        output_mode: {
          type: 'string',
          enum: ['content', 'files_with_matches', 'count'],
          description: 'Output mode. Default: "files_with_matches".',
        },
        context: {
          type: 'number',
          description: 'Lines of context around matches (for content mode).',
        },
        case_insensitive: {
          type: 'boolean',
          description: 'Case-insensitive search. Default: false.',
        },
        max_results: {
          type: 'number',
          description: 'Maximum results to return. Default: 250.',
        },
      },
      required: ['pattern'],
    },
  },
  {
    name: 'WebSearch',
    description:
      'Search the web for information. Returns summarized results. Use for questions ' +
      'about current events, documentation lookups, or when local context is insufficient.',
    input_schema: {
      type: 'object',
      properties: {
        query: {
          type: 'string',
          description: 'The search query.',
        },
        max_results: {
          type: 'number',
          description: 'Maximum results. Default: 5.',
        },
      },
      required: ['query'],
    },
  },
];

// ── Built-in Tool Handlers ──────────────────────────────────────────

function createBuiltinHandlers(engineCwd: string): Map<string, ToolHandler> {
  const handlers = new Map<string, ToolHandler>();

  // ── Read ──
  handlers.set('Read', async (input) => {
    const filePath = input['file_path'] as string;
    if (!filePath) return 'Error: file_path is required.';

    const absPath = resolve(filePath);

    if (!existsSync(absPath)) {
      return `Error: File not found: ${absPath}`;
    }

    try {
      const stat = statSync(absPath);
      if (stat.isDirectory()) {
        return `Error: Path is a directory, not a file: ${absPath}`;
      }

      const offset = Math.max(1, (input['offset'] as number | undefined) ?? 1);
      const limit = (input['limit'] as number | undefined) ?? 2000;

      const raw = readFileSync(absPath, 'utf-8');
      const lines = raw.split('\n');
      const startIdx = offset - 1;
      const endIdx = Math.min(lines.length, startIdx + limit);
      const slice = lines.slice(startIdx, endIdx);

      if (slice.length === 0) {
        return `(empty file or offset beyond end: ${absPath}, ${lines.length} lines total)`;
      }

      return slice.map((line, i) => `${startIdx + i + 1}\t${line}`).join('\n');
    } catch (err) {
      return `Error reading ${absPath}: ${err instanceof Error ? err.message : String(err)}`;
    }
  });

  // ── Write ──
  handlers.set('Write', async (input) => {
    const filePath = input['file_path'] as string;
    const content = input['content'] as string;
    if (!filePath) return 'Error: file_path is required.';
    if (content === undefined || content === null) return 'Error: content is required.';

    const absPath = resolve(filePath);

    try {
      const dir = dirname(absPath);
      if (!existsSync(dir)) {
        mkdirSync(dir, { recursive: true });
      }
      writeFileSync(absPath, content, 'utf-8');

      const lineCount = content.split('\n').length;
      const bytes = Buffer.byteLength(content, 'utf-8');
      return `Wrote ${lineCount} lines (${bytes} bytes) to ${absPath}`;
    } catch (err) {
      return `Error writing ${absPath}: ${err instanceof Error ? err.message : String(err)}`;
    }
  });

  // ── Edit ──
  handlers.set('Edit', async (input) => {
    const filePath = input['file_path'] as string;
    const oldStr = input['old_string'] as string;
    const newStr = input['new_string'] as string;
    const replaceAll = (input['replace_all'] as boolean) ?? false;

    if (!filePath) return 'Error: file_path is required.';
    if (oldStr === undefined || oldStr === '') return 'Error: old_string is required.';
    if (newStr === undefined) return 'Error: new_string is required.';
    if (oldStr === newStr) return 'Error: old_string and new_string must be different.';

    const absPath = resolve(filePath);

    if (!existsSync(absPath)) {
      return `Error: File not found: ${absPath}`;
    }

    try {
      const content = readFileSync(absPath, 'utf-8');

      if (!content.includes(oldStr)) {
        const lines = content.split('\n');
        const preview = lines.slice(0, 5).map((l, i) => `${i + 1}\t${l}`).join('\n');
        return (
          `Error: old_string not found in ${absPath}.\n` +
          `File has ${lines.length} lines. First 5:\n${preview}`
        );
      }

      // Uniqueness check when not replace_all
      if (!replaceAll) {
        const firstIdx = content.indexOf(oldStr);
        const secondIdx = content.indexOf(oldStr, firstIdx + 1);
        if (secondIdx !== -1) {
          const count = content.split(oldStr).length - 1;
          return (
            `Error: old_string appears ${count} times in the file. ` +
            `Provide more surrounding context to make it unique, or set replace_all: true.`
          );
        }
      }

      const updated = replaceAll
        ? content.replaceAll(oldStr, newStr)
        : content.replace(oldStr, newStr);

      writeFileSync(absPath, updated, 'utf-8');

      const count = replaceAll ? content.split(oldStr).length - 1 : 1;
      return `Edited ${absPath}: ${count} replacement${count !== 1 ? 's' : ''} made.`;
    } catch (err) {
      return `Error editing ${absPath}: ${err instanceof Error ? err.message : String(err)}`;
    }
  });

  // ── Bash ──
  handlers.set('Bash', async (input, _signal) => {
    const command = input['command'] as string;
    if (!command) return 'Error: command is required.';

    const timeout = Math.min(
      (input['timeout'] as number | undefined) ?? 120_000,
      600_000,
    );
    const cwd = (input['cwd'] as string | undefined) ?? engineCwd;

    try {
      const result = execSync(command, {
        cwd,
        timeout,
        maxBuffer: 10 * 1024 * 1024,
        encoding: 'utf-8',
        stdio: ['pipe', 'pipe', 'pipe'],
        env: { ...process.env },
        shell: process.env['SHELL'] || '/bin/zsh',
      });
      return result || '(no output)';
    } catch (err: unknown) {
      const e = err as {
        stdout?: string;
        stderr?: string;
        status?: number;
        killed?: boolean;
        signal?: string;
      };
      if (e.killed || e.signal === 'SIGTERM') {
        return `Error: Command timed out after ${timeout}ms.`;
      }
      const stdout = e.stdout || '';
      const stderr = e.stderr || '';
      const output = [stdout, stderr].filter(Boolean).join('\n');
      return output || `Command exited with code ${e.status ?? 1}`;
    }
  });

  // ── Glob ──
  handlers.set('Glob', async (input) => {
    const pattern = input['pattern'] as string;
    if (!pattern) return 'Error: pattern is required.';

    const searchPath = (input['path'] as string | undefined) ?? engineCwd;

    // Use Node.js fs.globSync (available in Node 22+)
    try {
      const matches = globSync(pattern, { cwd: searchPath });

      if (matches.length === 0) return '(no matches)';

      // Sort by modification time (newest first), cap at 500
      const withStats = matches.slice(0, 1000).map((m) => {
        const abs = resolve(searchPath, m);
        try {
          const s = statSync(abs);
          return { path: abs, mtime: s.mtimeMs };
        } catch {
          return { path: abs, mtime: 0 };
        }
      });

      withStats.sort((a, b) => b.mtime - a.mtime);
      return withStats.slice(0, 500).map((f) => f.path).join('\n');
    } catch {
      // Fallback to shell glob
      try {
        const result = execSync(
          `find ${shellQuote(searchPath)} -path ${shellQuote(join(searchPath, pattern))} -type f 2>/dev/null | head -500`,
          { encoding: 'utf-8', timeout: 30_000, shell: '/bin/zsh' },
        );
        return result.trim() || '(no matches)';
      } catch {
        return `Error: No matches for "${pattern}" in ${searchPath}`;
      }
    }
  });

  // ── Grep ──
  handlers.set('Grep', async (input) => {
    const pattern = input['pattern'] as string;
    if (!pattern) return 'Error: pattern is required.';

    const searchPath = (input['path'] as string | undefined) ?? engineCwd;
    const globFilter = input['glob'] as string | undefined;
    const outputMode = (input['output_mode'] as string | undefined) ?? 'files_with_matches';
    const context = input['context'] as number | undefined;
    const caseInsensitive = (input['case_insensitive'] as boolean) ?? false;
    const maxResults = (input['max_results'] as number | undefined) ?? 250;

    // Detect ripgrep availability (cached per handler set creation)
    const hasRg = (() => {
      try {
        execSync('which rg', { encoding: 'utf-8', stdio: 'pipe' });
        return true;
      } catch {
        return false;
      }
    })();

    const args: string[] = [];

    if (hasRg) {
      if (outputMode === 'files_with_matches') args.push('-l');
      else if (outputMode === 'count') args.push('-c');
      else args.push('-n');

      if (caseInsensitive) args.push('-i');
      if (context !== undefined && outputMode === 'content') args.push(`-C${context}`);
      if (globFilter) args.push('--glob', globFilter);
      args.push('--max-count', '1000');
      args.push('--', pattern, searchPath);

      const cmd = `rg ${args.map(shellQuote).join(' ')}`;

      try {
        const result = execSync(cmd, {
          encoding: 'utf-8',
          timeout: 30_000,
          maxBuffer: 5 * 1024 * 1024,
          stdio: ['pipe', 'pipe', 'pipe'],
          shell: '/bin/zsh',
        });
        if (!result.trim()) return '(no matches)';
        return result.trim().split('\n').slice(0, maxResults).join('\n');
      } catch (err: unknown) {
        const e = err as { status?: number; stdout?: string };
        if (e.status === 1) return '(no matches)';
        return e.stdout?.trim() || '(no matches)';
      }
    } else {
      // Fallback to grep
      args.push('-r', '-n');
      if (outputMode === 'files_with_matches') args.push('-l');
      else if (outputMode === 'count') args.push('-c');
      if (caseInsensitive) args.push('-i');
      if (context !== undefined && outputMode === 'content') args.push(`-C${context}`);
      if (globFilter) args.push(`--include=${globFilter}`);
      args.push('--', pattern, searchPath);

      const cmd = `grep ${args.map(shellQuote).join(' ')}`;

      try {
        const result = execSync(cmd, {
          encoding: 'utf-8',
          timeout: 30_000,
          maxBuffer: 5 * 1024 * 1024,
          stdio: ['pipe', 'pipe', 'pipe'],
          shell: '/bin/zsh',
        });
        if (!result.trim()) return '(no matches)';
        return result.trim().split('\n').slice(0, maxResults).join('\n');
      } catch (err: unknown) {
        const e = err as { status?: number; stdout?: string };
        if (e.status === 1) return '(no matches)';
        return e.stdout?.trim() || '(no matches)';
      }
    }
  });

  // ── WebSearch (stub -- requires external API integration) ──
  handlers.set('WebSearch', async (input) => {
    const query = input['query'] as string;
    if (!query) return 'Error: query is required.';
    return (
      `Web search not available in local engine. Query: "${query}"\n` +
      'Tip: Use Bash with curl to fetch URLs, or provide the information directly.'
    );
  });

  return handlers;
}

// ── Error Classification ────────────────────────────────────────────

interface ClassifiedError {
  message: string;
  code: string;
  retryable: boolean;
  retryDelayMs?: number;
}

function classifyApiError(err: unknown): ClassifiedError {
  if (err instanceof Anthropic.APIError) {
    const status = err.status;
    const msg = err.message || 'Unknown API error';

    if (status === 429) {
      return { message: `Rate limited: ${msg}`, code: 'RATE_LIMIT', retryable: true, retryDelayMs: 5000 };
    }
    if (status === 529) {
      return { message: `API overloaded: ${msg}`, code: 'OVERLOADED', retryable: true, retryDelayMs: 10_000 };
    }
    if (status >= 500) {
      return { message: `Server error (${status}): ${msg}`, code: 'SERVER_ERROR', retryable: true, retryDelayMs: 3000 };
    }
    if (status === 401) {
      return { message: 'Invalid API key. Check ANTHROPIC_API_KEY.', code: 'AUTH_ERROR', retryable: false };
    }
    if (status === 400) {
      return { message: `Bad request: ${msg}`, code: 'BAD_REQUEST', retryable: false };
    }
    return { message: `API error (${status}): ${msg}`, code: 'API_ERROR', retryable: false };
  }

  if (err instanceof Error) {
    if (/ECONNREFUSED|ETIMEDOUT|ENOTFOUND|fetch failed/i.test(err.message)) {
      return { message: `Network error: ${err.message}`, code: 'NETWORK_ERROR', retryable: true, retryDelayMs: 3000 };
    }
    if (err.name === 'AbortError') {
      return { message: 'Request aborted.', code: 'ABORT', retryable: false };
    }
    return { message: err.message, code: 'UNKNOWN', retryable: false };
  }

  return { message: String(err), code: 'UNKNOWN', retryable: false };
}

// ── Utilities ───────────────────────────────────────────────────────

/** Quote a string for safe shell argument passing. */
function shellQuote(s: string): string {
  return "'" + s.replace(/'/g, "'\\''") + "'";
}

function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

// ── Conversation Engine ─────────────────────────────────────────────

const DEFAULT_MODEL = 'claude-sonnet-4-20250514';
const DEFAULT_MAX_TURNS = 40;
const DEFAULT_MAX_TOKENS = 16_384;
const MAX_TOOL_RESULT_CHARS = 100_000;

export class ConversationEngine {
  private client: Anthropic | null = null;
  private messages: ConversationMessage[];
  private tools: ToolDefinition[];
  private toolHandlers: Map<string, ToolHandler>;
  private legacyExecutor: ToolExecutor | null = null;
  private systemPrompt: string;
  private model: string;
  private maxTokens: number;
  private maxTurns: number;
  private cwd: string;
  private abortController: AbortController | null = null;
  private _totalUsage: TokenUsage = { inputTokens: 0, outputTokens: 0 };

  /** @deprecated Use getUsage().inputTokens instead. Kept for App.tsx compatibility. */
  totalInputTokens = 0;
  /** @deprecated Use getUsage().outputTokens instead. Kept for App.tsx compatibility. */
  totalOutputTokens = 0;

  constructor(options: ConversationEngineOptions = {}) {
    const apiKey =
      options.apiKey ||
      process.env['ANTHROPIC_API_KEY'] ||
      loadSavedApiKey();

    if (apiKey) {
      // Direct API key mode
      try {
        this.client = new Anthropic({ apiKey });
      } catch {
        this.client = null;
      }
    } else {
      // Try Claude Code subscription (OAuth token from Keychain)
      const oauth = loadClaudeCodeOAuthToken();
      if (oauth) {
        try {
          // Claude Code pattern: apiKey=null, authToken=Bearer token
          // SDK uses authToken for Authorization: Bearer header
          this.client = new Anthropic({
            apiKey: null as unknown as string,
            authToken: oauth.accessToken,
          } as ConstructorParameters<typeof Anthropic>[0]);
          log.info('Using Claude Code subscription (OAuth) — token loaded');
        } catch (err) {
          log.warn('Failed to init Anthropic with OAuth token', { error: String(err) });
          this.client = null;
        }
      }
    }

    this.model = options.model || DEFAULT_MODEL;
    this.maxTokens = options.maxTokens ?? DEFAULT_MAX_TOKENS;
    this.maxTurns = options.maxTurns ?? DEFAULT_MAX_TURNS;
    this.cwd = options.cwd ?? process.cwd();
    this.messages = [];

    // Merge built-in tools with user-provided tools
    this.tools = [...BUILTIN_TOOLS, ...(options.tools ?? [])];

    // Merge built-in handlers with custom handlers
    this.toolHandlers = createBuiltinHandlers(this.cwd);
    if (options.customHandlers) {
      for (const [name, handler] of options.customHandlers) {
        this.toolHandlers.set(name, handler);
      }
    }

    // Support legacy toolExecutor option (wraps into per-tool handler)
    if (options.toolExecutor) {
      this.legacyExecutor = options.toolExecutor;
    }

    this.systemPrompt = options.systemPrompt ?? buildSystemPrompt(this.cwd);

    log.info('ConversationEngine initialized', {
      model: this.model,
      tools: this.tools.length,
      cwd: this.cwd,
    });
  }

  /** Whether a live API connection is available. */
  get isLive(): boolean {
    return this.client !== null;
  }

  // ── Core Streaming Method ─────────────────────────────────────────

  /**
   * Send a user message and yield streaming events.
   *
   * This is an async generator that yields StreamEvent objects as the model
   * responds. The caller (TUI) consumes these to render text, tool calls,
   * progress, and errors in real time.
   *
   * The generator handles the full agentic loop internally: if the model
   * requests tool use, tools are executed and the loop continues until
   * the model produces a final text response or max turns is reached.
   */
  async *query(userMessage: string): AsyncGenerator<StreamEvent> {
    if (!this.client) {
      yield this.ev<ErrorEvent>({
        type: 'error',
        error: 'No API key configured. Set ANTHROPIC_API_KEY or pass --api-key.',
        code: 'NO_API_KEY',
        retryable: false,
      });
      return;
    }

    // Append user message to conversation history
    this.messages.push({ role: 'user', content: userMessage });

    this.abortController = new AbortController();
    const { signal } = this.abortController;

    let turnCount = 0;

    try {
      while (turnCount < this.maxTurns) {
        if (signal.aborted) {
          yield this.ev<ErrorEvent>({
            type: 'error',
            error: 'Request cancelled.',
            code: 'ABORT',
            retryable: false,
          });
          return;
        }

        turnCount++;

        // Accumulators for this API call
        const assistantBlocks: ContentBlock[] = [];
        let currentToolId = '';
        let currentToolName = '';
        let accToolInput = '';
        let accText = '';
        let accThinking = '';
        let currentBlockType: string | null = null;
        let stopReason = 'end_turn';
        let inputTokens = 0;
        let outputTokens = 0;
        let messageId = '';

        // ── Create streaming request ──
        let stream: ReturnType<Anthropic['messages']['stream']>;
        try {
          stream = this.client!.messages.stream({
            model: this.model,
            max_tokens: this.maxTokens,
            system: this.systemPrompt,
            messages: this.messages as Anthropic.Messages.MessageParam[],
            tools: this.tools.map((t) => ({
              name: t.name,
              description: t.description,
              input_schema: t.input_schema as Anthropic.Messages.Tool.InputSchema,
            })),
          });
        } catch (err) {
          const classified = classifyApiError(err);
          yield this.ev<ErrorEvent>({
            type: 'error',
            error: classified.message,
            code: classified.code,
            retryable: classified.retryable,
          });
          return;
        }

        // Wire abort signal to stream cancellation
        const onAbort = () => stream.abort();
        signal.addEventListener('abort', onAbort, { once: true });

        // ── Process SSE events ──
        try {
          for await (const event of stream) {
            if (signal.aborted) {
              stream.abort();
              yield this.ev<StatusEvent>({ type: 'status', message: 'Cancelled.' });
              return;
            }

            switch (event.type) {
              // ── message_start: first event, contains message ID and initial usage ──
              case 'message_start': {
                const msg = (event as unknown as {
                  message: { id: string; model: string; usage?: { input_tokens: number } };
                }).message;
                messageId = msg?.id || '';
                if (msg?.usage?.input_tokens) inputTokens = msg.usage.input_tokens;
                yield this.ev<MessageStartEvent>({
                  type: 'message_start',
                  messageId,
                  model: msg?.model || this.model,
                });
                break;
              }

              // ── content_block_start: beginning of a text, tool_use, or thinking block ──
              case 'content_block_start': {
                const cb = (event as { content_block: { type: string; id?: string; name?: string } }).content_block;
                currentBlockType = cb.type;

                if (cb.type === 'tool_use') {
                  currentToolId = cb.id || '';
                  currentToolName = cb.name || '';
                  accToolInput = '';
                  yield this.ev<ToolUseStartEvent>({
                    type: 'tool_use_start',
                    toolCallId: currentToolId,
                    toolName: currentToolName,
                  });
                } else if (cb.type === 'text') {
                  accText = '';
                } else if (cb.type === 'thinking') {
                  accThinking = '';
                }
                break;
              }

              // ── content_block_delta: incremental content for current block ──
              case 'content_block_delta': {
                const delta = (event as {
                  delta: { type: string; text?: string; partial_json?: string; thinking?: string };
                }).delta;

                if (delta.type === 'text_delta' && delta.text) {
                  accText += delta.text;
                  yield this.ev<TextDeltaEvent>({
                    type: 'text_delta',
                    text: delta.text,
                  });
                } else if (delta.type === 'input_json_delta' && delta.partial_json) {
                  accToolInput += delta.partial_json;
                  yield this.ev<ToolInputDeltaEvent>({
                    type: 'tool_input_delta',
                    toolCallId: currentToolId,
                    partialJson: delta.partial_json,
                  });
                } else if (delta.type === 'thinking_delta' && delta.thinking) {
                  accThinking += delta.thinking;
                  yield this.ev<ThinkingDeltaEvent>({
                    type: 'thinking_delta',
                    text: delta.thinking,
                  });
                }
                break;
              }

              // ── content_block_stop: finalize the current block ──
              case 'content_block_stop': {
                if (currentBlockType === 'tool_use' && currentToolId) {
                  let parsed: Record<string, unknown> = {};
                  try {
                    parsed = accToolInput ? JSON.parse(accToolInput) : {};
                  } catch {
                    log.warn('Failed to parse tool input JSON', {
                      tool: currentToolName,
                      json: accToolInput.slice(0, 200),
                    });
                  }

                  const block: ToolUseBlock = {
                    type: 'tool_use',
                    id: currentToolId,
                    name: currentToolName,
                    input: parsed,
                  };
                  assistantBlocks.push(block);

                  yield this.ev<ToolUseEndEvent>({
                    type: 'tool_use_end',
                    toolCallId: currentToolId,
                    toolName: currentToolName,
                    input: parsed,
                  });

                  currentToolId = '';
                  currentToolName = '';
                  accToolInput = '';
                } else if (currentBlockType === 'text' && accText) {
                  assistantBlocks.push({ type: 'text', text: accText });
                  accText = '';
                } else if (currentBlockType === 'thinking' && accThinking) {
                  assistantBlocks.push({ type: 'thinking', thinking: accThinking });
                  accThinking = '';
                }
                currentBlockType = null;
                break;
              }

              // ── message_delta: updated stop_reason and output token count ──
              case 'message_delta': {
                const md = event as unknown as {
                  delta: { stop_reason?: string };
                  usage?: { output_tokens: number };
                };
                if (md.delta?.stop_reason) stopReason = md.delta.stop_reason;
                if (md.usage?.output_tokens) outputTokens = md.usage.output_tokens;
                break;
              }

              // ── message_stop: stream complete ──
              case 'message_stop':
                break;
            }
          }

          // Get authoritative final message for accurate usage counts
          const final = await stream.finalMessage();
          messageId = final.id;
          stopReason = final.stop_reason || 'end_turn';
          inputTokens = final.usage.input_tokens;
          outputTokens = final.usage.output_tokens;
        } catch (err) {
          if (signal.aborted) {
            yield this.ev<StatusEvent>({ type: 'status', message: 'Cancelled.' });
            return;
          }

          const classified = classifyApiError(err);
          yield this.ev<ErrorEvent>({
            type: 'error',
            error: classified.message,
            code: classified.code,
            retryable: classified.retryable,
          });

          // Retry once for transient errors on the first turn
          if (classified.retryable && turnCount <= 1 && classified.retryDelayMs) {
            yield this.ev<StatusEvent>({
              type: 'status',
              message: `Retrying after ${classified.code} (${classified.retryDelayMs}ms)...`,
            });
            await sleep(classified.retryDelayMs);
            continue;
          }
          return;
        } finally {
          signal.removeEventListener('abort', onAbort);
        }

        // ── Update totals and history ──
        this._totalUsage.inputTokens += inputTokens;
        this._totalUsage.outputTokens += outputTokens;
        this.totalInputTokens = this._totalUsage.inputTokens;
        this.totalOutputTokens = this._totalUsage.outputTokens;

        if (assistantBlocks.length > 0) {
          this.messages.push({ role: 'assistant', content: assistantBlocks });
        }

        yield this.ev<MessageEndEvent>({
          type: 'message_end',
          stopReason,
          inputTokens,
          outputTokens,
        });

        // ── Tool execution loop ──
        if (stopReason === 'tool_use') {
          const toolBlocks = assistantBlocks.filter(
            (b): b is ToolUseBlock => b.type === 'tool_use',
          );

          if (toolBlocks.length === 0) break;

          const toolResults: ToolResultBlock[] = [];

          for (const tool of toolBlocks) {
            if (signal.aborted) {
              yield this.ev<StatusEvent>({ type: 'status', message: 'Cancelled.' });
              return;
            }

            yield this.ev<StatusEvent>({
              type: 'status',
              message: `Running ${tool.name}...`,
            });

            const t0 = performance.now();
            let result: string;
            let isError = false;

            try {
              result = await this.executeTool(tool.name, tool.input, signal);
            } catch (err) {
              result = `Tool error: ${err instanceof Error ? err.message : String(err)}`;
              isError = true;
            }

            const durationMs = Math.round(performance.now() - t0);

            // Truncate oversized results to avoid blowing context limits
            if (result.length > MAX_TOOL_RESULT_CHARS) {
              result =
                result.slice(0, MAX_TOOL_RESULT_CHARS) +
                `\n\n[Truncated: ${result.length} total chars, showing first ${MAX_TOOL_RESULT_CHARS}]`;
            }

            yield this.ev<ToolResultEvent>({
              type: 'tool_result',
              toolCallId: tool.id,
              toolName: tool.name,
              result,
              isError,
              durationMs,
            });

            toolResults.push({
              type: 'tool_result',
              tool_use_id: tool.id,
              content: result,
              is_error: isError,
            });
          }

          // Add tool results as user message (Anthropic API format requirement)
          this.messages.push({ role: 'user', content: toolResults });

          // Continue the agentic loop -- next iteration calls the API again
          continue;
        }

        // Not tool_use (end_turn, max_tokens, etc.) -- conversation turn complete
        break;
      }

      if (turnCount >= this.maxTurns) {
        yield this.ev<ErrorEvent>({
          type: 'error',
          error: `Reached maximum tool turns (${this.maxTurns}).`,
          code: 'MAX_TURNS',
          retryable: false,
        });
      }
    } finally {
      this.abortController = null;
    }
  }

  // ── Public API ────────────────────────────────────────────────────

  /** Cancel the current streaming query. */
  abort(): void {
    if (this.abortController) {
      this.abortController.abort();
      log.info('Query aborted');
    }
  }

  /** Get full conversation history. */
  getMessages(): ConversationMessage[] {
    return [...this.messages];
  }

  /** Get cumulative token usage across all turns. */
  getUsage(): TokenUsage {
    return { ...this._totalUsage };
  }

  /** Get registered tool definitions. */
  getTools(): ToolDefinition[] {
    return [...this.tools];
  }

  /** Register a new tool at runtime. */
  addTool(definition: ToolDefinition, handler: ToolHandler): void {
    this.tools.push(definition);
    this.toolHandlers.set(definition.name, handler);
  }

  /** Replace the system prompt. */
  setSystemPrompt(prompt: string): void {
    this.systemPrompt = prompt;
  }

  /** Append extra context to the system prompt (e.g., CLAUDE.md contents). */
  appendSystemPrompt(extra: string): void {
    this.systemPrompt += '\n\n' + extra;
  }

  /** Clear conversation history and token counters. */
  reset(): void {
    this.messages = [];
    this._totalUsage = { inputTokens: 0, outputTokens: 0 };
    log.info('Conversation reset');
  }

  /** Number of messages in conversation history. */
  get messageCount(): number {
    return this.messages.length;
  }

  /** Current working directory used by tool handlers. */
  get workingDirectory(): string {
    return this.cwd;
  }

  /** Update working directory. Rebuilds built-in tool handlers for new cwd. */
  setCwd(newCwd: string): void {
    this.cwd = newCwd;
    // Preserve custom handlers while rebuilding builtins
    const builtinNames = new Set(BUILTIN_TOOLS.map((t) => t.name));
    const customs = new Map<string, ToolHandler>();
    for (const [name, handler] of this.toolHandlers) {
      if (!builtinNames.has(name)) customs.set(name, handler);
    }
    this.toolHandlers = createBuiltinHandlers(newCwd);
    for (const [name, handler] of customs) {
      this.toolHandlers.set(name, handler);
    }
  }

  // ── Private ───────────────────────────────────────────────────────

  /** Execute a tool by name using the registered handler or legacy executor. */
  private async executeTool(
    name: string,
    input: Record<string, unknown>,
    signal?: AbortSignal,
  ): Promise<string> {
    log.debug('Executing tool', { name, keys: Object.keys(input) });

    // Legacy executor takes priority if set (allows App.tsx to override all tools)
    if (this.legacyExecutor) {
      const { result, isError } = await this.legacyExecutor(name, input, signal);
      if (isError) throw new Error(result);
      log.debug('Tool completed (legacy executor)', { name, chars: result.length });
      return result;
    }

    const handler = this.toolHandlers.get(name);
    if (!handler) {
      return `Error: Unknown tool "${name}". Available: ${[...this.toolHandlers.keys()].join(', ')}`;
    }

    const result = await handler(input, signal);

    log.debug('Tool completed', { name, chars: result.length });
    return result;
  }

  /**
   * Create a timestamped event with backward-compatible fields.
   * Auto-populates toolCallId (alias for toolUseId) and message (alias for error).
   */
  private ev<T extends StreamEvent>(partial: Record<string, unknown>): T {
    const event: Record<string, unknown> = { ...partial, timestamp: Date.now() };

    // Backward compat: toolCallId mirrors toolUseId (used by App.tsx)
    if (event['toolUseId'] !== undefined && event['toolCallId'] === undefined) {
      event['toolCallId'] = event['toolUseId'];
    }

    // Backward compat: message mirrors error on ErrorEvent (used by App.tsx)
    if (event['type'] === 'error' && event['error'] !== undefined && event['message'] === undefined) {
      event['message'] = event['error'];
    }

    return event as T;
  }
}

// ── Convenience: collect full text from a query ─────────────────────

/**
 * Run a query and return the complete text response.
 * Useful for programmatic / non-interactive usage where streaming is not needed.
 */
export async function queryText(
  engine: ConversationEngine,
  message: string,
): Promise<{ text: string; usage: TokenUsage }> {
  let text = '';
  for await (const event of engine.query(message)) {
    if (event.type === 'text_delta') {
      text += event.text;
    }
  }
  return { text, usage: engine.getUsage() };
}

// ── Re-exports for external consumers ───────────────────────────────

export { BUILTIN_TOOLS, buildSystemPrompt as buildDefaultSystemPrompt, createBuiltinHandlers, classifyApiError };
