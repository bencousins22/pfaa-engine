#!/usr/bin/env python3
"""
Aussie Agents Team Spawner — Full team with JMEM memory.

Runs on Python 3.12+ (no lazy import syntax required).
Spawns all 6 agent roles, initializes JMEM semantic memory,
and executes goals via swarm or pipeline mode.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import os
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any, Self

# ── Claude API (optional) ──────────────────────────────────────────
try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _anthropic = None
    _HAS_ANTHROPIC = False

# ── Logging Setup ────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)-20s %(levelname)-5s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("pfaa.team")

# ── ANSI Colors ──────────────────────────────────────────────────────

C = "\033[36m"   # Cyan
G = "\033[32m"   # Green
Y = "\033[33m"   # Yellow
R = "\033[31m"   # Red
M = "\033[35m"   # Magenta
D = "\033[2m"    # Dim
B = "\033[1m"    # Bold
X = "\033[0m"    # Reset

BANNER = f"""
{C}{B}
╔═══════════════════════════════════════════════════════════════════════╗
║                                                                       ║
║    █████╗ ██╗   ██╗███████╗███████╗██╗███████╗                        ║
║   ██╔══██╗██║   ██║██╔════╝██╔════╝██║██╔════╝                        ║
║   ███████║██║   ██║███████╗███████╗██║█████╗                          ║
║   ██╔══██║██║   ██║╚════██║╚════██║██║██╔══╝                          ║
║   ██║  ██║╚██████╔╝███████║███████║██║███████╗                        ║
║   ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝╚═╝╚══════╝                        ║
║                 █████╗  ██████╗ ███████╗███╗   ██╗████████╗███████╗   ║
║                ██╔══██╗██╔════╝ ██╔════╝████╗  ██║╚══██╔══╝██╔════╝   ║
║                ███████║██║  ███╗█████╗  ██╔██╗ ██║   ██║   ███████╗   ║
║                ██╔══██║██║   ██║██╔══╝  ██║╚██╗██║   ██║   ╚════██║   ║
║                ██║  ██║╚██████╔╝███████╗██║ ╚████║   ██║   ███████║   ║
║                ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═══╝   ╚═╝   ╚══════╝   ║
║                                                                       ║
║   Phase-Fluid Agent Architecture — Agent Team Mode                    ║
║   JMEM Memory · 6 Agents · Q-Learning · Swarm Execution              ║
║                                                                       ║
╚═══════════════════════════════════════════════════════════════════════╝
{X}"""


# ═══════════════════════════════════════════════════════════════════
# Inline JMEM Vector Store (Pure Python TF-IDF + SQLite FTS5)
# ═══════════════════════════════════════════════════════════════════

_STOP_WORDS = frozenset({
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "to", "of", "in", "for",
    "on", "with", "at", "by", "from", "as", "into", "through", "during",
    "before", "after", "above", "below", "between", "out", "off", "over",
    "under", "not", "only", "same", "so", "than", "too", "very", "just",
    "because", "but", "and", "or", "if", "while", "that", "this", "it",
})
_TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN_RE.findall(text.lower()) if t not in _STOP_WORDS and len(t) > 1]


class TFIDFVectorizer:
    def __init__(self):
        self.doc_freqs: dict[str, int] = defaultdict(int)
        self.doc_count = 0
        self._vocab: dict[str, int] = {}

    def fit_transform(self, tokens: list[str]) -> list[float]:
        self.doc_count += 1
        seen: set[str] = set()
        for tok in tokens:
            if tok not in self._vocab:
                self._vocab[tok] = len(self._vocab)
            if tok not in seen:
                self.doc_freqs[tok] += 1
                seen.add(tok)
        return self._transform(tokens)

    def _transform(self, tokens: list[str]) -> list[float]:
        if not tokens or not self._vocab:
            return []
        tf = Counter(tokens)
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


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    dot = sum(a[i] * b[i] for i in range(n))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na > 0 and nb > 0 else 0.0


class VectorStore:
    """SQLite-backed vector store with TF-IDF."""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, text TEXT NOT NULL,
                metadata TEXT NOT NULL DEFAULT '{}',
                embedding TEXT NOT NULL DEFAULT '[]',
                created_at REAL NOT NULL
            );
        """)
        self._vectorizer = TFIDFVectorizer()
        self._cache: dict[str, list[float]] = {}
        # Load existing embeddings
        for row in self._conn.execute("SELECT id, embedding FROM documents").fetchall():
            if row[1]:
                try:
                    self._cache[row[0]] = json.loads(row[1])
                except:
                    pass

    def upsert(self, doc_id: str, text: str, metadata: dict | None = None) -> str:
        tokens = _tokenize(text)
        emb = self._vectorizer.fit_transform(tokens)
        self._conn.execute(
            "INSERT INTO documents (id, text, metadata, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
            "text=excluded.text, metadata=excluded.metadata, embedding=excluded.embedding",
            (doc_id, text, json.dumps(metadata or {}), json.dumps(emb), time.time()),
        )
        self._conn.commit()
        self._cache[doc_id] = emb
        return doc_id

    def search(self, query: str, top_k: int = 5) -> list[tuple[str, float, dict]]:
        tokens = _tokenize(query)
        if not tokens:
            return []
        q_vec = self._vectorizer._transform(tokens)
        scored = []
        for doc_id, emb in self._cache.items():
            cos = _cosine(q_vec, emb)
            row = self._conn.execute("SELECT metadata FROM documents WHERE id=?", (doc_id,)).fetchone()
            q_val = 0.5
            if row:
                meta = json.loads(row[0])
                q_val = float(meta.get("q_value", 0.5))
            score = 0.6 * cos + 0.3 * q_val + 0.1
            scored.append((doc_id, score, meta if row else {}))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def get(self, doc_id: str) -> dict | None:
        row = self._conn.execute("SELECT id, text, metadata FROM documents WHERE id=?", (doc_id,)).fetchone()
        if not row:
            return None
        return {"id": row[0], "text": row[1], "metadata": json.loads(row[2])}

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def close(self):
        self._conn.close()


