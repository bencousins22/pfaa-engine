/**
 * Swarm — Team/Swarm protocol for PFAA multi-agent orchestration.
 *
 * Inspired by Claude Code's TeamCreateTool/SendMessageTool patterns.
 * Provides team creation, file-based mailbox messaging, and coordinated
 * task dispatch across agent members.
 */

import { mkdirSync, readFileSync, writeFileSync, existsSync, readdirSync, unlinkSync } from 'node:fs'
import { join } from 'node:path'
// Aligns with PFAA's core type system (AgentEvent, PFAAConfig, etc.)

// ─── Types ───────────────────────────────────────────────────────────────────

export type MessageType = 'task_assignment' | 'status_update' | 'shutdown_request' | 'result'

export interface SwarmMessage {
  id: string
  from: string
  to: string
  type: MessageType
  content: string
  timestamp: string
  metadata?: Record<string, unknown>
}

export interface SwarmMember {
  agentId: string
  role: string
  model?: string
  joinedAt: string
  status: 'idle' | 'working' | 'done' | 'error'
}

export interface TeamFile {
  name: string
  description: string
  createdAt: string
  members: SwarmMember[]
}

export interface TaskAssignment {
  agentId: string
  role: string
  task: string
}

export interface SwarmResult {
  agentId: string
  role: string
  status: 'success' | 'error'
  output: string
  completedAt: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

const TEAMS_DIR = '.pfaa/teams'
const MAILBOX_DIR = '.pfaa/mailbox'

function ensureDir(dir: string): void {
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true })
  }
}

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

// ─── SwarmMailbox ────────────────────────────────────────────────────────────

/**
 * File-based message queue for inter-agent communication.
 * Each agent has a mailbox directory; messages are individual JSON files.
 */
export class SwarmMailbox {
  private baseDir: string

  constructor(baseDir: string = MAILBOX_DIR) {
    this.baseDir = baseDir
    ensureDir(this.baseDir)
  }

  /** Queue a message from one agent to another. */
  send(from: string, to: string, type: MessageType, content: string, metadata?: Record<string, unknown>): SwarmMessage {
    const msg: SwarmMessage = {
      id: generateId(),
      from,
      to,
      type,
      content,
      timestamp: new Date().toISOString(),
      metadata,
    }
    const agentDir = join(this.baseDir, to)
    ensureDir(agentDir)
    writeFileSync(join(agentDir, `${msg.id}.json`), JSON.stringify(msg, null, 2))
    return msg
  }

  /** Retrieve and consume all pending messages for an agent. */
  receive(agentId: string): SwarmMessage[] {
    const agentDir = join(this.baseDir, agentId)
    if (!existsSync(agentDir)) return []

    const files = readdirSync(agentDir).filter(f => f.endsWith('.json')).sort()
    const messages: SwarmMessage[] = []

    for (const file of files) {
      const filePath = join(agentDir, file)
      try {
        const msg = JSON.parse(readFileSync(filePath, 'utf-8')) as SwarmMessage
        messages.push(msg)
        unlinkSync(filePath) // consume on read
      } catch {
        // skip corrupted messages
      }
    }

    return messages
  }

  /** Peek at pending messages without consuming them. */
  peek(agentId: string): SwarmMessage[] {
    const agentDir = join(this.baseDir, agentId)
    if (!existsSync(agentDir)) return []

    const files = readdirSync(agentDir).filter(f => f.endsWith('.json')).sort()
    const messages: SwarmMessage[] = []

    for (const file of files) {
      try {
        messages.push(JSON.parse(readFileSync(join(agentDir, file), 'utf-8')))
      } catch {
        // skip corrupted
      }
    }

    return messages
  }

  /** Broadcast a message from one agent to all listed recipients. */
  broadcast(from: string, recipientIds: string[], type: MessageType, content: string, metadata?: Record<string, unknown>): SwarmMessage[] {
    return recipientIds
      .filter(id => id !== from)
      .map(id => this.send(from, id, type, content, metadata))
  }
}

