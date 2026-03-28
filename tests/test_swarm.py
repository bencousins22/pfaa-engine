"""Swarm agent test suite."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from python.swarm.agent_base import PFAAAgent, AgentContext, Response


class TestAgentContext:
    def test_creation(self):
        ctx = AgentContext(
            agent_id='test-001', tier='intelligence', role='tester',
            model='test', provider='claude', workspace='.', tools=['python'],
        )
        assert ctx.agent_id == 'test-001'
        assert ctx.tier == 'intelligence'

    def test_defaults(self):
        ctx = AgentContext(
            agent_id='x', tier='t', role='r', model='m',
            provider='p', workspace='.', tools=[],
        )
        assert ctx.memory_area == 'main'
        assert ctx.max_iterations == 20
        assert ctx.timeout_seconds == 90.0


class TestPFAAAgent:
    def test_system_prompt(self):
        ctx = AgentContext(
            agent_id='a', tier='scoring', role='scorer',
            model='m', provider='claude', workspace='/tmp', tools=['python'],
        )
        agent = PFAAAgent(ctx)
        prompt = agent.build_system_prompt()
        assert 'scoring' in prompt
        assert 'scorer' in prompt
        assert 'Python' in prompt

    def test_tool_defs(self):
        ctx = AgentContext(
            agent_id='a', tier='t', role='r', model='m',
            provider='claude', workspace='.', tools=['python', 'file', 'fetch', 'shell', 'memory_recall'],
        )
        agent = PFAAAgent(ctx)
        defs = agent._tool_defs()
        names = [d['name'] for d in defs]
        assert 'python' in names
        assert 'read_file' in names
        assert 'web_fetch' in names
        assert 'shell' in names
        assert 'memory_recall' in names


class TestResponse:
    def test_defaults(self):
        r = Response(message='hello')
        assert r.message == 'hello'
        assert r.break_loop is False
        assert r.tool_calls == 0
        assert r.error is None

    def test_error(self):
        r = Response(message='', error='oops', break_loop=True)
        assert r.error == 'oops'
        assert r.break_loop is True


class TestTierImports:
    @pytest.mark.parametrize('module,var', [
        ('python.swarm.agents.intelligence', 'INTELLIGENCE_AGENTS'),
        ('python.swarm.agents.acquisition', 'ACQUISITION_AGENTS'),
        ('python.swarm.agents.enrichment', 'ENRICHMENT_AGENTS'),
        ('python.swarm.agents.scoring', 'SCORING_AGENTS'),
        ('python.swarm.agents.outreach', 'OUTREACH_AGENTS'),
        ('python.swarm.agents.conversion', 'CONVERSION_AGENTS'),
        ('python.swarm.agents.nurture', 'NURTURE_AGENTS'),
        ('python.swarm.agents.content', 'CONTENT_AGENTS'),
        ('python.swarm.agents.operations', 'OPERATIONS_AGENTS'),
    ])
    def test_tier_import(self, module, var):
        import importlib
        mod = importlib.import_module(module)
        agents = getattr(mod, var)
        assert len(agents) >= 2
        for a in agents:
            assert 'cls' in a
            assert 'id' in a
            assert 'role' in a