# ═══════════════════════════════════════════════════════════════════
# Inline JMEM Engine
# ═══════════════════════════════════════════════════════════════════

class MemoryLevel(IntEnum):
    EPISODE = 1
    CONCEPT = 2
    PRINCIPLE = 3
    SKILL = 4


@dataclass
class MemoryNote:
    id: str
    content: str
    context: str = ""
    keywords: list[str] = field(default_factory=list)
    level: MemoryLevel = MemoryLevel.EPISODE
    q_value: float = 0.5
    retrieval_count: int = 0
    links: list[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class JMemEngine:
    def __init__(self, db_path: str):
        self._store = VectorStore(db_path)

    async def remember(self, content: str, level: MemoryLevel = MemoryLevel.EPISODE,
                       context: str = "", keywords: list[str] | None = None) -> str:
        note_id = hashlib.sha256(f"{content}:{level}:{time.time()}".encode()).hexdigest()[:16]
        kw = keywords or [t for t, _ in Counter(_tokenize(content)).most_common(6)]
        kw_text = " ".join(kw) * level.value
        full_text = f"{content} {kw_text} {context}"
        meta = {"level": level.value, "q_value": 0.5, "retrieval_count": 0,
                "keywords": kw, "links": [], "created_at": time.time()}
        self._store.upsert(note_id, full_text, meta)
        return note_id

    async def recall(self, query: str, limit: int = 5) -> list[MemoryNote]:
        results = self._store.search(query, top_k=limit)
        notes = []
        for doc_id, score, meta in results:
            doc = self._store.get(doc_id)
            if doc:
                note = MemoryNote(
                    id=doc_id, content=doc["text"][:300],
                    level=MemoryLevel(meta.get("level", 1)),
                    q_value=meta.get("q_value", 0.5),
                    retrieval_count=meta.get("retrieval_count", 0),
                    keywords=meta.get("keywords", []),
                )
                # Bump retrieval count
                meta["retrieval_count"] = note.retrieval_count + 1
                self._store.upsert(doc_id, doc["text"], meta)
                notes.append(note)
        return notes

    async def reward(self, note_id: str, signal: float) -> float:
        doc = self._store.get(note_id)
        if not doc:
            return 0.0
        meta = doc.get("metadata", {})
        if isinstance(meta, str):
            meta = json.loads(meta)
        current = float(meta.get("q_value", 0.5))
        alpha = 0.5 if abs(signal) > 0.5 else 0.15
        new_q = max(0.0, min(1.0, current + alpha * (signal - current)))
        meta["q_value"] = new_q
        self._store.upsert(note_id, doc["text"], meta)
        return new_q

    async def consolidate(self) -> dict:
        stats = {"promoted": 0, "linked": 0}
        # Auto-promote high-Q episodes
        for row in self._store._conn.execute("SELECT id, metadata FROM documents").fetchall():
            meta = json.loads(row[1])
            if meta.get("level") == 1 and meta.get("q_value", 0) > 0.8 and meta.get("retrieval_count", 0) > 3:
                meta["level"] = 2
                self._store._conn.execute("UPDATE documents SET metadata=? WHERE id=?", (json.dumps(meta), row[0]))
                stats["promoted"] += 1
        self._store._conn.commit()
        return stats

    async def reflect(self) -> dict:
        count = self._store.count()
        total_q = 0.0
        by_level = {l.name: 0 for l in MemoryLevel}
        for row in self._store._conn.execute("SELECT metadata FROM documents").fetchall():
            meta = json.loads(row[0])
            lvl = MemoryLevel(meta.get("level", 1))
            by_level[lvl.name] += 1
            total_q += meta.get("q_value", 0.5)
        avg_q = total_q / max(count, 1)
        return {"total": count, "by_level": by_level, "avg_q": round(avg_q, 3),
                "health": "good" if avg_q > 0.5 else "needs_consolidation"}

    def close(self):
        self._store.close()


# ═══════════════════════════════════════════════════════════════════
# Agent Team
# ═══════════════════════════════════════════════════════════════════

class TeamRole(Enum):
    STRATEGIST = "strategist"
    OPTIMIZER = "optimizer"
    RISK_MGR = "risk_manager"
    RESEARCHER = "researcher"
    VALIDATOR = "validator"
    DEPLOYER = "deployer"


ROLE_DESC = {
    TeamRole.STRATEGIST: ("Signal generation & parameter design", "VAPOR", ["signals", "indicators", "market"]),
    TeamRole.OPTIMIZER: ("Hyperparameter tuning & backtest", "LIQUID", ["hyperopt", "backtest", "tuning"]),
    TeamRole.RISK_MGR: ("Position sizing & drawdown protection", "VAPOR", ["risk", "sizing", "stops"]),
    TeamRole.RESEARCHER: ("Historical data & trend analysis", "VAPOR", ["search", "analysis", "data"]),
    TeamRole.VALIDATOR: ("OOS testing & overfitting detection", "SOLID", ["validation", "testing", "quality"]),
    TeamRole.DEPLOYER: ("Config generation & deployment", "SOLID", ["deploy", "config", "production"]),
}

ROLE_PROMPTS = {
    TeamRole.RESEARCHER: "You are a research analyst. Analyze data, find patterns, identify trends, and provide evidence-based insights to inform the team's decisions.",
    TeamRole.STRATEGIST: "You are a strategy architect. Design approaches, define signal combinations, and create comprehensive plans that balance risk and reward.",
    TeamRole.OPTIMIZER: "You are a performance optimizer. Find bottlenecks, tune hyperparameters, and maximize efficiency through systematic experimentation.",
    TeamRole.VALIDATOR: "You are a quality validator. Test, verify, find flaws, detect overfitting, and ensure all outputs meet rigorous quality standards.",
    TeamRole.RISK_MGR: "You are a risk manager. Identify risks, suggest mitigations, enforce position sizing limits, and protect against catastrophic drawdowns.",
    TeamRole.DEPLOYER: "You are a deployment specialist. Plan rollouts, generate production configs, and ensure smooth transitions from development to live systems.",
}


class ClaudeClient:
    """Wrapper around the Anthropic API with graceful fallback."""

    def __init__(self):
        self._client = None
        if _HAS_ANTHROPIC and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                self._client = _anthropic.Anthropic()
            except Exception:
                self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def ask(self, role_context: str, task: str, memories: list[str] | None = None) -> str:
        """Call Claude API. Returns response text, or raises on failure."""
        if not self._client:
            raise RuntimeError("Claude API client not available")
        mem_block = ""
        if memories:
            mem_block = "\n\n## Recalled Memories\n" + "\n".join(f"- {m}" for m in memories)
        system_prompt = f"{role_context}{mem_block}\n\nRespond concisely with actionable results. Use structured formatting."
        message = self._client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": task}],
        )
        return message.content[0].text


