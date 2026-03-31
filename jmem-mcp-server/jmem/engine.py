"""
JMemEngine — Core semantic memory engine.

Ported from https://github.com/Aussie-Agents/jmem-mcp-server

5-layer cognitive architecture:
    L1 RECALL     — Vector search via TF-IDF + BM25 + Q-boost
    L2 CONSOLIDATE — Zettelkasten linking + keyword clustering
    L3 RELATIONAL — Graph traversal for connected memories
    L4 EVOLUTION  — Context drift detection + mutation
    L5 META-LEARNING — Concept extraction, principle derivation, skill gen

Knowledge promotion pipeline:
    episode → concept → principle → skill
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from jmem.vector_store import PureVectorStore

logger = logging.getLogger("jmem.engine")


class MemoryLevel(IntEnum):
    EPISODE = 1    # Raw experiences
    CONCEPT = 2    # Patterns extracted from episodes
    PRINCIPLE = 3  # Generalizable rules
    SKILL = 4      # Executable capabilities
    META = 5       # Meta-learning insights (how to learn better)
    EMERGENT = 6   # Cross-agent emergent knowledge


@dataclass(slots=True)
class MemoryNote:
    """A single memory unit in the JMEM system."""
    id: str
    content: str
    context: str = ""
    keywords: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    level: MemoryLevel = MemoryLevel.EPISODE
    links: list[str] = field(default_factory=list)
    q_value: float = 0.5
    retrieval_count: int = 0
    created_at: float = field(default_factory=time.time)
    evolved_from: str | None = None

    def composite_text(self) -> str:
        """Level-aware text for search indexing — boosts higher abstractions."""
        level_boost = {
            MemoryLevel.EPISODE: 1,
            MemoryLevel.CONCEPT: 2,
            MemoryLevel.PRINCIPLE: 3,
            MemoryLevel.SKILL: 4,
        }
        boost = level_boost.get(self.level, 1)
        keywords_text = " ".join(self.keywords) * boost
        return f"{self.content} {keywords_text} {self.context}"

    def to_metadata(self) -> dict[str, Any]:
        return {
            "level": self.level.value,
            "q_value": self.q_value,
            "retrieval_count": self.retrieval_count,
            "keywords": self.keywords,
            "tags": self.tags,
            "links": self.links,
            "created_at": self.created_at,
            "evolved_from": self.evolved_from,
        }

    @classmethod
    def from_metadata(cls, doc_id: str, text: str, meta: dict[str, Any]) -> MemoryNote:
        return cls(
            id=doc_id,
            content=text,
            level=MemoryLevel(meta.get("level", 1)),
            q_value=meta.get("q_value", 0.5),
            retrieval_count=meta.get("retrieval_count", 0),
            keywords=meta.get("keywords", []),
            tags=meta.get("tags", []),
            links=meta.get("links", []),
            created_at=meta.get("created_at", 0),
            evolved_from=meta.get("evolved_from"),
        )


class RLScorer:
    """Q-learning reinforcement for memory scoring.

    Polarizing updates: strong alpha (0.5) for confident signals,
    weak alpha (0.15) for ambiguous ones.
    """

    @staticmethod
    def update(current_q: float, reward: float) -> float:
        alpha = 0.5 if abs(reward) > 0.5 else 0.15
        new_q = current_q + alpha * (reward - current_q)
        return max(0.0, min(1.0, new_q))


class JMemEngine:
    """
    Top-level JMEM API — persistent semantic memory for AI agents.

    Core operations:
        remember(content, level, context) → store memory
        recall(query, limit) → search with graph traversal
        reward(note_id, reward) → reinforce via Q-learning
        evolve(note_id, new_content) → mutate memory
        consolidate() → link related, auto-promote, synthesize
        reflect() → cognitive cycle with statistics
    """

    def __init__(self, namespace: str = "default", db_path: str | None = None):
        self.namespace = namespace
        self._store = PureVectorStore(db_path)
        self._scorer = RLScorer()
        # Auto-consolidation: trigger every N stores
        self._store_count = 0
        self._auto_consolidate_interval = 10
        # Retrieval tracking: maps recall query → list of note IDs returned
        self._recent_recalls: list[list[str]] = []
        # Adaptive thresholds (can be adjusted by meta_learn)
        self._promotion_thresholds: dict[int, tuple[float, int]] = {
            MemoryLevel.EPISODE.value: (0.65, 2),   # Q, retrievals
            MemoryLevel.CONCEPT.value: (0.75, 4),
            MemoryLevel.PRINCIPLE.value: (0.9, 6),
        }

    async def start(self) -> None:
        await self._store._ensure_initialized()
        await self._restore_adaptive_thresholds()

    async def _restore_adaptive_thresholds(self) -> None:
        """Restore persisted adaptive thresholds from a META memory (if any)."""
        try:
            results = await self._store.search(
                "adaptive-thresholds", top_k=5,
                where={"level": MemoryLevel.META.value},
            )
            for doc_id, _score, meta in results:
                keywords = meta.get("keywords", [])
                if "adaptive-thresholds" not in keywords:
                    continue
                doc = await self._store.get(doc_id)
                if not doc:
                    continue
                # Content stores the JSON thresholds
                content = doc.get("text", "")
                # Extract JSON from content (may be wrapped in descriptive text)
                json_start = content.find("{")
                json_end = content.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    parsed = json.loads(content[json_start:json_end])
                    restored: dict[int, tuple[float, int]] = {}
                    for k, v in parsed.items():
                        restored[int(k)] = (float(v[0]), int(v[1]))
                    self._promotion_thresholds = restored
                    logger.info("Restored adaptive thresholds from META memory %s: %s",
                                doc_id[:8], self._promotion_thresholds)
                return
        except Exception as e:
            logger.warning("Could not restore adaptive thresholds: %s", e)

    async def shutdown(self) -> None:
        await self._store.close()

    # ── Remember ─────────────────────────────────────────────────

    async def remember(
        self,
        content: str,
        level: MemoryLevel = MemoryLevel.EPISODE,
        context: str = "",
        keywords: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> str:
        """Store a memory at the given cognitive level."""
        note_id = self._generate_id(content, level)

        note = MemoryNote(
            id=note_id,
            content=content,
            context=context,
            level=level,
            keywords=keywords or self._extract_keywords(content),
            tags=tags or [],
        )

        await self._store.upsert(
            doc_id=note_id,
            text=note.composite_text(),
            metadata=note.to_metadata(),
        )

        logger.info("Remembered [L%d] %s: %.60s", level.value, note_id[:8], content)

        # Auto-consolidation: trigger every N stores
        self._store_count += 1
        if self._store_count % self._auto_consolidate_interval == 0:
            logger.info("Auto-consolidating after %d stores", self._store_count)
            await self.consolidate()

        return note_id

    # ── Recall ───────────────────────────────────────────────────

    async def recall(
        self,
        query: str,
        limit: int = 5,
        level: MemoryLevel | None = None,
        min_q: float = 0.0,
    ) -> list[MemoryNote]:
        """Search semantic memory with optional level/Q filtering."""
        where: dict[str, Any] = {}
        if level is not None:
            where["level"] = level.value
        if min_q > 0:
            where["q_value"] = {"$gte": min_q}

        results = await self._store.search(query, top_k=limit * 2, where=where or None)

        notes: list[MemoryNote] = []
        for doc_id, score, meta in results[:limit]:
            doc = await self._store.get(doc_id)
            if doc:
                note = MemoryNote.from_metadata(doc_id, doc["text"], meta)
                note.retrieval_count += 1
                # Update retrieval count
                meta["retrieval_count"] = note.retrieval_count
                await self._store.update_metadata(doc_id, meta)
                notes.append(note)

        # Graph traversal: follow links from top results
        if notes:
            linked_ids: set[str] = set()
            for note in notes[:3]:
                linked_ids.update(note.links)

            for link_id in linked_ids:
                if link_id not in {n.id for n in notes} and len(notes) < limit:
                    doc = await self._store.get(link_id)
                    if doc:
                        linked_note = MemoryNote.from_metadata(
                            link_id, doc["text"], doc.get("metadata", {}))
                        notes.append(linked_note)

        # Track recall for auto-reward
        recalled_ids = [n.id for n in notes]
        if recalled_ids:
            self._recent_recalls.append(recalled_ids)
            # Keep only last 50 recall batches
            if len(self._recent_recalls) > 50:
                self._recent_recalls = self._recent_recalls[-50:]

        return notes

    # ── Reward ───────────────────────────────────────────────────

    async def reward(self, note_id: str, reward_signal: float, context: str = "") -> float:
        """Reinforce a memory via Q-learning update."""
        doc = await self._store.get(note_id)
        if not doc:
            return 0.0

        meta = doc.get("metadata", {})
        if isinstance(meta, str):
            import json
            meta = json.loads(meta)

        current_q = float(meta.get("q_value", 0.5))
        new_q = self._scorer.update(current_q, reward_signal)
        meta["q_value"] = new_q
        await self._store.update_metadata(note_id, meta)

        logger.debug("Reward %s: %.2f → %.2f (signal=%.2f)", note_id[:8], current_q, new_q, reward_signal)
        return new_q

    # ── Evolve ───────────────────────────────────────────────────

    async def evolve(self, note_id: str, new_content: str) -> str:
        """Mutate a memory's content while preserving metadata."""
        doc = await self._store.get(note_id)
        if not doc:
            raise ValueError(f"Memory not found: {note_id}")

        meta = doc.get("metadata", {})
        if isinstance(meta, str):
            import json
            meta = json.loads(meta)

        meta["evolved_from"] = note_id

        # Create evolved version
        new_id = self._generate_id(new_content, MemoryLevel(meta.get("level", 1)))
        note = MemoryNote(
            id=new_id,
            content=new_content,
            level=MemoryLevel(meta.get("level", 1)),
            keywords=meta.get("keywords", []),
            q_value=meta.get("q_value", 0.5),
            evolved_from=note_id,
        )

        await self._store.upsert(new_id, note.composite_text(), note.to_metadata())
        return new_id

    # ── Consolidate ──────────────────────────────────────────────

    async def consolidate(self) -> dict[str, int]:
        """
        Link related memories, auto-promote high-Q episodes, synthesize concepts.

        Returns counts of operations performed.
        """
        stats = {"linked": 0, "promoted": 0, "synthesized": 0}

        # Get all documents
        all_docs = await self._store.get_all(limit=1000) if hasattr(self._store, 'get_all') else []

        # Auto-promote using adaptive thresholds (can be tuned by meta_learn)
        promotion_rules: dict[int, tuple[int, float, int]] = {}
        for src_level, (min_q, min_ret) in self._promotion_thresholds.items():
            match src_level:
                case 1: target = MemoryLevel.CONCEPT.value
                case 2: target = MemoryLevel.PRINCIPLE.value
                case 3: target = MemoryLevel.SKILL.value
                case _: continue
            promotion_rules[src_level] = (target, min_q, min_ret)
        for doc in all_docs:
            meta = doc.get("metadata", {})
            if isinstance(meta, str):
                import json
                meta = json.loads(meta)
            level = meta.get("level", 1)
            if level in promotion_rules:
                target, min_q, min_ret = promotion_rules[level]
                if meta.get("q_value", 0) >= min_q and meta.get("retrieval_count", 0) >= min_ret:
                    meta["level"] = target
                    await self._store.update_metadata(doc["id"], meta)
                    stats["promoted"] += 1
                    logger.info("Promoted %s: L%d → L%d (Q=%.2f, retrievals=%d)",
                                doc["id"][:8], level, target,
                                meta.get("q_value", 0), meta.get("retrieval_count", 0))

        # Keyword clustering: link memories sharing 2+ keywords
        keyword_map: dict[str, list[str]] = {}
        for doc in all_docs:
            meta = doc.get("metadata", {})
            if isinstance(meta, str):
                import json
                meta = json.loads(meta)
            for kw in meta.get("keywords", []):
                keyword_map.setdefault(kw, []).append(doc["id"])

        for kw, doc_ids in keyword_map.items():
            if len(doc_ids) >= 2:
                for i, id_a in enumerate(doc_ids):
                    for id_b in doc_ids[i + 1:]:
                        # Cross-link
                        doc_a = await self._store.get(id_a)
                        if doc_a:
                            meta_a = doc_a.get("metadata", {})
                            if isinstance(meta_a, str):
                                import json
                                meta_a = json.loads(meta_a)
                            links = meta_a.get("links", [])
                            if id_b not in links:
                                links.append(id_b)
                                meta_a["links"] = links[:20]  # cap at 20
                                await self._store.update_metadata(id_a, meta_a)
                                stats["linked"] += 1

        return stats

    # ── Reflect ──────────────────────────────────────────────────

    async def reflect(self) -> dict[str, Any]:
        """Run a cognitive cycle — statistics + health assessment."""
        count = await self._store.count()
        status = await self._store.status()

        # Count by level
        all_docs = await self._store.get_all(limit=2000) if hasattr(self._store, 'get_all') else []
        level_counts = {l.name: 0 for l in MemoryLevel}
        total_q = 0.0
        for doc in all_docs:
            meta = doc.get("metadata", {})
            if isinstance(meta, str):
                import json
                meta = json.loads(meta)
            raw_level = meta.get("level", 1)
            try:
                lvl = MemoryLevel(raw_level)
            except ValueError:
                lvl = MemoryLevel.EPISODE
            level_counts[lvl.name] += 1
            total_q += meta.get("q_value", 0.5)

        avg_q = total_q / max(count, 1)

        return {
            "total_memories": count,
            "by_level": level_counts,
            "average_q": round(avg_q, 3),
            "vocab_size": status.get("vocab_size", 0),
            "db_size_kb": status.get("db_size_kb", 0),
            "health": "good" if avg_q > 0.5 else "needs_consolidation",
        }

    # ── Status ───────────────────────────────────────────────────

    async def status(self) -> dict[str, Any]:
        store_status = await self._store.status()
        return {
            "namespace": self.namespace,
            "store": store_status,
        }

    # ── Auto-Reward Recalled Memories ────────────────────────────

    async def reward_recalled(self, reward_signal: float = 0.7) -> dict[str, Any]:
        """Reward all recently recalled memories (batch reinforcement).

        Call this after a successful task to reinforce the memories that
        were recalled during planning/execution.
        """
        if not self._recent_recalls:
            return {"rewarded": 0, "batches": 0}

        rewarded = 0
        all_ids: set[str] = set()
        for batch in self._recent_recalls:
            all_ids.update(batch)

        for note_id in all_ids:
            await self.reward(note_id, reward_signal, context="auto-reward from successful recall")
            rewarded += 1

        batches = len(self._recent_recalls)
        self._recent_recalls.clear()
        return {"rewarded": rewarded, "batches": batches}

    # ── Time-based Decay ────────────────────────────────────────

    async def decay_idle(self, hours_threshold: float = 24.0, decay_rate: float = 0.02) -> dict[str, Any]:
        """Apply time-based Q-decay to memories not accessed recently.

        Memories idle longer than hours_threshold lose Q-value at decay_rate per day.
        Prevents stale memories from clogging the promotion pipeline.
        """
        all_docs = await self._store.get_all(limit=2000) if hasattr(self._store, 'get_all') else []
        now = time.time()
        decayed = 0

        for doc in all_docs:
            meta = doc.get("metadata", {})
            if isinstance(meta, str):
                import json
                meta = json.loads(meta)

            created_at = meta.get("created_at", now)
            age_hours = (now - created_at) / 3600.0

            if age_hours > hours_threshold:
                current_q = meta.get("q_value", 0.5)
                days_idle = age_hours / 24.0
                new_q = max(0.1, current_q - (decay_rate * days_idle))
                if new_q < current_q:
                    meta["q_value"] = round(new_q, 4)
                    await self._store.update_metadata(doc["id"], meta)
                    decayed += 1

        return {"decayed": decayed, "threshold_hours": hours_threshold}

    # ── Skill Extraction ────────────────────────────────────────

    async def extract_skills(self) -> dict[str, Any]:
        """Auto-extract high-Q principles into structured SKILL memories.

        When a PRINCIPLE has Q≥0.92 and retrieval_count≥5, synthesize it
        into a SKILL with actionable steps.
        """
        all_docs = await self._store.get_all(limit=2000) if hasattr(self._store, 'get_all') else []
        extracted = 0

        for doc in all_docs:
            meta = doc.get("metadata", {})
            if isinstance(meta, str):
                import json
                meta = json.loads(meta)

            level = meta.get("level", 1)
            q = meta.get("q_value", 0.5)
            retrievals = meta.get("retrieval_count", 0)

            if level == MemoryLevel.PRINCIPLE.value and q >= 0.92 and retrievals >= 5:
                content = doc.get("text", "")
                skill_content = (
                    f"SKILL (auto-extracted from principle Q={q:.2f}, retrievals={retrievals}):\n"
                    f"{content}\n\n"
                    f"Application: Use this pattern when the context matches the keywords below."
                )
                await self.remember(
                    content=skill_content,
                    level=MemoryLevel.SKILL,
                    context=f"auto-extracted from principle {doc['id'][:8]}",
                    keywords=meta.get("keywords", []) + ["auto-skill"],
                    tags=["auto", "skill-extraction"],
                )
                extracted += 1

        return {"skills_extracted": extracted}

    # ── Meta-Learn ───────────────────────────────────────────────

    async def meta_learn(self) -> dict[str, Any]:
        """L4 Meta-Learning: analyze the learning process itself.

        Examines:
        - Promotion velocity (how fast memories climb levels)
        - Q-value distribution (healthy learning vs stagnation)
        - Keyword saturation (are we learning new things?)
        - Reward patterns (what types of memories get rewarded most)

        Stores insights as L5 META memories and adjusts promotion thresholds.
        """
        all_docs = await self._store.get_all(limit=2000) if hasattr(self._store, 'get_all') else []
        if not all_docs:
            return {"insights": [], "adjustments": []}

        insights: list[dict[str, str]] = []
        adjustments: list[dict[str, str]] = []

        # Parse all notes
        notes: list[MemoryNote] = []
        for doc in all_docs:
            meta = doc.get("metadata", {})
            if isinstance(meta, str):
                import json
                meta = json.loads(meta)
            notes.append(MemoryNote.from_metadata(doc["id"], doc.get("text", ""), meta))

        # 1. Q-value distribution analysis
        q_values = [n.q_value for n in notes]
        avg_q = sum(q_values) / max(len(q_values), 1)
        high_q = sum(1 for q in q_values if q > 0.8)
        low_q = sum(1 for q in q_values if q < 0.3)

        if avg_q < 0.4:
            insights.append({"category": "learning_rate", "observation": f"Average Q-value is low ({avg_q:.2f}). Memories are not being rewarded enough.", "suggestion": "Increase reward signals for successful outcomes."})
        if high_q > len(notes) * 0.5:
            insights.append({"category": "q_inflation", "observation": f"{high_q}/{len(notes)} memories have Q > 0.8. Possible reward inflation.", "suggestion": "Apply stricter reward criteria or increase decay rate."})
        if low_q > len(notes) * 0.5:
            insights.append({"category": "q_stagnation", "observation": f"{low_q}/{len(notes)} memories have Q < 0.3. Knowledge is decaying.", "suggestion": "Consolidate and recall more often to boost retrieval counts."})

        # 2. Level distribution analysis
        level_counts: dict[int, int] = {}
        for n in notes:
            level_counts[n.level.value] = level_counts.get(n.level.value, 0) + 1

        episodes = level_counts.get(1, 0)
        concepts = level_counts.get(2, 0)
        principles = level_counts.get(3, 0)
        skills = level_counts.get(4, 0)

        if episodes > 20 and concepts == 0:
            insights.append({"category": "promotion_stall", "observation": f"{episodes} episodes but 0 concepts. Auto-promotion is not triggering.", "suggestion": "Lowering episode promotion threshold."})
            # Actually adjust the threshold
            old_q, old_ret = self._promotion_thresholds.get(1, (0.65, 2))
            new_q = max(0.4, old_q - 0.1)
            new_ret = max(1, old_ret - 1)
            self._promotion_thresholds[1] = (new_q, new_ret)
            adjustments.append({"type": "lower_episode_threshold", "from": f"Q>{old_q}, ret>{old_ret}", "to": f"Q>{new_q}, ret>{new_ret}"})
        if concepts > 10 and principles == 0:
            insights.append({"category": "promotion_stall", "observation": f"{concepts} concepts but 0 principles. Lowering concept threshold.", "suggestion": "Reward validated concepts to push them toward principles."})
            old_q, old_ret = self._promotion_thresholds.get(2, (0.75, 4))
            new_q = max(0.5, old_q - 0.1)
            new_ret = max(2, old_ret - 1)
            self._promotion_thresholds[2] = (new_q, new_ret)
            adjustments.append({"type": "lower_concept_threshold", "from": f"Q>{old_q}, ret>{old_ret}", "to": f"Q>{new_q}, ret>{new_ret}"})

        # 3. Keyword diversity (are we learning new things?)
        all_keywords: set[str] = set()
        for n in notes:
            all_keywords.update(n.keywords)
        keyword_ratio = len(all_keywords) / max(len(notes), 1)

        if keyword_ratio < 1.0 and len(notes) > 10:
            insights.append({"category": "knowledge_saturation", "observation": f"Keyword diversity is low ({keyword_ratio:.1f} unique keywords per memory). Learning is repetitive.", "suggestion": "Explore new topics or domains."})

        # 4. Store meta-learning insight as L5 META memory
        if insights:
            insight_summary = "; ".join(f"[{i['category']}] {i['observation']}" for i in insights)
            await self.remember(
                content=f"META-LEARNING INSIGHT: {insight_summary}",
                level=MemoryLevel.META,
                context="auto-generated by meta_learn cycle",
                keywords=["meta-learning", "self-analysis"] + [i["category"] for i in insights],
                tags=["auto", "meta"],
            )

        # 5. Persist adaptive thresholds so they survive restarts
        await self._persist_adaptive_thresholds()

        return {
            "insights": insights,
            "adjustments": adjustments,
            "stats": {
                "avg_q": round(avg_q, 3),
                "high_q_count": high_q,
                "low_q_count": low_q,
                "level_distribution": level_counts,
                "keyword_diversity": round(keyword_ratio, 2),
                "total_memories": len(notes),
            },
        }

    # ── Emergent Synthesis ──────────────────────────────────────

    async def emergent_synthesis(self) -> dict[str, Any]:
        """L5 Emergent Knowledge: discover cross-cutting patterns.

        Analyzes the entire memory graph for:
        - Co-occurring keywords (concepts that belong together)
        - Promotion chains (what path do successful memories take)
        - Cluster density (tightly linked memory groups = strong knowledge areas)
        - Knowledge gaps (isolated memories with no links)

        Stores discoveries as L6 EMERGENT memories.
        """
        all_docs = await self._store.get_all(limit=2000) if hasattr(self._store, 'get_all') else []
        if not all_docs:
            return {"discoveries": [], "clusters": [], "gaps": []}

        discoveries: list[dict[str, Any]] = []
        notes: list[MemoryNote] = []
        for doc in all_docs:
            meta = doc.get("metadata", {})
            if isinstance(meta, str):
                import json
                meta = json.loads(meta)
            notes.append(MemoryNote.from_metadata(doc["id"], doc.get("text", ""), meta))

        # 1. Keyword co-occurrence — find concepts that cluster together
        from collections import Counter
        keyword_pairs: Counter[tuple[str, str]] = Counter()
        for n in notes:
            kws = sorted(set(n.keywords))
            for i, a in enumerate(kws):
                for b in kws[i + 1:]:
                    keyword_pairs[(a, b)] += 1

        strong_pairs = [(pair, count) for pair, count in keyword_pairs.most_common(20) if count >= 3]
        for pair, count in strong_pairs:
            discoveries.append({
                "type": "keyword_cluster",
                "description": f"'{pair[0]}' and '{pair[1]}' co-occur in {count} memories — strong conceptual link",
                "confidence": min(1.0, count / 10.0),
            })

        # 2. Knowledge gaps — orphan memories with no links
        orphans = [n for n in notes if not n.links and n.retrieval_count == 0]
        gaps = [{"id": n.id, "content": n.content[:80], "level": n.level.name} for n in orphans[:10]]

        # 3. Cluster density — count strongly-connected groups
        clusters: list[dict[str, Any]] = []
        visited: set[str] = set()
        note_map = {n.id: n for n in notes}

        for n in notes:
            if n.id in visited or not n.links:
                continue
            # BFS to find cluster
            cluster_ids: set[str] = set()
            queue = [n.id]
            while queue:
                current = queue.pop(0)
                if current in cluster_ids:
                    continue
                cluster_ids.add(current)
                if current in note_map:
                    for link_id in note_map[current].links:
                        if link_id not in cluster_ids:
                            queue.append(link_id)

            visited.update(cluster_ids)
            if len(cluster_ids) >= 3:
                cluster_keywords: Counter[str] = Counter()
                for cid in cluster_ids:
                    if cid in note_map:
                        cluster_keywords.update(note_map[cid].keywords)
                top_keywords = [kw for kw, _ in cluster_keywords.most_common(5)]
                clusters.append({
                    "size": len(cluster_ids),
                    "keywords": top_keywords,
                    "avg_q": round(sum(note_map[cid].q_value for cid in cluster_ids if cid in note_map) / len(cluster_ids), 3),
                })

        # 4. Promotion chain analysis — what makes memories succeed
        promoted = [n for n in notes if n.level.value >= 3]
        if promoted:
            avg_promoted_q = sum(n.q_value for n in promoted) / len(promoted)
            avg_promoted_retrievals = sum(n.retrieval_count for n in promoted) / len(promoted)
            discoveries.append({
                "type": "promotion_pattern",
                "description": f"Successful memories (L3+) have avg Q={avg_promoted_q:.2f}, avg retrievals={avg_promoted_retrievals:.1f}",
                "confidence": 0.8,
            })

        # Store emergent insight if we found patterns
        if discoveries:
            summary = "; ".join(d["description"] for d in discoveries[:5])
            await self.remember(
                content=f"EMERGENT KNOWLEDGE: {summary}",
                level=MemoryLevel.EMERGENT,
                context="auto-generated by emergent_synthesis cycle",
                keywords=["emergent", "synthesis", "cross-cutting"],
                tags=["auto", "emergent"],
            )

        return {
            "discoveries": discoveries,
            "clusters": clusters,
            "gaps": gaps,
            "orphan_count": len(orphans),
        }

    # ── Cross-Namespace Recall ─────────────────────────────────

    async def recall_cross_namespace(
        self,
        query: str,
        namespaces: list[str],
        limit: int = 5,
    ) -> list[MemoryNote]:
        """Search across multiple agent namespaces, merging results by Q-value.

        Each namespace maps to ~/.jmem/{namespace}/memory.db.
        Enables emergent cross-agent knowledge synthesis.
        """
        all_notes: list[MemoryNote] = []

        for ns in namespaces:
            db_path = os.path.join(os.path.expanduser("~/.jmem"), ns, "memory.db")
            if not os.path.exists(db_path):
                logger.debug("Skipping namespace %r — no database at %s", ns, db_path)
                continue

            ns_engine = JMemEngine(namespace=ns, db_path=db_path)
            try:
                await ns_engine.start()
                notes = await ns_engine.recall(query=query, limit=limit)
                # Tag each note with its source namespace for the caller
                for note in notes:
                    note.tags = list(set(note.tags) | {f"ns:{ns}"})
                all_notes.extend(notes)
            except Exception as e:
                logger.warning("Cross-namespace recall failed for %r: %s", ns, e)
            finally:
                await ns_engine.shutdown()

        # Merge by Q-value descending, then trim to limit
        all_notes.sort(key=lambda n: n.q_value, reverse=True)
        return all_notes[:limit]

    # ── Helpers ──────────────────────────────────────────────────

    async def _persist_adaptive_thresholds(self) -> None:
        """Store current adaptive thresholds as a META memory for restart persistence."""
        # Serialize thresholds: {level_int: [q_threshold, retrieval_threshold]}
        serializable = {str(k): list(v) for k, v in self._promotion_thresholds.items()}
        content = json.dumps(serializable)

        # Check if a threshold memory already exists — evolve it if so
        try:
            results = await self._store.search(
                "adaptive-thresholds", top_k=5,
                where={"level": MemoryLevel.META.value},
            )
            for doc_id, _score, meta in results:
                keywords = meta.get("keywords", [])
                if "adaptive-thresholds" in keywords:
                    await self.evolve(doc_id, content)
                    logger.info("Evolved adaptive-thresholds META memory %s", doc_id[:8])
                    return
        except Exception:
            pass

        # No existing memory found — create a new one
        await self.remember(
            content=content,
            level=MemoryLevel.META,
            context="adaptive promotion thresholds — persisted by meta_learn",
            keywords=["adaptive-thresholds"],
            tags=["auto", "meta", "thresholds"],
        )
        logger.info("Created new adaptive-thresholds META memory")

    def _generate_id(self, content: str, level: MemoryLevel) -> str:
        raw = f"{self.namespace}:{level.value}:{content}:{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
        """Simple keyword extraction based on word frequency."""
        from jmem.vector_store import _tokenize
        tokens = _tokenize(text)
        from collections import Counter
        freq = Counter(tokens)
        return [word for word, _ in freq.most_common(max_keywords)]