// ─── SwarmTeam ───────────────────────────────────────────────────────────────

/**
 * Manages team membership with file-based persistence.
 * Team state is stored as JSON in .pfaa/teams/<name>.json.
 */
export class SwarmTeam {
  private teamsDir: string
  private mailbox: SwarmMailbox

  constructor(teamsDir: string = TEAMS_DIR, mailbox?: SwarmMailbox) {
    this.teamsDir = teamsDir
    this.mailbox = mailbox ?? new SwarmMailbox()
    ensureDir(this.teamsDir)
  }

  /** Create a new team with initial roles. Returns the team file data. */
  create(name: string, description: string, roles: Array<{ agentId: string; role: string; model?: string }>): TeamFile {
    const filePath = this.teamFilePath(name)
    if (existsSync(filePath)) {
      throw new Error(`Team "${name}" already exists`)
    }

    const now = new Date().toISOString()
    const team: TeamFile = {
      name,
      description,
      createdAt: now,
      members: roles.map(r => ({
        agentId: r.agentId,
        role: r.role,
        model: r.model,
        joinedAt: now,
        status: 'idle',
      })),
    }

    writeFileSync(filePath, JSON.stringify(team, null, 2))
    return team
  }

  /** Add a member to an existing team. */
  addMember(teamName: string, agentId: string, role: string, model?: string): SwarmMember {
    const team = this.load(teamName)
    if (team.members.some(m => m.agentId === agentId)) {
      throw new Error(`Agent "${agentId}" is already a member of team "${teamName}"`)
    }

    const member: SwarmMember = {
      agentId,
      role,
      model,
      joinedAt: new Date().toISOString(),
      status: 'idle',
    }

    team.members.push(member)
    this.save(teamName, team)
    return member
  }

  /** Remove a member from an existing team. */
  removeMember(teamName: string, agentId: string): void {
    const team = this.load(teamName)
    const idx = team.members.findIndex(m => m.agentId === agentId)
    if (idx === -1) {
      throw new Error(`Agent "${agentId}" is not a member of team "${teamName}"`)
    }
    team.members.splice(idx, 1)
    this.save(teamName, team)
  }

  /** List all members of a team. */
  getMembers(teamName: string): SwarmMember[] {
    return this.load(teamName).members
  }

  /** Update a member's status. */
  updateStatus(teamName: string, agentId: string, status: SwarmMember['status']): void {
    const team = this.load(teamName)
    const member = team.members.find(m => m.agentId === agentId)
    if (!member) {
      throw new Error(`Agent "${agentId}" not found in team "${teamName}"`)
    }
    member.status = status
    this.save(teamName, team)
  }

  /** Broadcast a message to all team members. */
  broadcast(teamName: string, from: string, type: MessageType, content: string): SwarmMessage[] {
    const team = this.load(teamName)
    const recipientIds = team.members.map(m => m.agentId)
    return this.mailbox.broadcast(from, recipientIds, type, content)
  }

  /** Send a direct message to a specific team member. */
  sendTo(teamName: string, from: string, agentId: string, type: MessageType, content: string): SwarmMessage {
    const team = this.load(teamName)
    if (!team.members.some(m => m.agentId === agentId)) {
      throw new Error(`Agent "${agentId}" is not a member of team "${teamName}"`)
    }
    return this.mailbox.send(from, agentId, type, content)
  }

  /** Check if a team exists. */
  exists(teamName: string): boolean {
    return existsSync(this.teamFilePath(teamName))
  }

  /** Load a team from disk. */
  load(teamName: string): TeamFile {
    const filePath = this.teamFilePath(teamName)
    if (!existsSync(filePath)) {
      throw new Error(`Team "${teamName}" does not exist`)
    }
    return JSON.parse(readFileSync(filePath, 'utf-8')) as TeamFile
  }

  /** Delete a team file. */
  delete(teamName: string): void {
    const filePath = this.teamFilePath(teamName)
    if (existsSync(filePath)) {
      unlinkSync(filePath)
    }
  }

