#!/usr/bin/env python3
"""Detect circular import chains in the Python codebase.

Usage:
    python3 scripts/check_circular_imports.py [root_dir]

Defaults to current directory if no root_dir is given.
Exit code 0 = no cycles, 1 = cycles found, 2 = usage error.
"""
import ast
import sys
from collections import defaultdict
from pathlib import Path


def find_imports(filepath: str) -> list[str]:
    """Extract import targets from a Python file."""
    try:
        tree = ast.parse(Path(filepath).read_text())
    except (SyntaxError, FileNotFoundError):
        return []
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.append(node.module)
    return imports


def check_cycles(root: Path) -> list[list[str]]:
    """Build import graph from Python files under *root* and detect cycles."""
    graph: dict[str, set[str]] = defaultdict(set)
    py_files = list(root.rglob("*.py"))

    # Build module name -> set of imported module names
    for f in py_files:
        module = str(f.relative_to(root)).replace("/", ".").replace(".py", "")
        # Normalise __init__ modules: "pkg.__init__" -> "pkg"
        if module.endswith(".__init__"):
            module = module[: -len(".__init__")]
        for imp in find_imports(str(f)):
            graph[module].add(imp)

    # DFS cycle detection (only follows edges that land on internal modules)
    cycles: list[list[str]] = []
    visited: set[str] = set()
    path: list[str] = []
    on_stack: set[str] = set()

    def dfs(node: str) -> None:
        if node in on_stack:
            cycle_start = path.index(node)
            cycles.append(path[cycle_start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        on_stack.add(node)
        path.append(node)
        for neighbor in graph.get(node, []):
            if neighbor in graph:  # only follow internal modules
                dfs(neighbor)
        path.pop()
        on_stack.discard(node)

    for module in sorted(graph):
        dfs(module)

    return cycles


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    if not root.is_dir():
        print(f"Error: {root} is not a directory", file=sys.stderr)
        return 2

    cycles = check_cycles(root)
    if cycles:
        print(f"Found {len(cycles)} circular import chain(s):")
        for cycle in cycles[:10]:  # cap display at 10
            print(f"  {' -> '.join(cycle)}")
        return 1
    else:
        print("No circular imports detected.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
