# Aussie Session — Session State Management

Save, list, and restore session summaries using JMEM memory. Enables continuity across Claude Code sessions by persisting what was accomplished, what was learned, and what remains.

## When the user invokes /aussie-session [action]

Perform the requested session action. If no action is specified, show the current session summary.

### Actions

#### save [optional description]

Save a summary of the current session to JMEM.

1. **Gather session context**:
   - Review the conversation to identify: goals pursued, tasks completed, files modified, decisions made, and open items
   - Check git status for uncommitted changes
   - Note any errors encountered and how they were resolved

2. **Store session summary**:
```
Use mcp__jmem__jmem_remember(
  content="SESSION: <description or auto-generated summary>\nDate: <current datetime>\nGoals: <what was attempted>\nCompleted: <what was finished>\nFiles Modified: <list of changed files>\nDecisions: <key decisions made>\nOpen Items: <unfinished work>\nLessons: <anything learned>",
  level=1,
  keywords=["session", "<primary-topic-keywords>"],
  tags=["session", "session-state"]
)
```

3. **If significant patterns were discovered, also store at L2**:
```
Use mcp__jmem__jmem_remember(
  content="Pattern from session: <extracted insight>",
  level=2,
  keywords=["session-insight", "<topic>"],
  tags=["session", "pattern"]
)
```

4. **Confirm save**:
```
SESSION SAVED
=============
Summary:    [description]
Date:       [datetime]
Goals:      [N] tracked
Completed:  [N] tasks
Open Items: [N] remaining
Memory ID:  [note_id]
```

#### list

List all saved session summaries.

```
Use mcp__jmem__jmem_recall(query="SESSION", limit=20)
```

Filter to session-tagged results and display:

```
SAVED SESSIONS
==============
[1] [date] — [summary] (Q=[X.XX])
[2] [date] — [summary] (Q=[X.XX])
[3] [date] — [summary] (Q=[X.XX])
...
```

Sort by date (most recent first).

#### recall [keywords or date]

Recall a specific session's details.

```
Use mcp__jmem__jmem_recall(query="SESSION <keywords>", limit=5)
```

Display the full session content for the best match:

```
SESSION DETAILS
===============
Date:       [datetime]
Summary:    [description]
Goals:      [listed]
Completed:  [listed]
Files:      [listed]
Decisions:  [listed]
Open Items: [listed]
Lessons:    [listed]
Q-Value:    [X.XX]
Memory ID:  [note_id]
```

Reinforce the recalled session:
```
Use mcp__jmem__jmem_reward(note_id="<session_id>", reward=0.3, context="session recalled for continuity")
```

#### summary

Generate a high-level summary across recent sessions.

1. Recall the last 10 sessions:
```
Use mcp__jmem__jmem_recall(query="SESSION", limit=10)
```

2. Synthesize a cross-session report:
```
RECENT SESSION SUMMARY
======================
Sessions:    [N] in last [timeframe]
Top Goals:   [recurring themes]
Completion:  [overall progress trend]
Open Items:  [accumulated unfinished work]
Key Lessons: [cross-session insights]
```

## Default Behavior

If invoked with no arguments (`/aussie-session`), run **summary** to show a quick overview of recent sessions. If no sessions exist, prompt the user to save the current session.

## Options

- `--compact` — One-line-per-session format for list output
- `--full` — Include complete session content (not just summaries)
- `--since [date]` — Filter sessions after a specific date
