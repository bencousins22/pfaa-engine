# Aussie Analyze — Python 3.15 Code Analysis

Analyze Python files for Python 3.15 features, issues, and optimization opportunities.

## Usage

Full analysis:
```bash
cd pfaa-cli && npx tsx src/cli.ts py315 analyze <path>
```

Check runtime availability:
```bash
cd pfaa-cli && npx tsx src/cli.ts py315 check
```

Suggest lazy imports (PEP 810):
```bash
cd pfaa-cli && npx tsx src/cli.ts py315 lazy-imports <path>
```

## What It Detects

- **PEP 810** — `lazy import` usage and opportunities
- **PEP 814** — `frozendict` usage for immutable configs
- **PEP 695** — Type parameter syntax
- **PEP 654** — Exception groups
- **Free-threading** — GIL detection via `sys._is_gil_enabled()`
- **kqueue subprocess** — macOS kernel event optimization
- Mutable default arguments, bare excepts, print debugging
