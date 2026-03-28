"""JMEM — Persistent semantic memory for AI agents.

Ported from https://github.com/Aussie-Agents/jmem-mcp-server
into the PFAA engine for integrated agent team operation.

Features:
    - 7 MCP tools: recall, remember, consolidate, reflect, reward, evolve, status
    - 5 cognitive layers: episode → concept → principle → skill
    - TF-IDF + BM25 + Q-learning hybrid search
    - Pure Python, zero ML dependencies
    - SQLite FTS5 persistence
"""

__version__ = "1.0.0"

from jmem.engine import JMemEngine, MemoryLevel, MemoryNote  # noqa: F401
