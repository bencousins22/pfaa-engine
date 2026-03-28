/**
 * File tools — read, write, list operations.
 */

import type { Tool, ToolDefinition } from './base.js'
import { readFile, writeFile, appendFile, readdir, stat, mkdir } from 'fs/promises'
import { resolve, dirname } from 'path'

export class FileTool implements Tool {
  constructor(private workspace: string) {}

  definitions(): ToolDefinition[] {
    return [
      {
        name: 'read_file',
        description: 'Read a file from the workspace. Returns the file contents as a string.',
        input_schema: {
          type: 'object',
          properties: {
            path: { type: 'string', description: 'File path relative to workspace' },
            encoding: { type: 'string', enum: ['utf8', 'base64'], default: 'utf8' },
          },
          required: ['path'],
        },
      },
      {
        name: 'write_file',
        description: 'Write content to a file. Creates parent directories if needed.',
        input_schema: {
          type: 'object',
          properties: {
            path: { type: 'string' },
            content: { type: 'string' },
            mode: { type: 'string', enum: ['overwrite', 'append'], default: 'overwrite' },
          },
          required: ['path', 'content'],
        },
      },
      {
        name: 'list_dir',
        description: 'List files and directories at a given path.',
        input_schema: {
          type: 'object',
          properties: { path: { type: 'string', default: '.' } },
        },
      },
    ]
  }

  async execute(input: Record<string, any>): Promise<string> {
    if ('content' in input) return this.writeFile(input)
    const full = resolve(this.workspace, input.path ?? '.')
    const s = await stat(full).catch(() => null)
    if (s?.isDirectory()) return this.listDir(input)
    return this.readFile(input)
  }

  private async readFile(input: any): Promise<string> {
    const full = resolve(this.workspace, input.path)
    return await readFile(full, (input.encoding ?? 'utf8') as BufferEncoding) as string
  }

  private async writeFile(input: any): Promise<string> {
    const full = resolve(this.workspace, input.path)
    await mkdir(dirname(full), { recursive: true })
    if (input.mode === 'append') {
      await appendFile(full, input.content, 'utf8')
    } else {
      await writeFile(full, input.content, 'utf8')
    }
    return `Written to ${input.path}`
  }

  private async listDir(input: any): Promise<string> {
    const full = resolve(this.workspace, input.path ?? '.')
    const entries = await readdir(full, { withFileTypes: true })
    return entries.map(e => `${e.isDirectory() ? 'd' : 'f'} ${e.name}`).join('\n')
  }
}
