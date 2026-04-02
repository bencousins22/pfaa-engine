/**
 * Task Dependency System for PFAA Engine.
 * Provides task creation, dependency tracking (blocks/blockedBy),
 * auto-unblocking on completion, and file-based persistence.
 *
 * Inspired by Claude Code's TaskCreateTool/TaskUpdateTool patterns.
 */

import { randomUUID } from 'node:crypto'
import { existsSync, mkdirSync, readdirSync, readFileSync, writeFileSync, unlinkSync } from 'node:fs'
import { join } from 'node:path'

// ── Types ──────────────────────────────────────────────────────────────

export type TaskStatus = 'pending' | 'in_progress' | 'completed' | 'failed' | 'deleted'

export interface Task {
  id: string
  subject: string
  description: string
  status: TaskStatus
  owner: string | null
  metadata: Record<string, unknown>
  blocks: string[]
  blockedBy: string[]
  createdAt: string
  updatedAt: string
  completedAt: string | null
  result?: string
  failReason?: string
}

export interface TaskCreateOpts {
  owner?: string
  metadata?: Record<string, unknown>
  blocks?: string[]
  blockedBy?: string[]
}

export interface TaskUpdateFields {
  subject?: string
  description?: string
  status?: TaskStatus
  owner?: string
  metadata?: Record<string, unknown>
  addBlocks?: string[]
  addBlockedBy?: string[]
  result?: string
  failReason?: string
}

export interface TaskFilter {
  status?: TaskStatus | TaskStatus[]
  owner?: string
  blocked?: boolean // true = only blocked tasks, false = only unblocked
}

export type TaskEventType = 'created' | 'completed' | 'failed'
export type TaskEventHandler = (task: Task) => void | Promise<void>

// ── TaskManager ────────────────────────────────────────────────────────

export class TaskManager {
  private tasks: Map<string, Task> = new Map()
  private persistDir: string
  private hooks: Map<TaskEventType, TaskEventHandler[]> = new Map([
    ['created', []],
    ['completed', []],
    ['failed', []],
  ])

  constructor(workspaceRoot?: string) {
    const root = workspaceRoot ?? process.cwd()
    this.persistDir = join(root, '.pfaa', 'tasks')
    this._ensureDir()
    this._loadAll()
  }

  // ── Public API ─────────────────────────────────────────────────────

  /** Create a new task and return its ID. */
  create(subject: string, description: string, opts?: TaskCreateOpts): string {
    const now = new Date().toISOString()
    const id = randomUUID().slice(0, 8)

    const task: Task = {
      id,
      subject,
      description,
      status: 'pending',
      owner: opts?.owner ?? null,
      metadata: opts?.metadata ?? {},
      blocks: [],
      blockedBy: [],
      createdAt: now,
      updatedAt: now,
      completedAt: null,
    }

    this.tasks.set(id, task)

    // Wire up dependency edges
    if (opts?.blocks) {
      for (const targetId of opts.blocks) {
        this._addBlockEdge(id, targetId)
      }
    }
    if (opts?.blockedBy) {
      for (const blockerId of opts.blockedBy) {
        this._addBlockEdge(blockerId, id)
      }
    }

    this._persist(task)
    // Persist any tasks whose blockedBy/blocks arrays changed
    if (opts?.blocks) {
      for (const tid of opts.blocks) {
        const t = this.tasks.get(tid)
        if (t) this._persist(t)
      }
    }
    if (opts?.blockedBy) {
      for (const tid of opts.blockedBy) {
        const t = this.tasks.get(tid)
        if (t) this._persist(t)
      }
    }

    this._emit('created', task)
    return id
  }

  /** Update fields on an existing task. */
  update(taskId: string, updates: TaskUpdateFields): Task {
    const task = this._mustGet(taskId)
    const now = new Date().toISOString()

    if (updates.subject !== undefined) task.subject = updates.subject
    if (updates.description !== undefined) task.description = updates.description
    if (updates.owner !== undefined) task.owner = updates.owner
    if (updates.result !== undefined) task.result = updates.result
    if (updates.failReason !== undefined) task.failReason = updates.failReason

    if (updates.metadata !== undefined) {
      for (const [key, value] of Object.entries(updates.metadata)) {
        if (value === null) {
          delete task.metadata[key]
        } else {
          task.metadata[key] = value
        }
      }
    }

    if (updates.addBlocks) {
      for (const targetId of updates.addBlocks) {
        this._addBlockEdge(taskId, targetId)
        const t = this.tasks.get(targetId)
        if (t) this._persist(t)
      }
    }
    if (updates.addBlockedBy) {
      for (const blockerId of updates.addBlockedBy) {
        this._addBlockEdge(blockerId, taskId)
        const t = this.tasks.get(blockerId)
        if (t) this._persist(t)
      }
    }

    if (updates.status !== undefined && updates.status !== task.status) {
      task.status = updates.status
      if (updates.status === 'completed') {
        task.completedAt = now
        this._autoUnblock(taskId)
        this._persist(task)
        task.updatedAt = now
        this._emit('completed', task)
        return task
      }
      if (updates.status === 'failed') {
        task.completedAt = now
        this._persist(task)
        task.updatedAt = now
        this._emit('failed', task)
        return task
      }
    }

    task.updatedAt = now
    this._persist(task)
    return task
  }

