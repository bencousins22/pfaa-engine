"""
PureVectorStore — SQLite FTS5 + TF-IDF cosine similarity.

Zero external dependencies. Pure Python 3.12+ stdlib.
Replaces ChromaDB/Qdrant with a single SQLite database file.

Architecture:
    - SQLite FTS5 for full-text BM25 ranking
    - TF-IDF vectors computed in pure Python (math stdlib only)
    - Cosine similarity for semantic search
    - Q-value boosting on retrieval
    - WAL mode for concurrent reads

Storage: ~/.jmem/jmem_vectors.db
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import sqlite3
import time
from collections import Counter
from typing import Any

logger = logging.getLogger("jmem.vector_store")


class PureVectorStore:
    """
    Pure-Python vector store with TF-IDF + BM25 hybrid search.

    No numpy, no sentence-transformers, no external dependencies.
    Uses SQLite FTS5 for indexing and pure-Python TF-IDF for ranking.
    """

    __slots__ = ("_db_path", "_conn", "_initialized", "_idf_cache",
                 "_doc_count_cache", "_cache_ts")

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or os.path.join(
            os.path.expanduser("~/.jmem"), "jmem_vectors.db"
        )
        self._conn: sqlite3.Connection | None = None
        self._initialized = False
        self._idf_cache: dict[str, float] = {}
        self._doc_count_cache = 0
        self._cache_ts = 0.0

    @property
    def is_available(self) -> bool:
        return self._initialized

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        await asyncio.to_thread(self._init_sync)
        self._initialized = True

    def _init_sync(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                tfidf_vector TEXT NOT NULL DEFAULT '{}',
                created_at REAL NOT NULL DEFAULT 0
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                id, text, content=documents, content_rowid=rowid,
                tokenize='porter unicode61'
            );
            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, id, text) VALUES (new.rowid, new.id, new.text);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, id, text)
                VALUES('delete', old.rowid, old.id, old.text);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, id, text)
                VALUES('delete', old.rowid, old.id, old.text);
                INSERT INTO documents_fts(rowid, id, text) VALUES (new.rowid, new.id, new.text);
            END;
            CREATE INDEX IF NOT EXISTS idx_documents_created ON documents(created_at);
        """)

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Store not initialized — call _ensure_initialized() first")
        return self._conn

    # ── Tokenization ─────────────────────────────────────────────

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """Simple whitespace + punctuation tokenizer with lowering."""
        return [w for w in re.findall(r'[a-z0-9_]+', text.lower()) if len(w) > 1]

    # ── TF-IDF ───────────────────────────────────────────────────

    def _compute_tf(self, tokens: list[str]) -> dict[str, float]:
        """Term frequency with sublinear scaling: 1 + log(count)."""
        counts = Counter(tokens)
        n = len(tokens) or 1
        return {
            term: (1 + math.log(count)) / n
            for term, count in counts.items()
        }

    def _refresh_idf_cache(self) -> None:
        """Rebuild IDF cache from all documents (cached for 60s)."""
        now = time.time()
        if now - self._cache_ts < 60 and self._idf_cache:
            return

        conn = self._get_conn()
        rows = conn.execute("SELECT text FROM documents").fetchall()
        self._doc_count_cache = len(rows)
        if self._doc_count_cache == 0:
            self._idf_cache = {}
            self._cache_ts = now
            return

        df: Counter[str] = Counter()
        for (text,) in rows:
            tokens = set(self._tokenize(text))
            for t in tokens:
                df[t] += 1

        n = self._doc_count_cache
        self._idf_cache = {
            term: math.log((n + 1) / (count + 1)) + 1
            for term, count in df.items()
        }
        self._cache_ts = now

    def _compute_tfidf(self, text: str) -> dict[str, float]:
        """Compute TF-IDF vector for a text."""
        self._refresh_idf_cache()
        tokens = self._tokenize(text)
        tf = self._compute_tf(tokens)
        return {
            term: tf_val * self._idf_cache.get(term, 1.0)
            for term, tf_val in tf.items()
        }

    @staticmethod
    def _cosine_similarity(v1: dict[str, float], v2: dict[str, float]) -> float:
        """Cosine similarity between two sparse TF-IDF vectors."""
        common = set(v1) & set(v2)
        if not common:
            return 0.0
        dot = sum(v1[k] * v2[k] for k in common)
        norm1 = math.sqrt(sum(v * v for v in v1.values()))
        norm2 = math.sqrt(sum(v * v for v in v2.values()))
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    # ── CRUD ─────────────────────────────────────────────────────

    async def upsert(self, doc_id: str, text: str, metadata: dict[str, Any]) -> None:
        """Insert or update a document."""
        await self._ensure_initialized()

        def _do():
            conn = self._get_conn()
            tfidf = self._compute_tfidf(text)
            conn.execute(
                """INSERT OR REPLACE INTO documents (id, text, metadata, tfidf_vector, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (doc_id, text, json.dumps(metadata, default=str),
                 json.dumps(tfidf), metadata.get("created_at", time.time())),
            )
            conn.commit()
            # Invalidate cache since doc count changed
            self._cache_ts = 0

        await asyncio.to_thread(_do)

    async def get(self, doc_id: str) -> dict[str, Any] | None:
        """Get a single document by ID."""
        await self._ensure_initialized()

        def _do():
            conn = self._get_conn()
            row = conn.execute(
                "SELECT id, text, metadata FROM documents WHERE id = ?", (doc_id,)
            ).fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "text": row[1],
                "metadata": json.loads(row[2]),
            }

        return await asyncio.to_thread(_do)

    async def get_all(self) -> list[dict[str, Any]]:
        """Get all documents."""
        await self._ensure_initialized()

        def _do():
            conn = self._get_conn()
            rows = conn.execute("SELECT id, text, metadata FROM documents").fetchall()
            return [
                {"id": r[0], "text": r[1], "metadata": json.loads(r[2])}
                for r in rows
            ]

        return await asyncio.to_thread(_do)

    async def delete(self, doc_id: str) -> bool:
        """Delete a document."""
        await self._ensure_initialized()

        def _do():
            conn = self._get_conn()
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            conn.commit()
            self._cache_ts = 0
            return True

        return await asyncio.to_thread(_do)

    async def update_metadata(self, doc_id: str, metadata: dict[str, Any]) -> None:
        """Update just the metadata of a document."""
        await self._ensure_initialized()

        def _do():
            conn = self._get_conn()
            conn.execute(
                "UPDATE documents SET metadata = ? WHERE id = ?",
                (json.dumps(metadata, default=str), doc_id),
            )
            conn.commit()

        await asyncio.to_thread(_do)

    # ── Search ───────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        top_k: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        """
        Triple-hybrid search: BM25 + TF-IDF cosine + Q-value boost.

        1. BM25 via FTS5 (fast initial filtering)
        2. TF-IDF cosine similarity (semantic ranking)
        3. Q-value boost (reinforcement learning signal)

        Final score = 0.4 * cosine + 0.4 * bm25_norm + 0.2 * q_value
        """
        await self._ensure_initialized()

        def _do():
            conn = self._get_conn()
            query_vec = self._compute_tfidf(query)

            # Phase 1: BM25 candidates from FTS5 (fast, broad)
            safe_query = " OR ".join(
                f'"{t}"' for t in self._tokenize(query) if t
            )
            bm25_results: dict[str, float] = {}
            if safe_query:
                try:
                    rows = conn.execute(
                        """SELECT id, rank FROM documents_fts
                           WHERE documents_fts MATCH ? ORDER BY rank LIMIT ?""",
                        (safe_query, top_k * 5),
                    ).fetchall()
                    # FTS5 rank is negative (more negative = better match)
                    if rows:
                        max_rank = max(abs(r[1]) for r in rows) or 1
                        bm25_results = {
                            r[0]: abs(r[1]) / max_rank for r in rows
                        }
                except sqlite3.OperationalError:
                    pass  # empty FTS table

            # Phase 2: Get all candidate docs
            if bm25_results:
                placeholders = ",".join("?" * len(bm25_results))
                candidate_rows = conn.execute(
                    f"SELECT id, text, metadata, tfidf_vector FROM documents WHERE id IN ({placeholders})",
                    list(bm25_results.keys()),
                ).fetchall()
            else:
                # Fallback: scan all docs if FTS returned nothing
                candidate_rows = conn.execute(
                    "SELECT id, text, metadata, tfidf_vector FROM documents"
                ).fetchall()

            # Phase 3: Score each candidate
            scored: list[tuple[str, float, dict[str, Any]]] = []
            for row in candidate_rows:
                doc_id, text, meta_json, vec_json = row
                meta = json.loads(meta_json)

                # Apply metadata filters
                if where:
                    skip = False
                    for k, v in where.items():
                        if meta.get(k) != v:
                            skip = True
                            break
                    if skip:
                        continue

                # TF-IDF cosine
                doc_vec = json.loads(vec_json) if vec_json else {}
                cosine = self._cosine_similarity(query_vec, doc_vec)

                # BM25 (normalized)
                bm25 = bm25_results.get(doc_id, 0.0)

                # Q-value boost
                q_value = float(meta.get("q_value", 0.5))

                # Final: 0.4 * cosine + 0.4 * bm25 + 0.2 * q_value
                final_score = 0.4 * cosine + 0.4 * bm25 + 0.2 * q_value

                if final_score > 0.01:
                    scored.append((doc_id, final_score, meta))

            # Sort by score descending
            scored.sort(key=lambda x: x[1], reverse=True)
            return scored[:top_k]

        return await asyncio.to_thread(_do)

    # ── Status ───────────────────────────────────────────────────

    async def status(self) -> dict[str, Any]:
        """Return store statistics."""
        await self._ensure_initialized()

        def _do():
            conn = self._get_conn()
            count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            db_size = os.path.getsize(self._db_path) if os.path.exists(self._db_path) else 0
            return {
                "total_documents": count,
                "db_path": self._db_path,
                "db_size_kb": round(db_size / 1024, 1),
                "idf_cache_size": len(self._idf_cache),
                "backend": "SQLite FTS5 + TF-IDF",
            }

        return await asyncio.to_thread(_do)

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
            self._initialized = False
