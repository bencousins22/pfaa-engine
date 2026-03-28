/**
 * pfaa memory — Agent Zero-styled memory management UI.
 * View, search, manage, and inspect the jmem memory store.
 *
 * Subcommands:
 *   pfaa memory stats    — Show memory statistics
 *   pfaa memory search   — Semantic search across memories
 *   pfaa memory list     — List memories by area/type
 *   pfaa memory forget   — Soft-delete a memory
 *   pfaa memory inspect  — Show full details of a memory
 */

import { Command } from 'commander'
import { MemoryStore } from '../../memory/store.js'
import { loadConfig } from '../../core/config.js'
import chalk from 'chalk'

// Agent Zero PrintStyle colors
const toolHead = (t: string) => chalk.bgWhite.hex('#1B4F72').bold(` ${t} `)
const toolVal = (t: string) => chalk.hex('#85C1E9')(t)
const toolKey = (t: string) => chalk.hex('#85C1E9').bold(t)
const agentHead = (t: string) => chalk.bgHex('#1D8348').white.bold(` ${t} `)
const hint = (t: string) => chalk.hex('#6C3483')(t)
const info = (t: string) => chalk.blue(t)
const ok = (t: string) => chalk.green(t)
const err = (t: string) => chalk.red(t)
const warn = (t: string) => chalk.hex('#FFA500')(t)
const dim = (t: string) => chalk.hex('#808080')(t)