  private save(teamName: string, team: TeamFile): void {
    writeFileSync(this.teamFilePath(teamName), JSON.stringify(team, null, 2))
  }

  private teamFilePath(name: string): string {
    return join(this.teamsDir, `${name}.json`)
  }
}

// ─── SwarmCoordinator ────────────────────────────────────────────────────────

/**
 * Coordinates task dispatch and result collection across a team.
 * Decomposes a goal into role-based task assignments, dispatches via mailbox,
 * and collects results.
 */
export class SwarmCoordinator {
  private team: SwarmTeam
  private mailbox: SwarmMailbox
  private teamName: string
  private coordinatorId: string
  private results: Map<string, SwarmResult> = new Map()

  constructor(teamName: string, team: SwarmTeam, mailbox: SwarmMailbox, coordinatorId: string = 'coordinator') {
    this.teamName = teamName
    this.team = team
    this.mailbox = mailbox
    this.coordinatorId = coordinatorId
  }

  /**
   * Decompose a goal into task assignments based on team roles.
   * Uses a simple 1:1 role-to-task mapping. For complex decomposition,
   * feed the goal through the Orchestrator's planTask() first.
   */
  dispatch(goal: string, tasksByRole?: Record<string, string>): TaskAssignment[] {
    const members = this.team.getMembers(this.teamName)
    const assignments: TaskAssignment[] = []

    for (const member of members) {
      const task = tasksByRole?.[member.role] ?? `[${member.role}] ${goal}`

      this.mailbox.send(
        this.coordinatorId,
        member.agentId,
        'task_assignment',
        task,
        { goal, role: member.role },
      )

      this.team.updateStatus(this.teamName, member.agentId, 'working')

      assignments.push({
        agentId: member.agentId,
        role: member.role,
        task,
      })
    }

    return assignments
  }

  /** Submit a result for a specific agent. */
  submitResult(agentId: string, output: string, status: 'success' | 'error' = 'success'): void {
    const members = this.team.getMembers(this.teamName)
    const member = members.find(m => m.agentId === agentId)
    if (!member) {
      throw new Error(`Agent "${agentId}" is not a member of team "${this.teamName}"`)
    }

    this.results.set(agentId, {
      agentId,
      role: member.role,
      status,
      output,
      completedAt: new Date().toISOString(),
    })

    this.team.updateStatus(this.teamName, agentId, status === 'success' ? 'done' : 'error')

    // Notify coordinator via mailbox
    this.mailbox.send(agentId, this.coordinatorId, 'result', output, {
      status,
      role: member.role,
    })
  }

  /**
   * Check whether all team members have completed (status is 'done' or 'error').
   * Returns true when every member has a result.
   */
  isComplete(): boolean {
    const members = this.team.getMembers(this.teamName)
    return members.every(m => m.status === 'done' || m.status === 'error')
  }

  /**
   * Wait for all members to complete by polling status.
   * Returns once all members have status 'done' or 'error'.
   *
   * In practice, agents call submitResult() as they finish. This method
   * is useful for synchronous coordination or test harnesses.
   */
  async waitForAll(pollIntervalMs: number = 500, timeoutMs: number = 60_000): Promise<void> {
    const start = Date.now()
    while (!this.isComplete()) {
      if (Date.now() - start > timeoutMs) {
        throw new Error(`Swarm timeout: not all members completed within ${timeoutMs}ms`)
      }
      await new Promise(r => setTimeout(r, pollIntervalMs))
    }
  }

  /** Collect all submitted results. */
  collectResults(): SwarmResult[] {
    return Array.from(this.results.values())
  }

  /** Get results keyed by role for easy consumption. */
  collectResultsByRole(): Record<string, SwarmResult> {
    const byRole: Record<string, SwarmResult> = {}
    for (const result of this.results.values()) {
      byRole[result.role] = result
    }
    return byRole
  }

  /** Send a shutdown request to all team members. */
  shutdown(reason: string = 'Coordinator shutdown'): void {
    this.team.broadcast(this.teamName, this.coordinatorId, 'shutdown_request', reason)
  }
}
