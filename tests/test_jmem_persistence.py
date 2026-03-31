"""Persistence round-trip test for the JMEM engine.

Validates that the entire cognitive state — memories, Q-values, links,
promoted levels, META insights, and adaptive thresholds — survives an
engine restart against the same SQLite database.
"""

import asyncio
import os
import shutil
import sys
import tempfile

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
def db_path(tmp_dir):
    """Return a stable DB path that both engine instances will share."""
    return os.path.join(tmp_dir, "persistence_test.db")


# ── Full Persistence Round-Trip ─────────────────────────────────────

class TestPersistenceRoundTrip:
    """Full lifecycle: build state, shutdown, reopen, verify everything survived."""

    def test_full_round_trip(self, db_path):
        """
        Steps 1-10 of the persistence contract:
          1. Create engine with temp DB, store memories at various levels
          2. Reward some memories to boost Q-values
          3. Consolidate to create links and promote
          4. meta_learn to generate META insights and persist thresholds
          5. Shutdown engine
          6. Create NEW engine with SAME DB path
          7. Start it — verify adaptive thresholds restored
          8. Recall — verify memories, Q-values, links survived
          9. Verify promoted levels persisted
         10. Verify META memories from meta_learn are still there
        """
        async def t():
            # ── Phase A: Build cognitive state ──────────────────────

            # Step 1: Create engine, store memories at various levels
            engine1 = JMemEngine(db_path=db_path)
            await engine1.start()

            # Store L1 EPISODE memories (some will be promoted later)
            episode_ids = []
            for i in range(6):
                nid = await engine1.remember(
                    f"python error handling pattern number {i} for robustness",
                    keywords=["python", "error-handling", "robustness"],
                )
                episode_ids.append(nid)

            # Store an L2 CONCEPT directly
            concept_id = await engine1.remember(
                "retry with exponential backoff is essential for resilience",
                level=MemoryLevel.CONCEPT,
                keywords=["retry", "backoff", "resilience"],
            )

            # Store an L3 PRINCIPLE directly
            principle_id = await engine1.remember(
                "always validate inputs at system boundaries",
                level=MemoryLevel.PRINCIPLE,
                keywords=["validation", "boundaries", "security"],
            )

            # Step 2: Reward memories to boost Q-values
            for _ in range(5):
                await engine1.reward(episode_ids[0], 0.9)
                await engine1.reward(episode_ids[1], 0.85)
            # Push concept and principle Q high as well
            for _ in range(6):
                await engine1.reward(concept_id, 0.95)
                await engine1.reward(principle_id, 0.95)

            # Set retrieval counts high enough to trigger promotion
            for target_id, target_ret in [
                (episode_ids[0], 3),
                (episode_ids[1], 3),
                (concept_id, 5),
                (principle_id, 7),
            ]:
                doc = await engine1._store.get(target_id)
                meta = doc["metadata"]
                meta["retrieval_count"] = target_ret
                await engine1._store.update_metadata(target_id, meta)

            # Snapshot pre-consolidation Q-values for rewarded episodes
            doc0_pre = await engine1._store.get(episode_ids[0])
            q_episode0_pre_consolidate = doc0_pre["metadata"]["q_value"]
            assert q_episode0_pre_consolidate > 0.65, \
                f"Episode 0 Q should exceed 0.65 after rewards, got {q_episode0_pre_consolidate}"

            # Step 3: Consolidate — creates links and promotes
            stats = await engine1.consolidate()
            assert stats["promoted"] >= 1, f"Expected at least 1 promotion, got {stats}"
            assert stats["linked"] >= 1, f"Expected at least 1 link, got {stats}"

            # Capture promoted levels after consolidation
            doc_ep0 = await engine1._store.get(episode_ids[0])
            level_ep0_after = doc_ep0["metadata"]["level"]
            doc_concept = await engine1._store.get(concept_id)
            level_concept_after = doc_concept["metadata"]["level"]
            doc_principle = await engine1._store.get(principle_id)
            level_principle_after = doc_principle["metadata"]["level"]

            # Verify promotions actually happened for the boosted memories
            assert level_ep0_after == MemoryLevel.CONCEPT.value, \
                f"Episode 0 should promote to CONCEPT, got level={level_ep0_after}"
            assert level_concept_after == MemoryLevel.PRINCIPLE.value, \
                f"Concept should promote to PRINCIPLE, got level={level_concept_after}"
            assert level_principle_after == MemoryLevel.SKILL.value, \
                f"Principle should promote to SKILL, got level={level_principle_after}"

            # Capture links on episode_ids[0] after consolidation
            links_ep0 = doc_ep0["metadata"].get("links", [])
            assert len(links_ep0) >= 1, "Episode 0 should have keyword-based links"

            # Step 4: meta_learn — generates META insights and persists thresholds
            #
            # We need meta_learn to produce at least one insight so it stores
            # a META memory and persists adjusted thresholds.  After step 3
            # some episodes were promoted to CONCEPT, so the "promotion_stall"
            # condition (episodes>20, concepts==0) will not fire.
            #
            # Instead we use a SEPARATE engine against its own temp DB to
            # trigger the stall, then we come back to engine1 to persist the
            # thresholds with a manual adjustment + _persist call.
            # Simpler: manually adjust a threshold on engine1 and persist it.

            # Force a threshold adjustment (simulates what meta_learn does)
            old_q, old_ret = engine1._promotion_thresholds[MemoryLevel.EPISODE.value]
            engine1._promotion_thresholds[MemoryLevel.EPISODE.value] = (
                max(0.4, old_q - 0.1),
                max(1, old_ret - 1),
            )
            await engine1._persist_adaptive_thresholds()

            # Also store a META-LEARNING INSIGHT memory directly, exactly
            # as meta_learn would, so we can verify it survives restart.
            await engine1.remember(
                content="META-LEARNING INSIGHT: [promotion_stall] 25 episodes but 0 concepts.",
                level=MemoryLevel.META,
                context="auto-generated by meta_learn cycle",
                keywords=["meta-learning", "self-analysis", "promotion_stall"],
                tags=["auto", "meta"],
            )

            # Record the adjusted thresholds before shutdown
            thresholds_before_shutdown = dict(engine1._promotion_thresholds)

            # Collect Q-value for episode_ids[0] just before shutdown
            doc_ep0_final = await engine1._store.get(episode_ids[0])
            q_ep0_final = doc_ep0_final["metadata"]["q_value"]

            # Step 5: Shutdown engine
            await engine1.shutdown()

            # ── Phase B: Reopen and verify ──────────────────────────

            # Step 6: Create NEW engine with SAME DB path
            engine2 = JMemEngine(db_path=db_path)

            # Step 7: Start it — verify adaptive thresholds restored
            await engine2.start()

            assert engine2._promotion_thresholds == thresholds_before_shutdown, (
                f"Thresholds not restored.\n"
                f"  Before shutdown: {thresholds_before_shutdown}\n"
                f"  After restart:   {engine2._promotion_thresholds}"
            )

            # Step 8: Recall — verify memories, Q-values, links survived
            recalled = await engine2.recall("python error handling robustness", limit=10)
            recalled_ids = {n.id for n in recalled}
            assert episode_ids[0] in recalled_ids, \
                f"Episode 0 ({episode_ids[0][:8]}) not found in recall results"

            # Verify Q-value persisted
            doc_ep0_reloaded = await engine2._store.get(episode_ids[0])
            assert doc_ep0_reloaded is not None, "Episode 0 missing from DB after restart"
            q_ep0_reloaded = doc_ep0_reloaded["metadata"]["q_value"]
            assert abs(q_ep0_reloaded - q_ep0_final) < 0.001, (
                f"Q-value drift: before shutdown={q_ep0_final}, "
                f"after restart={q_ep0_reloaded}"
            )

            # Verify links survived
            links_ep0_reloaded = doc_ep0_reloaded["metadata"].get("links", [])
            assert links_ep0_reloaded == links_ep0, (
                f"Links lost.\n"
                f"  Before: {links_ep0}\n"
                f"  After:  {links_ep0_reloaded}"
            )

            # Step 9: Verify promoted levels persisted
            doc_ep0_r = await engine2._store.get(episode_ids[0])
            assert doc_ep0_r["metadata"]["level"] == level_ep0_after, \
                f"Episode 0 level reverted: expected {level_ep0_after}, got {doc_ep0_r['metadata']['level']}"

            doc_concept_r = await engine2._store.get(concept_id)
            assert doc_concept_r["metadata"]["level"] == level_concept_after, \
                f"Concept level reverted: expected {level_concept_after}, got {doc_concept_r['metadata']['level']}"

            doc_principle_r = await engine2._store.get(principle_id)
            assert doc_principle_r["metadata"]["level"] == level_principle_after, \
                f"Principle level reverted: expected {level_principle_after}, got {doc_principle_r['metadata']['level']}"

            # Step 10: Verify META memories from meta_learn still exist
            all_docs = await engine2._store.get_all(limit=500)
            meta_docs = [
                d for d in all_docs
                if d["metadata"].get("level") == MemoryLevel.META.value
            ]
            assert len(meta_docs) >= 1, "No META memories found after restart"

            # Check that at least one contains the meta-learning insight text
            meta_texts = [d["text"] for d in meta_docs]
            has_insight = any("META-LEARNING INSIGHT" in t for t in meta_texts)
            assert has_insight, (
                f"META-LEARNING INSIGHT text not found in META memories. "
                f"Texts: {[t[:80] for t in meta_texts]}"
            )

            # Also verify adaptive-thresholds META memory exists
            has_thresholds = any(
                "adaptive-thresholds" in d["metadata"].get("keywords", [])
                for d in meta_docs
            )
            # Thresholds may be stored as an evolved memory (new ID) — check all docs
            if not has_thresholds:
                all_keywords = []
                for d in all_docs:
                    kws = d["metadata"].get("keywords", [])
                    all_keywords.extend(kws)
                    if "adaptive-thresholds" in kws:
                        has_thresholds = True
                        break
            assert has_thresholds, "adaptive-thresholds META memory not found after restart"

            await engine2.shutdown()

        run(t())


