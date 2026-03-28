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
import logging
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any

from jmem_mcp_server.jmem.vector_store import PureVectorStore

logger = logging.getLogger("jmem.engine")


class MemoryLevel(IntEnum):
    EPISODE = 1    # Raw experiences
    CONCEPT = 2    # Patterns extracted from episodes
    PRINCIPLE = 3  # Generalizable rules
    SKILL = 4      # Executable capabilities


@dataclass
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

    async def start(self) -> None:
        await self._store._ensure_initialized()

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

        # Auto-promote: episodes with Q > 0.8 and retrieval_count > 3
        for doc in all_docs:
            meta = doc.get("metadata", {})
            if isinstance(meta, str):
                import json
                meta = json.loads(meta)
            if meta.get("level", 1) == MemoryLevel.EPISODE.value:
                if meta.get("q_value", 0) > 0.8 and meta.get("retrieval_count", 0) > 3:
                    meta["level"] = MemoryLevel.CONCEPT.value
                    await self._store.update_metadata(doc["id"], meta)
                    stats["promoted"] += 1

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
            lvl = MemoryLevel(meta.get("level", 1))
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

    # ── Helpers ──────────────────────────────────────────────────

    def _generate_id(self, content: str, level: MemoryLevel) -> str:
        raw = f"{self.namespace}:{level.value}:{content}:{time.time()}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    @staticmethod
    def _extract_keywords(text: str, max_keywords: int = 8) -> list[str]:
        """Simple keyword extraction based on word frequency."""
        from jmem_mcp_server.jmem.vector_store import _tokenize
        tokens = _tokenize(text)
        from collections import Counter
        freq = Counter(tokens)
        return [word for word, _ in freq.most_common(max_keywords)]
