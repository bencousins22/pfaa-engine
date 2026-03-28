# Aussie Memory — JMEM Operations

Manage the 5-layer JMEM semantic memory system.

## Usage

View memory status with bar charts:
```bash
cd pfaa-cli && npx tsx src/cli.ts memory stats
```

Search memory:
```bash
cd pfaa-cli && npx tsx src/cli.ts memory recall "database optimization"
```

Force learning cycle (extract L2/L3 patterns from episodes):
```bash
cd pfaa-cli && npx tsx src/cli.ts learn
```

Consolidate (promote validated knowledge):
```bash
cd pfaa-cli && npx tsx src/cli.ts memory consolidate
```

Full memory dump as JSON:
```bash
cd pfaa-cli && npx tsx src/cli.ts memory dump
```

Deferred tool discovery:
```bash
cd pfaa-cli && npx tsx src/cli.ts tool-search "git"
```

## Memory Layers

| Layer | Name | What It Stores |
|-------|------|---------------|
| L1 | Episodic | Raw execution traces |
| L2 | Semantic | Statistical patterns per tool |
| L3 | Strategic | Phase optimization strategies |
| L4 | Meta-Learning | Learning rate tuning |
| L5 | Emergent | Cross-agent knowledge synthesis |
