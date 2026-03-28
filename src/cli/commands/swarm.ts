/**
 * pfaa swarm — dispatch a task to the full PFAA 9-tier agent swarm.
 * Rich colorful output with per-tier color coding.
 */

import { Command } from 'commander'
import { SwarmOrchestrator, type AgentTier } from '../../swarm/team.js'
import { loadConfig } from '../../core/config.js'
import chalk from 'chalk'

// ── Per-tier color palette — each tier gets its own vibrant color ────
const TIER_STYLE: Record<AgentTier, { color: string; icon: string; label: string }> = {
  intelligence: { color: '#8B5CF6', icon: '🧠', label: 'Intelligence' },
  acquisition:  { color: '#3B82F6', icon: '🎯', label: 'Acquisition' },
  enrichment:   { color: '#06B6D4', icon: '🔍', label: 'Enrichment' },
  scoring:      { color: '#F59E0B', icon: '📊', label: 'Scoring' },
  outreach:     { color: '#10B981', icon: '📧', label: 'Outreach' },
  conversion:   { color: '#EF4444', icon: '🤝', label: 'Conversion' },
  nurture:      { color: '#EC4899', icon: '💌', label: 'Nurture' },
  content:      { color: '#84CC16', icon: '✏️', label: 'Content' },
  operations:   { color: '#6B7280', icon: '⚙️', label: 'Operations' },
}

const C = {
  purple:      chalk.hex('#8B5CF6'),
  purpleBold:  chalk.hex('#A78BFA').bold,
  emerald:     chalk.hex('#34D399'),
  emeraldBold: chalk.hex('#10B981').bold,
  cyan:        chalk.hex('#22D3EE'),
  amber:       chalk.hex('#FBBF24'),
  rose:        chalk.hex('#FB7185'),
  roseBold:    chalk.hex('#F43F5E').bold,
  bright:      chalk.hex('#F8FAFC'),
  dim:         chalk.hex('#94A3B8'),
  muted:       chalk.hex('#64748B'),
  lime:        chalk.hex('#A3E635'),
  indigo:      chalk.hex('#818CF8'),
}

function gradient(text: string, colors: string[]): string {
  const chars = [...text]
  return chars.map((c, i) => {
    const idx = Math.floor((i / chars.length) * colors.length)
    return chalk.hex(colors[Math.min(idx, colors.length - 1)])(c)
  }).join('')
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

      // ── Swarm banner ──────────────────────────────────────────
      console.log()
      console.log(gradient('╔══════════════════════════════════════════════════╗', ['#8B5CF6', '#EC4899', '#F59E0B']))
      console.log(
        C.purple('║') +
        chalk.bgHex('#7C3AED').white.bold(' 🐝 PFAA Swarm ') +
        '                                  ' +
        C.purple('║')
      )
      console.log(gradient('╚══════════════════════════════════════════════════╝', ['#F59E0B', '#EC4899', '#8B5CF6']))
      console.log()
      console.log(C.dim('  Prompt: ') + C.bright(prompt.slice(0, 70)))
      console.log(
        C.dim('  Provider: ') + C.amber(globals.provider) +
        C.muted('  ·  ') +
        C.dim('Tiers: ') + C.indigo('9') +
        C.muted('  ·  ') +
        C.dim('Agents: ') + C.lime('~25')
      )

      // ── Tier legend ───────────────────────────────────────────
      console.log()
      const tierEntries = Object.entries(TIER_STYLE) as [AgentTier, typeof TIER_STYLE[AgentTier]][]
      const legendRow1 = tierEntries.slice(0, 5).map(([_, s]) =>
        chalk.hex(s.color)(`${s.icon} ${s.label}`)
      ).join(C.muted(' · '))
      const legendRow2 = tierEntries.slice(5).map(([_, s]) =>
        chalk.hex(s.color)(`${s.icon} ${s.label}`)
      ).join(C.muted(' · '))
      console.log('  ' + legendRow1)
      console.log('  ' + legendRow2)
      console.log()
      console.log(C.muted('  ' + '─'.repeat(54)))
      console.log()

      // ── Event handlers ────────────────────────────────────────
      orchestrator.on('status', ({ type, message }: any) => {
        const icon = type === 'swarm_complete' ? '✨' : type === 'tier_start' ? '▸' : '●'
        console.log(C.amber(`  ${icon} `) + C.bright(message))
      })

      orchestrator.on('agent_event', (e: any) => {
        const style = TIER_STYLE[e.tier as AgentTier]
        if (!style) return
        const tierColor = chalk.hex(style.color)
        const tierColorBold = chalk.hex(style.color).bold

        switch (e.type) {
          case 'agent_start':
            process.stdout.write(
              tierColor(`    ${style.icon} `) +
              tierColorBold(e.agent_id) +
              C.dim(` ${(e.role ?? '').slice(0, 50)}`) + '\n'
            )
            break
          case 'tool_call':
            process.stdout.write(
              tierColor('      ') +
              C.cyan(`⚙ ${e.tool}`) +
              C.muted(` ${JSON.stringify(e.input ?? '').slice(0, 60)}`) + '\n'
            )
            break
          case 'agent_complete':
            process.stdout.write(
              tierColor(`    ✓ ${e.agent_id} `) +
              C.dim(`${e.duration_ms}ms · ${e.tokens} tokens`) + '\n'
            )
            break
          case 'agent_error':
            process.stdout.write(
              C.rose(`    ✗ ${e.agent_id} `) +
              C.roseBold((e.error ?? '').slice(0, 80)) + '\n'
            )
            break
        }
      })

      orchestrator.on('team_complete', (result: any) => {
        if (result.merged) {
          console.log()
          console.log(C.emeraldBold(`  ── Team result: ${result.task_id} ──`))
          console.log(C.bright(result.merged.slice(0, 1000)))
        }
      })

      orchestrator.on('team_error', (err: any) => {
        console.log(C.roseBold(`  ✗ Team error: ${err}`))
      })

      process.on('SIGINT', () => {
        console.log(C.amber('\n  ⚠ Interrupting swarm...'))
        orchestrator.interruptAll()
        process.exit(0)
      })

      await orchestrator.dispatchToSwarm(prompt)

      // ── Final summary ─────────────────────────────────────────
      console.log()
      console.log(gradient('  ═══════════════════════════════════════════', ['#10B981', '#8B5CF6', '#F59E0B']))
      console.log(C.emeraldBold('  ✨ Swarm complete'))
      console.log()
    })
}
