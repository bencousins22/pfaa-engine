# Aussie Pipeline — Sequential Step Execution

Execute a sequence of tools or steps where each step's output feeds into the next step's input. This is a pipeline/chain pattern for composing multi-step workflows.

## When the user invokes /aussie-pipeline

Parse the command for a sequence of steps. Format:
```
/aussie-pipeline <step1> | <step2> | <step3> ...
```

Steps can be tool names with arguments, shell commands, or natural language descriptions:
```
/aussie-pipeline "glob *.py" | "grep TODO" | "count lines"
/aussie-pipeline "read src/core/types.ts" | "extract interfaces" | "generate tests"
/aussie-pipeline "git diff HEAD~3" | "summarize changes" | "write changelog entry"
/aussie-pipeline "jmem_recall database" | "analyze patterns" | "jmem_remember consolidated insight"
```

### Step 1: Parse Pipeline

Split the input on `|` (pipe) characters. For each step, determine:
- **Type**: tool call, bash command, or natural language task
- **Arguments**: Parameters for the step
- **Transform**: How to pass output to next step (full text, extracted fields, etc.)

Build an ordered list of steps with their types.

### Step 2: Execute Sequentially

Run each step in order, passing the previous step's output as input to the next:

```
result_0 = execute(step_0, input=user_input)
result_1 = execute(step_1, input=result_0)
result_2 = execute(step_2, input=result_1)
...
final_result = result_N
```

For each step:
1. Log the step number and description
2. Execute the step using the appropriate tool:
   - **Glob/Grep/Read**: Use the corresponding Claude Code tool
   - **Bash command**: Use the Bash tool
   - **JMEM operation**: Use the corresponding MCP tool (mcp__jmem__jmem_recall, etc.)
   - **Natural language**: Interpret and execute using available tools
3. Capture the output
4. Check for errors -- if a step fails, report the failure and stop (unless --continue-on-error is set)
5. Pass the output to the next step

### Step 3: Track Progress

Display progress as the pipeline executes:

```
Pipeline: 4 steps
[1/4] glob *.py .................. OK (23 files)
[2/4] grep TODO .................. OK (7 matches)
[3/4] count lines ................ OK (7)
[4/4] format report .............. OK
```

### Step 4: Present Results

Show the final output plus a pipeline summary:

```
PIPELINE RESULTS
=================
Steps: N total (M succeeded, K failed)

Step 1: {description}
  Input:  {truncated input}
  Output: {truncated output}
  Time:   {X}ms

Step 2: {description}
  Input:  {from step 1}
  Output: {truncated output}
  Time:   {X}ms

...

FINAL OUTPUT
------------
{final_result}

Timing: Total {X}ms
```

### Step 5: Store in Memory

```
mcp__jmem__jmem_remember(
  content="Pipeline: {N} steps [{step_descriptions}]. Result: {summary}. Total time: {X}ms",
  level=1,
  tags=["pipeline", "sequential-execution"]
)
```

## Error Handling

- **Default**: Stop on first error, report which step failed and why
- **--continue-on-error**: Skip failed steps, pass empty string to next step
- **--retry N**: Retry failed steps up to N times before giving up

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| steps | *required* | Pipe-separated sequence of steps |
| --continue-on-error | false | Continue pipeline even if a step fails |
| --retry | 0 | Number of retries per failed step |
| --verbose | false | Show full input/output for each step |

## CLI Fallback

```bash
cd pfaa-cli && npx tsx src/cli.ts pipeline shell:ls glob:*.py
cd pfaa-cli && npx tsx src/cli.ts pipeline "grep:TODO" "wc:-l"
```
