/**
 * pfaa swarm — dispatch a task to the full PFAA 9-tier agent swarm.
 */

import { Command } from 'commander'
import { SwarmOrchestrator, type AgentTier } from '../../swarm/team.js'
import { loadConfig } from '../../core/config.js'
import chalk from 'chalk'

const TIER_COLORS: Record<AgentTier, string> = {
  intelligence: '#8B5CF6',
  acquisition: '#3B82F6',
  enrichment: '#06B6D4',
  scoring: '#F59E0B',
  outreach: '#10B981',
  conversion: '#EF4444',
  nurture: '#EC4899',
  content: '#84CC16',
  operations: '#6B7280',
}

export function swarmCommand(): Command {
  return new Command('swarm')
    .description('Dispatch a task to the full PFAA agent swarm (all 9 tiers)')
    .argument('<prompt>', 'Task for the swarm')
    .option('--tiers <tiers...>', 'Run specific tiers only')
    .option('--sequential', 'Run tiers sequentially', false)
    .action(async (prompt, opts, cmd) => {
      const globals = cmd.parent!.opts()
      const config = await loadConfig(globals.config)

      const orchestrator = new SwarmOrchestrator({
        provider: globals.provider,
        model: globals.model ?? '',
        workspace: globals.workspace,
        qdrantUrl: config.qdrantUrl ?? 'http://localhost:6333',
        pythonBin: config.pythonBin ?? 'python3',
        maxParallelTeams: config.maxParallelTeams ?? 9,
      })

      console.log('\n' + chalk.bgHex('#6C3483').white.bold(' PFAA Swarm '))
      console.log(chalk.gray(`  Prompt: ${prompt.slice(0, 80)}`))
      console.log(chalk.gray(`  Provider: ${globals.provider} | Tiers: 9 | Agents: ~25\n`))

      orchestrator.on('status', ({ type, message }: any) => {
        console.log(chalk.yellow(`  [${type}] `) + chalk.white(message))
      })

      orchestrator.on('agent_event', (e: any) => {
        const color = TIER_COLORS[e.tier as AgentTier] ?? '#888'
        switch (e.type) {
          case 'agent_start':
            process.stdout.write(chalk.hex(color)(`  ▶ ${e.agent_id} `) + chalk.gray((e.role ?? '').slice(0, 60)) + '\n')
            break
          case 'tool_call':
            process.stdout.write(chalk.hex(color)(`    ⚙ ${e.agent_id} `) + chalk.cyan(e.tool) + '\n')
            break
          case 'agent_complete':
            process.stdout.write(chalk.hex(color)(`  ✓ ${e.agent_id} `) + chalk.gray(`${e.duration_ms}ms · ${e.tokens} tokens`) + '\n')
            break
        }
      })

      orchestrator.on('team_complete', (result: any) => {
        if (result.merged) {
          console.log('\n' + chalk.bgHex('#1D8348').white.bold(` Team result: ${result.task_id} `))
          console.log(chalk.white(result.merged.slice(0, 1000)))
        }
      })

      process.on('SIGINT', () => {
        console.log(chalk.yellow('\n  Interrupting swarm...'))
        orchestrator.interruptAll()
        process.exit(0)
      })

      await orchestrator.dispatchToSwarm(prompt)
    })
}
