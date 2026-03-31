"""Deep AST-based Python 3.15 opportunity scanner."""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

HEAVY_MODULES = frozenset({
    "numpy", "pandas", "torch", "tensorflow", "requests", "httpx",
    "sqlalchemy", "flask", "fastapi", "django", "pydantic", "scipy",
    "matplotlib", "boto3", "celery", "sklearn",
})


@dataclass(frozen=True, slots=True)
class Suggestion:
    pep: str
    line: int
    current: str
    proposed: str
    confidence: float


def analyze(filepath: str) -> list[Suggestion]:
    # Path traversal protection
    resolved = Path(filepath).resolve()
    project_root = Path(os.environ.get("CLAUDE_PROJECT_DIR", os.environ.get("PWD", "/"))).resolve()
    if not str(resolved).startswith(str(project_root)):
        return []

    try:
        source = Path(filepath).read_text()
        tree = ast.parse(source, filename=filepath)
    except (SyntaxError, FileNotFoundError, UnicodeDecodeError):
        return []

    source_lines = source.splitlines()
    suggestions: list[Suggestion] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in HEAVY_MODULES:
                    # Check source line for 'lazy' keyword
                    source_line = source_lines[node.lineno - 1] if node.lineno <= len(source_lines) else ""
                    if "lazy" in source_line.split("#")[0]:  # skip comments
                        continue  # Already lazy
                    suggestions.append(Suggestion(
                        pep="PEP 810", line=node.lineno,
                        current=f"import {alias.name}",
                        proposed=f"lazy import {alias.name}",
                        confidence=0.95,
                    ))
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.module.split(".")[0] in HEAVY_MODULES:
                # Check source line for 'lazy' keyword
                source_line = source_lines[node.lineno - 1] if node.lineno <= len(source_lines) else ""
                if "lazy" in source_line.split("#")[0]:  # skip comments
                    continue  # Already lazy
                suggestions.append(Suggestion(
                    pep="PEP 810", line=node.lineno,
                    current=f"from {node.module} import ...",
                    proposed=f"lazy import {node.module}",
                    confidence=0.85,
                ))

    # PEP 814: Module-level UPPER_CASE dicts (scan tree.body only for scope)
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if (isinstance(target, ast.Name) and target.id.isupper()
                    and isinstance(node.value, ast.Dict)):
                suggestions.append(Suggestion(
                    pep="PEP 814", line=node.lineno,
                    current=f"{target.id} = {{...}}",
                    proposed=f"{target.id} = frozendict({{...}})",
                    confidence=0.85,
                ))
        elif isinstance(node, ast.AnnAssign) and node.target:
            if (isinstance(node.target, ast.Name) and node.target.id.isupper()
                    and isinstance(node.value, ast.Dict)):
                suggestions.append(Suggestion(
                    pep="PEP 814", line=node.lineno,
                    current=f"{node.target.id}: ... = {{...}}",
                    proposed=f"{node.target.id}: frozendict = frozendict({{...}})",
                    confidence=0.80,
                ))

    return suggestions
