# Aussie Audit — Self-Assessment

Audit the Aussie Agents system for reliability and completeness.

## Usage
```bash
cd pfaa-cli && npx tsx src/cli.ts status
cd pfaa-cli && npx tsx src/cli.ts tools
cd pfaa-cli && npx tsx src/cli.ts memory stats
cd pfaa-cli && npx tsx src/cli.ts learn
```

## Checks
- All skills registered and accessible (/aussie-*)
- All agents registered
- All hooks firing (check ECC_HOOK_PROFILE)
- JMEM MCP server connected
- Memory health (avg Q > 0.5)
- TypeScript compiles clean (npx tsc --noEmit)
- Python syntax valid
- Bridge entry point resolves
