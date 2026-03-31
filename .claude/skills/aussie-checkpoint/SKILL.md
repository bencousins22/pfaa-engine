# Aussie Checkpoint — Goal Save & Resume

Save in-progress goals as JMEM checkpoints and resume them later. Enables multi-session goal continuity by persisting goal state, progress, and remaining tasks into semantic memory.

## When the user invokes /aussie-checkpoint [action] [goal]

Perform the requested checkpoint action. If no action is specified, list recent checkpoints.

### Actions

#### save [goal description]

Save the current goal state as a checkpoint episode in JMEM.

1. **Gather current state**:
   - Identify the active goal (from argument or conversation context)
   - Determine completed subtasks and remaining work
   - Note any blockers, open questions, or partial results
   - Capture relevant file paths that were modified or read

2. **Store checkpoint**:
```
Use mcp__jmem__jmem_remember(
  content="CHECKPOINT: <goal description>\nStatus: <IN_PROGRESS|BLOCKED|PAUSED>\nCompleted: <list of done subtasks>\nRemaining: <list of remaining subtasks>\nBlockers: <any blockers or notes>\nFiles: <key file paths>\nTimestamp: <current datetime>",
  level=1,
  keywords=["checkpoint", "<goal-keywords>"],
  tags=["checkpoint", "goal-state"]
)
```

3. **Confirm save**:
```
CHECKPOINT SAVED
================
Goal:      [goal description]
Status:    IN_PROGRESS | BLOCKED | PAUSED
Completed: [N] subtasks
Remaining: [N] subtasks
Memory ID: [note_id from jmem_remember]
Resume:    /aussie-checkpoint resume "<goal keywords>"
```

#### resume [goal keywords]

Resume a previously checkpointed goal.

1. **Search for checkpoint**:
```
Use mcp__jmem__jmem_recall(query="CHECKPOINT <goal keywords>", limit=5, min_q=0.0)
```

Filter results to those tagged with "checkpoint". If multiple matches, show a selection list.

2. **Parse checkpoint state**:
   - Extract completed subtasks, remaining work, blockers, and file paths
   - Verify referenced files still exist and haven't changed significantly

3. **Present resume plan**:
```
CHECKPOINT RESUMED
==================
Goal:       [goal description]
Saved:      [timestamp]
Completed:  [list of done subtasks]
Remaining:  [list of remaining subtasks]
Blockers:   [any blockers]

Ready to continue? Proceeding with next subtask: [next task]
```

4. **Reinforce the checkpoint memory**:
```
Use mcp__jmem__jmem_reward(note_id="<checkpoint_id>", reward=0.5, context="checkpoint resumed")
```

5. **Execute remaining subtasks** following the same pattern as `/aussie-run`.

#### list

List all saved checkpoints.

```
Use mcp__jmem__jmem_recall(query="CHECKPOINT", limit=20)
```

Filter to checkpoint-tagged results and display:

```
SAVED CHECKPOINTS
=================
[1] [goal] — IN_PROGRESS (saved: [date], Q=[X.XX])
[2] [goal] — BLOCKED (saved: [date], Q=[X.XX])
[3] [goal] — PAUSED (saved: [date], Q=[X.XX])
```

#### clear [goal keywords]

Remove a checkpoint by decaying its Q-value to zero.

```
Use mcp__jmem__jmem_reward(note_id="<checkpoint_id>", reward=-1.0, context="checkpoint cleared by user")
```

## Default Behavior

If invoked with no arguments (`/aussie-checkpoint`), run the **list** action.

## Options

- `--verbose` — Include full checkpoint content in list output
- `--all` — Show all checkpoints including low-Q (decayed) ones
