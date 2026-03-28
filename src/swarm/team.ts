/**
 * SwarmOrchestrator — coordinates agent teams like Claude Code's subagent spawning.
 * Each "team" is a Python 3.15 process running a TaskGroup of agents in parallel.
 * Tiers run in dependency order; agents within a tier run concurrently.
 */

import { EventEmitter } from 'events'
import { execa, type ResultPromise } from 'execa'
import { resolve, dirname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = dirname(fileURLToPath(import.meta.url))

export type AgentTier =
  | 'acquisition' | 'enrichment' | 'scoring' | 'outreach'
  | 'conversion' | 'nurture' | 'intelligence' | 'content' | 'operations'

export interface AgentSpec {
  id: string
  tier: AgentTier
  role: string
  model?: string
  tools?: string[]
  memory_area?: string
  system_prompt?: string
}

export interface TeamTask {
  taskId: string
  prompt: string
  agents: AgentSpec[]
  parallel: boolean
  timeout?: number
}

export class AgentTeam extends EventEmitter {
  private proc: ResultPromise | null = null

  constructor(
    private spec: TeamTask,
    private opts: {
      provider: string
      model: string
      workspace: string
      qdrantUrl: string
      pythonBin: string
    }
  ) {
    super()
  }

  async run(): Promise<any> {
    const scriptPath = resolve(__dirname, '../../python/swarm/team_runner.py')

    const payload = JSON.stringify({
      task: this.spec,
      opts: this.opts,
    })

    this.proc = execa(
      this.opts.pythonBin,
      [scriptPath],
      {
        input: payload,
        env: {
          ...process.env,
          ANTHROPIC_API_KEY: process.env.ANTHROPIC_API_KEY,
          GEMINI_API_KEY: process.env.GEMINI_API_KEY,
          PYTHON_GIL: '0',
        },
        timeout: this.spec.timeout ?? 300_000,
        maxBuffer: 100 * 1024 * 1024,
      }
    )

    this.proc.stdout?.on('data', (chunk: Buffer) => {
      const lines = chunk.toString().split('\n').filter(Boolean)
      for (const line of lines) {
        try {
          const event = JSON.parse(line)
          this.emit('event', event)
        } catch {
          this.emit('log', line)
        }
      }
    })

    this.proc.stderr?.on('data', (chunk: Buffer) => {
      this.emit('error_log', chunk.toString())
    })

    const result = await this.proc
    const stdout = String(result.stdout ?? '')
    const finalLines = stdout.split('\n').filter((l: string) => {
      try { return JSON.parse(l)?.type === 'final_result' } catch { return false }
    })
    return JSON.parse(finalLines.at(-1) ?? '{}')
  }

  interrupt(): void {
    this.proc?.kill('SIGINT')
  }
}

// ── Tier dependency graph ─────────────────────────────────────────────
const TIER_ORDER: AgentTier[][] = [
  ['intelligence'],
  ['acquisition', 'enrichment'],
  ['scoring'],
  ['outreach', 'content'],
  ['conversion', 'nurture'],
  ['operations'],
]

// ── Agent spec builders ─────────────────────────────────────────────
function buildAgentsForTier(tier: AgentTier): AgentSpec[] {
  const specs: Record<AgentTier, AgentSpec[]> = {
    intelligence: [
      { id: 'int-market', tier: 'intelligence', role: 'Market intel — cap rates, vacancy, absorption', tools: ['fetch', 'python', 'memory_recall'] },
      { id: 'int-news', tier: 'intelligence', role: 'News monitor — zoning changes, council decisions', tools: ['fetch', 'memory_recall'] },
      { id: 'int-pricing', tier: 'intelligence', role: 'Pricing analyst — comp analysis', tools: ['fetch', 'python', 'memory_recall'] },
    ],
    acquisition: [
      { id: 'acq-scanner', tier: 'acquisition', role: 'Lead scanner — MLS, LoopNet, CoStar', tools: ['fetch', 'shell', 'memory_recall'] },
      { id: 'acq-qualifier', tier: 'acquisition', role: 'Cold qualifier — ICP scoring 0-100', tools: ['python', 'memory_recall'] },
      { id: 'acq-dedup', tier: 'acquisition', role: 'Deduplication — merge duplicate leads', tools: ['file', 'python'] },
    ],
    enrichment: [
      { id: 'enr-company', tier: 'enrichment', role: 'Company enricher — ABN, financials, directors', tools: ['fetch'] },
      { id: 'enr-contact', tier: 'enrichment', role: 'Contact enricher — emails, LinkedIn', tools: ['fetch'] },
      { id: 'enr-property', tier: 'enrichment', role: 'Property enricher — sales, zoning, council data', tools: ['fetch', 'python'] },
    ],
    scoring: [
      { id: 'scr-fit', tier: 'scoring', role: 'ICP fit scorer', tools: ['python', 'memory_recall'] },
      { id: 'scr-timing', tier: 'scoring', role: 'Buy/sell timing detector', tools: ['python', 'memory_recall'] },
      { id: 'scr-value', tier: 'scoring', role: 'Deal value + commission estimator', tools: ['python'] },
    ],
    outreach: [
      { id: 'out-email', tier: 'outreach', role: 'Email composer — personalised outreach', tools: ['file'] },
      { id: 'out-linkedin', tier: 'outreach', role: 'LinkedIn message composer', tools: ['file'] },
      { id: 'out-scheduler', tier: 'outreach', role: 'Follow-up scheduler — cadence management', tools: ['python'] },
    ],
    conversion: [
      { id: 'con-proposal', tier: 'conversion', role: 'Proposal writer — tailored CRE proposals', tools: ['file'] },
      { id: 'con-objection', tier: 'conversion', role: 'Objection handler — rebuttals from memory', tools: ['python'] },
    ],
    nurture: [
      { id: 'nur-newsletter', tier: 'nurture', role: 'Newsletter agent — weekly market updates', tools: ['file'] },
      { id: 'nur-re-engage', tier: 'nurture', role: 'Re-engagement — dormant lead revival', tools: ['file'] },
    ],
    content: [
      { id: 'cnt-listing', tier: 'content', role: 'Listing copywriter — MLS descriptions', tools: ['file'] },
      { id: 'cnt-social', tier: 'content', role: 'Social media — LinkedIn/Instagram posts', tools: ['file'] },
      { id: 'cnt-report', tier: 'content', role: 'Client report generator', tools: ['file', 'python'] },
    ],
    operations: [
      { id: 'ops-compliance', tier: 'operations', role: 'Compliance checker — real estate law', tools: ['python', 'fetch'] },
      { id: 'ops-crm-sync', tier: 'operations', role: 'CRM sync — HubSpot/Pipedrive push', tools: ['fetch', 'python'] },
      { id: 'ops-audit', tier: 'operations', role: 'Audit logger — immutable activity trail', tools: ['file'] },
    ],
  }
  return specs[tier] ?? []
}

export class SwarmOrchestrator extends EventEmitter {
  private teams: Map<string, AgentTeam> = new Map()

  constructor(private opts: {
    provider: string
    model: string
    workspace: string
    qdrantUrl: string
    pythonBin: string
    maxParallelTeams?: number
  }) {
    super()
  }

  async dispatchToSwarm(prompt: string): Promise<void> {
    this.emit('status', { type: 'swarm_start', message: `Dispatching to ${TIER_ORDER.flat().length}-tier swarm` })

    for (const tierGroup of TIER_ORDER) {
      this.emit('status', { type: 'tier_start', message: `Running tiers: ${tierGroup.join(', ')}` })

      const teamTasks = tierGroup.map(tier => ({
        taskId: `${tier}-${Date.now()}`,
        prompt,
        agents: buildAgentsForTier(tier),
        parallel: true,
        timeout: 120_000,
      }))

      const teamPromises = teamTasks.map(task => {
        const team = new AgentTeam(task, { ...this.opts })
        this.teams.set(task.taskId, team)
        team.on('event', (e: any) => this.emit('agent_event', e))
        team.on('log', (l: string) => this.emit('log', l))
        return team.run()
      })

      const results = await Promise.allSettled(teamPromises)
      for (const r of results) {
        if (r.status === 'fulfilled') this.emit('team_complete', r.value)
        else this.emit('team_error', r.reason)
      }
    }

    this.emit('status', { type: 'swarm_complete', message: 'All tiers complete' })
  }

  interruptAll(): void {
    for (const team of this.teams.values()) team.interrupt()
  }
}
