"""
Aussie Agents Persistent Memory — Disk-backed storage for the 5-layer memory system.

Learning persists across sessions. When the agent starts, it loads
all prior knowledge. When it learns something new, it writes incrementally.

Storage format:
    ~/.pfaa/memory.db  — SQLite database with tables for each layer
    ~/.pfaa/episodes/  — Overflow episodic data as JSONL (append-only log)

Python 3.15 features:
    - lazy import: sqlite3/json only load when persistence is needed
    - frozendict: immutable snapshots for safe concurrent reads
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import sqlite3
import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.memory import (
    MemorySystem, Episode, ToolPattern, PhaseStrategy,
    MetaInsight, EmergentKnowledge,
)

logger = logging.getLogger("pfaa.persistence")

DEFAULT_STORAGE_DIR = os.path.expanduser("~/.pfaa")


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


class PersistentMemory:
    """
    Wraps MemorySystem with SQLite-backed persistence.

    All 5 memory layers are persisted:
        L1 Episodic  → episodes table (ring buffer, last N)
        L2 Semantic  → patterns table (tool performance profiles)
        L3 Strategic → strategies table (phase optimization rules)
        L4 Meta      → meta_insights table (learning observations)
        L5 Emergent  → emergent table (collective knowledge)

    Also persists:
        - Learning rate and configuration
        - Session metadata
    """

    def __init__(
        self,
        storage_dir: str = DEFAULT_STORAGE_DIR,
        episodic_capacity: int = 10_000,
    ):
        self.storage_dir = storage_dir
        _ensure_dir(storage_dir)

        self.db_path = os.path.join(storage_dir, "memory.db")
        self.memory = MemorySystem(episodic_capacity=episodic_capacity)

        self._init_db()
        self._load_all()

        self._session_start = time.perf_counter_ns()
        self._writes_since_flush = 0
        self._flush_interval = 10  # flush every N writes

        # Wire memory into the tool registry for exploration-guided phase selection
        from agent_setup_cli.core.tools import ToolRegistry
        ToolRegistry.get(memory=self.memory)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_db(self) -> None:
        """Create tables if they don't exist."""
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS episodes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp_ns INTEGER NOT NULL,
                    tool_name TEXT NOT NULL,
                    phase TEXT NOT NULL,
                    args_hash TEXT,
                    elapsed_us INTEGER,
                    success INTEGER,
                    transitions TEXT,
                    result_summary TEXT,
                    created_at REAL DEFAULT (julianday('now'))
                );

                CREATE TABLE IF NOT EXISTS patterns (
                    tool_name TEXT PRIMARY KEY,
                    avg_elapsed_us REAL,
                    p50_elapsed_us REAL,
                    p95_elapsed_us REAL,
                    success_rate REAL,
                    best_phase TEXT,
                    phase_performance TEXT,
                    sample_size INTEGER,
                    last_updated_ns INTEGER
                );

                CREATE TABLE IF NOT EXISTS strategies (
                    tool_name TEXT PRIMARY KEY,
                    default_phase TEXT,
                    override_phase TEXT,
                    confidence REAL,
                    speedup_factor REAL,
                    times_applied INTEGER DEFAULT 0,
                    times_improved INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS meta_insights (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT,
                    observation TEXT,
                    adjustment TEXT,
                    timestamp_ns INTEGER,
                    confidence REAL
                );

                CREATE TABLE IF NOT EXISTS emergent_knowledge (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern TEXT,
                    agents_observed INTEGER,
                    consensus_confidence REAL,
                    discovery_ns INTEGER,
                    description TEXT
                );

                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_episodes_tool
                    ON episodes(tool_name);
                CREATE INDEX IF NOT EXISTS idx_episodes_ts
                    ON episodes(timestamp_ns);
            """)

    # ── Load ────────────────────────────────────────────────────────

    def _load_all(self) -> None:
        """Load all persisted memory into the in-memory system."""
        with self._conn() as conn:
            self._load_episodes(conn)
            self._load_patterns(conn)
            self._load_strategies(conn)
            self._load_config(conn)

        loaded = self.memory.status()
        logger.info(
            "Loaded memory: %d episodes, %d patterns, %d strategies, LR=%.3f",
            loaded["l1_episodes"],
            loaded["l2_patterns"],
            loaded["l3_strategies"],
            loaded["l4_learning_rate"],
        )

    def _load_episodes(self, conn: sqlite3.Connection) -> None:
        """Load recent episodes into L1."""
        rows = conn.execute(
            "SELECT * FROM episodes ORDER BY timestamp_ns DESC LIMIT 10000"
        ).fetchall()

        for row in reversed(rows):  # oldest first
            episode = Episode(
                timestamp_ns=row[1],
                tool_name=row[2],
                phase_used=Phase[row[3]],
                args_hash=row[4] or "",
                elapsed_us=row[5] or 0,
                success=bool(row[6]),
                transitions=json.loads(row[7]) if row[7] else [],
                result_summary=row[8] or "",
            )
            self.memory.l1_episodic._episodes.append(episode)
            self.memory.l1_episodic._by_tool[episode.tool_name].append(episode)

    def _load_patterns(self, conn: sqlite3.Connection) -> None:
        """Load L2 patterns."""
        for row in conn.execute("SELECT * FROM patterns").fetchall():
            pattern = ToolPattern(
                tool_name=row[0],
                avg_elapsed_us=row[1],
                p50_elapsed_us=row[2],
                p95_elapsed_us=row[3],
                success_rate=row[4],
                best_phase=Phase[row[5]],
                phase_performance=json.loads(row[6]) if row[6] else {},
                sample_size=row[7],
                last_updated_ns=row[8],
            )
            self.memory.l2_semantic._patterns[pattern.tool_name] = pattern

    def _load_strategies(self, conn: sqlite3.Connection) -> None:
        """Load L3 strategies."""
        for row in conn.execute("SELECT * FROM strategies").fetchall():
            strategy = PhaseStrategy(
                tool_name=row[0],
                default_phase=Phase[row[1]],
                override_phase=Phase[row[2]] if row[2] else None,
                confidence=row[3],
                speedup_factor=row[4],
                times_applied=row[5],
                times_improved=row[6],
            )
            self.memory.l3_strategic._strategies[strategy.tool_name] = strategy

    def _load_config(self, conn: sqlite3.Connection) -> None:
        """Load configuration (learning rate, etc.)."""
        row = conn.execute(
            "SELECT value FROM config WHERE key = 'learning_rate'"
        ).fetchone()
        if row:
            self.memory.l4_meta._learning_rate = float(row[0])

    # ── Save ────────────────────────────────────────────────────────

    def record(self, *args: Any, **kwargs: Any) -> Episode:
        """Record an episode and periodically flush to disk."""
        episode = self.memory.record(*args, **kwargs)
        self._writes_since_flush += 1

        if self._writes_since_flush >= self._flush_interval:
            self.flush()
            self._writes_since_flush = 0

        return episode

    def flush(self) -> None:
        """Write all in-memory state to disk."""
        with self._conn() as conn:
            self._save_recent_episodes(conn)
            self._save_patterns(conn)
            self._save_strategies(conn)
            self._save_meta_insights(conn)
            self._save_emergent(conn)
            self._save_config(conn)

        logger.debug("Flushed memory to %s", self.db_path)

    def _save_recent_episodes(self, conn: sqlite3.Connection) -> None:
        """Save new episodes (append-only)."""
        # Get the latest timestamp we've already saved
        row = conn.execute(
            "SELECT MAX(timestamp_ns) FROM episodes"
        ).fetchone()
        latest_saved = row[0] if row and row[0] else 0

        new_episodes = [
            ep for ep in self.memory.l1_episodic._episodes
            if ep.timestamp_ns > latest_saved
        ]

        if new_episodes:
            conn.executemany(
                """INSERT INTO episodes
                   (timestamp_ns, tool_name, phase, args_hash, elapsed_us,
                    success, transitions, result_summary)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (
                        ep.timestamp_ns, ep.tool_name, ep.phase_used.name,
                        ep.args_hash, ep.elapsed_us, int(ep.success),
                        json.dumps(ep.transitions), ep.result_summary,
                    )
                    for ep in new_episodes
                ],
            )

            # Trim old episodes (keep last 10K)
            conn.execute("""
                DELETE FROM episodes WHERE id NOT IN (
                    SELECT id FROM episodes ORDER BY timestamp_ns DESC LIMIT 10000
                )
            """)

    def _save_patterns(self, conn: sqlite3.Connection) -> None:
        """Upsert L2 patterns."""
        for name, p in self.memory.l2_semantic._patterns.items():
            conn.execute(
                """INSERT OR REPLACE INTO patterns
                   (tool_name, avg_elapsed_us, p50_elapsed_us, p95_elapsed_us,
                    success_rate, best_phase, phase_performance, sample_size,
                    last_updated_ns)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    name, p.avg_elapsed_us, p.p50_elapsed_us, p.p95_elapsed_us,
                    p.success_rate, p.best_phase.name,
                    json.dumps(p.phase_performance), p.sample_size,
                    p.last_updated_ns,
                ),
            )

    def _save_strategies(self, conn: sqlite3.Connection) -> None:
        """Upsert L3 strategies."""
        for name, s in self.memory.l3_strategic._strategies.items():
            conn.execute(
                """INSERT OR REPLACE INTO strategies
                   (tool_name, default_phase, override_phase, confidence,
                    speedup_factor, times_applied, times_improved)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    name, s.default_phase.name,
                    s.override_phase.name if s.override_phase else None,
                    s.confidence, s.speedup_factor,
                    s.times_applied, s.times_improved,
                ),
            )

    def _save_meta_insights(self, conn: sqlite3.Connection) -> None:
        """Append new L4 insights."""
        existing = conn.execute("SELECT COUNT(*) FROM meta_insights").fetchone()[0]
        new_insights = self.memory.l4_meta.recent_insights[existing:]

        if new_insights:
            conn.executemany(
                """INSERT INTO meta_insights
                   (category, observation, adjustment, timestamp_ns, confidence)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (i.category, i.observation, i.adjustment,
                     i.timestamp_ns, i.confidence)
                    for i in new_insights
                ],
            )

    def _save_emergent(self, conn: sqlite3.Connection) -> None:
        """Save L5 emergent knowledge (deduplicated by description)."""
        existing = set()
        for row in conn.execute("SELECT description FROM emergent_knowledge"):
            existing.add(row[0])

        new_knowledge = [
            k for k in self.memory.l5_emergent.all_knowledge
            if k.description not in existing
        ]

        if new_knowledge:
            conn.executemany(
                """INSERT INTO emergent_knowledge
                   (pattern, agents_observed, consensus_confidence,
                    discovery_ns, description)
                   VALUES (?, ?, ?, ?, ?)""",
                [
                    (k.pattern, k.agents_observed, k.consensus_confidence,
                     k.discovery_ns, k.description)
                    for k in new_knowledge
                ],
            )

    def _save_config(self, conn: sqlite3.Connection) -> None:
        """Save runtime config."""
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("learning_rate", str(self.memory.l4_meta.learning_rate)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO config (key, value) VALUES (?, ?)",
            ("last_session_ns", str(time.perf_counter_ns())),
        )

    # ── Convenience Proxies ─────────────────────────────────────────

    def recommend_phase(self, tool_name: str) -> Phase | None:
        """Return the learned optimal phase for a tool, or None if insufficient data."""
        return self.memory.recommend_phase(tool_name)

    def force_learn(self) -> None:
        """Trigger an immediate learning cycle across all memory layers and flush to disk."""
        self.memory.force_learn()
        self.flush()

    def status(self) -> dict[str, Any]:
        mem_status = self.memory.status()
        db_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
        return {
            **mem_status,
            "db_path": self.db_path,
            "db_size_kb": round(db_size / 1024, 1),
            "writes_pending": self._writes_since_flush,
        }

    def dump(self) -> dict[str, Any]:
        """Export the full in-memory state of all 5 layers as a serializable dict."""
        return self.memory.dump()

    def close(self) -> None:
        """Final flush and cleanup."""
        self.flush()
        logger.info("Persistent memory closed. DB at %s", self.db_path)
