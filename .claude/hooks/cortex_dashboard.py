#!/usr/bin/env python3
"""Cortex Health Dashboard — visualize system state."""
import json
import os
import sys
from pathlib import Path
from time import time

PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("PWD", "/Users/borris/Desktop/pfaa-engine")))
STATE_PATH = PROJECT_ROOT / ".claude" / "hooks" / "cortex_state.json"

# ANSI colors
C, G, Y, R, M, D, B, W, X = "\033[36m","\033[32m","\033[33m","\033[31m","\033[35m","\033[2m","\033[1m","\033[37m","\033[0m"

def main():
    # Load state
    try:
        state = json.loads(STATE_PATH.read_text())
    except:
        print(f"{R}No cortex state found.{X}")
        return

    print(f"\n{C}{B}  CORTEX HEALTH DASHBOARD{X}")
    print(f"  {D}{'─' * 50}{X}\n")

    # Core metrics
    decisions = state.get("total_decisions", 0)
    correct = state.get("correct_blocks", 0)
    overridden = state.get("overridden_blocks", 0)
    pressure = state.get("pressure", 0)
    phase = state.get("phase", "idle")
    baseline = state.get("interest_baseline", 0.5)
    dream_pending = state.get("dream_pending", False)

    total_blocks = correct + overridden
    accuracy = f"{correct/total_blocks:.0%}" if total_blocks > 0 else "N/A"

    print(f"  {B}Decisions:{X}  {G}{decisions}{X}")
    print(f"  {B}Blocks:{X}     {correct} correct / {overridden} overridden ({G}{accuracy}{X} accuracy)")
    print(f"  {B}Pressure:{X}   {Y}{pressure:.1f}{X} / 10.0")
    print(f"  {B}Phase:{X}      {C}{phase}{X}")
    print(f"  {B}Baseline:{X}   {baseline:.2f}")
    print(f"  {B}Dream:{X}      {'PENDING' if dream_pending else 'idle'}")

    # Circuit breaker
    disabled = state.get("disabled_handlers", [])
    if disabled:
        print(f"\n  {R}{B}Circuit Breakers Active:{X}")
        for h in disabled:
            print(f"    {R}✗ {h}{X}")
    else:
        print(f"\n  {G}✓ All handlers enabled{X}")

    # Error counts
    errors = state.get("error_counts", {})
    active_errors = {k: v for k, v in errors.items() if v > 0}
    if active_errors:
        print(f"\n  {Y}Error Counts:{X}")
        for handler, count in sorted(active_errors.items(), key=lambda x: -x[1]):
            color = R if count >= 3 else Y
            print(f"    {color}{handler}: {count}{X}")

    # Performance telemetry
    timings = state.get("event_timings", {})
    if timings:
        print(f"\n  {B}Performance (avg ms):{X}")
        for event, times in sorted(timings.items()):
            if times:
                avg = sum(times) / len(times)
                color = G if avg < 100 else Y if avg < 300 else R
                bar_len = min(int(avg / 10), 40)
                bar = "█" * bar_len
                print(f"    {event:25s} {color}{avg:6.0f}ms {D}{bar}{X}")

    # Project profile
    profile = state.get("project_profile", {})
    if profile:
        print(f"\n  {B}Project Profile:{X}")
        print(f"    {profile.get('py_count', 0)} Python / {profile.get('ts_count', 0)} TypeScript / {profile.get('test_count', 0)} tests")
        print(f"    Language: {profile.get('primary_language', '?')} | Py3.15: {profile.get('py315_enforcement', '?')} | Security: {profile.get('security_emphasis', '?')}")

    # JMEM status (try to load via engine)
    try:
        jmem_path = str(PROJECT_ROOT / "jmem-mcp-server")
        if jmem_path not in sys.path:
            sys.path.append(jmem_path)
        import asyncio
        from jmem.engine import JMemEngine
        async def get_jmem():
            e = JMemEngine(db_path=os.path.expanduser("~/.jmem/claude-code/memory.db"))
            return await e.reflect()
        status = asyncio.run(get_jmem())
        print(f"\n  {B}JMEM Memory:{X}")
        by_level = status.get("by_level", {})
        total = status.get("total_memories", 0)
        avg_q = status.get("average_q", 0)
        print(f"    Total: {G}{total}{X} memories (avg Q={avg_q:.3f})")
        for level in ["EPISODE", "CONCEPT", "PRINCIPLE", "SKILL", "META", "EMERGENT"]:
            count = by_level.get(level, 0)
            if count > 0:
                print(f"    {level:12s} {M}{count}{X}")
        health = status.get("health", "unknown")
        color = G if health == "good" else R
        print(f"    Health: {color}{health}{X}")
    except Exception:
        print(f"\n  {Y}JMEM: unavailable{X}")

    print()


if __name__ == "__main__":
    main()
