"""
PFAA Self-Builder — The engine that builds itself.

Uses its own tools, memory, and Claude bridge to:
    1. Analyze its own codebase (line_count, file_stats, grep)
    2. Identify improvements (Claude reviews its own code)
    3. Generate new tools/capabilities (Claude generates, sandbox tests)
    4. Learn from each self-improvement cycle (memory persists)
    5. Report what it learned and what it changed

This is genuine recursive self-improvement:
    The agent → analyzes itself → proposes changes → tests changes
    → learns from results → applies learning → repeats

Python 3.15:
    - lazy import: only loads heavy deps when self-build actually runs
    - frozendict: immutable snapshots of self-analysis
    - kqueue: subprocess management for Claude calls + sandbox testing
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any

lazy import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolRegistry
from agent_setup_cli.core.persistence import PersistentMemory
from agent_setup_cli.core.claude_bridge import ClaudeBridge, ClaudeConfig
from agent_setup_cli.core.nucleus import Nucleus
from agent_setup_cli.core.agent import AgentConfig

# Register all tools
import agent_setup_cli.core.tools_extended  # noqa: F401

logger = logging.getLogger("pfaa.self_build")

# Path to our own source code
SELF_ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SELF_ROOT)


@dataclass
class SelfAnalysis:
    """Snapshot of the engine's own state."""
    total_files: int = 0
    total_lines: int = 0
    total_tools: int = 0
    modules: list[dict] = field(default_factory=list)
    memory_status: dict = field(default_factory=dict)
    issues_found: list[str] = field(default_factory=list)
    improvements: list[str] = field(default_factory=list)
    timestamp: float = 0.0


