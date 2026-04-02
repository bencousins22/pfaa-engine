/**
 * PFAA CLI Tool Registry — Complete tool definitions and executors
 * for Claude tool_use during conversations.
 *
 * Tools: Read, Write, Edit, Bash, Glob, Grep, WebSearch
 */

import * as fs from "node:fs";
import * as path from "node:path";
import { execSync } from "node:child_process";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ToolDefinition {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface ToolResult {
  tool_use_id: string;
  content: string;
  is_error?: boolean;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MAX_OUTPUT_CHARS = 10_000;
const DEFAULT_BASH_TIMEOUT_MS = 30_000;
const DEFAULT_READ_LIMIT = 2000;

/** Commands that are too dangerous to allow. */
const BLOCKED_COMMANDS = [
  /\brm\s+(-\w*)?r\w*\s+(-\w*\s+)*\/\s*$/,  // rm -rf /
  /\bmkfs\b/,
  /\bdd\s+.*of=\/dev\/[sh]d/,
  /:(){ :|:& };:/,  // fork bomb
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function truncate(text: string, max = MAX_OUTPUT_CHARS): string {
  if (text.length <= max) return text;
  const half = Math.floor(max / 2) - 30;
  return (
    text.slice(0, half) +
    `\n\n... [truncated ${text.length - max} chars] ...\n\n` +
    text.slice(-half)
  );
}

function addLineNumbers(content: string, offset: number): string {
  const lines = content.split("\n");
  const width = String(offset + lines.length).length;
  return lines
    .map((line, i) => `${String(offset + i + 1).padStart(width)}\t${line}`)
    .join("\n");
}

/**
 * Recursively walk a directory yielding file paths that match a glob-like
 * pattern. Supports `*`, `**`, and `?` wildcards.
 */
function globMatch(root: string, pattern: string): string[] {
  const results: string[] = [];
  const segments = pattern.split("/").filter(Boolean);

  function patternToRegex(seg: string): RegExp {
    let re = seg
      .replace(/[.+^${}()|[\]\\]/g, "\\$&")
      .replace(/\*\*/g, "<<<GLOBSTAR>>>")
      .replace(/\*/g, "[^/]*")
      .replace(/\?/g, "[^/]")
      .replace(/<<<GLOBSTAR>>>/g, ".*");
    return new RegExp(`^${re}$`);
  }

  function walk(dir: string, segIdx: number): void {
    if (segIdx >= segments.length) return;

    const seg = segments[segIdx];
    const isLast = segIdx === segments.length - 1;
    const isGlobstar = seg === "**";

    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }

    if (isGlobstar) {
      // Match zero directories (skip **)
      walk(dir, segIdx + 1);

      for (const entry of entries) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory() && !entry.name.startsWith(".")) {
          // Match one directory level and continue with **
          walk(full, segIdx);
        }
        if (isLast) {
          // ** at the end matches everything
          results.push(full);
          if (entry.isDirectory() && !entry.name.startsWith(".")) {
            walkAll(full);
          }
        }
      }
    } else {
      const re = patternToRegex(seg);
      for (const entry of entries) {
        if (!re.test(entry.name)) continue;
        const full = path.join(dir, entry.name);
        if (isLast) {
          results.push(full);
        } else if (entry.isDirectory()) {
          walk(full, segIdx + 1);
        }
      }
    }
  }

  /** Collect every file recursively (used when ** is at end). */
  function walkAll(dir: string): void {
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (entry.name.startsWith(".")) continue;
      const full = path.join(dir, entry.name);
      results.push(full);
      if (entry.isDirectory()) walkAll(full);
    }
  }

  walk(root, 0);
  return results.sort();
}

// ---------------------------------------------------------------------------
// Tool Definitions (JSON Schema)
// ---------------------------------------------------------------------------

