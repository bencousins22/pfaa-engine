/**
 * pfaa swarm — dispatch a task to the full Aussie Agents 9-tier agent swarm.
 * Uses Aussie Agents PrintStyle colors throughout.
 */

import { Command } from 'commander'
import { SwarmOrchestrator, type AgentTier } from '../../swarm/team.js'
import { loadConfig } from '../../core/config.js'
import chalk from 'chalk'

// JMEM brand: emerald + gold
const s = {
  userPrompt:     chalk.bgHex('#D4A017').hex('#1a1a1a').bold,
  agentHeader:    chalk.bgHex('#2E7D32').white.bold,
  agentStream:    chalk.hex('#00E676').italic,
  toolHeader:     chalk.bgHex('#C9A73B').hex('#1a1a1a').bold,
  toolArg:        chalk.hex('#4CAF50'),
  toolArgBold:    chalk.hex('#C9A73B').bold,
  error:          chalk.hex('#EF5350'),
  warning:        chalk.hex('#D4A017'),
  hint:           chalk.hex('#2E7D32'),
  info:           chalk.hex('#4CAF50'),
  success:        chalk.hex('#00E676'),
  white:          chalk.white,
}

// Per-tier colors — emerald/gold spectrum
const TIER_COLOR: Record<AgentTier, string> = {
  intelligence: '#00E676',   // bright emerald
  acquisition:  '#4CAF50',   // mid emerald
  enrichment:   '#4CAF50',
  scoring:      '#D4A017',   // gold
  outreach:     '#2E7D32',   // dark emerald
  conversion:   '#C9A73B',   // muted gold
  nurture:      '#C9A73B',
  content:      '#2E7D32',   // dark emerald
  operations:   '#5A6A5A',   // grey-green
}

export function swarmCommand(): Command {
  return new Command('swarm')
    .description('Dispatch a task to the full Aussie Agents swarm (all 9 tiers)')
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

      // Aussie Agents style header
      console.log()
      console.log(s.agentHeader(` Aussie: Dispatching to 9-tier swarm `))
      console.log(s.hint(`Prompt: ${prompt.slice(0, 80)}`))
      console.log(s.info(`Info: Provider: ${globals.provider} | Tiers: 9 | Agents: ~25`))
      console.log()

      orchestrator.on('status', ({ type, message }: any) => {
        if (type === 'swarm_complete') {
          console.log()
          console.log(s.agentHeader(` Aussie: Swarm complete `))
        } else if (type === 'tier_start') {
          console.log()
          console.log(s.toolHeader(` ${message} `))
        } else {
          console.log(s.info(`Info: ${message}`))
        }
      })

      orchestrator.on('agent_event', (e: any) => {
        const color = TIER_COLOR[e.tier as AgentTier] ?? '#808080'

        switch (e.type) {
          case 'agent_start':
            process.stdout.write(
              chalk.hex(color).bold(`  ${e.agent_id}: `) +
              chalk.hex(color)((e.role ?? '').slice(0, 60)) + '\n'
            )
            break
          case 'tool_call':
            process.stdout.write(
              s.toolArgBold(`    tool: ${e.tool} `) +
              s.toolArg(JSON.stringify(e.input ?? '').slice(0, 80)) + '\n'
            )
            break
          case 'agent_complete':
            process.stdout.write(
              s.success(`  ${e.agent_id}: done `) +
              s.hint(`${e.duration_ms}ms · ${e.tokens} tokens`) + '\n'
            )
            break
          case 'agent_error':
            process.stdout.write(
              s.error(`  ${e.agent_id}: ${(e.error ?? '').slice(0, 80)}`) + '\n'
            )
            break
        }
      })

      orchestrator.on('team_complete', (result: any) => {
        if (result.merged) {
          console.log()
          console.log(s.agentHeader(` Aussie: Team result (${result.task_id}) `))
          console.log(s.white(result.merged.slice(0, 1000)))
        }
      })

      orchestrator.on('team_error', (err: any) => {
        console.log(s.error(`Error: ${err}`))
      })

      process.on('SIGINT', () => {
        console.log()
        console.log(s.warning('Interrupting swarm...'))
        orchestrator.interruptAll()
        process.exit(0)
      })

      await orchestrator.dispatchToSwarm(prompt)
    })
}
