/**
 * CronScheduler — 5-field cron job scheduler for PFAA agents.
 *
 * Inspired by Claude Code's CronCreateTool pattern. Supports recurring and
 * one-shot jobs, durable persistence to .pfaa/cron.json, and auto-expiry.
 *
 * Cron format: "M H DoM Mon DoW" (standard 5-field, local time)
 *   - M: 0-59, H: 0-23, DoM: 1-31, Mon: 1-12, DoW: 0-6 (0=Sun)
 *   - Supports: wildcard, ranges (1-5), lists (1,3,5), steps (star/5)
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs'
import { join } from 'path'
import { randomUUID } from 'crypto'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface CronJob {
  id: string
  cron: string
  prompt: string
  recurring: boolean
  durable: boolean
  agentId?: string
  createdAt: string        // ISO 8601
  lastRun?: string         // ISO 8601
  nextRun?: string         // ISO 8601
  expiresAt?: string       // ISO 8601 — auto-expire date
}

export interface ScheduleOptions {
  recurring?: boolean      // default true
  durable?: boolean        // default false
  agentId?: string
  maxAgeDays?: number      // default 14
}

type JobHandler = (job: CronJob) => void | Promise<void>

// ---------------------------------------------------------------------------
// Cron Parsing
// ---------------------------------------------------------------------------

interface CronFields {
  minute: number[]
  hour: number[]
  dom: number[]
  month: number[]
  dow: number[]
}

function parseField(field: string, min: number, max: number): number[] | null {
  const values = new Set<number>()

  for (const part of field.split(',')) {
    const stepMatch = part.match(/^(.+)\/(\d+)$/)
    let range: string
    let step = 1

    if (stepMatch) {
      range = stepMatch[1]
      step = parseInt(stepMatch[2], 10)
      if (step < 1) return null
    } else {
      range = part
    }

    let start: number
    let end: number

    if (range === '*') {
      start = min
      end = max
    } else if (range.includes('-')) {
      const [lo, hi] = range.split('-').map(Number)
      if (isNaN(lo) || isNaN(hi) || lo < min || hi > max || lo > hi) return null
      start = lo
      end = hi
    } else {
      const val = parseInt(range, 10)
      if (isNaN(val) || val < min || val > max) return null
      if (stepMatch) {
        start = val
        end = max
      } else {
        values.add(val)
        continue
      }
    }

    for (let i = start; i <= end; i += step) {
      values.add(i)
    }
  }

  return values.size > 0 ? Array.from(values).sort((a, b) => a - b) : null
}

export function parseCronExpression(expr: string): CronFields | null {
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return null

  const minute = parseField(parts[0], 0, 59)
  const hour = parseField(parts[1], 0, 23)
  const dom = parseField(parts[2], 1, 31)
  const month = parseField(parts[3], 1, 12)
  const dow = parseField(parts[4], 0, 6)

  if (!minute || !hour || !dom || !month || !dow) return null

  return { minute, hour, dom, month, dow }
}

/**
 * Returns the next Date when the cron fires, starting from `after`.
 * Searches up to 366 days ahead; returns null if no match is found.
 */
export function nextCronRun(cron: string, after: Date = new Date()): Date | null {
  const fields = parseCronExpression(cron)
  if (!fields) return null

  const candidate = new Date(after.getTime())
  // Advance by 1 minute to avoid matching the current minute
  candidate.setSeconds(0, 0)
  candidate.setMinutes(candidate.getMinutes() + 1)

  const limit = after.getTime() + 366 * 24 * 60 * 60 * 1000

  while (candidate.getTime() < limit) {
    if (
      fields.month.includes(candidate.getMonth() + 1) &&
      fields.dom.includes(candidate.getDate()) &&
      fields.dow.includes(candidate.getDay()) &&
      fields.hour.includes(candidate.getHours()) &&
      fields.minute.includes(candidate.getMinutes())
    ) {
      return candidate
    }
    candidate.setMinutes(candidate.getMinutes() + 1)
  }

  return null
}

/**
 * Human-readable description of a cron expression.
 */
export function cronToHuman(cron: string): string {
  const fields = parseCronExpression(cron)
  if (!fields) return cron

  const parts = cron.trim().split(/\s+/)

  if (parts[0] === '*' && parts[1] === '*' && parts[2] === '*' && parts[3] === '*' && parts[4] === '*') {
    return 'every minute'
  }
  if (parts[0].startsWith('*/') && parts[1] === '*') {
    return `every ${parts[0].slice(2)} minutes`
  }
  if (parts[1].startsWith('*/') && parts[0] === '0') {
    return `every ${parts[1].slice(2)} hours`
  }

  const minute = parts[0].padStart(2, '0')
  const hour = parts[1]

  if (hour !== '*' && !hour.includes('/') && !hour.includes(',')) {
    const h = parseInt(hour, 10)
    const ampm = h >= 12 ? 'PM' : 'AM'
    const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h
    return `at ${h12}:${minute} ${ampm}`
  }

  return cron
}

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

const PFAA_DIR = '.pfaa'
const CRON_FILE = 'cron.json'

function getCronFilePath(workspace?: string): string {
  const base = workspace ?? process.cwd()
  return join(base, PFAA_DIR, CRON_FILE)
}

function ensurePfaaDir(workspace?: string): void {
  const dir = join(workspace ?? process.cwd(), PFAA_DIR)
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true })
  }
}

