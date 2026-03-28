# Aussie Swarm — Multi-Agent Swarm

Dispatch a task to all 8 specialist agents in parallel.

## Usage

When the user wants a comprehensive multi-agent attack on a problem:

```bash
cd pfaa-cli && npx tsx src/cli.ts swarm "the task here"
```

With specific roles:
```bash
cd pfaa-cli && npx tsx src/cli.ts swarm "task" --roles analyzer,tester,reviewer
```

## Agent Roles

| Role | Phase | Specialty |
|------|-------|-----------|
| analyzer | VAPOR | Code analysis, security, complexity |
| refactorer | LIQUID | Code transformation, py315 migration |
| tester | SOLID | Test generation, coverage, benchmarks |
| deployer | SOLID | Docker, CI/CD, deployment |
| researcher | VAPOR | Search, docs, API research |
| orchestrator | VAPOR | Planning, decomposition |
| reviewer | VAPOR | Code review, security audit |
| builder | SOLID | Build, compile, package |