# ── Focused Sub-Tests ────────────────────────────────────────────────

class TestQValuePersistence:
    """Q-values survive shutdown/restart exactly."""

    def test_q_values_survive_restart(self, db_path):
        async def t():
            engine1 = JMemEngine(db_path=db_path)
            await engine1.start()

            nid = await engine1.remember(
                "important pattern about caching strategies",
                keywords=["caching", "performance"],
            )
            # Reward to push Q well above 0.5 default
            for _ in range(4):
                await engine1.reward(nid, 0.95)

            doc = await engine1._store.get(nid)
            q_before = doc["metadata"]["q_value"]
            assert q_before > 0.7, f"Q should be high after rewards, got {q_before}"

            await engine1.shutdown()

            engine2 = JMemEngine(db_path=db_path)
            await engine2.start()

            doc_after = await engine2._store.get(nid)
            assert doc_after is not None
            q_after = doc_after["metadata"]["q_value"]
            assert abs(q_after - q_before) < 0.001, \
                f"Q-value changed across restart: {q_before} -> {q_after}"

            await engine2.shutdown()

        run(t())


class TestLinkPersistence:
    """Consolidation links survive shutdown/restart."""

    def test_links_survive_restart(self, db_path):
        async def t():
            engine1 = JMemEngine(db_path=db_path)
            await engine1.start()

            ids = []
            for i in range(5):
                nid = await engine1.remember(
                    f"shared topic about database indexing strategy {i}",
                    keywords=["database", "indexing"],
                )
                ids.append(nid)

            await engine1.consolidate()

            # Collect all links from first memory
            doc = await engine1._store.get(ids[0])
            links_before = doc["metadata"].get("links", [])
            assert len(links_before) >= 1, "Consolidation should create links"

            await engine1.shutdown()

            engine2 = JMemEngine(db_path=db_path)
            await engine2.start()

            doc_after = await engine2._store.get(ids[0])
            links_after = doc_after["metadata"].get("links", [])
            assert links_after == links_before, \
                f"Links changed: {links_before} -> {links_after}"

            await engine2.shutdown()

        run(t())


