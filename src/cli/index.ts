/**
 * PFAA CLI — Commander-based entry point.
 * Subcommands: run, chat, exec, swarm
 */

import { Command } from 'commander'
import { readFileSync } from 'fs'
import { runCommand } from './commands/run.js'
import { chatCommand } from './commands/chat.js'
import { execCommand } from './commands/exec.js'
import { swarmCommand } from './commands/swarm.js'

const pkg = JSON.parse(readFileSync(new URL('../../package.json', import.meta.url), 'utf8'))

const program = new Command()

program
  .name('pfaa')
  .description('Platform for Autonomous Agents — enterprise CLI')
  .version(pkg.version)

program
  .option('-p, --provider <provider>', 'AI provider: claude | gemini', 'claude')
  .option('-m, --model <model>', 'Model name (overrides provider default)')
  .option('--sandbox', 'Run code in isolated Python 3.15 sandbox', false)
  .option('--no-audit', 'Disable audit logging for this session')
  .option('--config <path>', 'Path to pfaa.config.json', './pfaa.config.json')
  .option('--workspace <path>', 'Working directory', process.cwd())
  .option('--max-tokens <n>', 'Max output tokens', '8192')
  .option('--compact-threshold <n>', 'Auto-compact context at N tokens', '80000')
  .option('--json', 'Output structured JSON instead of streaming text', false)

program.addCommand(runCommand())
program.addCommand(chatCommand())
program.addCommand(execCommand())
program.addCommand(swarmCommand())

program.parse()
