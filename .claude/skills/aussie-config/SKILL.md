# Aussie Config — Configuration Management

View and manage the Aussie Agents configuration. Reads `.claude/settings.json` to display registered agents, skills, hooks, MCP servers, and permissions. Supports adding and removing permissions.

## When the user invokes /aussie-config [action]

Perform the requested configuration action. If no action is specified, show the full configuration summary.

### Actions

#### show (default)

Read `.claude/settings.json` and display a structured overview.

1. **Read configuration**:
```
Read the file at .claude/settings.json
```

2. **Display summary**:
```
AUSSIE CONFIG
=============

AGENTS ([N] registered):
  [agent-name]     — [description from agent .md file]
  [agent-name]     — [description]
  ...

SKILLS ([N] registered):
  /[skill-name]    — [description from SKILL.md first line]
  /[skill-name]    — [description]
  ...

HOOKS ([N] active):
  [event-type]     — [brief description of what it does]
  [event-type]     — [brief description]
  ...

MCP SERVERS ([N] configured):
  [server-name]    — [command] (args: [args])
  ...

PERMISSIONS ([N] entries):
  Allow: [list of allowed patterns]
  Deny:  [list of denied patterns]
```

#### agents

List all registered agents with their details.

```
Read .claude/settings.json for the agents section.
For each agent, also read .claude/agents/<name>.md if it exists.
```

Display each agent's name, role, phase, and description.

#### skills

List all registered skills with their descriptions.

```
Read .claude/settings.json for the skills section.
For each skill, also read the first line of its SKILL.md.
```

#### hooks

List all hooks with their event types, matchers, and commands.

```
Read .claude/settings.json for the hooks section.
Parse each hook's type, matcher pattern, and command.
```

Flag any issues: missing matchers, unreasonable timeouts, hardcoded paths.

#### permissions

Show the current permissions list.

```
Read .claude/settings.json for the permissions section.
```

Display allowed and denied patterns separately.

#### add-permission [pattern]

Add a new permission entry to settings.json.

1. Read current `.claude/settings.json`
2. Parse the permissions array (typically under `permissions.allow` or similar)
3. Check if the pattern already exists (avoid duplicates)
4. Add the new pattern to the allow list
5. Write the updated settings back

```
PERMISSION ADDED
================
Pattern: [pattern]
Total:   [N] permissions
```

**Important**: Only add to the allow list. Never modify deny rules without explicit user confirmation.

#### remove-permission [pattern]

Remove a permission entry from settings.json.

1. Read current `.claude/settings.json`
2. Find the matching permission pattern
3. Confirm with the user before removing
4. Remove the pattern and write back

```
PERMISSION REMOVED
==================
Pattern: [removed pattern]
Total:   [N] remaining permissions
```

#### mcp

Show MCP server configuration details.

```
Read .claude/settings.json for the mcpServers section.
For each server, show: name, command, args, and environment variables.
```

### Validation

After any modification (add-permission, remove-permission), validate the settings.json:
- Confirm it is valid JSON
- Confirm the structure matches expected schema (has permissions, hooks, agents, etc.)
- Report any parse errors immediately

## Default Behavior

If invoked with no arguments (`/aussie-config`), run the **show** action to display the full configuration summary.

## Options

- `--json` — Output raw JSON instead of formatted display
- `--check` — Validate settings.json without displaying (just report errors)
