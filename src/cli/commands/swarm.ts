/**
 * pfaa swarm — dispatch a task to the full PFAA 9-tier agent swarm.
 * Uses Agent Zero PrintStyle colors throughout.
 */

import { Command } from 'commander'
import { SwarmOrchestrator, type AgentTier } from '../../swarm/team.js'
import { loadConfig } from '../../core/config.js'
import chalk from 'chalk'

// Agent Zero color scheme
const s = {
  userPrompt:     chalk.bgHex('#6C3483').white.bold,
  agentHeader:    chalk.bgHex('#1D8348').white.bold,
  agentStream:    chalk.hex('#b3ffd9').italic,
  toolHeader:     chalk.bgWhite.hex('#1B4F72').bold,
  toolArg:        chalk.hex('#85C1E9'),
  toolArgBold:    chalk.hex('#85C1E9').bold,
  error:          chalk.red,
  warning:        chalk.hex('#FFA500'),
  hint:           chalk.hex('#6C3483'),
  info:           chalk.blue,
  success:        chalk.green,
  white:          chalk.white,
}

// Per-tier colors (extending Agent Zero's palette for 9 tiers)
const TIER_COLOR: Record<AgentTier, string> = {
  intelligence: '#b3ffd9',   // mint (agent stream color)
  acquisition:  '#85C1E9',   // light blue (tool color)
  enrichment:   '#85C1E9',
  scoring:      '#FFA500',   // orange (warning color)
  outreach:     '#1D8348',   // green (agent header)
  conversion:   '#6C3483',   // purple (user prompt)
  nurture:      '#6C3483',
  content:      '#1B4F72',   // dark blue (tool header)
  operations:   '#808080',   // gray
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

      // Agent Zero style header
      console.log()
      console.log(s.agentHeader(` Agent 0: Dispatching to 9-tier swarm `))
      console.log(s.hint(`Prompt: ${prompt.slice(0, 80)}`))
      console.log(s.info(`Info: Provider: ${globals.provider} | Tiers: 9 | Agents: ~25`))
      console.log()

      orchestrator.on('status', ({ type, message }: any) => {
        if (type === 'swarm_complete') {
          console.log()
          console.log(s.agentHeader(` Agent 0: Swarm complete `))
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
          console.log(s.agentHeader(` Agent 0: Team result (${result.task_id}) `))
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
