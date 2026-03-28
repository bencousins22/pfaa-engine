# Aussie Exec — Python Sandbox

Execute Python code in the PFAA sandbox (Python 3.15 with free-threading).

## Usage

Inline code:
```bash
cd pfaa-cli && npx tsx src/cli.ts exec -c "print('hello')"
```

Run a file:
```bash
cd pfaa-cli && npx tsx src/cli.ts exec -f script.py
```

Single tool execution:
```bash
cd pfaa-cli && npx tsx src/cli.ts tool compute "sqrt(144)"
cd pfaa-cli && npx tsx src/cli.ts tool shell "ls -la"
cd pfaa-cli && npx tsx src/cli.ts tool git_status
```

Fan-out across inputs:
```bash
cd pfaa-cli && npx tsx src/cli.ts scatter grep "TODO" "FIXME" "HACK"
```

Sequential pipeline:
```bash
cd pfaa-cli && npx tsx src/cli.ts pipeline shell:ls glob:*.py
```