# Module-level singleton — created lazily
_claude_client: ClaudeClient | None = None


def _get_claude_client() -> ClaudeClient:
    global _claude_client
    if _claude_client is None:
        _claude_client = ClaudeClient()
    return _claude_client


@dataclass
class AgentState:
    role: TeamRole
    name: str
    active: bool = True
    tasks_ok: int = 0
    tasks_fail: int = 0
    total_ms: float = 0.0
    memories: int = 0


class AgentTeam:
    def __init__(self, roles: list[TeamRole] | None = None, namespace: str = "pfaa-team", live: bool = False):
        self.roles = roles or list(TeamRole)
        self.agents: dict[TeamRole, AgentState] = {}
        self.namespace = namespace
        self._engine: JMemEngine | None = None
        self._task_count = 0
        self._start = time.time()
        self.live = live
        self._claude: ClaudeClient | None = None

    async def start(self) -> None:
        print(BANNER)
        db_path = os.path.expanduser(f"~/.pfaa/team/{self.namespace}/memory.db")
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._engine = JMemEngine(db_path)
        print(f"  {C}▸{X} JMEM memory initialized: {D}{db_path}{X}")
        if self.live:
            self._claude = _get_claude_client()
            if self._claude.available:
                print(f"  {G}▸{X} Claude API: {G}LIVE{X} (claude-sonnet-4-20250514)")
            else:
                print(f"  {Y}▸{X} Claude API: {Y}FALLBACK{X} (no API key or anthropic not installed)")
        else:
            print(f"  {D}▸{X} Claude API: {D}SIMULATED{X} (use --live for real API calls)")

        for role in self.roles:
            agent = AgentState(role=role, name=f"pfaa-{role.value}")
            self.agents[role] = agent
            # Recall prior knowledge
            memories = await self._engine.recall(f"agent {role.value} patterns", limit=3)
            mem_str = f"{G}{len(memories)} memories{X}" if memories else f"{D}no prior knowledge{X}"
            print(f"  {G}✓{X} Spawned {Y}{agent.name:18s}{X} {mem_str}")

        print(f"\n  {C}▸{X} Team ready: {B}{len(self.agents)}{X} agents active\n")

    async def execute(self, role: TeamRole, task: str, ctx: dict | None = None) -> dict:
        agent = self.agents.get(role)
        if not agent:
            return {"success": False, "error": f"No agent for {role.value}"}

        start = time.perf_counter()

        # Recall context
        memories = await self._engine.recall(task, limit=3)
        mem_context = [f"[L{m.level} Q={m.q_value:.2f}] {m.content[:80]}" for m in memories]

        # Try real Claude API call if --live and client is available
        live_response = None
        if self.live and self._claude and self._claude.available:
            role_prompt = ROLE_PROMPTS.get(role, f"You are a {role.value} agent.")
            desc, phase, caps = ROLE_DESC.get(role, ("Agent", "VAPOR", []))
            full_context = f"{role_prompt}\n\nRole: {desc}\nPhase: {phase}\nCapabilities: {', '.join(caps)}"
            try:
                live_response = self._claude.ask(full_context, task, mem_context)
            except Exception as e:
                logger.warning(f"Claude API call failed for {role.value}: {e}")
                agent.tasks_fail += 1

        if live_response:
            result = {
                "task": task[:100],
                "context_recalled": len(memories),
                "prior_knowledge": mem_context[:3],
                "response": live_response,
                "live": True,
            }
        else:
            result = {
                "task": task[:100],
                "context_recalled": len(memories),
                "prior_knowledge": mem_context[:3],
                "live": False,
            }

        elapsed = (time.perf_counter() - start) * 1000
        agent.tasks_ok += 1
        agent.total_ms += elapsed

        # Store outcome (real response or simulated) in JMEM
        mem_content = f"[{role.value}] {task[:200]} | OK in {elapsed:.0f}ms"
        if live_response:
            mem_content = f"[{role.value}] {task[:100]} | {live_response[:300]}"
        note_id = await self._engine.remember(
            content=mem_content,
            level=MemoryLevel.EPISODE,
            context=json.dumps(ctx or {}),
            keywords=_tokenize(task)[:6],
        )
        await self._engine.reward(note_id, 0.85 if live_response else 0.8)
        agent.memories += 1
        self._task_count += 1

        # Auto-consolidate every 10 tasks
        if self._task_count % 10 == 0:
            stats = await self._engine.consolidate()
            if stats.get("promoted", 0) > 0:
                print(f"    {M}⟳ Auto-consolidation: {stats}{X}")

        return {
            "success": True, "agent": agent.name, "role": role.value,
            "result": result, "elapsed_ms": round(elapsed, 1),
            "memories_recalled": len(memories), "memory_id": note_id,
        }

    async def swarm(self, goal: str) -> list[dict]:
        """Execute goal across ALL agents in parallel."""
        print(f"  {C}⚡ Swarming all agents...{X}\n")
        tasks = [self.execute(role, f"[{role.value}] {goal}") for role in self.agents]
        results = await asyncio.gather(*tasks)
        results = list(results)
        for r in results:
            icon = f"{G}✓{X}" if r["success"] else f"{R}✗{X}"
            role = r.get("role", "?")
            ms = r.get("elapsed_ms", 0)
            recalled = r.get("memories_recalled", 0)
            print(f"    {icon} {Y}{role:14s}{X} {D}{ms:>7.1f}ms{X}  recalled={recalled}")
        ok = sum(1 for r in results if r["success"])
        print(f"\n  {G}✓{X} Swarm complete: {ok}/{len(results)} succeeded")
        return results

    async def pipeline(self, steps: list[tuple[TeamRole, str]]) -> list[dict]:
        """Execute steps sequentially, passing context."""
        print(f"  {C}▸ Pipeline: {len(steps)} stages{X}\n")
        results = []
        ctx: dict = {}
        for role, task in steps:
            r = await self.execute(role, task, ctx)
            results.append(r)
            ctx[role.value] = r
            icon = f"{G}✓{X}" if r["success"] else f"{R}✗{X}"
            print(f"    {icon} {Y}{role.value:14s}{X} {D}{r.get('elapsed_ms', 0):>7.1f}ms{X}")
        return results

    async def status(self) -> dict:
        reflect = await self._engine.reflect() if self._engine else {}
        return {
            "team_size": len(self.agents),
            "total_tasks": self._task_count,
            "uptime_s": round(time.time() - self._start, 1),
            "agents": {
                r.value: {"ok": a.tasks_ok, "fail": a.tasks_fail,
                           "avg_ms": round(a.total_ms / max(a.tasks_ok, 1), 1),
                           "memories": a.memories}
                for r, a in self.agents.items()
            },
            "memory": reflect,
        }

    async def shutdown(self) -> None:
        if self._engine:
            stats = await self._engine.consolidate()
            print(f"\n  {M}⟳ Final consolidation: {stats}{X}")
            reflect = await self._engine.reflect()
            print(f"  {C}📊 Memory: {reflect['total']} memories, avg Q={reflect['avg_q']}, health={reflect['health']}{X}")
            self._engine.close()
        print(f"  {G}✓{X} Agent team shutdown ({time.time() - self._start:.1f}s uptime)")


