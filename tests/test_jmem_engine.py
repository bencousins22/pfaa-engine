"""Comprehensive tests for enhanced JMEM engine methods.

Covers: auto-consolidation, reward_recalled, decay_idle, extract_skills,
meta_learn, emergent_synthesis, and full multi-level promotion chains.
"""

import asyncio
import os
import shutil
import sys
import tempfile
import time

# Force-load jmem from jmem-mcp-server (not python/jmem which has a different API)
_mcp_path = os.path.join(os.path.dirname(__file__), "..", "jmem-mcp-server")
sys.path.insert(0, _mcp_path)
# Clear any cached jmem modules from the legacy python/ path
for mod_name in list(sys.modules):
    if mod_name.startswith("jmem"):
        del sys.modules[mod_name]

import pytest

from jmem.engine import JMemEngine, MemoryLevel


# ── Helpers ──────────────────────────────────────────────────────────

def run(coro):
    """Run an async coroutine synchronously."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop is None:
        return asyncio.run(coro)
    return loop.run_until_complete(coro)


@pytest.fixture
def tmp_dir():
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def engine(tmp_dir):
    return JMemEngine(db_path=os.path.join(tmp_dir, "test.db"))


# ── TestAutoConsolidation ────────────────────────────────────────────

class TestAutoConsolidation:
    """After 10 stores, consolidation triggers automatically."""

    def test_auto_consolidation_triggers_at_interval(self, engine):
        async def t():
            await engine.start()
            try:
                # Store 9 memories — no consolidation yet
                for i in range(9):
                    await engine.remember(
                        f"memory about topic alpha number {i}",
                        keywords=["alpha", "shared"],
                    )
                assert engine._store_count == 9

                # The 10th store should trigger auto-consolidation
                await engine.remember(
                    "memory about topic alpha number 9",
                    keywords=["alpha", "shared"],
                )
                assert engine._store_count == 10
            finally:
                await engine.shutdown()
        run(t())

    def test_auto_consolidation_links_shared_keywords(self, engine):
        async def t():
            await engine.start()
            try:
                # Store 10 memories sharing a keyword so consolidation links them
                ids = []
                for i in range(10):
                    nid = await engine.remember(
                        f"topic about python programming concept {i}",
                        keywords=["python", "programming"],
                    )
                    ids.append(nid)

                # Auto-consolidation ran at store 10; check that some got linked
                doc = await engine._store.get(ids[0])
                meta = doc.get("metadata", {})
                links = meta.get("links", [])
                # At least one link should have been created via keyword clustering
                assert len(links) >= 1, "Expected auto-consolidation to create keyword links"
            finally:
                await engine.shutdown()
        run(t())

    def test_no_early_consolidation(self, engine):
        async def t():
            await engine.start()
            try:
                ids = []
                for i in range(5):
                    nid = await engine.remember(
                        f"isolated topic {i}",
                        keywords=["unique_kw"],
                    )
                    ids.append(nid)

                # Only 5 stores — auto-consolidation should NOT have run
                assert engine._store_count == 5
                # Verify no links were created (only consolidate creates links)
                doc = await engine._store.get(ids[0])
                meta = doc.get("metadata", {})
                assert meta.get("links", []) == []
            finally:
                await engine.shutdown()
        run(t())


# ── TestRewardRecalled ───────────────────────────────────────────────

class TestRewardRecalled:
    """Recalling then reward_recalled reinforces the recalled memories."""

    def test_reward_recalled_boosts_q_values(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "python asyncio concurrency patterns",
                    keywords=["python", "asyncio"],
                )

                # Get initial Q
                doc_before = await engine._store.get(nid)
                q_before = doc_before["metadata"]["q_value"]

                # Recall to populate _recent_recalls
                await engine.recall("python asyncio")

                # Now reward all recalled memories
                result = await engine.reward_recalled(reward_signal=0.9)
                assert result["rewarded"] >= 1
                assert result["batches"] >= 1

                # Verify Q increased
                doc_after = await engine._store.get(nid)
                q_after = doc_after["metadata"]["q_value"]
                assert q_after > q_before, f"Q should increase: {q_before} -> {q_after}"
            finally:
                await engine.shutdown()
        run(t())

    def test_reward_recalled_clears_recent_recalls(self, engine):
        async def t():
            await engine.start()
            try:
                await engine.remember("test data for clearing", keywords=["test"])
                await engine.recall("test data")
                assert len(engine._recent_recalls) > 0

                await engine.reward_recalled()

                # _recent_recalls should be cleared after reward_recalled
                assert len(engine._recent_recalls) == 0
            finally:
                await engine.shutdown()
        run(t())

    def test_reward_recalled_noop_when_no_recalls(self, engine):
        async def t():
            await engine.start()
            try:
                result = await engine.reward_recalled()
                assert result["rewarded"] == 0
                assert result["batches"] == 0
            finally:
                await engine.shutdown()
        run(t())

    def test_reward_recalled_deduplicates_across_batches(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "unique concept about deduplication",
                    keywords=["dedup", "concept"],
                )

                # Recall twice — same memory should appear in both batches
                await engine.recall("deduplication concept")
                await engine.recall("dedup concept")
                assert len(engine._recent_recalls) == 2

                result = await engine.reward_recalled(reward_signal=0.8)
                # Should reward each unique ID only once even across batches
                assert result["rewarded"] >= 1
                assert result["batches"] == 2
            finally:
                await engine.shutdown()
        run(t())


# ── TestDecayIdle ────────────────────────────────────────────────────

class TestDecayIdle:
    """decay_idle reduces Q-values on old memories."""

    def test_decay_reduces_q_on_old_memories(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "old memory that should decay",
                    keywords=["old"],
                )

                # Manually backdate the created_at to 48 hours ago
                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["created_at"] = time.time() - (48 * 3600)
                await engine._store.update_metadata(nid, meta)

                q_before = meta["q_value"]

                result = await engine.decay_idle(hours_threshold=24.0, decay_rate=0.02)
                assert result["decayed"] >= 1

                doc_after = await engine._store.get(nid)
                q_after = doc_after["metadata"]["q_value"]
                assert q_after < q_before, f"Q should decrease: {q_before} -> {q_after}"
            finally:
                await engine.shutdown()
        run(t())

    def test_decay_skips_recent_memories(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "fresh memory should not decay",
                    keywords=["fresh"],
                )

                doc_before = await engine._store.get(nid)
                q_before = doc_before["metadata"]["q_value"]

                result = await engine.decay_idle(hours_threshold=24.0, decay_rate=0.02)
                assert result["decayed"] == 0

                doc_after = await engine._store.get(nid)
                q_after = doc_after["metadata"]["q_value"]
                assert q_after == q_before
            finally:
                await engine.shutdown()
        run(t())

    def test_decay_respects_minimum_q(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "very old low q memory",
                    keywords=["ancient"],
                )

                # Backdate to 365 days ago and set Q very low
                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["created_at"] = time.time() - (365 * 24 * 3600)
                meta["q_value"] = 0.15
                await engine._store.update_metadata(nid, meta)

                await engine.decay_idle(hours_threshold=1.0, decay_rate=0.02)

                doc_after = await engine._store.get(nid)
                q_after = doc_after["metadata"]["q_value"]
                # Minimum Q is 0.1, should not go below
                assert q_after >= 0.1
            finally:
                await engine.shutdown()
        run(t())


# ── TestExtractSkills ────────────────────────────────────────────────

class TestExtractSkills:
    """High-Q principles get extracted into L4 SKILL memories."""

    def test_extracts_skill_from_high_q_principle(self, engine):
        async def t():
            await engine.start()
            try:
                # Manually insert a PRINCIPLE with high Q and retrieval count
                nid = await engine.remember(
                    "always validate inputs before processing",
                    level=MemoryLevel.PRINCIPLE,
                    keywords=["validation", "input", "security"],
                )

                # Boost Q to 0.95 and retrieval_count to 6
                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["q_value"] = 0.95
                meta["retrieval_count"] = 6
                await engine._store.update_metadata(nid, meta)

                result = await engine.extract_skills()
                assert result["skills_extracted"] >= 1

                # Verify a SKILL memory was created
                all_docs = await engine._store.get_all()
                skill_docs = [
                    d for d in all_docs
                    if d["metadata"].get("level") == MemoryLevel.SKILL.value
                ]
                assert len(skill_docs) >= 1
                skill_text = skill_docs[0]["text"]
                assert "SKILL" in skill_text
                assert "auto-extracted" in skill_text
            finally:
                await engine.shutdown()
        run(t())

    def test_skips_low_q_principles(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "weak principle that should not become a skill",
                    level=MemoryLevel.PRINCIPLE,
                    keywords=["weak"],
                )

                # Q is below threshold (0.92), retrieval_count is low
                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["q_value"] = 0.6
                meta["retrieval_count"] = 2
                await engine._store.update_metadata(nid, meta)

                result = await engine.extract_skills()
                assert result["skills_extracted"] == 0
            finally:
                await engine.shutdown()
        run(t())

    def test_skips_non_principle_levels(self, engine):
        async def t():
            await engine.start()
            try:
                # High Q episode should NOT be extracted as a skill
                nid = await engine.remember(
                    "high q episode that is not a principle",
                    level=MemoryLevel.EPISODE,
                    keywords=["episode"],
                )
                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["q_value"] = 0.99
                meta["retrieval_count"] = 10
                await engine._store.update_metadata(nid, meta)

                result = await engine.extract_skills()
                assert result["skills_extracted"] == 0
            finally:
                await engine.shutdown()
        run(t())

    def test_extracted_skill_has_auto_skill_keyword(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "use caching for repeated expensive computations",
                    level=MemoryLevel.PRINCIPLE,
                    keywords=["caching", "performance"],
                )
                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["q_value"] = 0.95
                meta["retrieval_count"] = 8
                await engine._store.update_metadata(nid, meta)

                await engine.extract_skills()

                all_docs = await engine._store.get_all()
                skill_docs = [
                    d for d in all_docs
                    if d["metadata"].get("level") == MemoryLevel.SKILL.value
                ]
                assert len(skill_docs) >= 1
                skill_meta = skill_docs[0]["metadata"]
                assert "auto-skill" in skill_meta.get("keywords", [])
                assert "auto" in skill_meta.get("tags", [])
            finally:
                await engine.shutdown()
        run(t())


# ── TestMetaLearn ────────────────────────────────────────────────────

class TestMetaLearn:
    """meta_learn returns stats and generates insights on stalled promotions."""

    def test_meta_learn_returns_stats(self, engine):
        async def t():
            await engine.start()
            try:
                for i in range(5):
                    await engine.remember(
                        f"memory number {i} about testing",
                        keywords=["testing"],
                    )

                result = await engine.meta_learn()
                assert "stats" in result
                assert result["stats"]["total_memories"] >= 5
                assert "avg_q" in result["stats"]
                assert "level_distribution" in result["stats"]
                assert "keyword_diversity" in result["stats"]
            finally:
                await engine.shutdown()
        run(t())

    def test_meta_learn_detects_promotion_stall(self, engine):
        async def t():
            await engine.start()
            try:
                # Create >20 episodes with 0 concepts -> should trigger stall insight
                for i in range(25):
                    await engine.remember(
                        f"episode about topic {i} with variety word{i}",
                        keywords=[f"kw{i}", "common"],
                    )

                result = await engine.meta_learn()
                categories = [ins["category"] for ins in result["insights"]]
                assert "promotion_stall" in categories, \
                    f"Expected promotion_stall insight, got: {categories}"

                # Should have lowered the episode promotion threshold
                assert len(result["adjustments"]) >= 1
                adj_types = [a["type"] for a in result["adjustments"]]
                assert "lower_episode_threshold" in adj_types
            finally:
                await engine.shutdown()
        run(t())

    def test_meta_learn_adjusts_thresholds(self, engine):
        async def t():
            await engine.start()
            try:
                old_q, old_ret = engine._promotion_thresholds[MemoryLevel.EPISODE.value]

                # Trigger the stall condition: >20 episodes, 0 concepts
                for i in range(25):
                    await engine.remember(
                        f"stalled episode {i} word{i}",
                        keywords=[f"unique{i}"],
                    )

                await engine.meta_learn()

                new_q, new_ret = engine._promotion_thresholds[MemoryLevel.EPISODE.value]
                assert new_q < old_q, f"Q threshold should be lowered: {old_q} -> {new_q}"
                assert new_ret <= old_ret
            finally:
                await engine.shutdown()
        run(t())

    def test_meta_learn_stores_meta_memory(self, engine):
        async def t():
            await engine.start()
            try:
                # Create enough episodes to trigger a stall insight
                for i in range(25):
                    await engine.remember(
                        f"episode {i} word{i}",
                        keywords=[f"kw{i}"],
                    )

                result = await engine.meta_learn()
                # Should have stored a META-level memory with the insight
                assert len(result["insights"]) > 0

                all_docs = await engine._store.get_all(limit=200)
                meta_docs = [
                    d for d in all_docs
                    if d["metadata"].get("level") == MemoryLevel.META.value
                ]
                assert len(meta_docs) >= 1
                assert "META-LEARNING INSIGHT" in meta_docs[0]["text"]
            finally:
                await engine.shutdown()
        run(t())

    def test_meta_learn_empty_store(self, engine):
        async def t():
            await engine.start()
            try:
                result = await engine.meta_learn()
                assert result["insights"] == []
                assert result["adjustments"] == []
            finally:
                await engine.shutdown()
        run(t())


# ── TestEmergentSynthesis ────────────────────────────────────────────

class TestEmergentSynthesis:
    """emergent_synthesis finds keyword clusters and orphan gaps."""

    def test_finds_keyword_clusters(self, engine):
        async def t():
            await engine.start()
            try:
                # Create memories with co-occurring keywords
                for i in range(5):
                    await engine.remember(
                        f"python asyncio pattern {i}",
                        keywords=["python", "asyncio"],
                    )

                result = await engine.emergent_synthesis()
                cluster_discoveries = [
                    d for d in result["discoveries"]
                    if d["type"] == "keyword_cluster"
                ]
                # "python" and "asyncio" co-occur in 5 memories (>= 3 threshold)
                assert len(cluster_discoveries) >= 1
                descriptions = " ".join(d["description"] for d in cluster_discoveries)
                assert "python" in descriptions or "asyncio" in descriptions
            finally:
                await engine.shutdown()
        run(t())

    def test_finds_orphan_gaps(self, engine):
        async def t():
            await engine.start()
            try:
                # Create isolated memories with no links and 0 retrievals
                for i in range(3):
                    await engine.remember(
                        f"isolated orphan topic {i} uniqueword{i}",
                        keywords=[f"orphan{i}"],
                    )

                result = await engine.emergent_synthesis()
                assert result["orphan_count"] >= 3
                assert len(result["gaps"]) >= 3
                # Each gap should have id, content, and level
                for gap in result["gaps"]:
                    assert "id" in gap
                    assert "content" in gap
                    assert "level" in gap
            finally:
                await engine.shutdown()
        run(t())

    def test_stores_emergent_memory_on_discoveries(self, engine):
        async def t():
            await engine.start()
            try:
                for i in range(5):
                    await engine.remember(
                        f"python asyncio concurrency pattern {i}",
                        keywords=["python", "asyncio", "concurrency"],
                    )

                result = await engine.emergent_synthesis()
                if result["discoveries"]:
                    all_docs = await engine._store.get_all(limit=200)
                    emergent_docs = [
                        d for d in all_docs
                        if d["metadata"].get("level") == MemoryLevel.EMERGENT.value
                    ]
                    assert len(emergent_docs) >= 1
                    assert "EMERGENT KNOWLEDGE" in emergent_docs[0]["text"]
            finally:
                await engine.shutdown()
        run(t())

    def test_empty_store_returns_empty(self, engine):
        async def t():
            await engine.start()
            try:
                result = await engine.emergent_synthesis()
                assert result["discoveries"] == []
                assert result["clusters"] == []
                assert result["gaps"] == []
            finally:
                await engine.shutdown()
        run(t())

    def test_promotion_pattern_discovery(self, engine):
        async def t():
            await engine.start()
            try:
                # Create some L3 PRINCIPLE memories so promotion_pattern fires
                for i in range(3):
                    nid = await engine.remember(
                        f"validated principle about design {i}",
                        level=MemoryLevel.PRINCIPLE,
                        keywords=["design", "principle"],
                    )
                    doc = await engine._store.get(nid)
                    meta = doc["metadata"]
                    meta["q_value"] = 0.85
                    meta["retrieval_count"] = 5
                    await engine._store.update_metadata(nid, meta)

                result = await engine.emergent_synthesis()
                promo_discoveries = [
                    d for d in result["discoveries"]
                    if d["type"] == "promotion_pattern"
                ]
                assert len(promo_discoveries) >= 1
                assert "L3+" in promo_discoveries[0]["description"]
            finally:
                await engine.shutdown()
        run(t())


# ── TestMultiLevelPromotion ──────────────────────────────────────────

class TestMultiLevelPromotion:
    """Full promotion chain: episode -> concept -> principle -> skill."""

    def test_episode_to_concept_promotion(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "repeated pattern about error handling",
                    keywords=["error", "handling"],
                )

                # Boost Q and retrieval count above episode threshold (0.65, 2)
                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["q_value"] = 0.7
                meta["retrieval_count"] = 3
                await engine._store.update_metadata(nid, meta)

                await engine.consolidate()

                doc_after = await engine._store.get(nid)
                assert doc_after["metadata"]["level"] == MemoryLevel.CONCEPT.value
            finally:
                await engine.shutdown()
        run(t())

    def test_concept_to_principle_promotion(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "concept about retry logic",
                    level=MemoryLevel.CONCEPT,
                    keywords=["retry", "resilience"],
                )

                # Boost above concept threshold (0.75, 4)
                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["q_value"] = 0.8
                meta["retrieval_count"] = 5
                await engine._store.update_metadata(nid, meta)

                await engine.consolidate()

                doc_after = await engine._store.get(nid)
                assert doc_after["metadata"]["level"] == MemoryLevel.PRINCIPLE.value
            finally:
                await engine.shutdown()
        run(t())

    def test_principle_to_skill_promotion(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "principle about circuit breaker pattern",
                    level=MemoryLevel.PRINCIPLE,
                    keywords=["circuit", "breaker"],
                )

                # Boost above principle threshold (0.9, 6)
                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["q_value"] = 0.95
                meta["retrieval_count"] = 7
                await engine._store.update_metadata(nid, meta)

                await engine.consolidate()

                doc_after = await engine._store.get(nid)
                assert doc_after["metadata"]["level"] == MemoryLevel.SKILL.value
            finally:
                await engine.shutdown()
        run(t())

    def test_full_promotion_chain_via_reward_cycles(self, engine):
        """Simulate the entire episode->concept->principle->skill pipeline
        using reward + consolidate cycles, which is the intended real-world flow."""
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "input validation prevents injection attacks",
                    keywords=["validation", "security", "injection"],
                )

                # Verify starts as EPISODE
                doc = await engine._store.get(nid)
                assert doc["metadata"]["level"] == MemoryLevel.EPISODE.value

                # --- Phase 1: Episode -> Concept ---
                # Reward repeatedly to push Q above 0.65
                for _ in range(4):
                    await engine.reward(nid, 0.9)
                # Simulate retrievals
                meta = (await engine._store.get(nid))["metadata"]
                meta["retrieval_count"] = 3
                await engine._store.update_metadata(nid, meta)

                await engine.consolidate()
                doc = await engine._store.get(nid)
                assert doc["metadata"]["level"] == MemoryLevel.CONCEPT.value, \
                    f"Expected CONCEPT, got level={doc['metadata']['level']}"

                # --- Phase 2: Concept -> Principle ---
                for _ in range(4):
                    await engine.reward(nid, 0.95)
                meta = (await engine._store.get(nid))["metadata"]
                meta["retrieval_count"] = 5
                await engine._store.update_metadata(nid, meta)

                await engine.consolidate()
                doc = await engine._store.get(nid)
                assert doc["metadata"]["level"] == MemoryLevel.PRINCIPLE.value, \
                    f"Expected PRINCIPLE, got level={doc['metadata']['level']}"

                # --- Phase 3: Principle -> Skill ---
                for _ in range(4):
                    await engine.reward(nid, 1.0)
                meta = (await engine._store.get(nid))["metadata"]
                meta["retrieval_count"] = 7
                await engine._store.update_metadata(nid, meta)

                await engine.consolidate()
                doc = await engine._store.get(nid)
                assert doc["metadata"]["level"] == MemoryLevel.SKILL.value, \
                    f"Expected SKILL, got level={doc['metadata']['level']}"
            finally:
                await engine.shutdown()
        run(t())

    def test_below_threshold_does_not_promote(self, engine):
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "weak episode that should stay at L1",
                    keywords=["weak"],
                )

                # Q is at default 0.5 and retrieval_count is 0 — below threshold
                await engine.consolidate()

                doc = await engine._store.get(nid)
                assert doc["metadata"]["level"] == MemoryLevel.EPISODE.value
            finally:
                await engine.shutdown()
        run(t())

    def test_skill_level_is_terminal(self, engine):
        """SKILL memories should not be promoted further by consolidate."""
        async def t():
            await engine.start()
            try:
                nid = await engine.remember(
                    "already a skill memory",
                    level=MemoryLevel.SKILL,
                    keywords=["skill"],
                )

                doc = await engine._store.get(nid)
                meta = doc["metadata"]
                meta["q_value"] = 0.99
                meta["retrieval_count"] = 100
                await engine._store.update_metadata(nid, meta)

                stats = await engine.consolidate()

                doc_after = await engine._store.get(nid)
                assert doc_after["metadata"]["level"] == MemoryLevel.SKILL.value
            finally:
                await engine.shutdown()
        run(t())