class TestPromotionPersistence:
    """Promoted memory levels survive shutdown/restart."""

    def test_promoted_level_survives_restart(self, db_path):
        async def t():
            engine1 = JMemEngine(db_path=db_path)
            await engine1.start()

            nid = await engine1.remember(
                "error handling with retries",
                keywords=["error", "retry"],
            )

            # Boost past EPISODE promotion threshold
            doc = await engine1._store.get(nid)
            meta = doc["metadata"]
            meta["q_value"] = 0.75
            meta["retrieval_count"] = 4
            await engine1._store.update_metadata(nid, meta)

            await engine1.consolidate()

            doc_promoted = await engine1._store.get(nid)
            assert doc_promoted["metadata"]["level"] == MemoryLevel.CONCEPT.value

            await engine1.shutdown()

            engine2 = JMemEngine(db_path=db_path)
            await engine2.start()

            doc_after = await engine2._store.get(nid)
            assert doc_after["metadata"]["level"] == MemoryLevel.CONCEPT.value, \
                f"Level reverted to {doc_after['metadata']['level']} after restart"

            await engine2.shutdown()

        run(t())


class TestAdaptiveThresholdPersistence:
    """Adaptive thresholds adjusted by meta_learn survive restart."""

    def test_adjusted_thresholds_survive_restart(self, db_path):
        async def t():
            engine1 = JMemEngine(db_path=db_path)
            await engine1.start()

            # Record default thresholds
            default_thresholds = dict(engine1._promotion_thresholds)

            # Store enough episodes to trigger promotion_stall adjustment
            for i in range(25):
                await engine1.remember(
                    f"stall episode {i} word{i}",
                    keywords=[f"unique{i}"],
                )

            result = await engine1.meta_learn()
            adjusted_thresholds = dict(engine1._promotion_thresholds)

            # Verify meta_learn actually adjusted something
            assert adjusted_thresholds != default_thresholds, \
                "meta_learn should have adjusted thresholds"

            await engine1.shutdown()

            engine2 = JMemEngine(db_path=db_path)
            await engine2.start()

            # Thresholds should be restored from the META memory
            assert engine2._promotion_thresholds == adjusted_thresholds, (
                f"Thresholds not restored.\n"
                f"  Expected: {adjusted_thresholds}\n"
                f"  Got:      {engine2._promotion_thresholds}"
            )

            await engine2.shutdown()

        run(t())


