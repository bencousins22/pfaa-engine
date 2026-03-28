"""
Pure-Python 3.15 Vector Store — TF-IDF + BM25 + FTS5.

Ported from https://github.com/Aussie-Agents/jmem-mcp-server

Features:
    - Hybrid search: FTS5 keyword + TF-IDF semantic ranking
    - BM25 document scoring with length normalization
    - Q-value boosting for reinforcement learning
    - Incremental vocabulary building
    - SQLite WAL persistence
    - Async-safe via asyncio.to_thread()
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
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Self

logger = logging.getLogger("pfaa.vector_store")

# ── PEP 695 Type Aliases ──────────────────────────────────────────
Embedding = list[float]
TokenFreqs = dict[str, float]
DocumentID = str
SearchResult = tuple[str, float, dict[str, Any]]
SearchResults = list[SearchResult]


# ═══════════════════════════════════════════════════════════════════
# TF-IDF Vectorizer — Pure Python, zero dependencies
# ═══════════════════════════════════════════════════════════════════

_STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "because", "but", "and", "or", "if", "while", "that", "this", "it",
})

_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    """Tokenize text into lowercase word tokens, stripping stop words."""
    return [
        tok for tok in _TOKEN_RE.findall(text.lower())
        if tok not in _STOP_WORDS and len(tok) > 1
    ]


@dataclass(slots=True)
class TFIDFVectorizer:
    """Incremental TF-IDF vectorizer — builds vocabulary on-the-fly."""

    doc_freqs: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    doc_count: int = 0
    _vocab: dict[str, int] = field(default_factory=dict)

    def fit_document(self, tokens: list[str]) -> None:
        self.doc_count += 1
        seen: set[str] = set()
        for tok in tokens:
            if tok not in self._vocab:
                self._vocab[tok] = len(self._vocab)
            if tok not in seen:
                self.doc_freqs[tok] += 1
                seen.add(tok)

    def transform(self, tokens: list[str]) -> Embedding:
        if not tokens or not self._vocab:
            return []
        tf: Counter[str] = Counter(tokens)
        max_tf = max(tf.values()) if tf else 1
        vec = [0.0] * len(self._vocab)
        for tok, count in tf.items():
            idx = self._vocab.get(tok)
            if idx is not None:
                tf_score = 0.5 + 0.5 * (count / max_tf)
                df = self.doc_freqs.get(tok, 1)
                idf = math.log((self.doc_count + 1) / (df + 1)) + 1.0
                vec[idx] = tf_score * idf
        return vec

    def fit_transform(self, tokens: list[str]) -> Embedding:
        self.fit_document(tokens)
        return self.transform(tokens)

    @property
    def vocab_size(self) -> int:
        return len(self._vocab)

    def to_dict(self) -> dict[str, Any]:
        return {
            "doc_freqs": dict(self.doc_freqs),
            "doc_count": self.doc_count,
            "vocab": self._vocab,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        v = cls()
        v.doc_freqs = defaultdict(int, data.get("doc_freqs", {}))
        v.doc_count = data.get("doc_count", 0)
        v._vocab = data.get("vocab", {})
        return v


# ═══════════════════════════════════════════════════════════════════
# Scoring Functions
# ═══════════════════════════════════════════════════════════════════

def _cosine_similarity(a: Embedding, b: Embedding) -> float:
    if not a or not b:
        return 0.0
    min_len = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(min_len))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def _bm25_score(
    query_tokens: list[str],
    doc_tokens: list[str],
    doc_freqs: dict[str, int],
    total_docs: int,
    avg_doc_len: float,
    k1: float = 1.5,
    b: float = 0.75,
) -> float:
    if not query_tokens or not doc_tokens or total_docs == 0:
        return 0.0
    score = 0.0
    doc_len = len(doc_tokens)
    tf_map = Counter(doc_tokens)
    for term in query_tokens:
        if term not in tf_map:
            continue
        tf = tf_map[term]
        df = doc_freqs.get(term, 0)
        idf = math.log((total_docs - df + 0.5) / (df + 0.5) + 1.0)
        tf_norm = (tf * (k1 + 1)) / (tf + k1 * (1 - b + b * doc_len / max(avg_doc_len, 1)))
        score += idf * tf_norm
    return score


# ═══════════════════════════════════════════════════════════════════
# Vector Store — SQLite-backed with in-memory TF-IDF index
# ═══════════════════════════════════════════════════════════════════

class PureVectorStore:
    """
    Pure-Python vector store with SQLite FTS5 + TF-IDF cosine similarity.

    Hybrid search: FTS5 keyword + TF-IDF semantic + Q-boost reranking.
    """

    __slots__ = (
        "_db_path", "_conn", "_vectorizer", "_embedding_cache",
        "_lock", "_initialized",
    )

    def __init__(self, db_path: str | None = None):
        self._db_path = db_path or os.path.join(
            os.path.expanduser("~/.pfaa"), "vector_store.db"
        )
        self._conn: sqlite3.Connection | None = None
        self._vectorizer = TFIDFVectorizer()
        self._embedding_cache: dict[str, Embedding] = {}
        self._lock = asyncio.Lock()
        self._initialized = False

    async def __aenter__(self) -> Self:
        await self._ensure_initialized()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

    async def _ensure_initialized(self) -> None:
        if self._initialized:
            return
        await asyncio.to_thread(self._init_sync)
        self._initialized = True

    def _init_sync(self) -> None:
        os.makedirs(os.path.dirname(self._db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("PRAGMA cache_size=-8000")
        self._conn.execute("PRAGMA mmap_size=268435456")

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                text TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                embedding TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL
            );
            CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
                id, text, content=documents, content_rowid=rowid,
                tokenize='porter unicode61'
            );
            CREATE TRIGGER IF NOT EXISTS documents_ai AFTER INSERT ON documents BEGIN
                INSERT INTO documents_fts(rowid, id, text) VALUES (new.rowid, new.id, new.text);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_ad AFTER DELETE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, id, text) VALUES('delete', old.rowid, old.id, old.text);
            END;
            CREATE TRIGGER IF NOT EXISTS documents_au AFTER UPDATE ON documents BEGIN
                INSERT INTO documents_fts(documents_fts, rowid, id, text) VALUES('delete', old.rowid, old.id, old.text);
                INSERT INTO documents_fts(rowid, id, text) VALUES (new.rowid, new.id, new.text);
            END;
            CREATE TABLE IF NOT EXISTS vectorizer_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                state TEXT NOT NULL DEFAULT '{}'
            );
        """)

        row = self._conn.execute("SELECT state FROM vectorizer_state WHERE id = 1").fetchone()
        if row:
            self._vectorizer = TFIDFVectorizer.from_dict(json.loads(row[0]))

        for row in self._conn.execute("SELECT id, embedding FROM documents").fetchall():
            if emb_json := row[1]:
                self._embedding_cache[row[0]] = json.loads(emb_json)

        logger.info("VectorStore initialized: %s (%d docs, %d vocab)",
                     self._db_path, len(self._embedding_cache), self._vectorizer.vocab_size)

    async def upsert(self, doc_id: str, text: str, metadata: dict[str, Any] | None = None) -> str:
        async with self._lock:
            await self._ensure_initialized()

            def _upsert_sync() -> str:
                tokens = _tokenize(text)
                embedding = self._vectorizer.fit_transform(tokens)
                meta_json = json.dumps(metadata or {})
                emb_json = json.dumps(embedding)
                now = time.time()
                self._conn.execute(
                    """INSERT INTO documents (id, text, metadata, embedding, created_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(id) DO UPDATE SET
                           text = excluded.text, metadata = excluded.metadata,
                           embedding = excluded.embedding""",
                    (doc_id, text, meta_json, emb_json, now),
                )
                self._conn.commit()
                self._embedding_cache[doc_id] = embedding
                if self._vectorizer.doc_count % 50 == 0:
                    self._save_vectorizer_state()
                return doc_id

            return await asyncio.to_thread(_upsert_sync)

    async def search(self, query: str, top_k: int = 5, where: dict[str, Any] | None = None, q_boost: bool = True) -> SearchResults:
        await self._ensure_initialized()

        def _search_sync() -> SearchResults:
            query_tokens = _tokenize(query)
            if not query_tokens:
                return []

            fts_candidates: set[str] = set()
            try:
                fts_query = " OR ".join(f'"{tok}"' for tok in query_tokens)
                if fts_query:
                    rows = self._conn.execute(
                        "SELECT id FROM documents_fts WHERE documents_fts MATCH ? LIMIT ?",
                        (fts_query, top_k * 10),
                    ).fetchall()
                    fts_candidates = {r[0] for r in rows}
            except sqlite3.OperationalError:
                pass

            query_vec = self._vectorizer.transform(query_tokens)
            candidate_ids = fts_candidates.copy()
            if len(candidate_ids) < top_k * 3:
                candidate_ids.update(self._embedding_cache.keys())

            all_texts = self._conn.execute(
                "SELECT id, text FROM documents WHERE id IN ({})".format(
                    ",".join("?" for _ in candidate_ids)),
                list(candidate_ids),
            ).fetchall() if candidate_ids else []

            doc_text_map = {r[0]: r[1] for r in all_texts}
            doc_token_map = {did: _tokenize(txt) for did, txt in doc_text_map.items()}
            avg_doc_len = sum(len(t) for t in doc_token_map.values()) / max(len(doc_token_map), 1)

            scored: list[tuple[str, float]] = []
            for doc_id in candidate_ids:
                doc_tokens = doc_token_map.get(doc_id, [])
                bm25 = _bm25_score(query_tokens, doc_tokens, self._vectorizer.doc_freqs,
                                    self._vectorizer.doc_count, avg_doc_len)
                cosine = 0.0
                if query_vec and (doc_emb := self._embedding_cache.get(doc_id)):
                    cosine = _cosine_similarity(query_vec, doc_emb)

                q_val = 0.5
                if q_boost:
                    row = self._conn.execute("SELECT metadata FROM documents WHERE id = ?", (doc_id,)).fetchone()
                    if row:
                        meta = json.loads(row[0])
                        q_val = float(meta.get("q_value", 0.5))

                bm25_norm = min(1.0, bm25 / 10.0) if bm25 > 0 else 0.0
                fts_bonus = 1.0 if doc_id in fts_candidates else 0.0

                final = 0.30 * cosine + 0.30 * bm25_norm + 0.18 * q_val + 0.07 * fts_bonus + 0.08
                scored.append((doc_id, final))

            scored.sort(key=lambda x: x[1], reverse=True)

            results: SearchResults = []
            for doc_id, score in scored:
                if len(results) >= top_k:
                    break
                row = self._conn.execute("SELECT metadata FROM documents WHERE id = ?", (doc_id,)).fetchone()
                if not row:
                    continue
                meta = json.loads(row[0])
                if where and not self._matches_filter(meta, where):
                    continue
                results.append((doc_id, round(score, 4), meta))
            return results

        return await asyncio.to_thread(_search_sync)

    async def get(self, doc_id: str) -> dict[str, Any] | None:
        await self._ensure_initialized()
        def _get_sync() -> dict[str, Any] | None:
            row = self._conn.execute(
                "SELECT id, text, metadata, created_at FROM documents WHERE id = ?", (doc_id,),
            ).fetchone()
            if not row:
                return None
            return {"id": row[0], "text": row[1], "metadata": json.loads(row[2]) if row[2] else {}, "created_at": row[3]}
        return await asyncio.to_thread(_get_sync)

    async def update_metadata(self, doc_id: str, metadata: dict[str, Any]) -> None:
        async with self._lock:
            await self._ensure_initialized()
            def _update_sync() -> None:
                self._conn.execute("UPDATE documents SET metadata = ? WHERE id = ?", (json.dumps(metadata), doc_id))
                self._conn.commit()
            await asyncio.to_thread(_update_sync)

    async def delete(self, doc_id: str) -> None:
        async with self._lock:
            await self._ensure_initialized()
            def _delete_sync() -> None:
                self._conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
                self._conn.commit()
                self._embedding_cache.pop(doc_id, None)
            await asyncio.to_thread(_delete_sync)

    async def get_all(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Return all documents up to limit."""
        await self._ensure_initialized()
        def _get_all_sync() -> list[dict[str, Any]]:
            rows = self._conn.execute(
                "SELECT id, text, metadata, created_at FROM documents LIMIT ?", (limit,),
            ).fetchall()
            return [
                {"id": r[0], "text": r[1], "metadata": json.loads(r[2]) if r[2] else {}, "created_at": r[3]}
                for r in rows
            ]
        return await asyncio.to_thread(_get_all_sync)

    async def count(self) -> int:
        await self._ensure_initialized()
        row = await asyncio.to_thread(lambda: self._conn.execute("SELECT COUNT(*) FROM documents").fetchone())
        return row[0] if row else 0

    @staticmethod
    def _matches_filter(meta: dict[str, Any], where: dict[str, Any]) -> bool:
        for key, value in where.items():
            if isinstance(value, dict):
                meta_val = meta.get(key)
                for op, operand in value.items():
                    if op == "$gt" and not (meta_val is not None and meta_val > operand):
                        return False
                    if op == "$gte" and not (meta_val is not None and meta_val >= operand):
                        return False
                    if op == "$lt" and not (meta_val is not None and meta_val < operand):
                        return False
                    if op == "$ne" and meta_val == operand:
                        return False
            else:
                if meta.get(key) != value:
                    return False
        return True

    def _save_vectorizer_state(self) -> None:
        state_json = json.dumps(self._vectorizer.to_dict())
        self._conn.execute(
            "INSERT INTO vectorizer_state (id, state) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET state = excluded.state",
            (state_json,),
        )
        self._conn.commit()

    @property
    def is_available(self) -> bool:
        return self._conn is not None

    async def flush(self) -> None:
        async with self._lock:
            if self._conn:
                await asyncio.to_thread(self._save_vectorizer_state)

    async def close(self) -> None:
        if self._conn:
            def _close_sync() -> None:
                self._save_vectorizer_state()
                self._conn.close()
            await asyncio.to_thread(_close_sync)
            self._conn = None
            self._initialized = False

    async def status(self) -> dict[str, Any]:
        await self._ensure_initialized()
        db_size = os.path.getsize(self._db_path) if os.path.exists(self._db_path) else 0
        return {
            "available": self.is_available,
            "db_path": self._db_path,
            "db_size_kb": round(db_size / 1024, 1),
            "documents": len(self._embedding_cache),
            "vocab_size": self._vectorizer.vocab_size,
        }
