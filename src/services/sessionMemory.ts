/**
 * SessionMemoryExtractor — extracts durable memories from conversation sessions.
 *
 * Inspired by Claude Code's extractMemories service. Analyzes conversation
 * transcripts to identify key learnings, preferences, and patterns, then
 * persists them as structured memory files under .pfaa/sessions/.
 *
 * Memories are tagged and contextualised for later retrieval by JMEM or
 * other recall systems.
 */

import { readFileSync, writeFileSync, mkdirSync, existsSync, readdirSync } from 'fs'
import { join, basename } from 'path'
import { randomUUID } from 'crypto'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ConversationMessage {
  role: 'user' | 'assistant' | 'system' | 'tool_call' | 'tool_result'
  content: string
  timestamp?: string
  toolName?: string
  tokenCount?: number
}

export interface ExtractedMemory {
  id: string
  content: string
  tags: string[]
  context: string           // Brief description of what prompted this memory
  source: 'session'
  confidence: number        // 0.0-1.0
  extractedAt: string       // ISO 8601
  sessionId?: string
}

export interface ExtractionThresholds {
  minTokens: number         // Minimum token count before extraction triggers
  minToolCalls: number      // Minimum tool call count before extraction triggers
}

export interface SessionMemoryFile {
  sessionId: string
  extractedAt: string
  memories: ExtractedMemory[]
  stats: {
    messageCount: number
    tokenCount: number
    toolCallCount: number
  }
}

// ---------------------------------------------------------------------------
// Pattern matchers for memory extraction
// ---------------------------------------------------------------------------

/**
 * Patterns that indicate a message contains extractable knowledge.
 * Each pattern has a tag category and a regex or keyword trigger.
 */
interface ExtractionPattern {
  tag: string
  test: (content: string) => boolean
  contextPrefix: string
}