class TestMetaMemoryPersistence:
    """META memories created by meta_learn survive restart."""

    def test_meta_insight_survives_restart(self, db_path):
        async def t():
            engine1 = JMemEngine(db_path=db_path)
            await engine1.start()

            # Trigger a meta_learn cycle that creates insight memories
            for i in range(25):
                await engine1.remember(
                    f"episode for meta test {i} uniquedata{i}",
                    keywords=[f"meta_kw_{i}"],
                )

            ml_result = await engine1.meta_learn()
            assert len(ml_result["insights"]) >= 1

            # Count META memories before shutdown
            all_docs = await engine1._store.get_all(limit=500)
            meta_count_before = sum(
                1 for d in all_docs
                if d["metadata"].get("level") == MemoryLevel.META.value
            )
            assert meta_count_before >= 1

            await engine1.shutdown()

            engine2 = JMemEngine(db_path=db_path)
            await engine2.start()

            all_docs_after = await engine2._store.get_all(limit=500)
            meta_docs_after = [
                d for d in all_docs_after
                if d["metadata"].get("level") == MemoryLevel.META.value
            ]
            assert len(meta_docs_after) >= meta_count_before, \
                f"META memories lost: had {meta_count_before}, now {len(meta_docs_after)}"

            # Verify insight text is intact
            has_insight = any("META-LEARNING INSIGHT" in d["text"] for d in meta_docs_after)
            assert has_insight, "META-LEARNING INSIGHT text lost after restart"

            await engine2.shutdown()

        run(t())
