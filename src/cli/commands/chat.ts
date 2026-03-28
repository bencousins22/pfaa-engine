/**
 * pfaa chat — placeholder for interactive mode (run_cli.ts is the full implementation).
 */

import { Command } from 'commander'
import chalk from 'chalk'

export function chatCommand(): Command {
  return new Command('chat')
    .description('Start interactive chat mode (alias: pfaa-cli)')
    .action(() => {
      console.log(chalk.cyan('Use `pfaa-cli` or `node bin/pfaa-cli.js` for interactive mode.'))
    })
}
