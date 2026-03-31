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


def _is_isinstance_chain(node: ast.If) -> int:
    """Count consecutive isinstance elif branches."""
    count = 0
    current = node
    while current:
        test = current.test
        if isinstance(test, ast.Call) and isinstance(test.func, ast.Name) and test.func.id == "isinstance":
            count += 1
        else:
            break
        if current.orelse and len(current.orelse) == 1 and isinstance(current.orelse[0], ast.If):
            current = current.orelse[0]
        else:
            break
    return count


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
        match node:
            case ast.Import(names=names):
                for alias in names:
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
            case ast.ImportFrom(module=module) if module:
                if module.split(".")[0] in HEAVY_MODULES:
                    # Check source line for 'lazy' keyword
                    source_line = source_lines[node.lineno - 1] if node.lineno <= len(source_lines) else ""
                    if "lazy" in source_line.split("#")[0]:  # skip comments
                        continue  # Already lazy
                    suggestions.append(Suggestion(
                        pep="PEP 810", line=node.lineno,
                        current=f"from {module} import ...",
                        proposed=f"lazy import {module}",
                        confidence=0.85,
                    ))
            case ast.FunctionDef(name=fn_name) if not getattr(node, 'type_params', None):
                # PEP 695: Detect functions using TypeVar without new type parameter syntax
                for child in ast.walk(node):
                    match child:
                        case ast.Subscript(value=ast.Name(id="TypeVar")):
                            suggestions.append(Suggestion(
                                pep="PEP 695", line=node.lineno,
                                current=f"def {fn_name}(...) with TypeVar",
                                proposed=f"def {fn_name}[T](...)",
                                confidence=0.75,
                            ))
                            break
            case ast.If() if _is_isinstance_chain(node) >= 3:
                # PEP 634: isinstance if/elif chains that could be match/case
                suggestions.append(Suggestion(
                    pep="PEP 634", line=node.lineno,
                    current=f"if/elif isinstance chain ({_is_isinstance_chain(node)} branches)",
                    proposed="match/case with structural patterns",
                    confidence=0.70,
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
