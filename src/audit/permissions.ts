/**
 * Permission gate — blocks dangerous operations before execution.
 */

export interface PermissionConfig {
  deny?: string[]
  requireConfirm?: string[]
  allowPaths?: string[]
}

export interface PermissionResult {
  allowed: boolean
  reason?: string
}

export class PermissionGate {
  constructor(private config: PermissionConfig) {}

  check(toolName: string, input: Record<string, any>): PermissionResult {
    if (this.config.deny?.includes(toolName)) {
      return { allowed: false, reason: `Tool "${toolName}" is in the deny list` }
    }

    if (toolName === 'shell') {
      const dangerous = ['rm -rf', 'mkfs', 'dd if=', ':(){:|:&};:', 'chmod 777 /', 'sudo rm']
      const cmd: string = input.command ?? ''
      for (const d of dangerous) {
        if (cmd.includes(d)) {
          return { allowed: false, reason: `Blocked potentially destructive command: "${d}"` }
        }
      }
    }

    return { allowed: true }
  }
}