const EXTRACTION_PATTERNS: ExtractionPattern[] = [
  {
    tag: 'preference',
    test: (c) => /\b(prefer|always|never|don't|do not|make sure|ensure)\b/i.test(c),
    contextPrefix: 'User preference',
  },
  {
    tag: 'error-fix',
    test: (c) => /\b(fix|bug|error|issue|wrong|broken|crash|fail)\b/i.test(c),
    contextPrefix: 'Error resolution',
  },
  {
    tag: 'architecture',
    test: (c) => /\b(architect|design|pattern|structure|refactor|module|component)\b/i.test(c),
    contextPrefix: 'Architecture decision',
  },
  {
    tag: 'workflow',
    test: (c) => /\b(workflow|process|pipeline|deploy|ci|cd|build|test)\b/i.test(c),
    contextPrefix: 'Workflow pattern',
  },
  {
    tag: 'tool-usage',
    test: (c) => /\b(tool|command|script|cli|api|endpoint)\b/i.test(c),
    contextPrefix: 'Tool usage',
  },
  {
    tag: 'learning',
    test: (c) => /\b(learn|discover|realize|found out|turns out|TIL|insight)\b/i.test(c),
    contextPrefix: 'Learning',
  },
  {
    tag: 'config',
    test: (c) => /\b(config|setting|environment|env|variable|flag|option)\b/i.test(c),
    contextPrefix: 'Configuration',
  },
]

// ---------------------------------------------------------------------------
// Persistence
// ---------------------------------------------------------------------------

const PFAA_DIR = '.pfaa'
const SESSIONS_DIR = 'sessions'

function getSessionsDir(workspace?: string): string {
  return join(workspace ?? process.cwd(), PFAA_DIR, SESSIONS_DIR)
}

function ensureSessionsDir(workspace?: string): void {
  const dir = getSessionsDir(workspace)
  if (!existsSync(dir)) {
    mkdirSync(dir, { recursive: true })
  }
}

// ---------------------------------------------------------------------------
// SessionMemoryExtractor
// ---------------------------------------------------------------------------

const DEFAULT_THRESHOLDS: ExtractionThresholds = {
  minTokens: 5000,
  minToolCalls: 5,
}

export class SessionMemoryExtractor {
  private thresholds: ExtractionThresholds
  private workspace?: string

  constructor(opts?: { thresholds?: Partial<ExtractionThresholds>; workspace?: string }) {
    this.thresholds = { ...DEFAULT_THRESHOLDS, ...opts?.thresholds }
    this.workspace = opts?.workspace
  }

  // --- Public API ---

  /**
   * Check whether the conversation has enough substance to warrant extraction.
   */
  shouldExtract(tokenCount: number, toolCallCount: number): boolean {
    return (
      tokenCount >= this.thresholds.minTokens &&
      toolCallCount >= this.thresholds.minToolCalls
    )
  }

  /**
   * Extract structured memories from a conversation transcript.
   * Scans assistant messages for patterns that indicate durable knowledge.
   */
  extract(messages: ConversationMessage[]): ExtractedMemory[] {
    const memories: ExtractedMemory[] = []
    const seen = new Set<string>()

    // Focus on assistant messages — those contain the synthesised knowledge
    const assistantMessages = messages.filter(m => m.role === 'assistant')

    for (const msg of assistantMessages) {
      const sentences = this.splitIntoSentences(msg.content)

      for (const sentence of sentences) {
        const trimmed = sentence.trim()
        if (trimmed.length < 20 || trimmed.length > 500) continue

        // Deduplicate by normalised content
        const normalised = trimmed.toLowerCase().replace(/\s+/g, ' ')
        if (seen.has(normalised)) continue

        const matchedPatterns = EXTRACTION_PATTERNS.filter(p => p.test(trimmed))
        if (matchedPatterns.length === 0) continue

        seen.add(normalised)

        const tags = matchedPatterns.map(p => p.tag)
        const context = matchedPatterns[0].contextPrefix

        memories.push({
          id: randomUUID().slice(0, 8),
          content: trimmed,
          tags,
          context,
          source: 'session',
          confidence: this.computeConfidence(trimmed, matchedPatterns.length, messages.length),
          extractedAt: new Date().toISOString(),
        })
      }
    }

    // Also extract from user messages that express explicit preferences
    const userMessages = messages.filter(m => m.role === 'user')
    for (const msg of userMessages) {
      const sentences = this.splitIntoSentences(msg.content)

      for (const sentence of sentences) {
        const trimmed = sentence.trim()
        if (trimmed.length < 15 || trimmed.length > 300) continue

        const normalised = trimmed.toLowerCase().replace(/\s+/g, ' ')
        if (seen.has(normalised)) continue

        // Only extract strong preference signals from user messages
        if (/\b(always|never|don't|do not|prefer|make sure)\b/i.test(trimmed)) {
          seen.add(normalised)
          memories.push({
            id: randomUUID().slice(0, 8),
            content: trimmed,
            tags: ['preference', 'user-stated'],
            context: 'User-stated preference',
            source: 'session',
            confidence: 0.9, // Direct user statements get high confidence
            extractedAt: new Date().toISOString(),
          })
        }
      }
    }

    return memories
  }

  /**
   * Save extracted memories to .pfaa/sessions/<sessionId>.json.
   * Returns the file path written.
   */
  save(
    memories: ExtractedMemory[],
    messages: ConversationMessage[],
    sessionId?: string,
  ): string {
    ensureSessionsDir(this.workspace)

    const id = sessionId ?? `session-${Date.now()}`
    const tokenCount = this.estimateTokens(messages)
    const toolCallCount = messages.filter(
      m => m.role === 'tool_call' || m.role === 'tool_result',
    ).length

    // Attach sessionId to each memory
    const tagged = memories.map(m => ({ ...m, sessionId: id }))

    const file: SessionMemoryFile = {
      sessionId: id,
      extractedAt: new Date().toISOString(),
      memories: tagged,
      stats: {
        messageCount: messages.length,
        tokenCount,
        toolCallCount,
      },
    }

    const filePath = join(getSessionsDir(this.workspace), `${id}.json`)
    writeFileSync(filePath, JSON.stringify(file, null, 2), 'utf-8')

    return filePath
  }

  /**
   * Load all previously saved session memory files.
   */
  loadAll(): SessionMemoryFile[] {
    const dir = getSessionsDir(this.workspace)
    if (!existsSync(dir)) return []

    const files = readdirSync(dir).filter(f => f.endsWith('.json'))
    const results: SessionMemoryFile[] = []

    for (const file of files) {
      try {
        const raw = readFileSync(join(dir, file), 'utf-8')
        results.push(JSON.parse(raw) as SessionMemoryFile)
      } catch {
        // Skip corrupt files
      }
    }

    return results.sort(
      (a, b) => new Date(b.extractedAt).getTime() - new Date(a.extractedAt).getTime(),
    )
  }

  /**
   * Search across all saved session memories by tag or content substring.
   */
  search(query: string): ExtractedMemory[] {
    const all = this.loadAll()
    const q = query.toLowerCase()

    return all.flatMap(session =>
      session.memories.filter(
        m =>
          m.content.toLowerCase().includes(q) ||
          m.tags.some(t => t.toLowerCase().includes(q)),
      ),
    )
  }

  // --- Internal ---

  private splitIntoSentences(text: string): string[] {
    // Split on sentence-ending punctuation, keeping the delimiter
    return text
      .split(/(?<=[.!?])\s+/)
      .filter(s => s.length > 0)
  }

  private computeConfidence(
    content: string,
    patternMatchCount: number,
    totalMessages: number,
  ): number {
    let score = 0.5

    // More pattern matches = higher confidence
    score += Math.min(patternMatchCount * 0.1, 0.3)

    // Longer, more specific content = higher confidence
    if (content.length > 100) score += 0.1

    // Conversations with more messages produce higher-confidence extractions
    if (totalMessages > 20) score += 0.1

    return Math.min(score, 1.0)
  }

  private estimateTokens(messages: ConversationMessage[]): number {
    // If messages carry tokenCount, sum them; otherwise estimate ~4 chars/token
    let total = 0
    for (const msg of messages) {
      if (msg.tokenCount) {
        total += msg.tokenCount
      } else {
        total += Math.ceil(msg.content.length / 4)
      }
    }
    return total
  }
}
