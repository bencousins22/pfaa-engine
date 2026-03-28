# Aussie Chat — Interactive Agent Loop

Start the interactive Aussie Agents chat loop (Agent Zero-style terminal UI).

## Usage

```bash
cd pfaa-cli && npx tsx src/cli.ts chat
```

With live Claude API:
```bash
cd pfaa-cli && npx tsx src/cli.ts chat --live
```

Custom agent name:
```bash
cd pfaa-cli && npx tsx src/cli.ts chat --name "Aussie 1"
```

## Features

- Gold prompt header, emerald agent responses (JMEM brand colors)
- Streaming text output
- `e` to exit, empty to continue
- Routes through bridge to Claude when `--live` is set
- Simulates responses without API key
