"""Stubs for optional dependencies (ClaudeBridge, SkillGenerator).

These features require the full Aussie Agents framework. In standalone JMEM mode,
they gracefully degrade — consolidation and reflection still work, but
LLM-powered principle extraction and auto-skill generation are disabled.
"""

from __future__ import annotations


class ClaudeBridge:
    """Stub — LLM-powered features disabled in standalone mode."""
    is_available = False
    def __init__(self, *a, **kw): pass
    async def ask(self, *a, **kw):
        class R:
            success = False
            output = ""
        return R()
    async def __aenter__(self): return self
    async def __aexit__(self, *a): pass


class ClaudeConfig:
    """Stub config."""
    def __init__(self, *a, **kw): pass


class SkillGenerator:
    """Stub — skill generation disabled in standalone mode."""
    def __init__(self, *a, **kw): pass
    async def generate_skill(self, *a, **kw): return None
    def generate_and_install(self, *a, **kw): return None
    def install_skill(self, *a, **kw): return False
