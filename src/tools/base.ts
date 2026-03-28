/**
 * Base tool interface for PFAA tool system.
 */

export interface ToolDefinition {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

export interface Tool {
  definitions(): ToolDefinition[]
  execute(input: Record<string, any>): Promise<string>
}
