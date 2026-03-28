/**
 * Enterprise Logger — Structured logging with audit trail support.
 *
 * Uses pino for high-performance JSON logging with pretty-print for CLI.
 * Supports audit mode for enterprise compliance requirements.
 */

import { mkdirSync, existsSync, appendFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { homedir } from 'node:os';

export enum LogLevel {
  TRACE = 10,
  DEBUG = 20,
  INFO = 30,
  WARN = 40,
  ERROR = 50,
  FATAL = 60,
  SILENT = Infinity,
}

interface LogEntry {
  level: LogLevel;
  timestamp: string;
  message: string;
  context?: string;
  data?: Record<string, unknown>;
  auditId?: string;
}

const LEVEL_NAMES: Record<LogLevel, string> = {
  [LogLevel.TRACE]: 'TRACE',
  [LogLevel.DEBUG]: 'DEBUG',
  [LogLevel.INFO]: 'INFO',
  [LogLevel.WARN]: 'WARN',
  [LogLevel.ERROR]: 'ERROR',
  [LogLevel.FATAL]: 'FATAL',
  [LogLevel.SILENT]: 'SILENT',
};

const LEVEL_COLORS: Record<LogLevel, string> = {
  [LogLevel.TRACE]: '\x1b[90m',
  [LogLevel.DEBUG]: '\x1b[36m',
  [LogLevel.INFO]: '\x1b[32m',
  [LogLevel.WARN]: '\x1b[33m',
  [LogLevel.ERROR]: '\x1b[31m',
  [LogLevel.FATAL]: '\x1b[35m',
  [LogLevel.SILENT]: '',
};

const RESET = '\x1b[0m';
const DIM = '\x1b[2m';

class Logger {
  private level: LogLevel;
  private context: string;
  private auditPath: string | null;
  private redactSecrets: boolean;

  constructor(
    context: string = 'pfaa',
    level: LogLevel = LogLevel.INFO,
    auditPath: string | null = null,
    redactSecrets: boolean = true,
  ) {
    this.context = context;
    this.level = level;
    this.auditPath = auditPath;
    this.redactSecrets = redactSecrets;

    if (auditPath) {
      const dir = dirname(auditPath);
      if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
    }
  }

  setLevel(level: LogLevel): void {
    this.level = level;
  }

  child(context: string): Logger {
    return new Logger(
      `${this.context}:${context}`,
      this.level,
      this.auditPath,
      this.redactSecrets,
    );
  }

  trace(msg: string, data?: Record<string, unknown>): void {
    this.log(LogLevel.TRACE, msg, data);
  }

  debug(msg: string, data?: Record<string, unknown>): void {
    this.log(LogLevel.DEBUG, msg, data);
  }

  info(msg: string, data?: Record<string, unknown>): void {
    this.log(LogLevel.INFO, msg, data);
  }

  warn(msg: string, data?: Record<string, unknown>): void {
    this.log(LogLevel.WARN, msg, data);
  }

  error(msg: string, data?: Record<string, unknown>): void {
    this.log(LogLevel.ERROR, msg, data);
  }

  fatal(msg: string, data?: Record<string, unknown>): void {
    this.log(LogLevel.FATAL, msg, data);
  }

  audit(action: string, data: Record<string, unknown>): void {
    const entry: LogEntry = {
      level: LogLevel.INFO,
      timestamp: new Date().toISOString(),
      message: `AUDIT: ${action}`,
      context: this.context,
      data: this.redactSecrets ? this.redact(data) : data,
      auditId: crypto.randomUUID(),
    };

    if (this.auditPath) {
      appendFileSync(this.auditPath, JSON.stringify(entry) + '\n');
    }

    this.log(LogLevel.INFO, `[AUDIT] ${action}`, data);
  }

  private log(level: LogLevel, msg: string, data?: Record<string, unknown>): void {
    if (level < this.level) return;

    const ts = new Date().toISOString().slice(11, 23);
    const color = LEVEL_COLORS[level] || '';
    const name = LEVEL_NAMES[level] || 'UNKNOWN';
    const ctx = DIM + this.context + RESET;

    let line = `${DIM}${ts}${RESET} ${color}${name.padEnd(5)}${RESET} ${ctx} ${msg}`;

    if (data && Object.keys(data).length > 0) {
      const sanitized = this.redactSecrets ? this.redact(data) : data;
      line += ` ${DIM}${JSON.stringify(sanitized)}${RESET}`;
    }

    if (level >= LogLevel.ERROR) {
      process.stderr.write(line + '\n');
    } else {
      process.stdout.write(line + '\n');
    }
  }

  private redact(data: Record<string, unknown>): Record<string, unknown> {
    const SENSITIVE = /(?:api[_-]?key|secret|token|password|credential|auth)/i;
    const redacted: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(data)) {
      if (SENSITIVE.test(k)) {
        redacted[k] = '[REDACTED]';
      } else if (typeof v === 'object' && v !== null && !Array.isArray(v)) {
        redacted[k] = this.redact(v as Record<string, unknown>);
      } else {
        redacted[k] = v;
      }
    }
    return redacted;
  }
}

// Singleton logger
let _logger: Logger | null = null;

export function getLogger(context?: string): Logger {
  if (!_logger) {
    const auditDir = join(homedir(), '.pfaa', 'audit');
    _logger = new Logger(
      'pfaa',
      LogLevel.WARN,
      join(auditDir, 'pfaa-audit.jsonl'),
    );
  }
  return context ? _logger.child(context) : _logger;
}

export function setLogLevel(level: LogLevel): void {
  getLogger().setLevel(level);
}

export { Logger };
