"""
JMEM Engine — 5-layer cognitive memory architecture.

Implements the full JMEM cognitive loop:
    Phase 1 ENCODE:       Store memories with composite TF-IDF vectors
    Phase 2 CONSOLIDATE:  Zettelkasten linking, auto-promotion, keyword
                          clustering, orphan repair, decay, concept synthesis
    Phase 3 REFLECT:      Health assessment, maturity analysis, stats

Uses reinforcement learning (Q-values) to surface high-value memories and
decay stale ones.  Graph-walk augmentation on recall follows Zettelkasten
links for 1-hop traversal and re-ranking.

Python 3.12+ — match/case, dataclass(slots=True), type aliases, walrus.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from jmem.vector_store import PureVectorStore

if TYPE_CHECKING:
    from jmem._stubs import ClaudeBridge

logger = logging.getLogger("jmem.engine")

# ── Type aliases ────────────────────────────────────────────────────
NoteID: type = str
Score: type = float
TagSet: type = set[str]


# ═══════════════════════════════════════════════════════════════════
#  MemoryLevel
# ═══════════════════════════════════════════════════════════════════

class MemoryLevel(str, Enum):
    """Cognitive hierarchy — memories promote upward through the stack."""
    EPISODE   = "episode"
    CONCEPT   = "concept"
    PRINCIPLE = "principle"
    SKILL     = "skill"

    @property
    def promotion_target(self) -> MemoryLevel | None:
        """Return the next level in the hierarchy, or None at the top."""
        match self:
            case MemoryLevel.EPISODE:
                return MemoryLevel.CONCEPT
            case MemoryLevel.CONCEPT:
                return MemoryLevel.PRINCIPLE
            case MemoryLevel.PRINCIPLE:
                return MemoryLevel.SKILL
            case MemoryLevel.SKILL:
                return None


# ═══════════════════════════════════════════════════════════════════
#  MemoryNote
# ═══════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class MemoryNote:
    """Single memory unit in the JMEM cognitive architecture."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    content: str = ""
    context: str = ""
    keywords: list[str] = field(default_factory=list)
    tags: set[str] = field(default_factory=set)
    level: MemoryLevel = MemoryLevel.EPISODE
    links: list[str] = field(default_factory=list)
    q_value: float = 0.5
    reward_history: list[float] = field(default_factory=list)
    evolution_count: int = 0
    evolution_history: list[str] = field(default_factory=list)
    retrieval_count: int = 0
    last_accessed: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)
    source: str = ""
    area: str = ""

    # ── Composite text with level-aware keyword boosting ─────────

    def composite_text(self) -> str:
        """Build searchable text with keyword repetition scaled by level.

        Higher-level memories get heavier keyword boosting so they
        surface more readily in TF-IDF search.
        """
        match self.level:
            case MemoryLevel.EPISODE:
                boost = 1
            case MemoryLevel.CONCEPT:
                boost = 2
            case MemoryLevel.PRINCIPLE:
                boost = 3
            case MemoryLevel.SKILL:
                boost = 4

        keyword_block = (" ".join(self.keywords) + " ") * boost if self.keywords else ""
        parts = [
            self.content,
            self.context,
            keyword_block.strip(),
            " ".join(sorted(self.tags)),
        ]
        return " ".join(p for p in parts if p)

    # ── Serialisation helpers ────────────────────────────────────

    def to_metadata(self) -> dict[str, Any]:
        """Flatten to a metadata dict suitable for the vector store."""
        return {
            "id": self.id,
            "content": self.content,
            "context": self.context,
            "keywords": ",".join(self.keywords),
            "tags": ",".join(sorted(self.tags)),
            "level": self.level.value,
            "links": ",".join(self.links),
            "q_value": self.q_value,
            "reward_history": ",".join(str(r) for r in self.reward_history),
            "evolution_count": self.evolution_count,
            "evolution_history": ",".join(self.evolution_history),
            "retrieval_count": self.retrieval_count,
            "last_accessed": self.last_accessed,
            "created_at": self.created_at,
            "source": self.source,
            "area": self.area,
        }

    @classmethod
    def from_metadata(cls, meta: dict[str, Any]) -> MemoryNote:
        """Reconstruct a MemoryNote from a vector-store metadata dict."""
        def _split(v: str) -> list[str]:
            return [x for x in v.split(",") if x] if v else []

        return cls(
            id=meta.get("id", uuid.uuid4().hex[:12]),
            content=meta.get("content", ""),
            context=meta.get("context", ""),
            keywords=_split(meta.get("keywords", "")),
            tags=set(_split(meta.get("tags", ""))),
            level=MemoryLevel(meta.get("level", "episode")),
            links=_split(meta.get("links", "")),
            q_value=float(meta.get("q_value", 0.5)),
            reward_history=[float(r) for r in _split(meta.get("reward_history", ""))],
            evolution_count=int(meta.get("evolution_count", 0)),
            evolution_history=_split(meta.get("evolution_history", "")),
            retrieval_count=int(meta.get("retrieval_count", 0)),
            last_accessed=float(meta.get("last_accessed", 0)),
            created_at=float(meta.get("created_at", 0)),
            source=meta.get("source", ""),
            area=meta.get("area", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """Full dictionary representation (for JSON export)."""
        return {
            "id": self.id,
            "content": self.content,
            "context": self.context,
            "keywords": self.keywords,
            "tags": sorted(self.tags),
            "level": self.level.value,
            "links": self.links,
            "q_value": self.q_value,
            "reward_history": self.reward_history,
            "evolution_count": self.evolution_count,
            "evolution_history": self.evolution_history,
            "retrieval_count": self.retrieval_count,
            "last_accessed": self.last_accessed,
            "created_at": self.created_at,
            "source": self.source,
            "area": self.area,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> MemoryNote:
        """Reconstruct from a full dict (JSON import)."""
        return cls(
            id=d.get("id", uuid.uuid4().hex[:12]),
            content=d.get("content", ""),
            context=d.get("context", ""),
            keywords=d.get("keywords", []),
            tags=set(d.get("tags", [])),
            level=MemoryLevel(d.get("level", "episode")),
            links=d.get("links", []),
            q_value=float(d.get("q_value", 0.5)),
            reward_history=d.get("reward_history", []),
            evolution_count=int(d.get("evolution_count", 0)),
            evolution_history=d.get("evolution_history", []),
            retrieval_count=int(d.get("retrieval_count", 0)),
            last_accessed=float(d.get("last_accessed", 0)),
            created_at=float(d.get("created_at", 0)),
            source=d.get("source", ""),
            area=d.get("area", ""),
        )


# ═══════════════════════════════════════════════════════════════════
#  RLScorer — reinforcement learning for memory Q-values
# ═══════════════════════════════════════════════════════════════════

class RLScorer:
    """Adaptive Q-learning scorer for memory reinforcement.

    Uses variable learning rate:
        - Strong signals (reward > 0.85 or < 0.15): alpha = 0.50
        - Weak / ambiguous signals:                 alpha = 0.15
    """

    __slots__ = ()

    @staticmethod
    def _alpha(reward: float) -> float:
        """Select learning rate based on signal strength."""
        match reward:
            case r if r > 0.85 or r < 0.15:
                return 0.50
            case _:
                return 0.15

    @staticmethod
    def record_reward(note: MemoryNote, reward: float) -> float:
        """Apply a reward signal and update the Q-value.

        Returns the new Q-value (clamped to [0.01, 0.99]).
        """
        alpha = RLScorer._alpha(reward)
        old_q = note.q_value
        new_q = old_q + alpha * (reward - old_q)
        note.q_value = max(0.01, min(0.99, new_q))
        note.reward_history.append(round(reward, 4))
        # Keep reward history bounded
        if len(note.reward_history) > 50:
            note.reward_history = note.reward_history[-50:]
        return note.q_value

    @staticmethod
    def decay_unused(note: MemoryNote, hours_since_access: float) -> float:
        """Apply time-based decay, aggressive for never-retrieved memories.

        Returns the new Q-value after decay.
        """
        match note.retrieval_count:
            case 0:
                # Never retrieved — aggressive decay
                decay_rate = 0.05
            case n if n < 3:
                decay_rate = 0.02
            case _:
                decay_rate = 0.005

        # Decay scales with time since last access
        periods = hours_since_access / 24.0  # per-day decay
        decay = decay_rate * periods
        note.q_value = max(0.01, note.q_value - decay)
        return note.q_value


# ═══════════════════════════════════════════════════════════════════
#  CognitiveLoop — encode / consolidate / reflect
# ═══════════════════════════════════════════════════════════════════

class CognitiveLoop:
    """Three-phase cognitive memory loop.

    Phase 1 — ENCODE:       Persist new memories with composite TF-IDF.
    Phase 2 — CONSOLIDATE:  Link, promote, cluster, repair, decay, synthesise.
    Phase 3 — REFLECT:      Health stats, maturity assessment.
    """

    __slots__ = ("_store", "_scorer", "_bridge")

    def __init__(
        self,
        store: PureVectorStore,
        scorer: RLScorer,
        bridge: ClaudeBridge | None = None,
    ) -> None:
        self._store = store
        self._scorer = scorer
        self._bridge = bridge

    # ── Phase 1: ENCODE ──────────────────────────────────────────

    async def encode(self, note: MemoryNote) -> str:
        """Store a memory with its composite TF-IDF text."""
        composite = note.composite_text()
        await self._store.upsert(note.id, composite, note.to_metadata())
        logger.info("ENCODE  [%s] %s — level=%s q=%.2f",
                     note.id, note.content[:60], note.level.value, note.q_value)
        return note.id

    # ── Phase 2: CONSOLIDATE ─────────────────────────────────────

    async def consolidate(self) -> dict[str, Any]:
        """Run all consolidation sub-phases in parallel where possible."""
        all_docs = await self._store.get_all()
        notes = [MemoryNote.from_metadata(d["metadata"]) for d in all_docs]

        if not notes:
            return {"status": "empty", "total": 0}

        stats: dict[str, Any] = {"total": len(notes)}

        # Parallel consolidation tasks via TaskGroup
        async with asyncio.TaskGroup() as tg:
            link_task = tg.create_task(self._zettelkasten_link(notes))
            promote_task = tg.create_task(self._auto_promote(notes))
            cluster_task = tg.create_task(self._keyword_cluster(notes))
            orphan_task = tg.create_task(self._orphan_repair(notes))
            decay_task = tg.create_task(self._decay_pass(notes))

        stats["links_created"] = link_task.result()
        stats["promotions"] = promote_task.result()
        stats["clusters"] = cluster_task.result()
        stats["orphans_repaired"] = orphan_task.result()
        stats["decayed"] = decay_task.result()

        # Concept synthesis (depends on updated notes, runs after parallel phase)
        stats["synthesised"] = await self._concept_synthesis(notes)

        # Persist all updated notes
        for note in notes:
            await self._store.upsert(note.id, note.composite_text(), note.to_metadata())

        # Optional LLM principle extraction
        if self._bridge and (extracted := await self._extract_principles(notes)):
            stats["principles_extracted"] = extracted

        logger.info("CONSOLIDATE complete — %s", stats)
        return stats

    async def _zettelkasten_link(self, notes: list[MemoryNote]) -> int:
        """Create bidirectional links between related memories."""
        created = 0
        for i, a in enumerate(notes):
            for b in notes[i + 1:]:
                overlap = set(a.keywords) & set(b.keywords)
                if len(overlap) >= 2 and b.id not in a.links:
                    a.links.append(b.id)
                    b.links.append(a.id)
                    created += 1
        return created

    async def _auto_promote(self, notes: list[MemoryNote]) -> int:
        """Promote memories that have earned enough retrievals and Q-value."""
        promotions = 0
        for note in notes:
            if (target := note.level.promotion_target) is None:
                continue
            # Promotion thresholds scale with level
            match note.level:
                case MemoryLevel.EPISODE:
                    min_retrievals, min_q = 3, 0.65
                case MemoryLevel.CONCEPT:
                    min_retrievals, min_q = 5, 0.75
                case MemoryLevel.PRINCIPLE:
                    min_retrievals, min_q = 8, 0.85
                case _:
                    continue

            if note.retrieval_count >= min_retrievals and note.q_value >= min_q:
                old_level = note.level
                note.level = target
                note.evolution_count += 1
                note.evolution_history.append(
                    f"{old_level.value}->{target.value}@{time.time():.0f}"
                )
                promotions += 1
                logger.info("PROMOTE [%s] %s -> %s (q=%.2f, retrievals=%d)",
                            note.id, old_level.value, target.value,
                            note.q_value, note.retrieval_count)
        return promotions

    async def _keyword_cluster(self, notes: list[MemoryNote]) -> int:
        """Cross-pollinate keywords among tightly-linked memory groups."""
        clusters = 0
        for note in notes:
            if len(note.links) < 2:
                continue
            linked = [n for n in notes if n.id in note.links]
            if not linked:
                continue
            # Collect frequent keywords from the cluster
            kw_counts: Counter[str] = Counter()
            for ln in linked:
                kw_counts.update(ln.keywords)
            # Inject common keywords the note is missing
            common = [kw for kw, cnt in kw_counts.items() if cnt >= 2]
            added = False
            for kw in common:
                if kw not in note.keywords:
                    note.keywords.append(kw)
                    added = True
            if added:
                clusters += 1
        return clusters

    async def _orphan_repair(self, notes: list[MemoryNote]) -> int:
        """Find orphan notes (no links) and attempt to connect them."""
        repaired = 0
        orphans = [n for n in notes if not n.links]
        linked_notes = [n for n in notes if n.links]
        for orphan in orphans:
            best_overlap = 0
            best_match: MemoryNote | None = None
            for candidate in linked_notes:
                if overlap := len(set(orphan.keywords) & set(candidate.keywords)):
                    if overlap > best_overlap:
                        best_overlap = overlap
                        best_match = candidate
            if best_match and best_overlap >= 1:
                orphan.links.append(best_match.id)
                best_match.links.append(orphan.id)
                repaired += 1
        return repaired

    async def _decay_pass(self, notes: list[MemoryNote]) -> int:
        """Apply time-based decay to all memories."""
        now = time.time()
        decayed = 0
        for note in notes:
            hours = (now - note.last_accessed) / 3600.0
            if hours > 1.0:
                old_q = note.q_value
                self._scorer.decay_unused(note, hours)
                if note.q_value < old_q:
                    decayed += 1
        return decayed

    async def _concept_synthesis(self, notes: list[MemoryNote]) -> int:
        """Merge highly-related episodes into new concept notes."""
        episodes = [n for n in notes if n.level == MemoryLevel.EPISODE]
        if len(episodes) < 3:
            return 0

        synthesised = 0
        # Group episodes by shared keyword pairs
        pair_groups: dict[tuple[str, str], list[MemoryNote]] = {}
        for ep in episodes:
            kws = sorted(set(ep.keywords))
            for i, a in enumerate(kws):
                for b in kws[i + 1:]:
                    pair_groups.setdefault((a, b), []).append(ep)

        for (kw_a, kw_b), group in pair_groups.items():
            if len(group) < 3:
                continue
            # Create a synthetic concept from the cluster
            concept_id = hashlib.sha256(
                f"{kw_a}:{kw_b}:{len(notes)}".encode()
            ).hexdigest()[:12]
            # Skip if we already synthesised this concept
            if any(n.id == concept_id for n in notes):
                continue
            concept = MemoryNote(
                id=concept_id,
                content=f"Synthesised concept: {kw_a} + {kw_b} (from {len(group)} episodes)",
                context="auto-synthesised during consolidation",
                keywords=[kw_a, kw_b],
                tags={"synthesised", "concept"},
                level=MemoryLevel.CONCEPT,
                links=[ep.id for ep in group[:5]],
                q_value=0.55,
                source="consolidation",
            )
            notes.append(concept)
            # Back-link the source episodes
            for ep in group[:5]:
                if concept_id not in ep.links:
                    ep.links.append(concept_id)
            synthesised += 1
            if synthesised >= 5:
                break  # cap synthesis per pass
        return synthesised

    async def _extract_principles(self, notes: list[MemoryNote]) -> int:
        """Use LLM (ClaudeBridge) to extract principles from mature concepts."""
        if not self._bridge:
            return 0
        concepts = [
            n for n in notes
            if n.level == MemoryLevel.CONCEPT and n.q_value >= 0.7 and n.retrieval_count >= 3
        ]
        if not concepts:
            return 0

        extracted = 0
        for concept in concepts[:3]:
            prompt = (
                f"Given this concept memory, extract a concise principle or rule:\n"
                f"Content: {concept.content}\n"
                f"Keywords: {', '.join(concept.keywords)}\n"
                f"Retrieved {concept.retrieval_count} times, Q-value {concept.q_value:.2f}.\n"
                f"Respond with ONLY the principle statement."
            )
            response = await self._bridge.ask(prompt)
            if response.success and response.output.strip():
                principle = MemoryNote(
                    content=response.output.strip(),
                    context=f"extracted from concept {concept.id}",
                    keywords=concept.keywords.copy(),
                    tags=concept.tags | {"llm-extracted"},
                    level=MemoryLevel.PRINCIPLE,
                    links=[concept.id],
                    q_value=0.6,
                    source="llm-extraction",
                )
                notes.append(principle)
                concept.links.append(principle.id)
                extracted += 1
        return extracted

    # ── Phase 3: REFLECT ─────────────────────────────────────────

    async def reflect(self) -> dict[str, Any]:
        """Produce a health and maturity report for the memory system."""
        all_docs = await self._store.get_all()
        notes = [MemoryNote.from_metadata(d["metadata"]) for d in all_docs]
        total = len(notes)

        if total == 0:
            return {
                "total": 0,
                "health": "critical",
                "maturity": "episodes_only",
                "levels": {},
            }

        # Level breakdown
        level_counts: dict[str, int] = Counter()
        total_q = 0.0
        total_retrievals = 0
        orphan_count = 0
        link_count = 0

        for note in notes:
            level_counts[note.level.value] += 1
            total_q += note.q_value
            total_retrievals += note.retrieval_count
            if not note.links:
                orphan_count += 1
            link_count += len(note.links)

        avg_q = total_q / total
        avg_retrievals = total_retrievals / total
        orphan_ratio = orphan_count / total

        # Health assessment via match/case on thresholds
        match (avg_q, orphan_ratio):
            case (q, o) if q >= 0.65 and o < 0.2:
                health = "excellent"
            case (q, o) if q >= 0.50 and o < 0.4:
                health = "healthy"
            case (q, o) if q >= 0.35 and o < 0.6:
                health = "needs_attention"
            case _:
                health = "critical"

        # Maturity assessment based on level distribution
        has_skills = level_counts.get("skill", 0) > 0
        has_principles = level_counts.get("principle", 0) > 0
        has_concepts = level_counts.get("concept", 0) > 0

        match (has_skills, has_principles, has_concepts):
            case (True, True, True):
                maturity = "full_hierarchy"
            case (False, True, True):
                maturity = "concepts_and_principles"
            case (False, False, True):
                maturity = "concepts_emerging"
            case _:
                maturity = "episodes_only"

        return {
            "total": total,
            "health": health,
            "maturity": maturity,
            "levels": dict(level_counts),
            "avg_q_value": round(avg_q, 3),
            "avg_retrievals": round(avg_retrievals, 2),
            "orphan_ratio": round(orphan_ratio, 3),
            "total_links": link_count,
        }


# ═══════════════════════════════════════════════════════════════════
#  JMemEngine — main entry point (singleton)
# ═══════════════════════════════════════════════════════════════════

class JMemEngine:
    """Top-level JMEM engine with singleton access.

    Usage::

        async with JMemEngine.get() as engine:
            await engine.remember("learned X about Y", context="project Z")
            results = await engine.recall("X and Y")
    """

    _instance: JMemEngine | None = None

    __slots__ = ("_store", "_scorer", "_loop", "_bridge", "_initialized")

    def __init__(self, db_path: str | None = None) -> None:
        self._store = PureVectorStore(db_path)
        self._scorer = RLScorer()
        self._bridge: ClaudeBridge | None = None
        self._loop = CognitiveLoop(self._store, self._scorer, self._bridge)
        self._initialized = False

    # ── Singleton ────────────────────────────────────────────────

    @classmethod
    def get(cls, db_path: str | None = None) -> JMemEngine:
        """Return the singleton engine instance (create if needed)."""
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Destroy the singleton (for testing)."""
        cls._instance = None

    # ── Async context manager ────────────────────────────────────

    async def __aenter__(self) -> JMemEngine:
        await self._store._ensure_initialized()
        self._initialized = True

        # Try to load real ClaudeBridge, fall back to stub
        try:
            from jmem._stubs import ClaudeBridge as Bridge
            self._bridge = Bridge()
            self._loop._bridge = self._bridge
        except Exception:
            pass

        logger.info("JMemEngine ready (store=%s)", self._store._db_path)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        await self._store.close()
        self._initialized = False
        logger.info("JMemEngine closed")

    # ── remember ─────────────────────────────────────────────────

    async def remember(
        self,
        content: str,
        *,
        context: str = "",
        keywords: list[str] | None = None,
        tags: set[str] | None = None,
        level: MemoryLevel = MemoryLevel.EPISODE,
        source: str = "",
        area: str = "",
    ) -> MemoryNote:
        """Encode a new memory into the store."""
        note = MemoryNote(
            content=content,
            context=context,
            keywords=keywords or [],
            tags=tags or set(),
            level=level,
            source=source,
            area=area,
        )
        await self._loop.encode(note)
        return note

    # ── recall ───────────────────────────────────────────────────

    async def recall(
        self,
        query: str,
        *,
        top_k: int = 5,
        level: MemoryLevel | None = None,
    ) -> list[MemoryNote]:
        """Retrieve memories via direct search + graph-walk augmentation.

        Pipeline:
            1. Direct TF-IDF + BM25 search
            2. Graph walk — follow 1-hop Zettelkasten links from top results
            3. Re-rank the combined set by composite score
            4. Update retrieval stats + Q-value recall boost
        """
        # Phase 1: direct search
        where = {"level": level.value} if level else None
        raw_results = await self._store.search(query, top_k=top_k * 2, where=where)

        if not raw_results:
            return []

        # Build note map from direct results
        seen: dict[str, tuple[MemoryNote, float]] = {}
        for doc_id, score, meta in raw_results:
            note = MemoryNote.from_metadata(meta)
            seen[doc_id] = (note, score)

        # Phase 2: graph walk — 1-hop link traversal
        link_ids: set[str] = set()
        for note, _ in list(seen.values()):
            for linked_id in note.links:
                if linked_id not in seen:
                    link_ids.add(linked_id)

        for linked_id in link_ids:
            if doc := await self._store.get(linked_id):
                linked_note = MemoryNote.from_metadata(doc["metadata"])
                # Graph-walked results get a reduced score
                seen[linked_id] = (linked_note, 0.3)

        # Phase 3: re-rank — combine search score with Q-value
        ranked: list[tuple[MemoryNote, float]] = []
        for note, base_score in seen.values():
            final_score = 0.7 * base_score + 0.3 * note.q_value
            ranked.append((note, final_score))

        ranked.sort(key=lambda x: x[1], reverse=True)
        top_notes = [note for note, _ in ranked[:top_k]]

        # Phase 4: update retrieval stats + recall Q-boost
        now = time.time()
        for note in top_notes:
            note.retrieval_count += 1
            note.last_accessed = now
            # Small positive reward for being recalled
            self._scorer.record_reward(note, 0.6)
            await self._store.update_metadata(note.id, note.to_metadata())

        return top_notes

    # ── evolve ───────────────────────────────────────────────────

    async def evolve(
        self,
        note_id: str,
        new_content: str,
        *,
        new_keywords: list[str] | None = None,
    ) -> MemoryNote | None:
        """Update a memory's content (evolution), preserving lineage."""
        if not (doc := await self._store.get(note_id)):
            logger.warning("evolve: note %s not found", note_id)
            return None

        note = MemoryNote.from_metadata(doc["metadata"])
        note.evolution_count += 1
        note.evolution_history.append(f"evolved@{time.time():.0f}")
        note.content = new_content
        if new_keywords:
            note.keywords = list(set(note.keywords) | set(new_keywords))
        note.last_accessed = time.time()

        await self._store.upsert(note.id, note.composite_text(), note.to_metadata())
        logger.info("EVOLVE  [%s] v%d — %s", note.id, note.evolution_count, new_content[:60])
        return note

    # ── reward ───────────────────────────────────────────────────

    async def reward(self, note_id: str, reward: float) -> float | None:
        """Apply an explicit reward signal to a memory."""
        if not (doc := await self._store.get(note_id)):
            logger.warning("reward: note %s not found", note_id)
            return None

        note = MemoryNote.from_metadata(doc["metadata"])
        new_q = self._scorer.record_reward(note, reward)
        await self._store.update_metadata(note.id, note.to_metadata())
        logger.info("REWARD  [%s] reward=%.2f -> q=%.3f", note_id, reward, new_q)
        return new_q

    # ── reflect ──────────────────────────────────────────────────

    async def reflect(self) -> dict[str, Any]:
        """Run Phase 3 REFLECT — health and maturity analysis."""
        return await self._loop.reflect()

    # ── consolidate ──────────────────────────────────────────────

    async def consolidate(self) -> dict[str, Any]:
        """Run Phase 2 CONSOLIDATE — linking, promotion, decay, synthesis."""
        return await self._loop.consolidate()

    # ── PFAA integration ─────────────────────────────────────────

    async def record_tool_execution(
        self,
        tool_name: str,
        *,
        input_summary: str = "",
        output_summary: str = "",
        success: bool = True,
        execution_time_ms: float = 0,
    ) -> MemoryNote:
        """Record a tool execution as an episode memory for PFAA integration."""
        content = f"Tool '{tool_name}': {input_summary}"
        if output_summary:
            content += f" -> {output_summary}"

        tags = {"tool-execution", tool_name}
        if not success:
            tags.add("failed")

        note = await self.remember(
            content=content,
            context=f"execution_time={execution_time_ms:.0f}ms success={success}",
            keywords=[tool_name, "tool-execution"],
            tags=tags,
            source="pfaa",
            area="tool-execution",
        )

        # Reward based on outcome
        reward_val = 0.7 if success else 0.2
        self._scorer.record_reward(note, reward_val)
        await self._store.update_metadata(note.id, note.to_metadata())

        return note

    # ── status ───────────────────────────────────────────────────

    async def status(self) -> dict[str, Any]:
        """Return combined engine + store status."""
        store_status = await self._store.status()
        reflection = await self._loop.reflect()
        return {
            "engine": "JMemEngine",
            "initialized": self._initialized,
            "store": store_status,
            "memory": reflection,
        }