const TOOL_DEFINITIONS: ToolDefinition[] = [
  {
    name: "Read",
    description:
      "Read a file from the filesystem. Returns content with line numbers (like cat -n). " +
      "Reads up to `limit` lines starting from `offset`.",
    input_schema: {
      type: "object",
      required: ["file_path"],
      properties: {
        file_path: {
          type: "string",
          description: "Absolute path to the file to read.",
        },
        offset: {
          type: "number",
          description:
            "1-based line number to start reading from. Defaults to 1.",
        },
        limit: {
          type: "number",
          description: `Maximum number of lines to read. Defaults to ${DEFAULT_READ_LIMIT}.`,
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "Write",
    description:
      "Write content to a file. Creates parent directories if they do not exist. " +
      "Overwrites the file if it already exists.",
    input_schema: {
      type: "object",
      required: ["file_path", "content"],
      properties: {
        file_path: {
          type: "string",
          description: "Absolute path to the file to write.",
        },
        content: {
          type: "string",
          description: "The full content to write to the file.",
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "Edit",
    description:
      "Replace an exact string in a file. The old_string must appear exactly once " +
      "in the file (unless it is not found, which is an error). Preserves file encoding.",
    input_schema: {
      type: "object",
      required: ["file_path", "old_string", "new_string"],
      properties: {
        file_path: {
          type: "string",
          description: "Absolute path to the file to edit.",
        },
        old_string: {
          type: "string",
          description: "The exact text to find (must be unique in the file).",
        },
        new_string: {
          type: "string",
          description: "The replacement text.",
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "Bash",
    description:
      "Execute a shell command and return stdout + stderr. " +
      "Output is truncated to 10K characters. Dangerous commands are blocked.",
    input_schema: {
      type: "object",
      required: ["command"],
      properties: {
        command: {
          type: "string",
          description: "The shell command to execute.",
        },
        timeout: {
          type: "number",
          description:
            "Timeout in milliseconds. Defaults to 30 000 (30 seconds). Max 300 000.",
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "Glob",
    description:
      "Find files matching a glob pattern (supports *, **, and ?). " +
      "Returns sorted list of matching absolute paths.",
    input_schema: {
      type: "object",
      required: ["pattern"],
      properties: {
        pattern: {
          type: "string",
          description:
            'Glob pattern to match, e.g. "**/*.ts" or "src/**/*.test.ts".',
        },
        path: {
          type: "string",
          description:
            "Root directory to search in. Defaults to current working directory.",
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "Grep",
    description:
      "Search file contents for a regex pattern. Returns matching lines with " +
      "file path, line number, and content.",
    input_schema: {
      type: "object",
      required: ["pattern"],
      properties: {
        pattern: {
          type: "string",
          description: "Regular expression pattern to search for.",
        },
        path: {
          type: "string",
          description:
            "File or directory to search in. Defaults to current working directory.",
        },
        include: {
          type: "string",
          description:
            'Glob filter for files to search, e.g. "*.ts" or "*.py".',
        },
      },
      additionalProperties: false,
    },
  },
  {
    name: "WebSearch",
    description:
      "Search the web for information. Returns relevant snippets and URLs.",
    input_schema: {
      type: "object",
      required: ["query"],
      properties: {
        query: {
          type: "string",
          description: "The search query.",
        },
      },
      additionalProperties: false,
    },
  },
];

// ---------------------------------------------------------------------------
// Tool Executors
// ---------------------------------------------------------------------------

async function executeRead(input: Record<string, unknown>): Promise<string> {
  const filePath = input.file_path as string;
  const offset = Math.max(1, (input.offset as number) || 1);
  const limit = (input.limit as number) || DEFAULT_READ_LIMIT;

  if (!path.isAbsolute(filePath)) {
    throw new Error(`file_path must be absolute, got: ${filePath}`);
  }

  const raw = fs.readFileSync(filePath, "utf-8");
  const allLines = raw.split("\n");
  const sliced = allLines.slice(offset - 1, offset - 1 + limit);
  const numbered = addLineNumbers(sliced.join("\n"), offset - 1);

  return truncate(numbered);
}

async function executeWrite(input: Record<string, unknown>): Promise<string> {
  const filePath = input.file_path as string;
  const content = input.content as string;

  if (!path.isAbsolute(filePath)) {
    throw new Error(`file_path must be absolute, got: ${filePath}`);
  }

  const dir = path.dirname(filePath);
  fs.mkdirSync(dir, { recursive: true });
  fs.writeFileSync(filePath, content, "utf-8");

  const lineCount = content.split("\n").length;
  const bytes = Buffer.byteLength(content, "utf-8");
  return `Wrote ${lineCount} lines (${bytes} bytes) to ${filePath}`;
}

async function executeEdit(input: Record<string, unknown>): Promise<string> {
  const filePath = input.file_path as string;
  const oldString = input.old_string as string;
  const newString = input.new_string as string;

  if (!path.isAbsolute(filePath)) {
    throw new Error(`file_path must be absolute, got: ${filePath}`);
  }

  const content = fs.readFileSync(filePath, "utf-8");

  // Count occurrences
  let count = 0;
  let searchFrom = 0;
  while (true) {
    const idx = content.indexOf(oldString, searchFrom);
    if (idx === -1) break;
    count++;
    searchFrom = idx + oldString.length;
  }

  if (count === 0) {
    throw new Error(
      `old_string not found in ${filePath}. Make sure the string matches exactly, including whitespace and indentation.`
    );
  }
  if (count > 1) {
    throw new Error(
      `old_string appears ${count} times in ${filePath}. It must be unique — provide more surrounding context to disambiguate.`
    );
  }

  const updated = content.replace(oldString, newString);
  fs.writeFileSync(filePath, updated, "utf-8");

  // Compute a summary: which line range was affected
  const beforeLines = content.slice(0, content.indexOf(oldString)).split("\n");
  const startLine = beforeLines.length;
  const oldLineCount = oldString.split("\n").length;
  const newLineCount = newString.split("\n").length;

  return (
    `Edited ${filePath}: replaced ${oldLineCount} line(s) starting at line ${startLine} ` +
    `with ${newLineCount} line(s).`
  );
}

async function executeBash(input: Record<string, unknown>): Promise<string> {
  const command = input.command as string;
  const timeout = Math.min(
    (input.timeout as number) || DEFAULT_BASH_TIMEOUT_MS,
    300_000
  );

  // Safety check
  for (const blocked of BLOCKED_COMMANDS) {
    if (blocked.test(command)) {
      throw new Error(`Blocked dangerous command: ${command}`);
    }
  }

  try {
    const stdout = execSync(command, {
      encoding: "utf-8",
      timeout,
      maxBuffer: 1024 * 1024 * 10, // 10 MB
      shell: "/bin/bash",
      stdio: ["pipe", "pipe", "pipe"],
    });
    return truncate(stdout);
  } catch (err: unknown) {
    const execErr = err as {
      status?: number;
      stdout?: string;
      stderr?: string;
      message?: string;
    };

    const parts: string[] = [];
    if (execErr.stdout) parts.push(execErr.stdout);
    if (execErr.stderr) parts.push(execErr.stderr);
    if (parts.length === 0 && execErr.message) parts.push(execErr.message);

    const combined = parts.join("\n");
    const exitInfo = execErr.status != null ? `Exit code: ${execErr.status}\n` : "";
    return truncate(exitInfo + combined);
  }
}

async function executeGlob(input: Record<string, unknown>): Promise<string> {
  const pattern = input.pattern as string;
  const root = (input.path as string) || process.cwd();

  if (root && !path.isAbsolute(root)) {
    throw new Error(`path must be absolute, got: ${root}`);
  }

  const matches = globMatch(root, pattern);

  if (matches.length === 0) {
    return "No files matched the pattern.";
  }

  const limited = matches.slice(0, 500);
  const result = limited.join("\n");
  const suffix =
    matches.length > 500
      ? `\n\n... and ${matches.length - 500} more files`
      : "";

  return truncate(result + suffix);
}

async function executeGrep(input: Record<string, unknown>): Promise<string> {
  const pattern = input.pattern as string;
  const searchPath = (input.path as string) || process.cwd();
  const include = input.include as string | undefined;

  let re: RegExp;
  try {
    re = new RegExp(pattern);
  } catch {
    throw new Error(`Invalid regex pattern: ${pattern}`);
  }

  const results: string[] = [];
  const MAX_RESULTS = 200;

  function shouldIncludeFile(filePath: string): boolean {
    if (!include) return true;
    // Simple include filter: convert glob to regex
    const escaped = include
      .replace(/[.+^${}()|[\]\\]/g, "\\$&")
      .replace(/\*/g, ".*")
      .replace(/\?/g, ".");
    return new RegExp(`^${escaped}$`).test(path.basename(filePath));
  }

  function searchFile(filePath: string): void {
    if (results.length >= MAX_RESULTS) return;
    if (!shouldIncludeFile(filePath)) return;

    let content: string;
    try {
      // Skip binary files (quick heuristic: check first 512 bytes)
      const fd = fs.openSync(filePath, "r");
      const buf = Buffer.alloc(512);
      const bytesRead = fs.readSync(fd, buf, 0, 512, 0);
      fs.closeSync(fd);
      if (bytesRead > 0 && buf.slice(0, bytesRead).includes(0)) return;

      content = fs.readFileSync(filePath, "utf-8");
    } catch {
      return;
    }

    const lines = content.split("\n");
    for (let i = 0; i < lines.length; i++) {
      if (results.length >= MAX_RESULTS) return;
      if (re.test(lines[i])) {
        results.push(`${filePath}:${i + 1}:${lines[i]}`);
      }
    }
  }

  function searchDir(dir: string): void {
    if (results.length >= MAX_RESULTS) return;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      if (results.length >= MAX_RESULTS) break;
      if (entry.name.startsWith(".")) continue;
      if (entry.name === "node_modules") continue;
      if (entry.name === "dist") continue;

      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        searchDir(full);
      } else if (entry.isFile()) {
        searchFile(full);
      }
    }
  }

  // If searchPath is a file, search just that file
  const stat = fs.statSync(searchPath, { throwIfNoEntry: false });
  if (!stat) {
    throw new Error(`Path does not exist: ${searchPath}`);
  }
  if (stat.isFile()) {
    searchFile(searchPath);
  } else {
    searchDir(searchPath);
  }

  if (results.length === 0) {
    return "No matches found.";
  }

  const suffix =
    results.length >= MAX_RESULTS
      ? `\n\n... results truncated at ${MAX_RESULTS} matches`
      : "";
  return truncate(results.join("\n") + suffix);
}

async function executeWebSearch(
  _input: Record<string, unknown>
): Promise<string> {
  return "Web search is not available in standalone mode. Use the Bash tool with `curl` for HTTP requests, or connect an MCP web-search server.";
}

// ---------------------------------------------------------------------------
// Executor dispatch
// ---------------------------------------------------------------------------

const EXECUTORS: Record<
  string,
  (input: Record<string, unknown>) => Promise<string>
> = {
  Read: executeRead,
  Write: executeWrite,
  Edit: executeEdit,
  Bash: executeBash,
  Glob: executeGlob,
  Grep: executeGrep,
  WebSearch: executeWebSearch,
};

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/**
 * Returns the list of tool definitions suitable for the Anthropic API
 * `tools` parameter.
 */
export function getToolDefinitions(): ToolDefinition[] {
  return TOOL_DEFINITIONS;
}

/**
 * Execute a tool by name with the given input and return a ToolResult
 * ready to be sent back to the API as a `tool_result` content block.
 */
export async function executeTool(
  name: string,
  input: Record<string, unknown>,
  toolUseId: string
): Promise<ToolResult> {
  const executor = EXECUTORS[name];
  if (!executor) {
    return {
      tool_use_id: toolUseId,
      content: `Unknown tool: ${name}. Available tools: ${Object.keys(EXECUTORS).join(", ")}`,
      is_error: true,
    };
  }

  try {
    const content = await executor(input);
    return { tool_use_id: toolUseId, content };
  } catch (err: unknown) {
    const message =
      err instanceof Error ? err.message : String(err);
    return {
      tool_use_id: toolUseId,
      content: `Error: ${message}`,
      is_error: true,
    };
  }
}