# ═══════════════════════════════════════════════════════════════════
# Main — Full Agent Team Spawn
# ═══════════════════════════════════════════════════════════════════

async def main_async():
    import argparse
    p = argparse.ArgumentParser(description="Aussie Agents Team Spawner")
    p.add_argument("goal", nargs="?", default="self-build the most profitable bitcoin freqtrade config")
    p.add_argument("--ns", default="pfaa-btc-team", help="JMEM namespace")
    p.add_argument("--live", action="store_true", help="Enable real Claude API calls (requires ANTHROPIC_API_KEY)")
    args = p.parse_args()

    goal = args.goal
    team = AgentTeam(namespace=args.ns, live=args.live)
    await team.start()

    try:
        # Phase 1: Full swarm — all agents attack the goal simultaneously
        print(f"  {B}Phase 1: Swarm Execution{X}")
        print(f"  {D}Goal: {goal}{X}\n")
        swarm_results = await team.swarm(goal)

        # Phase 2: Sequential pipeline for BTC strategy optimization
        print(f"\n  {B}Phase 2: Strategy Optimization Pipeline{X}\n")
        pipeline_results = await team.pipeline([
            (TeamRole.RESEARCHER, f"Research BTC 2025-2026: peaked $126K Oct 2025, corrected to $66K. "
                                   f"Support $64.7K, resistance $78K/$82.5K. Identify regime."),
            (TeamRole.STRATEGIST, f"Design multi-signal entry: EMA cross + RSI + BB squeeze + MACD + Volume. "
                                   f"Optimal params for correction/recovery regime."),
            (TeamRole.OPTIMIZER, f"Hyperopt config: SharpeHyperOptLoss, NSGAIIISampler, 1000 epochs, "
                                  f"timerange 20250401-20260301, spaces buy sell."),
            (TeamRole.VALIDATOR, f"Walk-forward validation: 70/30 split, check OOS Sharpe > 50% of IS. "
                                  f"Flag overfitting if win rate > 80% or trades < 50."),
            (TeamRole.RISK_MGR, f"Risk check: max drawdown < 20%, trailing stop +1.8%/+4.5% offset, "
                                 f"stoploss -6%, ATR-scaled dynamic stops."),
            (TeamRole.DEPLOYER, f"Generate production config: BTC/USDT on Binance, dry_run=true, "
                                 f"max_open_trades=3, 5m timeframe with 1h informative."),
        ])

        # Phase 3: Status report
        print(f"\n  {B}Phase 3: Final Status{X}\n")
        status = await team.status()
        print(f"  {D}Tasks completed: {status['total_tasks']}{X}")
        print(f"  {D}Uptime: {status['uptime_s']}s{X}")
        for role, info in status["agents"].items():
            print(f"    {Y}{role:14s}{X} tasks={info['ok']} avg={info['avg_ms']:.1f}ms memories={info['memories']}")
        mem = status.get("memory", {})
        if mem:
            print(f"\n  {C}🧠 Memory Health{X}")
            print(f"    Total: {mem.get('total', 0)} memories")
            print(f"    By level: {json.dumps(mem.get('by_level', {}))}")
            print(f"    Avg Q: {mem.get('avg_q', 0)}")
            print(f"    Health: {mem.get('health', '?')}")

    finally:
        await team.shutdown()


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
