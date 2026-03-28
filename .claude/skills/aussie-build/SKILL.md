# Aussie Build — Self-Improvement

Run a self-improvement cycle where the engine analyzes and extends itself.

## Usage

Analyze only (no changes):
```bash
cd pfaa-cli && npx tsx src/cli.ts self-build
```

Auto-apply validated changes:
```bash
cd pfaa-cli && npx tsx src/cli.ts self-build --apply
```

Phase exploration (discover optimal execution phases):
```bash
cd pfaa-cli && npx tsx src/cli.ts explore --rounds 200 --epsilon 0.3
```

Generate code via Claude:
```bash
cd pfaa-cli && npx tsx src/cli.ts generate "a Python 3.15 async HTTP client"
```

## Self-Build Cycle

1. **Introspect** — Analyze own codebase with own tools
2. **Diagnose** — Static analysis + Claude review
3. **Propose** — Generate new tool code following PFAA patterns
4. **Sandbox** — Execute in isolated subprocess (SOLID phase)
5. **Apply** — Write validated code to `tools_generated.py`
6. **Learn** — Record cycle in persistent memory
