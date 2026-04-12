"""
Aussie Agents Instinct Learner — Python 3.15
Extracts recurring patterns from PFAA memory into instincts.

Features: import, match/case, PEP 695 type aliases, frozendict
"""
from __future__ import annotations

import json
import os
import time
import sqlite3
import yaml

from collections import Counter
from dataclasses import dataclass, field, asdict
from typing import TypeAlias

# PEP 695
InstinctId: TypeAlias = str
Confidence: TypeAlias = float
Domain: TypeAlias = str


@dataclass(slots=True)
class Instinct:
    trigger: str
    action: str
    confidence: Confidence
    domain: Domain
    evidence: list[str] = field(default_factory=list)
    source: str = "auto-extracted"
    created: float = field(default_factory=time.time)


def extract_instincts(db_path: str | None = None) -> list[Instinct]:
    """Extract instincts from the PFAA memory database."""
    db = db_path or os.path.expanduser("~/.pfaa/memory.db")
    if not os.path.exists(db):
        return []

    conn = sqlite3.connect(db)
    instincts: list[Instinct] = []

    # Extract tool co-occurrence patterns
    rows = conn.execute(
        "SELECT tool_name, phase_used, elapsed_us, success "
        "FROM episodes ORDER BY timestamp DESC LIMIT 500"
    ).fetchall()

    if not rows:
        conn.close()
        return []

    # Pattern 1: Tool phase preferences
    phase_counts: dict[str, Counter] = {}
    for tool, phase, elapsed, success in rows:
        phase_counts.setdefault(tool, Counter())[phase] += 1

    for tool, counts in phase_counts.items():
        best_phase = counts.most_common(1)[0]
        total = sum(counts.values())
        if total >= 3:
            conf = best_phase[1] / total
            if conf > 0.6:
                instincts.append(Instinct(
                    trigger=f"executing {tool}",
                    action=f"prefer {best_phase[0]} phase",
                    confidence=round(conf, 2),
                    domain="phase-optimization",
                    evidence=[f"{best_phase[1]}/{total} executions in {best_phase[0]}"],
                ))

    # Pattern 2: Tool success rates
    success_rates: dict[str, list[bool]] = {}
    for tool, phase, elapsed, success in rows:
        success_rates.setdefault(tool, []).append(bool(success))

    for tool, results in success_rates.items():
        rate = sum(results) / len(results)
        if len(results) >= 5 and rate < 0.7:
            instincts.append(Instinct(
                trigger=f"using {tool}",
                action=f"caution: {rate:.0%} success rate",
                confidence=round(1 - rate, 2),
                domain="reliability",
                evidence=[f"{sum(results)}/{len(results)} succeeded"],
            ))

    # Pattern 3: Tool speed tiers
    speed_data: dict[str, list[int]] = {}
    for tool, phase, elapsed, success in rows:
        if success:
            speed_data.setdefault(tool, []).append(elapsed)

    for tool, times in speed_data.items():
        avg = sum(times) / len(times)
        match avg:
            case t if t < 1000:
                tier = "fast"
            case t if t < 100000:
                tier = "medium"
            case _:
                tier = "slow"

        if len(times) >= 3:
            instincts.append(Instinct(
                trigger=f"choosing tool for speed",
                action=f"{tool} is {tier} (avg {avg:.0f}μs)",
                confidence=min(0.95, len(times) / 10),
                domain="performance",
                evidence=[f"avg={avg:.0f}μs over {len(times)} runs"],
            ))

    conn.close()
    return instincts


def save_instincts(instincts: list[Instinct], path: str | None = None) -> str:
    """Save instincts to YAML file."""
    out_dir = path or os.path.expanduser("~/.pfaa/instincts")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, f"instincts_{int(time.time())}.yaml")

    data = [asdict(i) for i in instincts]
    with open(out_file, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    return out_file


if __name__ == "__main__":
    instincts = extract_instincts()
    if instincts:
        path = save_instincts(instincts)
        print(json.dumps({"instincts": len(instincts), "path": path}))
    else:
        print(json.dumps({"instincts": 0, "message": "no patterns found yet"}))
