# Aussie Generate — Code Generation from Natural Language

Generate code from a natural language description, write it to files, and validate with tests.

## When the user invokes /aussie-generate

Parse the command for a description and optional target language/path. Format:
```
/aussie-generate "description of what to build"
/aussie-generate "REST API endpoint for user auth" --lang typescript --path src/auth/
/aussie-generate "data pipeline for CSV processing" --lang python
```

### Step 1: Recall Context

Query JMEM for relevant patterns and past generations:
```
mcp__jmem__jmem_recall(query="{description keywords}", limit=5, min_q=0.5)
```

Also read the project structure to understand conventions:
```
Glob for existing files matching the target language
Read nearby files to understand coding style, imports, and patterns
```

### Step 2: Plan the Generation

Before writing code, produce a brief plan:
- **Files to create**: List each file with its purpose
- **Files to modify**: Any existing files that need updates (imports, registrations, etc.)
- **Dependencies**: New packages or imports required
- **Test files**: Corresponding test files to create

Present the plan to the user and wait for confirmation (unless --auto is set).

### Step 3: Generate Code

Write the code using Write and Edit tools:

1. **Create new files** using the Write tool
   - Follow the project's existing style and conventions
   - Include proper imports, types, and error handling
   - Add inline comments for non-obvious logic
   - For Python: follow PEP 695 type params, use match/case where appropriate
   - For TypeScript: include proper type annotations, avoid `any`

2. **Update existing files** using the Edit tool
   - Add imports for new modules
   - Register new components in registries/indexes
   - Update type definitions if needed

### Step 4: Generate Tests

Create test files for the generated code:

1. **Unit tests**: Test individual functions/methods
2. **Integration tests**: Test component interactions (if applicable)
3. **Edge cases**: Null inputs, empty collections, error paths

For Python:
```bash
python3 -m pytest {test_file} -v 2>&1
```

For TypeScript:
```bash
cd pfaa-cli && npx tsx {test_file} 2>&1
# or
npx jest {test_file} --no-coverage 2>&1
```

### Step 5: Validate

Run validation checks on the generated code:

```bash
# TypeScript type-check
cd pfaa-cli && npx tsc --noEmit 2>&1

# Python syntax check
python3 -m py_compile {file} 2>&1
```

If validation fails:
1. Read the error output
2. Fix the issues using Edit
3. Re-run validation
4. Repeat until clean (max 3 iterations)

### Step 6: Present Results

```
GENERATION COMPLETE
====================
Description: "{description}"
Language:    {language}

Files Created:
  {path1} ({lines} lines)
  {path2} ({lines} lines)

Files Modified:
  {path3} (+{added} -{removed} lines)

Tests:
  {test_path} — {N} tests, {M} passed, {K} failed

Validation: PASS|FAIL
```

### Step 7: Store in Memory

```
mcp__jmem__jmem_remember(
  content="Generated: {description}. Files: {file_list}. Tests: {pass/fail}. Language: {lang}",
  level=1,
  tags=["code-generation", "{language}"]
)
```

## Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| description | *required* | Natural language description of what to generate |
| --lang | auto-detect | Target language (python, typescript, etc.) |
| --path | . | Directory to write generated files |
| --auto | false | Skip confirmation, generate immediately |
| --tests | true | Generate test files alongside code |
| --dry-run | false | Show plan only, do not write files |

## Safety

- Never overwrite existing files without showing a diff first
- Always present the plan before writing (unless --auto)
- Run validation after every generation
- If tests fail after 3 fix attempts, present the code as-is with a warning

## CLI Fallback

```bash
cd pfaa-cli && npx tsx src/cli.ts generate "description here"
cd pfaa-cli && npx tsx src/cli.ts self-build --apply
```