  /** Get a single task by ID. Returns undefined if not found. */
  get(taskId: string): Task | undefined {
    return this.tasks.get(taskId)
  }

  /** List tasks with optional filtering. */
  list(filter?: TaskFilter): Task[] {
    let results = Array.from(this.tasks.values()).filter(t => t.status !== 'deleted')

    if (filter?.status) {
      const statuses = Array.isArray(filter.status) ? filter.status : [filter.status]
      results = results.filter(t => statuses.includes(t.status))
    }
    if (filter?.owner !== undefined) {
      results = results.filter(t => t.owner === filter.owner)
    }
    if (filter?.blocked === true) {
      results = results.filter(t => this._hasUnresolvedBlockers(t))
    } else if (filter?.blocked === false) {
      results = results.filter(t => !this._hasUnresolvedBlockers(t))
    }

    return results
  }

  /** Get tasks that are pending and have no unresolved blockers — ready to execute. */
  getReady(): Task[] {
    return this.list({ status: 'pending', blocked: false })
  }

  /** Assign a task to an agent. */
  assignTo(taskId: string, ownerId: string): Task {
    return this.update(taskId, { owner: ownerId })
  }

  /** Mark a task as completed. Auto-unblocks dependents. */
  complete(taskId: string, result?: string): Task {
    return this.update(taskId, { status: 'completed', result })
  }

  /** Mark a task as failed. */
  fail(taskId: string, reason?: string): Task {
    return this.update(taskId, { status: 'failed', failReason: reason })
  }

  // ── Event Hooks ────────────────────────────────────────────────────

  onTaskCreated(handler: TaskEventHandler): void {
    this.hooks.get('created')!.push(handler)
  }

  onTaskCompleted(handler: TaskEventHandler): void {
    this.hooks.get('completed')!.push(handler)
  }

  onTaskFailed(handler: TaskEventHandler): void {
    this.hooks.get('failed')!.push(handler)
  }

  // ── Internal ───────────────────────────────────────────────────────

  private _mustGet(taskId: string): Task {
    const task = this.tasks.get(taskId)
    if (!task) throw new Error(`Task not found: ${taskId}`)
    return task
  }

  /** Add a "blocker blocks target" edge in both directions. */
  private _addBlockEdge(blockerId: string, targetId: string): void {
    const blocker = this.tasks.get(blockerId)
    const target = this.tasks.get(targetId)
    if (blocker && !blocker.blocks.includes(targetId)) {
      blocker.blocks.push(targetId)
    }
    if (target && !target.blockedBy.includes(blockerId)) {
      target.blockedBy.push(blockerId)
    }
  }

  /** When a task completes, remove it from all dependents' blockedBy lists. */
  private _autoUnblock(completedId: string): void {
    const completed = this.tasks.get(completedId)
    if (!completed) return

    for (const dependentId of completed.blocks) {
      const dependent = this.tasks.get(dependentId)
      if (dependent) {
        dependent.blockedBy = dependent.blockedBy.filter(id => id !== completedId)
        dependent.updatedAt = new Date().toISOString()
        this._persist(dependent)
      }
    }
  }

  /** Check if a task has any blockers that are not yet completed. */
  private _hasUnresolvedBlockers(task: Task): boolean {
    if (task.blockedBy.length === 0) return false
    return task.blockedBy.some(id => {
      const blocker = this.tasks.get(id)
      return blocker && blocker.status !== 'completed'
    })
  }

  // ── Persistence ────────────────────────────────────────────────────

  private _ensureDir(): void {
    if (!existsSync(this.persistDir)) {
      mkdirSync(this.persistDir, { recursive: true })
    }
  }

  private _taskPath(id: string): string {
    return join(this.persistDir, `${id}.json`)
  }

  private _persist(task: Task): void {
    writeFileSync(this._taskPath(task.id), JSON.stringify(task, null, 2), 'utf-8')
  }

  private _loadAll(): void {
    if (!existsSync(this.persistDir)) return

    for (const file of readdirSync(this.persistDir)) {
      if (!file.endsWith('.json')) continue
      try {
        const raw = readFileSync(join(this.persistDir, file), 'utf-8')
        const task: Task = JSON.parse(raw)
        this.tasks.set(task.id, task)
      } catch {
        // Skip corrupt files
      }
    }
  }

  private async _emit(event: TaskEventType, task: Task): Promise<void> {
    const handlers = this.hooks.get(event) ?? []
    for (const handler of handlers) {
      try {
        await handler(task)
      } catch {
        // Swallow hook errors to avoid breaking the task lifecycle
      }
    }
  }
}

export default TaskManager
