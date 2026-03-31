# Aussie Ask — Smart Question Answering

Answer questions using full agent context: JMEM memory recall, codebase search, and learned patterns. A "smart ask" that leverages the entire knowledge stack before responding.

## When the user invokes /aussie-ask [question]

Answer the question by combining JMEM memory with codebase context. Never answer from general knowledge alone — always ground the response in project-specific memory and code.

### Step 1: Parse the Question

Extract the core intent and key terms from the user's question. Identify:
- **Domain**: Which part of the system does this relate to? (memory, agents, skills, hooks, CLI, strategy, etc.)
- **Type**: Is this a "how", "why", "what", "where", or "when" question?
- **Scope**: Single file, subsystem, or cross-cutting concern?

### Step 2: Recall JMEM Context

Search memory across multiple layers for relevant knowledge:

```
Use mcp__jmem__jmem_recall(query="<question keywords>", limit=10)
```

If the question targets a specific domain, also run a focused recall:
```
Use mcp__jmem__jmem_recall(query="<domain-specific terms>", limit=5, min_q=0.5)
```

For higher-level architectural questions, check strategic memory:
```
Use mcp__jmem__jmem_recall(query="<question keywords>", level=3, limit=5)
```

### Step 3: Search the Codebase

Based on the question domain, search relevant code:

- **Architecture questions** → Read relevant files in `src/`, `agent_setup_cli/core/`, `.claude/`
- **Agent questions** → Glob `.claude/agents/*.md` and read matching agents
- **Skill questions** → Glob `.claude/skills/*/SKILL.md` and read matching skills
- **Memory questions** → Check `jmem-mcp-server/jmem/` and JMEM tool docs
- **CLI questions** → Read `pfaa-cli/src/cli.ts` and related command files
- **Config questions** → Read `.claude/settings.json`

Use Grep to find specific patterns, function names, or references across the codebase.

### Step 4: Synthesize Answer

Combine memory context and codebase findings into a clear answer:

1. Lead with the direct answer
2. Cite specific memories (note IDs and Q-values) that informed the answer
3. Reference specific files and line numbers from the codebase
4. Flag any contradictions between memory and current code (memory may be stale)
5. Note confidence level: HIGH (strong memory + code match), MEDIUM (partial match), LOW (mostly inference)

### Step 5: Store and Reinforce

Store the Q&A as an episode for future recall:
```
Use mcp__jmem__jmem_remember(content="Q: <question> A: <concise answer summary>", level=1, keywords=["qa", "<domain>"], tags=["aussie-ask"])
```

Reinforce any recalled memories that contributed to the answer:
```
Use mcp__jmem__jmem_reward_recalled(reward=0.6)
```

### Response Format

```
AUSSIE ASK
==========
Q: [original question]

A: [clear, grounded answer]

Sources:
  Memory: [N] memories recalled (avg Q=[X.XX])
    - [note_id]: [brief content] (Q=[X.XX], L[N])
  Code:   [N] files referenced
    - [file_path]:[line] — [what was found]

Confidence: HIGH | MEDIUM | LOW
```

## Options (passed as arguments)

- `--deep` — Expand search to all 5 memory layers and full codebase scan
- `--no-store` — Answer without storing the Q&A as an episode
- `--code-only` — Skip memory recall, answer from codebase alone
- `--memory-only` — Skip codebase search, answer from JMEM alone