export function memoryCommand(): Command {
  const cmd = new Command('memory')
    .description('Manage the jmem memory store (Qdrant + sentence-transformers)')

  // ── stats ──────────────────────────────────────────────────────
  cmd.command('stats')
    .description('Show memory statistics')
    .action(async (_opts, c) => {
      const globals = c.parent!.parent!.opts()
      const config = await loadConfig(globals.config)
      const store = new MemoryStore(config.qdrantUrl)
      const s = await store.stats()

      console.log()
      console.log(toolHead('Agent 0: Memory Statistics'))
      console.log()

      if (!s.available) {
        console.log(warn('Warning: Qdrant not available. Memory is disabled.'))
        console.log(hint(`Hint: Start Qdrant with: docker run -p 6333:6333 qdrant/qdrant`))
        return
      }

      console.log(toolKey('Total memories: ') + toolVal(String(s.total)))
      console.log()

      if (Object.keys(s.byArea).length) {
        console.log(toolKey('By area:'))
        for (const [area, count] of Object.entries(s.byArea)) {
          const bar = '█'.repeat(Math.min(count, 40))
          console.log(toolVal(`  ${area.padEnd(15)} ${String(count).padStart(4)} `) + hint(bar))
        }
        console.log()
      }

      if (Object.keys(s.byType).length) {
        console.log(toolKey('By fact type:'))
        for (const [type, count] of Object.entries(s.byType)) {
          const bar = '█'.repeat(Math.min(count, 40))
          console.log(toolVal(`  ${type.padEnd(15)} ${String(count).padStart(4)} `) + hint(bar))
        }
        console.log()
      }

      console.log(ok('Success: Stats retrieved'))
    })

  // ── search ─────────────────────────────────────────────────────
  cmd.command('search')
    .description('Semantic search across memories')
    .argument('<query>', 'Search query')
    .option('-n, --limit <n>', 'Max results', '5')
    .option('-a, --area <area>', 'Filter by area')
    .option('-t, --type <type>', 'Filter by fact type')
    .action(async (query, opts, c) => {
      const globals = c.parent!.parent!.opts()
      const config = await loadConfig(globals.config)
      const store = new MemoryStore(config.qdrantUrl)

      console.log()
      console.log(toolHead(`Agent 0: Using tool 'memory_recall':`))
      console.log(toolKey('query: ') + toolVal(query))
      if (opts.area) console.log(toolKey('area: ') + toolVal(opts.area))
      if (opts.type) console.log(toolKey('type: ') + toolVal(opts.type))
      console.log()

      const results = await store.recall(query, parseInt(opts.limit), {
        area: opts.area,
        fact_type: opts.type,
      })

      console.log(toolHead(`Agent 0: Response from tool 'memory_recall':`))
      console.log()

      if (!results.length) {
        console.log(dim('  No memories found.'))
        return
      }

      for (const r of results) {
        const score = r.score ? (r.score * 100).toFixed(1) + '%' : '?'
        const area = (r.metadata.area as string) ?? '?'
        const type = (r.metadata.fact_type as string) ?? '?'
        const utility = (r.metadata.utility_score as number)?.toFixed(2) ?? '?'
        const retrievals = r.metadata.retrieval_count ?? 0

        console.log(toolKey(`  [${score}] `) + chalk.white(r.content.slice(0, 120)))
        console.log(dim(`         id=${r.id.slice(0, 8)}  area=${area}  type=${type}  utility=${utility}  retrievals=${retrievals}`))
        console.log()
      }

      console.log(ok(`Success: ${results.length} memories found`))
    })

  // ── list ───────────────────────────────────────────────────────
  cmd.command('list')
    .description('List memories by area/type')
    .option('-a, --area <area>', 'Filter by area')
    .option('-t, --type <type>', 'Filter by fact type')
    .option('-n, --limit <n>', 'Max results', '20')
    .action(async (opts, c) => {
      const globals = c.parent!.parent!.opts()
      const config = await loadConfig(globals.config)
      const store = new MemoryStore(config.qdrantUrl)

      console.log()
      console.log(toolHead('Agent 0: Memory listing'))
      console.log()

      const memories = await store.list({
        area: opts.area,
        fact_type: opts.type,
        limit: parseInt(opts.limit),
      })

      if (!memories.length) {
        console.log(dim('  No memories found.'))
        return
      }

      for (const m of memories) {
        const area = (m.metadata.area as string) ?? '?'
        const type = (m.metadata.fact_type as string) ?? '?'
        const utility = ((m.metadata.utility_score as number) ?? 0).toFixed(2)
        const ts = m.metadata.timestamp
          ? new Date((m.metadata.timestamp as number) * 1000).toISOString().slice(0, 16)
          : '?'

        console.log(
          toolKey(`  ${m.id.slice(0, 8)} `) +
          dim(`${ts} `) +
          hint(`[${area}/${type}] `) +
          toolVal(`u=${utility} `) +
          chalk.white(m.content.slice(0, 80))
        )
      }

      console.log()
      console.log(ok(`Success: ${memories.length} memories listed`))
    })

  // ── forget ─────────────────────────────────────────────────────
  cmd.command('forget')
    .description('Soft-delete a memory by ID')
    .argument('<id>', 'Memory ID')
    .option('--hard', 'Permanently delete (no undo)', false)
    .action(async (id, opts, c) => {
      const globals = c.parent!.parent!.opts()
      const config = await loadConfig(globals.config)
      const store = new MemoryStore(config.qdrantUrl)

      console.log()
      const success = opts.hard
        ? await store.forgetHard(id)
        : await store.forget(id)

      if (success) {
        console.log(ok(`Success: Memory ${id.slice(0, 8)} ${opts.hard ? 'permanently deleted' : 'marked as forgotten'}`))
      } else {
        console.log(err(`Error: Failed to forget memory ${id.slice(0, 8)}`))
      }
    })

  // ── inspect ────────────────────────────────────────────────────
  cmd.command('inspect')
    .description('Show full details of a memory')
    .argument('<id>', 'Memory ID')
    .action(async (id, _opts, c) => {
      const globals = c.parent!.parent!.opts()
      const config = await loadConfig(globals.config)
      const store = new MemoryStore(config.qdrantUrl)

      console.log()
      console.log(toolHead(`Agent 0: Memory inspection`))
      console.log()

      // Search with the ID as query — not ideal but works for inspection
      const all = await store.list({ limit: 100 })
      const mem = all.find(m => m.id === id || m.id.startsWith(id))

      if (!mem) {
        console.log(err(`Error: Memory ${id} not found`))
        return
      }

      const md = mem.metadata
      console.log(toolKey('id:              ') + toolVal(mem.id))
      console.log(toolKey('content:         ') + chalk.white(mem.content))
      console.log(toolKey('query:           ') + toolVal(String(md.query ?? '')))
      console.log(toolKey('area:            ') + toolVal(String(md.area ?? '?')))
      console.log(toolKey('fact_type:       ') + toolVal(String(md.fact_type ?? '?')))
      console.log(toolKey('confidence:      ') + toolVal(String(md.confidence ?? '?')))
      console.log(toolKey('utility_score:   ') + toolVal(String(md.utility_score ?? '?')))
      console.log(toolKey('retrieval_count: ') + toolVal(String(md.retrieval_count ?? 0)))
      console.log(toolKey('success_count:   ') + toolVal(String(md.success_count ?? 0)))
      console.log(toolKey('failure_count:   ') + toolVal(String(md.failure_count ?? 0)))
      console.log(toolKey('trust_score:     ') + toolVal(String(md.trust_score ?? '?')))
      console.log(toolKey('source_agent:    ') + toolVal(String(md.source_agent ?? '?')))
      console.log(toolKey('visibility:      ') + toolVal(String(md.visibility ?? '?')))
      console.log(toolKey('tags:            ') + toolVal(JSON.stringify(md.tags ?? [])))

      const ts = md.timestamp ? new Date((md.timestamp as number) * 1000).toISOString() : '?'
      const vf = md.valid_from ? new Date((md.valid_from as number) * 1000).toISOString() : '?'
      const vt = md.valid_to ? new Date((md.valid_to as number) * 1000).toISOString() : 'current'
      console.log(toolKey('timestamp:       ') + toolVal(ts))
      console.log(toolKey('valid_from:      ') + toolVal(vf))
      console.log(toolKey('valid_to:        ') + toolVal(vt))
      console.log()
    })

  return cmd
}
