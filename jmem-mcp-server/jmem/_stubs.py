"""Stubs for optional dependencies (ClaudeBridge, SkillGenerator).

These features require the full Aussie Agents framework. In standalone JMEM mode,
they gracefully degrade — consolidation and reflection still work, but
LLM-powered principle extraction and auto-skill generation are disabled.
"""
from __future__ import annotations


class ClaudeBridge:
    """Stub — LLM-powered features disabled in standalone mode."""
    def __init__(self, *args, **kwargs): pass
    async def generate(self, *args, **kwargs): return ""
    async def __aenter__(self): return self
    async def __aexit__(self, *args): pass


class ClaudeConfig:
    """Stub config."""
    def __init__(self, *args, **kwargs): pass


class SkillGenerator:
    """Stub — skill generation disabled in standalone mode."""
    def __init__(self, *args, **kwargs): pass
    async def generate_skill(self, *args, **kwargs): return None
    def install_skill(self, *args, **kwargs): return False
