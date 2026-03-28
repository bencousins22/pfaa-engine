# Aussie Tools — Tool Management

List and inspect all registered PFAA tools.

## Usage

List all tools grouped by phase:
```bash
cd pfaa-cli && npx tsx src/cli.ts tools
```

Search for tools by keyword:
```bash
cd pfaa-cli && npx tsx src/cli.ts tool-search "git"
cd pfaa-cli && npx tsx src/cli.ts tool-search "docker"
cd pfaa-cli && npx tsx src/cli.ts tool-search "file"
```

Full system status:
```bash
cd pfaa-cli && npx tsx src/cli.ts status
```

Run benchmarks:
```bash
cd pfaa-cli && npx tsx src/cli.ts bench
```

## Tool Phases

| Phase | Speed | Use Case |
|-------|-------|----------|
| VAPOR | ~6μs | Async I/O — file reads, HTTP, DNS |
| LIQUID | ~10μs | CPU-bound — grep, compute, hash |
| SOLID | ~1ms | Isolated — shell, git, docker, sandbox |
