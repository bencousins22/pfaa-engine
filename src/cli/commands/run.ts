/**
 * pfaa run — one-shot task execution with autonomous agents.
 */

import { Command } from 'commander'
import { Orchestrator } from '../../core/orchestrator.js'
import { loadConfig } from '../../core/config.js'
import { StreamRenderer } from '../render/stream.js'
import { AuditLogger } from '../../audit/logger.js'
import chalk from 'chalk'

export function runCommand(): Command {
  return new Command('run')
    .description('Run a one-shot task with autonomous agents')
    .argument('<prompt>', 'Task prompt or path to prompt file')
    .option('-t, --tools <tools...>', 'Enable specific tools', ['file', 'shell', 'fetch', 'code'])
    .option('--plan', 'Show execution plan before running', false)
    .option('--dry-run', 'Show what would happen, do not execute', false)
    .option('--output <path>', 'Save output to file')
    .action(async (prompt, opts, cmd) => {
      const globals = cmd.parent!.opts()
      const config = await loadConfig(globals.config)
      const audit = globals.audit !== false ? new AuditLogger(config.auditDir) : null

      const orchestrator = new Orchestrator({
        provider: globals.provider,
        model: globals.model,
        sandbox: globals.sandbox,
        maxTokens: parseInt(globals.maxTokens),
        compactThreshold: parseInt(globals.compactThreshold),
        workspace: globals.workspace,
        tools: opts.tools,
        config,
        audit,
        deferredTools: globals.deferred,
      })

      if (opts.plan) {
        const plan = await orchestrator.planTask(prompt)
        console.log(chalk.cyan('\n── Execution plan ──'))
        plan.steps.forEach((s: string, i: number) => console.log(chalk.gray(`  ${i + 1}.`), s))
        console.log()
      }

      const renderer = new StreamRenderer({ json: globals.json })

      for await (const event of orchestrator.run(prompt, { dryRun: opts.dryRun })) {
        renderer.render(event)
      }

      if (opts.output) {
        await renderer.saveToFile(opts.output)
        console.log(chalk.green(`\n  Output saved to ${opts.output}`))
      }

      await audit?.finalise()
    })
}
