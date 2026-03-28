/**
 * pfaa exec — execute Python 3.15 code in the isolated sandbox.
 */

import { Command } from 'commander'
import { PythonSandbox } from '../../sandbox/python.js'
import { loadConfig } from '../../core/config.js'
import chalk from 'chalk'
import { readFileSync } from 'fs'

export function execCommand(): Command {
  return new Command('exec')
    .description('Execute Python 3.15 code in the isolated sandbox')
    .argument('[file]', 'Python file to execute (or pipe via stdin)')
    .option('-c, --code <code>', 'Inline code string to execute')
    .option('--timeout <ms>', 'Execution timeout in ms', '30000')
    .option('--memory-limit <mb>', 'Memory limit in MB', '512')
    .option('--no-network', 'Block network access inside sandbox')
    .option('--persist', 'Keep REPL state between runs', false)
    .action(async (file, opts, cmd) => {
      const globals = cmd.parent!.opts()
      const config = await loadConfig(globals.config)

      const sandbox = new PythonSandbox({
        timeout: parseInt(opts.timeout),
        memoryLimitMb: parseInt(opts.memoryLimit),
        allowNetwork: opts.network !== false,
        persist: opts.persist,
        workspace: globals.workspace,
        pythonBin: config.pythonBin ?? 'python3',
      })

      let code: string
      if (opts.code) {
        code = opts.code
      } else if (file) {
        code = readFileSync(file, 'utf8')
      } else {
        code = readFileSync('/dev/stdin', 'utf8')
      }

      console.log(chalk.gray('── sandbox exec ──'))
      const result = await sandbox.execute(code)

      if (result.stdout) process.stdout.write(result.stdout)
      if (result.stderr) process.stderr.write(chalk.yellow(result.stderr))

      if (result.error) {
        console.error(chalk.red(`\n  ✗ ${result.error.type}: ${result.error.message}`))
        process.exit(1)
      }

      console.log(chalk.green(`\n  completed in ${result.durationMs}ms`))
    })
}