class SelfBuilder:
    """
    The agent that builds itself.

    Workflow:
        1. introspect()  — Analyze own codebase with PFAA tools
        2. diagnose()    — Use Claude to find issues and improvements
        3. propose()     — Generate specific code changes
        4. test()        — Sandbox-test proposed changes
        5. apply()       — Apply validated changes
        6. learn()       — Record what worked in persistent memory
    """

    def __init__(self):
        self._registry = ToolRegistry.get()
        self._memory = PersistentMemory()
        self._bridge = ClaudeBridge(
            config=ClaudeConfig(model="sonnet", timeout_s=120.0),
            memory=self._memory.memory,
        )
        self._nucleus = Nucleus()
        self._analysis: SelfAnalysis | None = None

    # ═══════════════════════════════════════════════════════════════
    # STEP 1: INTROSPECT — Analyze own codebase
    # ═══════════════════════════════════════════════════════════════

    async def introspect(self) -> SelfAnalysis:
        """Analyze the PFAA engine's own source code using its own tools."""
        print("\n🔍 INTROSPECTING — Analyzing own codebase...")
        analysis = SelfAnalysis(timestamp=time.time())

        # Fan-out: run multiple analysis tools in parallel on ourselves
        results = await self._registry.execute_many([
            ("line_count", (SELF_ROOT,), {"extensions": ".py"}),
            ("file_stats", (SELF_ROOT,), {}),
            ("glob_search", ("*.py",), {"root": SELF_ROOT}),
            ("git_status", (PROJECT_ROOT,), {}),
        ])

        # Process line count
        if not isinstance(results[0], Exception):
            lc = results[0].result
            analysis.total_lines = lc.get("total_lines", 0)
            print(f"  Lines of code: {analysis.total_lines}")
            self._memory.record(results[0], "line_count", (SELF_ROOT,))

        # Process file stats
        if not isinstance(results[1], Exception):
            fs = results[1].result
            analysis.total_files = fs.get("total_files", 0)
            print(f"  Total files: {analysis.total_files}")
            self._memory.record(results[1], "file_stats", (SELF_ROOT,))

        # Process glob results
        if not isinstance(results[2], Exception):
            files = results[2].result.get("matches", [])
            for f in sorted(files):
                basename = os.path.basename(f)
                # Read each module to get its docstring
                read_result = await self._registry.execute("read_file", os.path.join(SELF_ROOT, f))
                content = read_result.result.get("content", "")
                first_line = ""
                for line in content.split("\n"):
                    line = line.strip()
                    if line.startswith('"""') or line.startswith("'''"):
                        first_line = line.strip('"').strip("'").strip()
                        break
                    elif line and not line.startswith("#") and not line.startswith("from") and not line.startswith("import") and not line.startswith("lazy"):
                        break

                size = len(content)
                lines = content.count("\n")
                analysis.modules.append({
                    "file": basename,
                    "lines": lines,
                    "size": size,
                    "description": first_line[:80] if first_line else "(no docstring)",
                })
                print(f"    {basename:30s} {lines:5d} lines  {first_line[:50]}")

        # Memory status
        analysis.memory_status = self._memory.status()
        analysis.total_tools = len(self._registry.list_tools())

        self._analysis = analysis
        print(f"\n  Summary: {analysis.total_files} files, {analysis.total_lines} lines, "
              f"{analysis.total_tools} tools, {analysis.memory_status.get('l1_episodes', 0)} memories")

        return analysis

    # ═══════════════════════════════════════════════════════════════
    # STEP 2: DIAGNOSE — Find issues and improvements
    # ═══════════════════════════════════════════════════════════════

    async def diagnose(self) -> list[str]:
        """Use Claude to analyze our own code and find improvements."""
        if not self._analysis:
            await self.introspect()

        print("\n🩺 DIAGNOSING — Asking Claude to review our architecture...")

        if not self._bridge.is_available:
            print("  Claude not available — running static analysis only")
            return await self._static_diagnose()

        # Read our own key files
        key_files = ["phase.py", "agent.py", "nucleus.py", "tools.py", "memory.py"]
        file_contents = {}
        for fname in key_files:
            fpath = os.path.join(SELF_ROOT, fname)
            if os.path.exists(fpath):
                result = await self._registry.execute("read_file", fpath)
                file_contents[fname] = result.result.get("content", "")[:3000]

        # Build the self-review prompt
        module_summary = "\n".join(
            f"  {m['file']:30s} {m['lines']:5d} lines — {m['description']}"
            for m in (self._analysis.modules if self._analysis else [])
        )

        prompt = f"""You are reviewing the Phase-Fluid Agent Architecture (PFAA) — a Python 3.15
agent framework that YOU are part of. This is self-analysis.

Architecture: Agents exist in 3 phases (Vapor=coroutine, Liquid=thread, Solid=subprocess)
and transition between them at runtime based on task demands.

Modules:
{module_summary}

Stats: {self._analysis.total_lines if self._analysis else '?'} lines, {self._analysis.total_tools if self._analysis else '?'} tools

Key source excerpts:
{''.join(f'--- {name} ---\\n{code[:1500]}\\n' for name, code in list(file_contents.items())[:3])}

As a Python 3.15 expert, identify:
1. Missing Python 3.15 features we should leverage (frozendict patterns, lazy import opportunities, PEP 798 unpacking)
2. Architectural improvements (missing tools, better phase transitions, memory gaps)
3. Performance optimizations
4. New capabilities that would make the system more powerful

Return each finding on its own line prefixed with "- ". Be specific and actionable.
Focus on what would make this agent MORE POWERFUL at building itself."""

        result = await self._bridge.ask(prompt, timeout=60.0)

        improvements = []
        if result.success:
            for line in result.output.split("\n"):
                line = line.strip()
                if line.startswith("- "):
                    improvements.append(line[2:])
            print(f"  Claude found {len(improvements)} improvements:")
            for imp in improvements[:10]:
                print(f"    • {imp[:100]}")
        else:
            print(f"  Claude review failed: {result.output[:100]}")
            improvements = await self._static_diagnose()

        if self._analysis:
            self._analysis.improvements = improvements
        return improvements

    async def _static_diagnose(self) -> list[str]:
        """Fallback static analysis when Claude isn't available."""
        improvements = []

        # Check for files >300 lines (split candidates)
        if self._analysis:
            for m in self._analysis.modules:
                if m["lines"] > 300:
                    improvements.append(
                        f"Module {m['file']} has {m['lines']} lines — consider splitting"
                    )
                if m["description"] == "(no docstring)":
                    improvements.append(
                        f"Module {m['file']} missing module docstring"
                    )

        # Check for missing lazy imports
        grep_result = await self._registry.execute(
            "grep", r"^import \w", SELF_ROOT, "*.py"
        )
        eager_imports = grep_result.result.get("total_matches", 0)
        if eager_imports > 0:
            improvements.append(
                f"Found {eager_imports} eager imports — consider converting to 'lazy import'"
            )

        # Check memory utilization
        mem_status = self._memory.status()
        if mem_status.get("l1_episodes", 0) < 50:
            improvements.append(
                "Memory has <50 episodes — need more execution history for L2+ learning"
            )
        if mem_status.get("l3_strategies", 0) == 0:
            improvements.append(
                "No L3 strategies learned yet — run more diverse workloads"
            )

        print(f"  Static analysis found {len(improvements)} improvements:")
        for imp in improvements[:10]:
            print(f"    • {imp[:100]}")

        return improvements

    # ═══════════════════════════════════════════════════════════════
    # STEP 3: PROPOSE — Generate new tool code
    # ═══════════════════════════════════════════════════════════════

    async def propose_tool(self, description: str) -> dict[str, Any]:
        """
        Use Claude to generate a new PFAA tool based on a description.
        The generated tool follows our exact tool registration pattern.
        """
        print(f"\n🔧 PROPOSING TOOL: {description}")

        # Read our tools.py as the template
        template_result = await self._registry.execute(
            "read_file", os.path.join(SELF_ROOT, "tools.py")
        )
        template = template_result.result.get("content", "")[:2000]

        prompt = f"""Generate a new PFAA tool following this EXACT pattern from our codebase:

```python
{template[:1500]}
```

The tool must:
1. Use @registry.register(ToolSpec(...)) decorator
2. Choose correct phase: VAPOR for I/O, LIQUID for CPU, SOLID for isolation
3. Use 'lazy import' for any heavy dependencies
4. Return dict with 'success' key
5. Follow Python 3.15 best practices (type hints, lazy imports, frozendict where useful)

Generate a tool for: {description}

Return ONLY the Python code for the tool function and its registration. No explanation."""

        if not self._bridge.is_available:
            return {"success": False, "reason": "Claude not available"}

        result = await self._bridge.ask(prompt, timeout=60.0)

        if result.success:
            code = result.output
            if "```python" in code:
                code = code.split("```python")[1].split("```")[0].strip()
            elif "```" in code:
                code = code.split("```")[1].split("```")[0].strip()

            return {
                "success": True,
                "code": code,
                "description": description,
                "elapsed_ms": result.elapsed_ms,
            }

        return {"success": False, "error": result.output}

    # ═══════════════════════════════════════════════════════════════
    # STEP 4: TEST — Sandbox-test proposed changes
    # ═══════════════════════════════════════════════════════════════

    async def test_code(self, code: str) -> dict[str, Any]:
        """Sandbox-test generated code by executing it in isolation."""
        print("\n🧪 TESTING generated code in sandbox...")

        # Build a test script that imports our framework and tests the code
        test_script = f"""
import sys
sys.path.insert(0, {repr(os.path.dirname(PROJECT_ROOT))})

# Step 1: Verify the code compiles
try:
    compile({repr(code)}, '<generated>', 'exec')
    print("COMPILE: OK")
except SyntaxError as e:
    print(f"COMPILE: FAIL — {{e}}")
    sys.exit(1)

# Step 2: Try executing WITH our framework imports
try:
    from agent_setup_cli.core.phase import Phase
    from agent_setup_cli.core.tools import ToolSpec, registry
    ns = {{
        "__builtins__": __builtins__,
        "Phase": Phase,
        "ToolSpec": ToolSpec,
        "registry": registry,
    }}
    exec({repr(code)}, ns)
    print("EXEC: OK")
except Exception as e:
    print(f"EXEC: FAIL — {{e}}")
    sys.exit(1)

print("ALL CHECKS PASSED")
"""

        result = await self._registry.execute(
            "sandbox_exec", test_script, 10.0
        )
        sandbox_result = result.result

        success = sandbox_result.get("success", False)
        stdout = sandbox_result.get("stdout", "")
        stderr = sandbox_result.get("stderr", "")

        print(f"  Compile: {'✓' if 'COMPILE: OK' in stdout else '✗'}")
        print(f"  Execute: {'✓' if 'EXEC: OK' in stdout else '✗'}")
        if stderr:
            print(f"  Stderr: {stderr[:200]}")

        self._memory.record(result, "sandbox_exec", ("self_test",))

        return {
            "success": success and "ALL CHECKS PASSED" in stdout,
            "stdout": stdout,
            "stderr": stderr,
        }

    # ═══════════════════════════════════════════════════════════════
    # STEP 5: APPLY — Write validated code to codebase
    # ═══════════════════════════════════════════════════════════════

    async def apply_tool(
        self, code: str, target_file: str = "tools_generated.py"
    ) -> dict[str, Any]:
        """Append validated tool code to the generated tools file."""
        target_path = os.path.join(SELF_ROOT, target_file)

        # Read existing content or create with header
        if os.path.exists(target_path):
            existing_result = await self._registry.execute("read_file", target_path)
            existing = existing_result.result.get("content", "")
        else:
            existing = '''"""
PFAA Generated Tools — Auto-generated by the self-builder.

These tools were created by the PFAA engine analyzing its own needs
and using Claude to generate implementations. Each tool was:
    1. Proposed based on self-analysis
    2. Generated by Claude following PFAA patterns
    3. Sandbox-tested for compilation and basic execution
    4. Appended to this file

Python 3.15: Uses lazy imports throughout.
"""

from __future__ import annotations

lazy import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolSpec, registry

'''

        # Append new tool
        new_content = existing.rstrip() + "\n\n" + code + "\n"

        result = await self._registry.execute(
            "write_file", target_path, new_content
        )
        self._memory.record(result, "write_file", (target_path,))

        print(f"  ✓ Tool written to {target_file}")
        return {"success": True, "path": target_path, "size": len(new_content)}

    # ═══════════════════════════════════════════════════════════════
    # STEP 6: LEARN — Record self-improvement in memory
    # ═══════════════════════════════════════════════════════════════

    async def learn_from_cycle(self, improvements_applied: int) -> None:
        """Record what we learned from this self-improvement cycle."""
        self._memory.force_learn()
        status = self._memory.status()
        print(f"\n📚 LEARNING from self-build cycle:")
        print(f"    Episodes: {status['l1_episodes']}")
        print(f"    Patterns: {status['l2_patterns']}")
        print(f"    Strategies: {status['l3_strategies']}")
        print(f"    Improvements applied: {improvements_applied}")

    # ═══════════════════════════════════════════════════════════════
    # FULL SELF-BUILD CYCLE
    # ═══════════════════════════════════════════════════════════════

    async def build_self(
        self,
        tools_to_generate: list[str] | None = None,
        auto_apply: bool = False,
    ) -> dict[str, Any]:
        """
        Run a full self-improvement cycle:
            introspect → diagnose → propose → test → apply → learn
        """
        print("╔══════════════════════════════════════════════════════╗")
        print("║  PFAA SELF-BUILD CYCLE                              ║")
        print("║  The engine that builds itself.                     ║")
        print("╚══════════════════════════════════════════════════════╝")

        start = time.perf_counter_ns()
        results = {
            "introspection": None,
            "diagnosis": [],
            "proposals": [],
            "tests": [],
            "applied": 0,
        }

        # 1. Introspect
        analysis = await self.introspect()
        results["introspection"] = {
            "files": analysis.total_files,
            "lines": analysis.total_lines,
            "tools": analysis.total_tools,
            "modules": len(analysis.modules),
        }

        # 2. Diagnose
        improvements = await self.diagnose()
        results["diagnosis"] = improvements

        # 3. Propose & Test tools
        tool_descriptions = tools_to_generate or []
        if not tool_descriptions and improvements:
            # Auto-extract tool ideas from improvements
            for imp in improvements:
                lower = imp.lower()
                if any(w in lower for w in ["tool", "add", "create", "implement", "build"]):
                    tool_descriptions.append(imp)

        for desc in tool_descriptions[:3]:  # cap at 3 per cycle
            proposal = await self.propose_tool(desc)
            results["proposals"].append(proposal)

            if proposal.get("success") and proposal.get("code"):
                test_result = await self.test_code(proposal["code"])
                results["tests"].append(test_result)

                if test_result.get("success") and auto_apply:
                    await self.apply_tool(proposal["code"])
                    results["applied"] += 1

        # 6. Learn
        await self.learn_from_cycle(results["applied"])

        elapsed_ms = (time.perf_counter_ns() - start) / 1_000_000

        print(f"\n╔══════════════════════════════════════════════════════╗")
        print(f"║  SELF-BUILD COMPLETE in {elapsed_ms:.0f}ms".ljust(55) + "║")
        print(f"║  Diagnosed: {len(improvements)} improvements".ljust(55) + "║")
        print(f"║  Proposed: {len(results['proposals'])} tools".ljust(55) + "║")
        print(f"║  Tested: {len(results['tests'])} tools".ljust(55) + "║")
        print(f"║  Applied: {results['applied']} tools".ljust(55) + "║")
        print(f"╚══════════════════════════════════════════════════════╝")

        self._memory.close()
        return results

    async def shutdown(self) -> None:
        self._memory.close()
        await self._bridge.shutdown()
        await self._nucleus.shutdown()


# ── CLI Entry Point ─────────────────────────────────────────────────

async def main():
    builder = SelfBuilder()
    try:
        await builder.build_self()
    finally:
        await builder.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
