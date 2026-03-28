/**
 * Python 3.15 Code Tools — Analysis, migration, and optimization.
 *
 * Specialized tools for Python 3.15 development:
 * - Detect and suggest PEP 810 lazy imports
 * - Detect and suggest PEP 814 frozendict usage
 * - Detect kqueue subprocess opportunities
 * - Free-threading (no-GIL) analysis
 * - Phase-fluid execution recommendations
 */

import { spawn } from 'node:child_process';
import { readFileSync, existsSync } from 'node:fs';
import { getLogger } from '../utils/logger.js';
import type {
  CodeAnalysis,
  Py315Feature,
  CodeIssue,
  CodeSuggestion,
  Python315Config,
} from '../types.js';

const log = getLogger('py315');

// ── Python 3.15 Feature Detection Patterns ──────────────────────────

const PY315_PATTERNS = {
  lazyImport: {
    pattern: /^lazy\s+import\s+(\w+)/gm,
    pep: 'PEP 810',
    description: 'Lazy import — module loads on first use',
  },
  frozendict: {
    pattern: /frozendict\s*\(/gm,
    pep: 'PEP 814',
    description: 'Immutable dictionary — hashable, no defensive copying',
  },
  gilCheck: {
    pattern: /sys\._is_gil_enabled\(\)/gm,
    pep: 'Free-threading',
    description: 'Runtime GIL detection for free-threading awareness',
  },
  kqueueSubprocess: {
    pattern: /subprocess\.(run|Popen|call)\(/gm,
    pep: 'kqueue',
    description: 'Subprocess with kernel event queue (macOS optimization)',
  },
  typeParamSyntax: {
    pattern: /def\s+\w+\[(\w+)\]/gm,
    pep: 'PEP 695',
    description: 'Type parameter syntax',
  },
  exceptionGroups: {
    pattern: /except\*\s+/gm,
    pep: 'PEP 654',
    description: 'Exception groups',
  },
};

// ── Import Analysis for Lazy Import Suggestions ─────────────────────

const HEAVY_MODULES = new Set([
  'numpy', 'pandas', 'scipy', 'sklearn', 'torch', 'tensorflow',
  'matplotlib', 'plotly', 'seaborn', 'requests', 'httpx', 'aiohttp',
  'sqlalchemy', 'django', 'flask', 'fastapi', 'pydantic',
  'json', 'yaml', 'toml', 'xml', 'csv',
  'subprocess', 'multiprocessing', 'threading',
  'logging', 'pathlib', 'shutil', 'tempfile',
  'cryptography', 'jwt', 'boto3', 'google.cloud',
]);

export class Python315Tools {
  private pythonPath: string;
  private config: Python315Config;

  constructor(config: Python315Config) {
    this.config = config;
    this.pythonPath = config.interpreterPath;
  }

  /**
   * Analyze a Python file for Python 3.15 features and opportunities.
   */
  analyzeFile(filePath: string): CodeAnalysis {
    if (!existsSync(filePath)) {
      return {
        file: filePath,
        language: 'python',
        py315Features: [],
        complexity: 0,
        issues: [{ severity: 'error', line: 0, message: 'File not found', rule: 'file-exists' }],
        suggestions: [],
      };
    }

    const code = readFileSync(filePath, 'utf-8');
    const lines = code.split('\n');

    const features = this.detectFeatures(code, lines);
    const issues = this.detectIssues(code, lines);
    const suggestions = this.generateSuggestions(code, lines);
    const complexity = this.estimateComplexity(code);

    return {
      file: filePath,
      language: 'python',
      py315Features: features,
      complexity,
      issues,
      suggestions,
    };
  }

  /**
   * Analyze an entire directory of Python files.
   */
  analyzeDirectory(dirPath: string): CodeAnalysis[] {
    const files = this.findPythonFiles(dirPath);
    return files.map((f) => this.analyzeFile(f));
  }

  /**
   * Suggest lazy import conversions for a file.
   */
  suggestLazyImports(filePath: string): CodeSuggestion[] {
    const code = readFileSync(filePath, 'utf-8');
    const suggestions: CodeSuggestion[] = [];

    const importPattern = /^import\s+(\w[\w.]*)/gm;
    const fromImportPattern = /^from\s+(\w[\w.]*)\s+import/gm;

    let match: RegExpExecArray | null;

    while ((match = importPattern.exec(code)) !== null) {
      const moduleName = match[1];
      if (HEAVY_MODULES.has(moduleName)) {
        const line = code.slice(0, match.index).split('\n').length;
        suggestions.push({
          type: 'py315',
          line,
          original: match[0],
          suggested: `lazy import ${moduleName}`,
          reason: `PEP 810: '${moduleName}' is heavy — lazy import defers loading until first use, cutting startup time`,
        });
      }
    }

    return suggestions;
  }

  /**
   * Suggest frozendict usage for immutable configs.
   */
  suggestFrozenDict(filePath: string): CodeSuggestion[] {
    const code = readFileSync(filePath, 'utf-8');
    const suggestions: CodeSuggestion[] = [];
    const lines = code.split('\n');

    // Detect dict literals that are never mutated
    const constDictPattern = /^(\s*)([\w]+)\s*=\s*\{[^}]+\}\s*$/gm;
    let match: RegExpExecArray | null;

    while ((match = constDictPattern.exec(code)) !== null) {
      const varName = match[2];
      const lineNum = code.slice(0, match.index).split('\n').length;

      // Check if this dict is never mutated (simple heuristic)
      const mutations = [
        `${varName}[`,
        `${varName}.update`,
        `${varName}.pop`,
        `${varName}.setdefault`,
        `${varName}.clear`,
      ];

      const isMutated = mutations.some((m) => code.includes(m));

      if (!isMutated && varName === varName.toUpperCase()) {
        suggestions.push({
          type: 'py315',
          line: lineNum,
          original: `${varName} = {…}`,
          suggested: `${varName} = frozendict({…})`,
          reason: `PEP 814: '${varName}' appears constant — frozendict is hashable, thread-safe, and prevents accidental mutation`,
        });
      }
    }

    return suggestions;
  }

  /**
   * Run a Python 3.15 script in the engine's sandbox.
   */
  async runScript(
    code: string,
    timeout: number = 30_000,
  ): Promise<{ success: boolean; stdout: string; stderr: string; exitCode: number }> {
    return new Promise((resolve) => {
      const proc = spawn(this.pythonPath, ['-c', code], {
        timeout,
        env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' },
      });

      let stdout = '';
      let stderr = '';

      proc.stdout.on('data', (d) => { stdout += d.toString(); });
      proc.stderr.on('data', (d) => { stderr += d.toString(); });

      proc.on('close', (exitCode) => {
        resolve({
          success: exitCode === 0,
          stdout: stdout.trim(),
          stderr: stderr.trim(),
          exitCode: exitCode || 0,
        });
      });

      proc.on('error', (err) => {
        resolve({
          success: false,
          stdout: '',
          stderr: err.message,
          exitCode: 1,
        });
      });
    });
  }

  /**
   * Check if Python 3.15 is available on the system.
   */
  async checkRuntime(): Promise<{
    available: boolean;
    version: string;
    features: string[];
    gilEnabled: boolean;
    path: string;
  }> {
    const checkScript = `
import sys
import json

features = []

# Check lazy import
try:
    exec("lazy import os")
    features.append("lazy_import")
except SyntaxError:
    pass

# Check frozendict
try:
    fd = frozendict({"a": 1})
    features.append("frozendict")
except NameError:
    pass

# Check GIL
try:
    gil = sys._is_gil_enabled()
    features.append("gil_detection")
except AttributeError:
    gil = True

print(json.dumps({
    "version": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
    "features": features,
    "gil_enabled": gil,
    "path": sys.executable,
}))
`;

    const result = await this.runScript(checkScript);
    if (!result.success) {
      return {
        available: false,
        version: 'unknown',
        features: [],
        gilEnabled: true,
        path: this.pythonPath,
      };
    }

    try {
      const data = JSON.parse(result.stdout);
      return { available: true, ...data };
    } catch {
      return {
        available: false,
        version: 'parse-error',
        features: [],
        gilEnabled: true,
        path: this.pythonPath,
      };
    }
  }

  // ── Internal ─────────────────────────────────────────────────────

  private detectFeatures(code: string, lines: string[]): Py315Feature[] {
    const features: Py315Feature[] = [];

    for (const [name, spec] of Object.entries(PY315_PATTERNS)) {
      const regex = new RegExp(spec.pattern.source, spec.pattern.flags);
      let match: RegExpExecArray | null;

      while ((match = regex.exec(code)) !== null) {
        const line = code.slice(0, match.index).split('\n').length;
        features.push({
          feature: name,
          pep: spec.pep,
          line,
          usage: match[0].trim(),
        });
      }
    }

    return features;
  }

  private detectIssues(code: string, lines: string[]): CodeIssue[] {
    const issues: CodeIssue[] = [];

    // Detect print() debugging
    lines.forEach((line, i) => {
      if (/^\s*print\(/.test(line) && !/noqa/.test(line)) {
        issues.push({
          severity: 'info',
          line: i + 1,
          message: 'print() statement — consider using logging',
          rule: 'no-print',
        });
      }
    });

    // Detect bare except
    lines.forEach((line, i) => {
      if (/^\s*except\s*:/.test(line)) {
        issues.push({
          severity: 'warning',
          line: i + 1,
          message: 'Bare except catches all exceptions including SystemExit',
          rule: 'no-bare-except',
        });
      }
    });

    // Detect mutable default args
    const mutableDefaultPattern = /def\s+\w+\([^)]*=\s*(\[\]|\{\}|\bdict\(\)|\blist\(\))/gm;
    let match: RegExpExecArray | null;
    while ((match = mutableDefaultPattern.exec(code)) !== null) {
      const line = code.slice(0, match.index).split('\n').length;
      issues.push({
        severity: 'warning',
        line,
        message: 'Mutable default argument — use None and assign in body',
        rule: 'mutable-default',
      });
    }

    return issues;
  }

  private generateSuggestions(code: string, lines: string[]): CodeSuggestion[] {
    const suggestions: CodeSuggestion[] = [];

    // Suggest async for I/O patterns
    const syncIOPattern = /(?:open|read|write|requests\.(?:get|post)|urlopen)\(/gm;
    let match: RegExpExecArray | null;
    while ((match = syncIOPattern.exec(code)) !== null) {
      const line = code.slice(0, match.index).split('\n').length;
      suggestions.push({
        type: 'performance',
        line,
        original: match[0],
        suggested: `async ${match[0]}  # Consider aiofiles/httpx`,
        reason: 'Phase-Fluid: I/O operations should run in VAPOR phase (async coroutine)',
      });
    }

    // Add lazy import suggestions
    suggestions.push(...this.suggestLazyImports_inline(code));

    return suggestions;
  }

  private suggestLazyImports_inline(code: string): CodeSuggestion[] {
    const suggestions: CodeSuggestion[] = [];
    const importPattern = /^import\s+(\w[\w.]*)/gm;
    let match: RegExpExecArray | null;

    while ((match = importPattern.exec(code)) !== null) {
      const mod = match[1];
      if (HEAVY_MODULES.has(mod) && !code.includes(`lazy import ${mod}`)) {
        const line = code.slice(0, match.index).split('\n').length;
        suggestions.push({
          type: 'py315',
          line,
          original: `import ${mod}`,
          suggested: `lazy import ${mod}`,
          reason: `PEP 810: Defer loading '${mod}' — saves startup time`,
        });
      }
    }

    return suggestions;
  }

  private estimateComplexity(code: string): number {
    let complexity = 1;
    const patterns = [
      /\bif\b/g, /\belif\b/g, /\bfor\b/g, /\bwhile\b/g,
      /\bexcept\b/g, /\band\b/g, /\bor\b/g, /\blambda\b/g,
    ];
    for (const p of patterns) {
      const matches = code.match(p);
      if (matches) complexity += matches.length;
    }
    return complexity;
  }

  private findPythonFiles(dir: string): string[] {
    const { readdirSync, statSync } = require('node:fs');
    const { join } = require('node:path');
    const files: string[] = [];

    try {
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        const stat = statSync(full);
        if (stat.isDirectory() && !entry.startsWith('.') && entry !== 'node_modules' && entry !== '__pycache__') {
          files.push(...this.findPythonFiles(full));
        } else if (entry.endsWith('.py')) {
          files.push(full);
        }
      }
    } catch {
      // Permission or access error
    }

    return files;
  }
}