function loadJobs(workspace?: string): CronJob[] {
  const filePath = getCronFilePath(workspace)
  if (!existsSync(filePath)) return []
  try {
    const raw = readFileSync(filePath, 'utf-8')
    return JSON.parse(raw) as CronJob[]
  } catch {
    return []
  }
}

function saveJobs(jobs: CronJob[], workspace?: string): void {
  ensurePfaaDir(workspace)
  const filePath = getCronFilePath(workspace)
  writeFileSync(filePath, JSON.stringify(jobs, null, 2), 'utf-8')
}

// ---------------------------------------------------------------------------
// CronScheduler
// ---------------------------------------------------------------------------

const DEFAULT_MAX_AGE_DAYS = 14
const MAX_JOBS = 50
const CHECK_INTERVAL_MS = 60_000

export class CronScheduler {
  private jobs: CronJob[] = []
  private timer: ReturnType<typeof setInterval> | null = null
  private handler: JobHandler
  private workspace?: string

  constructor(handler: JobHandler, workspace?: string) {
    this.handler = handler
    this.workspace = workspace
    this.jobs = loadJobs(workspace)
  }

  // --- Public API ---

  /**
   * Schedule a new cron job. Returns the job ID.
   */
  schedule(cron: string, prompt: string, opts: ScheduleOptions = {}): string {
    const fields = parseCronExpression(cron)
    if (!fields) {
      throw new Error(`Invalid cron expression '${cron}'. Expected 5 fields: M H DoM Mon DoW.`)
    }

    if (this.jobs.length >= MAX_JOBS) {
      throw new Error(`Too many scheduled jobs (max ${MAX_JOBS}). Cancel one first.`)
    }

    const now = new Date()
    const recurring = opts.recurring ?? true
    const durable = opts.durable ?? false
    const maxAgeDays = opts.maxAgeDays ?? DEFAULT_MAX_AGE_DAYS

    const next = nextCronRun(cron, now)

    const job: CronJob = {
      id: randomUUID().slice(0, 8),
      cron,
      prompt,
      recurring,
      durable,
      agentId: opts.agentId,
      createdAt: now.toISOString(),
      nextRun: next?.toISOString(),
      expiresAt: recurring
        ? new Date(now.getTime() + maxAgeDays * 24 * 60 * 60 * 1000).toISOString()
        : undefined,
    }

    this.jobs.push(job)
    if (durable) this.persist()

    return job.id
  }

  /**
   * Cancel a job by ID. Returns true if found and removed.
   */
  cancel(jobId: string): boolean {
    const idx = this.jobs.findIndex(j => j.id === jobId)
    if (idx === -1) return false

    const [removed] = this.jobs.splice(idx, 1)
    if (removed.durable) this.persist()
    return true
  }

  /**
   * List all jobs with computed next run times.
   */
  list(): CronJob[] {
    const now = new Date()
    return this.jobs.map(job => ({
      ...job,
      nextRun: nextCronRun(job.cron, now)?.toISOString(),
    }))
  }

  /**
   * Start the scheduler loop (checks every 60s).
   */
  start(): void {
    if (this.timer) return
    this.timer = setInterval(() => this.tick(), CHECK_INTERVAL_MS)
    // Run an immediate check
    this.tick()
  }

  /**
   * Stop the scheduler loop.
   */
  stop(): void {
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
  }

  /**
   * Execute a job immediately, regardless of its schedule.
   */
  async runNow(jobId: string): Promise<void> {
    const job = this.jobs.find(j => j.id === jobId)
    if (!job) throw new Error(`Job ${jobId} not found`)
    await this.executeJob(job)
  }

  // --- Internal ---

  private async tick(): Promise<void> {
    const now = new Date()

    // Remove expired jobs
    const expiredIds: string[] = []
    this.jobs = this.jobs.filter(job => {
      if (job.expiresAt && new Date(job.expiresAt) <= now) {
        expiredIds.push(job.id)
        return false
      }
      return true
    })

    if (expiredIds.length > 0) {
      this.persist()
    }

    // Check each job
    for (const job of this.jobs) {
      if (this.shouldFire(job, now)) {
        await this.executeJob(job)
      }
    }
  }

  private shouldFire(job: CronJob, now: Date): boolean {
    const fields = parseCronExpression(job.cron)
    if (!fields) return false

    return (
      fields.minute.includes(now.getMinutes()) &&
      fields.hour.includes(now.getHours()) &&
      fields.dom.includes(now.getDate()) &&
      fields.month.includes(now.getMonth() + 1) &&
      fields.dow.includes(now.getDay())
    )
  }

  private async executeJob(job: CronJob): Promise<void> {
    const now = new Date()
    job.lastRun = now.toISOString()
    job.nextRun = nextCronRun(job.cron, now)?.toISOString()

    try {
      await this.handler(job)
    } catch {
      // Handler errors are non-fatal — job stays scheduled
    }

    if (!job.recurring) {
      // One-shot: remove after firing
      this.jobs = this.jobs.filter(j => j.id !== job.id)
    }

    if (job.durable || this.jobs.some(j => j.durable)) {
      this.persist()
    }
  }

  private persist(): void {
    const durableJobs = this.jobs.filter(j => j.durable)
    saveJobs(durableJobs, this.workspace)
  }
}
