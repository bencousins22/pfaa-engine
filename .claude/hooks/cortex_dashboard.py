#!/usr/bin/env python3
"""Cortex Health Dashboard — pearl glossy visualization."""
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("PWD", str(Path(__file__).resolve().parent.parent.parent))))
STATE_PATH = PROJECT_ROOT / ".claude" / "hooks" / "cortex_state.json"

# Adaptive pearl ANSI palette — detects light/dark terminal
X = "\033[0m"
B = "\033[1m"
D = "\033[2m"

def rgb(r, g, b, s): return f"\033[38;2;{r};{g};{b}m{s}{X}"

def _is_light_bg() -> bool:
    cfg = os.environ.get("COLORFGBG", "")
    if cfg:
        parts = cfg.split(";")
        try:
            bg = int(parts[-1])
            if bg >= 8:
                return True
        except ValueError:
            pass
    vsc = os.environ.get("VSCODE_THEME_KIND", "")
    if vsc in ("vscode-light", "vscode-high-contrast-light"):
        return True
    if "light" in os.environ.get("ITERM_PROFILE", "").lower():
        return True
    return False

_LIGHT = _is_light_bg()

if _LIGHT:
    PEARL   = lambda s: rgb(60, 50, 70, s)
    SILVER  = lambda s: rgb(140, 130, 150, s)
    SHIMMER = lambda s: rgb(160, 120, 40, s)
    MINT    = lambda s: rgb(30, 130, 90, s)
    SKY     = lambda s: rgb(40, 90, 180, s)
    ROSE    = lambda s: rgb(180, 60, 70, s)
    LAV     = lambda s: rgb(100, 70, 160, s)
    WARM    = lambda s: rgb(180, 110, 30, s)
    MUTED   = lambda s: rgb(120, 110, 130, s)
else:
    PEARL   = lambda s: rgb(248, 248, 255, s)
    SILVER  = lambda s: rgb(212, 212, 216, s)
    SHIMMER = lambda s: rgb(232, 213, 183, s)
    MINT    = lambda s: rgb(168, 230, 207, s)
    SKY     = lambda s: rgb(181, 212, 255, s)
    ROSE    = lambda s: rgb(255, 228, 225, s)
    LAV     = lambda s: rgb(230, 230, 250, s)
    WARM    = lambda s: rgb(255, 228, 181, s)
    MUTED   = lambda s: rgb(142, 142, 147, s)


def main():
    try:
        state = json.loads(STATE_PATH.read_text())
    except Exception:
        print(ROSE("No cortex state found."))
        return

    print(f"\n  {PEARL(B + 'CORTEX HEALTH DASHBOARD')}")
    print(f"  {SILVER('━' * 50)}\n")

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

    print(f"  {PEARL(B + 'Decisions:')}  {MINT(str(decisions))}")
    print(f"  {PEARL(B + 'Blocks:')}     {correct} correct / {overridden} overridden ({MINT(accuracy)} accuracy)")
    print(f"  {PEARL(B + 'Pressure:')}   {WARM(f'{pressure:.1f}')} / 10.0")
    print(f"  {PEARL(B + 'Phase:')}      {SKY(phase)}")
    print(f"  {PEARL(B + 'Baseline:')}   {SILVER(f'{baseline:.2f}')}")
    print(f"  {PEARL(B + 'Dream:')}      {LAV('PENDING') if dream_pending else MUTED('idle')}")

    # Circuit breaker
    disabled = state.get("disabled_handlers", [])
    if disabled:
        print(f"\n  {ROSE(B + 'Circuit Breakers Active:')}")
        for h in disabled:
            print(f"    {ROSE('✗ ' + h)}")
    else:
        print(f"\n  {MINT('✓ All handlers enabled')}")

    # Error counts
    errors = state.get("error_counts", {})
    active_errors = {k: v for k, v in errors.items() if v > 0}
    if active_errors:
        print(f"\n  {WARM('Error Counts:')}")
        for handler, count in sorted(active_errors.items(), key=lambda x: -x[1]):
            color = ROSE if count >= 3 else WARM
            print(f"    {color(f'{handler}: {count}')}")

    # Performance telemetry
    timings = state.get("event_timings", {})
    if timings:
        print(f"\n  {PEARL(B + 'Performance (avg ms):')}")
        for event, times in sorted(timings.items()):
            if times:
                avg = sum(times) / len(times)
                color = MINT if avg < 100 else WARM if avg < 300 else ROSE
                bar_len = min(int(avg / 10), 40)
                bar = "█" * bar_len
                print(f"    {SILVER(f'{event:25s}')} {color(f'{avg:6.0f}ms')} {MUTED(bar)}")

    # Project profile
    profile = state.get("project_profile", {})
    if profile:
        print(f"\n  {PEARL(B + 'Project Profile:')}")
        print(f"    {SILVER(str(profile.get('py_count', 0)))} Python / {SILVER(str(profile.get('ts_count', 0)))} TypeScript / {SILVER(str(profile.get('test_count', 0)))} tests")
        print(f"    Language: {SKY(profile.get('primary_language', '?'))} | Py3.15: {LAV(str(profile.get('py315_enforcement', '?')))} | Security: {ROSE(str(profile.get('security_emphasis', '?')))}")

    # JMEM status
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
        print(f"\n  {PEARL(B + 'JMEM Memory:')}")
        by_level = status.get("by_level", {})
        total = status.get("total_memories", 0)
        avg_q = status.get("average_q", 0)
        print(f"    Total: {MINT(str(total))} memories (avg Q={SHIMMER(f'{avg_q:.3f}')})")
        level_colors = {
            "EPISODE": SILVER, "CONCEPT": SKY, "PRINCIPLE": LAV,
            "SKILL": SHIMMER, "META": ROSE, "EMERGENT": PEARL,
        }
        for level in ["EPISODE", "CONCEPT", "PRINCIPLE", "SKILL", "META", "EMERGENT"]:
            count = by_level.get(level, 0)
            if count > 0:
                color = level_colors.get(level, SILVER)
                print(f"    {MUTED(f'{level:12s}')} {color(str(count))}")
        health = status.get("health", "unknown")
        color = MINT if health == "good" else ROSE
        print(f"    Health: {color(health)}")
    except Exception:
        print(f"\n  {WARM('JMEM: unavailable')}")

    print()


if __name__ == "__main__":
    main()
