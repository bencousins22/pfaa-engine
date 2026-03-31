"""JMEM engine test suite."""
import asyncio
import os
import tempfile
import shutil
import pytest

# Add python dir to path
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'python'))

from jmem.engine import JMemEngine, MemoryLevel, MemoryNote
from jmem.vector_store import PureVectorStore


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def engine(tmp_dir):
    return JMemEngine(db_path=os.path.join(tmp_dir, 'test.db'))


def run(coro):
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


class TestMemoryNote:
    def test_to_dict_roundtrip(self):
        note = MemoryNote(id='abc', content='hello', keywords=['a', 'b'], level=MemoryLevel.CONCEPT)
        d = note.to_dict()
        restored = MemoryNote.from_dict(d)
        assert restored.content == 'hello'
        assert restored.level == MemoryLevel.CONCEPT
        assert restored.keywords == ['a', 'b']

    def test_composite_text_boosting(self):
        ep = MemoryNote(content='test', keywords=['kw'], level=MemoryLevel.EPISODE)
        sk = MemoryNote(content='test', keywords=['kw'], level=MemoryLevel.SKILL)
        # Skill should have more keyword repetitions
        assert len(sk.composite_text()) > len(ep.composite_text())

    def test_promotion_target(self):
        assert MemoryLevel.EPISODE.promotion_target == MemoryLevel.CONCEPT
        assert MemoryLevel.CONCEPT.promotion_target == MemoryLevel.PRINCIPLE
        assert MemoryLevel.PRINCIPLE.promotion_target == MemoryLevel.SKILL
        assert MemoryLevel.SKILL.promotion_target is None


class TestVectorStore:
    def test_upsert_and_get(self, tmp_dir):
        store = PureVectorStore(db_path=os.path.join(tmp_dir, 'vs.db'))
        async def t():
            await store._ensure_initialized()
            await store.upsert('doc1', 'hello world python', {'level': 'episode'})
            doc = await store.get('doc1')
            assert doc is not None
            assert doc['metadata']['level'] == 'episode'
            await store.close()
        run(t())

    def test_search(self, tmp_dir):
        store = PureVectorStore(db_path=os.path.join(tmp_dir, 'vs.db'))
        async def t():
            await store._ensure_initialized()
            await store.upsert('d1', 'python programming language', {'q_value': 0.8})
            await store.upsert('d2', 'javascript web development', {'q_value': 0.5})
            await store.upsert('d3', 'python asyncio concurrency', {'q_value': 0.6})
            results = await store.search('python programming')
            assert len(results) >= 1
            assert results[0][0] in ('d1', 'd3')  # should match python docs
            await store.close()
        run(t())

    def test_delete(self, tmp_dir):
        store = PureVectorStore(db_path=os.path.join(tmp_dir, 'vs.db'))
        async def t():
            await store._ensure_initialized()
            await store.upsert('d1', 'test doc', {})
            assert await store.get('d1') is not None
            await store.delete('d1')
            assert await store.get('d1') is None
            await store.close()
        run(t())


class TestJMemEngine:
    def test_remember(self, engine):
        async def t():
            async with engine:
                note = await engine.remember('test content', keywords=['test'])
                assert note.id
                assert note.level == MemoryLevel.EPISODE
        run(t())

    def test_recall(self, engine):
        async def t():
            async with engine:
                await engine.remember('Python is great for AI', keywords=['python', 'ai'])
                await engine.remember('JavaScript for web dev', keywords=['js', 'web'])
                results = await engine.recall('python artificial intelligence')
                assert len(results) >= 1
        run(t())

    def test_reward(self, engine):
        async def t():
            async with engine:
                note = await engine.remember('test', keywords=['t'])
                new_q = await engine.reward(note.id, 0.9)
                assert new_q > 0.5
        run(t())

    def test_consolidate(self, engine):
        async def t():
            async with engine:
                for i in range(5):
                    await engine.remember(f'memory {i}', keywords=['shared'])
                report = await engine.consolidate()
                assert isinstance(report, dict)
        run(t())

    def test_reflect(self, engine):
        async def t():
            async with engine:
                await engine.remember('test', keywords=['t'])
                ref = await engine.reflect()
                assert ref['total'] >= 1
                assert ref['health'] in ('excellent', 'healthy', 'needs_attention', 'critical')
        run(t())

    def test_status(self, engine):
        async def t():
            async with engine:
                await engine.remember('x', keywords=['y'])
                s = await engine.status()
                assert 'store' in s
        run(t())
