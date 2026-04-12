"""
Aussie Agents Skill Evolver — Python 3.15
Clusters high-confidence instincts into auto-generated skills.

Features: import, match/case, PEP 695 type aliases, frozendict
"""
from __future__ import annotations

import json
import os
import time
import glob
import yaml

from collections import defaultdict
from typing import TypeAlias

# PEP 695
SkillName: TypeAlias = str
ClusterId: TypeAlias = str


def load_instincts(path: str | None = None) -> list[dict]:
    """Load all instinct YAML files."""
    instinct_dir = path or os.path.expanduser("~/.pfaa/instincts")
    if not os.path.exists(instinct_dir):
        return []

    all_instincts = []
    for f in glob.glob(os.path.join(instinct_dir, "*.yaml")):
        with open(f) as fh:
            data = yaml.safe_load(fh)
            if isinstance(data, list):
                all_instincts.extend(data)
    return all_instincts


def cluster_by_domain(instincts: list[dict]) -> dict[str, list[dict]]:
    """Group instincts by domain."""
    clusters: dict[str, list[dict]] = defaultdict(list)
    for inst in instincts:
        domain = inst.get("domain", "general")
        clusters[domain].append(inst)
    return dict(clusters)


def evolve_skills(
    min_confidence: float = 0.7,
    min_cluster_size: int = 3,
    skills_dir: str | None = None,
) -> dict[str, list[str]]:
    """Evolve high-confidence instinct clusters into skills."""
    instincts = load_instincts()
    if not instincts:
        return {"evolved": 0, "new_skills": []}

    clusters = cluster_by_domain(instincts)
    out_dir = skills_dir or os.path.expanduser(
        os.path.join(os.getcwd(), ".claude", "skills")
    )
    new_skills: list[str] = []

    for domain, cluster in clusters.items():
        # Filter by confidence
        high_conf = [i for i in cluster if i.get("confidence", 0) >= min_confidence]
        if len(high_conf) < min_cluster_size:
            continue

        # Generate skill name
        skill_name = f"auto-{domain.replace(' ', '-').lower()}"
        skill_dir = os.path.join(out_dir, skill_name)
        os.makedirs(skill_dir, exist_ok=True)

        # Generate SKILL.md
        avg_conf = sum(i["confidence"] for i in high_conf) / len(high_conf)
        actions = "\n".join(f"- {i['action']}" for i in high_conf)
        triggers = "\n".join(f"- {i['trigger']}" for i in high_conf)

        content = f"""# Auto-Generated: {domain.title()} Patterns

Auto-evolved from {len(high_conf)} learned instincts (avg confidence: {avg_conf:.2f}).

## When To Apply
{triggers}

## Recommended Actions
{actions}

## Evidence
Generated at {time.strftime('%Y-%m-%d %H:%M')} from JMEM memory analysis.
Confidence threshold: {min_confidence}
"""
        with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
            f.write(content)

        new_skills.append(skill_name)

    return {"evolved": len(new_skills), "new_skills": new_skills}


if __name__ == "__main__":
    result = evolve_skills()
    print(json.dumps(result))
