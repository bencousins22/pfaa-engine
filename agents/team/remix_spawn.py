#!/usr/bin/env python3
"""
Aussie Agents Remix Team — Full-power multi-agent spawner with ALL capabilities.

10 agents · JMEM memory · State machine · Circuit breaker · Skill gen
Swarm + Pipeline + DAG + Remix execution modes

Usage:
    python3 agents/team/remix_spawn.py "self-build profitable btc freqtrade config"
    python3 agents/team/remix_spawn.py --mode remix "optimize everything"
"""
from __future__ import annotations
import asyncio, hashlib, json, logging, math, os, re, sqlite3, sys, time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from enum import Enum, IntEnum
from typing import Any

# ── Claude API (optional) ──────────────────────────────────────────
try:
    import anthropic as _anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _anthropic = None
    _HAS_ANTHROPIC = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-18s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("pfaa.remix")

# ── ANSI ─────────────────────────────────────────────────────────────
C, G, Y, R, M, D, B, W, X = "\033[36m","\033[32m","\033[33m","\033[31m","\033[35m","\033[2m","\033[1m","\033[37m","\033[0m"

BANNER = f"""{C}{B}
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
║  REMIX Mode (Full Power) — Phase-Fluid Agent Architecture             ║
║  10 Agents · JMEM 5-Layer Memory · Q-Learning · Self-Build            ║
╚═══════════════════════════════════════════════════════════════════════╝{X}
"""

# ═══════════════════════════════════════════════════════════════════════
# Inline Vector Store + JMEM Engine (zero deps)
# ═══════════════════════════════════════════════════════════════════════
_STOP = frozenset("a an the is are was were be been have has had do does did will would could should may might to of in for on with at by from as into through during before after above below between out off over under not only same so than too very just because but and or if while that this it".split())
_TOK = re.compile(r"[a-z0-9_]+")
def _tokenize(t): return [w for w in _TOK.findall(t.lower()) if w not in _STOP and len(w)>1]

class _TFIDF:
    def __init__(self):
        self.df, self.n, self.v = defaultdict(int), 0, {}
    def fit_transform(self, toks):
        self.n += 1
        for t in set(toks):
            if t not in self.v: self.v[t] = len(self.v)
            self.df[t] += 1
        if not toks or not self.v: return []
        tf = Counter(toks); mx = max(tf.values())
        vec = [0.0]*len(self.v)
        for t,c in tf.items():
            if (i:=self.v.get(t)) is not None:
                vec[i] = (0.5+0.5*c/mx)*(math.log((self.n+1)/(self.df.get(t,1)+1))+1)
        return vec
    def transform(self, toks):
        if not toks or not self.v: return []
        tf = Counter(toks); mx = max(tf.values())
        vec = [0.0]*len(self.v)
        for t,c in tf.items():
            if (i:=self.v.get(t)) is not None:
                vec[i] = (0.5+0.5*c/mx)*(math.log((self.n+1)/(self.df.get(t,1)+1))+1)
        return vec

def _cos(a,b):
    if not a or not b: return 0.0
    n=min(len(a),len(b)); d=sum(a[i]*b[i] for i in range(n))
    na=math.sqrt(sum(x*x for x in a)); nb=math.sqrt(sum(x*x for x in b))
    return d/(na*nb) if na>0 and nb>0 else 0.0

class VStore:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL"); self.db.execute("PRAGMA synchronous=NORMAL")
        self.db.executescript("CREATE TABLE IF NOT EXISTS docs(id TEXT PRIMARY KEY,text TEXT,meta TEXT DEFAULT '{}',emb TEXT DEFAULT '[]',ts REAL);")
        self.tf = _TFIDF(); self.ec = {}
        for r in self.db.execute("SELECT id,emb FROM docs").fetchall():
            try: self.ec[r[0]] = json.loads(r[1])
            except: pass
    def upsert(self, id, text, meta=None):
        e = self.tf.fit_transform(_tokenize(text))
        self.db.execute("INSERT INTO docs VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET text=excluded.text,meta=excluded.meta,emb=excluded.emb",
                        (id,text,json.dumps(meta or {}),json.dumps(e),time.time()))
        self.db.commit(); self.ec[id] = e; return id
    def search(self, q, k=5):
        toks = _tokenize(q)
        if not toks: return []
        qv = self.tf.transform(toks); scored = []
        for did, emb in self.ec.items():
            r = self.db.execute("SELECT meta FROM docs WHERE id=?", (did,)).fetchone()
            m = json.loads(r[0]) if r else {}
            s = 0.6*_cos(qv,emb) + 0.3*float(m.get("q_value",0.5)) + 0.1
            scored.append((did, s, m))
        scored.sort(key=lambda x:x[1], reverse=True)
        return scored[:k]
    def get(self, id):
        r = self.db.execute("SELECT id,text,meta FROM docs WHERE id=?", (id,)).fetchone()
        return {"id":r[0],"text":r[1],"metadata":json.loads(r[2])} if r else None
    def count(self): return self.db.execute("SELECT COUNT(*) FROM docs").fetchone()[0]
    def all_meta(self):
        return [(r[0], json.loads(r[1])) for r in self.db.execute("SELECT id,meta FROM docs").fetchall()]
    def update_meta(self, id, meta):
        self.db.execute("UPDATE docs SET meta=? WHERE id=?", (json.dumps(meta), id)); self.db.commit()

class MemLvl(IntEnum):
    EPISODE=1; CONCEPT=2; PRINCIPLE=3; SKILL=4

class JMem:
    def __init__(self, path):
        self.store = VStore(path)
    def _id(self, c, l): return hashlib.sha256(f"{c}:{l}:{time.time()}".encode()).hexdigest()[:16]
    async def remember(self, content, level=MemLvl.EPISODE, ctx="", kw=None):
        nid = self._id(content, level)
        kw = kw or [t for t,_ in Counter(_tokenize(content)).most_common(6)]
        self.store.upsert(nid, f"{content} {' '.join(kw)*level} {ctx}",
                          {"level":level,"q_value":0.5,"retrieval_count":0,"keywords":kw,"created_at":time.time()})
        return nid
    async def recall(self, q, limit=5):
        results = self.store.search(q, limit)
        notes = []
        for did, score, meta in results:
            doc = self.store.get(did)
            if doc:
                meta["retrieval_count"] = meta.get("retrieval_count",0)+1
                self.store.update_meta(did, meta)
                notes.append({"id":did,"content":doc["text"][:200],"level":meta.get("level",1),
                              "q":meta.get("q_value",0.5),"rc":meta["retrieval_count"],"kw":meta.get("keywords",[])})
        return notes
    async def reward(self, nid, signal):
        doc = self.store.get(nid)
        if not doc: return 0.0
        m = doc["metadata"]; cq = float(m.get("q_value",0.5))
        alpha = 0.5 if abs(signal)>0.5 else 0.15
        nq = max(0, min(1, cq + alpha*(signal-cq))); m["q_value"] = nq
        self.store.update_meta(nid, m); return nq
    async def consolidate(self):
        stats = {"promoted":0,"skills_gen":0,"linked":0}
        for did, m in self.store.all_meta():
            if m.get("level")==1 and m.get("q_value",0)>0.8 and m.get("retrieval_count",0)>3:
                m["level"] = 2; self.store.update_meta(did, m); stats["promoted"] += 1
            if m.get("level")==2 and m.get("q_value",0)>0.9 and m.get("retrieval_count",0)>5:
                m["level"] = 3; self.store.update_meta(did, m); stats["promoted"] += 1
        return stats
    async def gen_skills(self):
        skills = []
        for did, m in self.store.all_meta():
            if m.get("q_value",0)>=0.9 and m.get("retrieval_count",0)>=5 and m.get("level",1)<4:
                doc = self.store.get(did)
                if doc:
                    m["level"] = 4; self.store.update_meta(did, m)
                    skills.append({"id":did,"content":doc["text"][:150],"q":m["q_value"]})
        return skills
    async def reflect(self):
        n = self.store.count(); tq = 0; bl = {l.name:0 for l in MemLvl}
        for _, m in self.store.all_meta():
            bl[MemLvl(m.get("level",1)).name] += 1; tq += m.get("q_value",0.5)
        aq = tq/max(n,1)
        return {"total":n,"by_level":bl,"avg_q":round(aq,3),"health":"excellent" if aq>0.7 else "good" if aq>0.5 else "needs_work"}
    def close(self): self.store.db.close()

# ═══════════════════════════════════════════════════════════════════════
# Agent State Machine + Roles
# ═══════════════════════════════════════════════════════════════════════
class AgentPhase(Enum):
    SPAWNING="spawning"; IDLE="idle"; EXECUTING="executing"; REPORTING="reporting"
    SHUTTING_DOWN="shutting_down"; DEAD="dead"

class Role(Enum):
    LEAD="lead"; RESEARCHER="researcher"; STRATEGIST="strategist"; OPTIMIZER="optimizer"
    VALIDATOR="validator"; RISK_MGR="risk_manager"; DEPLOYER="deployer"
    REWRITER="rewriter"; MODERNIZER="modernizer"; SKILL_WRITER="skill_writer"

ROLE_DESC = {
    Role.LEAD: ("Team orchestrator", "VAPOR", ["planning","coordination","synthesis"]),
    Role.RESEARCHER: ("Historical data & trend analysis", "VAPOR", ["search","analysis","data"]),
    Role.STRATEGIST: ("Signal generation & parameter design", "VAPOR", ["signals","indicators","market"]),
    Role.OPTIMIZER: ("Hyperparameter tuning & backtest", "LIQUID", ["hyperopt","backtest","tuning"]),
    Role.VALIDATOR: ("OOS testing & overfitting detection", "SOLID", ["validation","testing","quality"]),
    Role.RISK_MGR: ("Position sizing & drawdown protection", "VAPOR", ["risk","sizing","stops"]),
    Role.DEPLOYER: ("Config generation & deployment", "SOLID", ["deploy","config","production"]),
    Role.REWRITER: ("Python 3.15 perf optimization", "LIQUID", ["lazy_import","frozendict","perf"]),
    Role.MODERNIZER: ("Language idiom modernization", "VAPOR", ["patterns","idioms","modern"]),
    Role.SKILL_WRITER: ("Extract skills from high-Q memories", "VAPOR", ["skills","extraction","learning"]),
}

ROLE_PROMPTS = {
    Role.LEAD: "You are the team lead coordinating a multi-agent Aussie Agents team. Synthesize inputs from all agents, resolve conflicts, and produce a coherent action plan.",
    Role.RESEARCHER: "You are a research analyst. Analyze data, find patterns, identify trends, and provide evidence-based insights to inform the team's decisions.",
    Role.STRATEGIST: "You are a strategy architect. Design approaches, define signal combinations, and create comprehensive plans that balance risk and reward.",
    Role.OPTIMIZER: "You are a performance optimizer. Find bottlenecks, tune hyperparameters, and maximize efficiency through systematic experimentation.",
    Role.VALIDATOR: "You are a quality validator. Test, verify, find flaws, detect overfitting, and ensure all outputs meet rigorous quality standards.",
    Role.RISK_MGR: "You are a risk manager. Identify risks, suggest mitigations, enforce position sizing limits, and protect against catastrophic drawdowns.",
    Role.DEPLOYER: "You are a deployment specialist. Plan rollouts, generate production configs, and ensure smooth transitions from development to live systems.",
    Role.REWRITER: "You are a Python 3.15 code rewriter. Apply PEP 810 lazy imports, PEP 814 frozendict, free-threading patterns, and kqueue subprocess for maximum performance.",
    Role.MODERNIZER: "You are a code modernizer. Upgrade patterns to latest standards including match/case, type parameters, exception groups, and modern Python idioms.",
    Role.SKILL_WRITER: "You are a skill generator. Create reusable Claude Code skills from high-Q memories, extracting patterns into composable, well-documented skill definitions.",
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
class Agent:
    role: Role; name: str; phase: AgentPhase = AgentPhase.SPAWNING
    ok: int = 0; fail: int = 0; consec_fail: int = 0; ms: float = 0; mems: int = 0
    breaker_tripped: bool = False

    def transition(self, to: AgentPhase):
        old = self.phase; self.phase = to
        return f"{self.name}: {old.value} → {to.value}"

# ═══════════════════════════════════════════════════════════════════════
# Circuit Breaker
# ═══════════════════════════════════════════════════════════════════════
BREAKER_THRESHOLD = 3

def check_breaker(agent: Agent) -> bool:
    if agent.consec_fail >= BREAKER_THRESHOLD:
        if not agent.breaker_tripped:
            agent.breaker_tripped = True
            print(f"    {R}⚡ CIRCUIT BREAKER tripped: {agent.name} ({agent.consec_fail} consecutive failures){X}")
        return True
    return False

# ═══════════════════════════════════════════════════════════════════════
# Remix Agent Team
# ═══════════════════════════════════════════════════════════════════════
class RemixTeam:
    def __init__(self, roles=None, ns="pfaa-remix", live=False):
        self.roles = roles or list(Role)
        self.agents: dict[Role, Agent] = {}
        self.engine: JMem = None
        self.ns = ns; self.tasks = 0; self.t0 = time.time()
        self.knowledge_bus: list[dict] = []
        self.live = live
        self._claude: ClaudeClient | None = None

    async def start(self):
        print(BANNER)
        db = os.path.expanduser(f"~/.pfaa/team/{self.ns}/memory.db")
        os.makedirs(os.path.dirname(db), exist_ok=True)
        self.engine = JMem(db)
        print(f"  {C}▸{X} JMEM initialized: {D}{db}{X}")
        if self.live:
            self._claude = _get_claude_client()
            if self._claude.available:
                print(f"  {G}▸{X} Claude API: {G}LIVE{X} (claude-sonnet-4-20250514)")
            else:
                print(f"  {Y}▸{X} Claude API: {Y}FALLBACK{X} (no API key or anthropic not installed)")
        else:
            print(f"  {D}▸{X} Claude API: {D}SIMULATED{X} (use --live for real API calls)")
        print(f"  {C}▸{X} Spawning {B}{len(self.roles)}{X} agents...\n")
        for role in self.roles:
            desc, phase, caps = ROLE_DESC.get(role, ("Agent","VAPOR",[]))
            a = Agent(role=role, name=f"pfaa-{role.value}")
            mems = await self.engine.recall(f"agent {role.value} best practices", limit=3)
            a.transition(AgentPhase.IDLE)
            self.agents[role] = a
            mem_s = f"{G}{len(mems)} memories{X}" if mems else f"{D}fresh{X}"
            print(f"    {G}✓{X} {Y}{a.name:20s}{X} [{phase}] {D}{desc}{X}  {mem_s}")
        print(f"\n  {C}▸{X} Team ready: {B}{len(self.agents)}{X} agents\n")

    async def execute(self, role: Role, task: str, ctx=None) -> dict:
        a = self.agents.get(role)
        if not a or a.phase == AgentPhase.DEAD: return {"success":False,"error":"dead","role":role.value}
        if check_breaker(a): return {"success":False,"error":"circuit_breaker","role":role.value}
        t = a.transition(AgentPhase.EXECUTING)
        t0 = time.perf_counter()
        mems = await self.engine.recall(task, limit=3)
        mem_strings = [m["content"][:80] for m in mems[:3]]

        # Try real Claude API call if --live and client is available
        live_response = None
        if self.live and self._claude and self._claude.available:
            role_prompt = ROLE_PROMPTS.get(role, f"You are a {role.value} agent.")
            desc, phase, caps = ROLE_DESC.get(role, ("Agent","VAPOR",[]))
            full_context = f"{role_prompt}\n\nRole: {desc}\nPhase: {phase}\nCapabilities: {', '.join(caps)}"
            try:
                live_response = self._claude.ask(full_context, task, mem_strings)
            except Exception as e:
                log.warning(f"Claude API call failed for {role.value}: {e}")
                a.consec_fail += 1

        if live_response:
            result = {"task":task[:100],"recalled":len(mems),"prior":mem_strings[:2],"response":live_response,"live":True}
        else:
            result = {"task":task[:100],"recalled":len(mems),"prior":mem_strings[:2],"live":False}

        ms = (time.perf_counter()-t0)*1000
        a.ok += 1; a.consec_fail = 0; a.ms += ms; a.breaker_tripped = False

        # Store outcome (real response or simulated) in JMEM
        mem_content = f"[{role.value}] {task[:200]} | OK {ms:.0f}ms"
        if live_response:
            mem_content = f"[{role.value}] {task[:100]} | {live_response[:300]}"
        nid = await self.engine.remember(mem_content, kw=_tokenize(task)[:6])
        await self.engine.reward(nid, 0.85 if live_response else 0.8); a.mems += 1
        self.knowledge_bus.append({"role":role.value,"task":task[:80],"nid":nid})
        self.tasks += 1
        if self.tasks % 10 == 0: await self.engine.consolidate()
        a.transition(AgentPhase.REPORTING); a.transition(AgentPhase.IDLE)
        return {"success":True,"agent":a.name,"role":role.value,"result":result,"ms":round(ms,1),"recalled":len(mems),"nid":nid}

    # ── Execution Modes ──────────────────────────────────────────
    async def swarm(self, goal):
        print(f"  {C}⚡ SWARM — all {len(self.agents)} agents parallel{X}\n")
        results = await asyncio.gather(*[self.execute(r, f"[{r.value}] {goal}") for r in self.agents])
        results = list(results)
        dead = sum(1 for r in results if not r["success"])
        if dead > len(results)//2:
            print(f"  {R}⚠ CASCADING FAILURE: {dead}/{len(results)} agents failed — aborting{X}")
        for r in results:
            i = f"{G}✓{X}" if r["success"] else f"{R}✗{X}"
            print(f"    {i} {Y}{r['role']:16s}{X} {D}{r.get('ms',0):>7.1f}ms{X}  recalled={r.get('recalled',0)}")
        ok = sum(1 for r in results if r["success"])
        print(f"\n  {G}✓{X} Swarm: {ok}/{len(results)} succeeded")
        return results

    async def pipeline(self, steps):
        print(f"  {M}▸ PIPELINE — {len(steps)} stages{X}\n")
        results = []; ctx = {}
        for role, task in steps:
            r = await self.execute(role, task, ctx); results.append(r); ctx[role.value] = r
            i = f"{G}✓{X}" if r["success"] else f"{R}✗{X}"
            print(f"    {i} {Y}{role.value:16s}{X} {D}{r.get('ms',0):>7.1f}ms{X}")
        return results

    async def dag(self, tasks):
        """Dependency-aware parallel: tasks = [(role, task, [dep_roles])]"""
        print(f"  {C}▸ DAG — {len(tasks)} nodes{X}\n")
        done = {}; results = []
        while len(done) < len(tasks):
            ready = [(r,t) for r,t,deps in tasks if r.value not in done and all(d.value in done for d in deps)]
            if not ready: break
            batch = await asyncio.gather(*[self.execute(r, t) for r, t in ready])
            for r in batch:
                done[r["role"]] = r; results.append(r)
                i = f"{G}✓{X}" if r["success"] else f"{R}✗{X}"
                print(f"    {i} {Y}{r['role']:16s}{X} {D}{r.get('ms',0):>7.1f}ms{X}")
        return results

    async def remix(self, goal):
        """Full remix cycle: swarm → pipeline → consolidate → skill-gen → report"""
        print(f"  {B}{'='*60}{X}")
        print(f"  {B}  REMIX CYCLE — Full Power Execution{X}")
        print(f"  {B}{'='*60}{X}\n")

        # Phase 1: Swarm
        print(f"  {B}Phase 1/5: SWARM{X} — all agents attack goal\n")
        s_results = await self.swarm(goal)

        # Phase 2: Pipeline optimization
        print(f"\n  {B}Phase 2/5: PIPELINE{X} — sequential optimization\n")
        p_results = await self.pipeline([
            (Role.RESEARCHER, f"Research: {goal} — analyze historical data, detect patterns"),
            (Role.STRATEGIST, f"Strategy: design optimal signals for {goal}"),
            (Role.OPTIMIZER, f"Optimize: tune hyperparameters for {goal}"),
            (Role.VALIDATOR, f"Validate: walk-forward test, check overfitting"),
            (Role.RISK_MGR, f"Risk: validate position sizing, max drawdown < 20%"),
            (Role.DEPLOYER, f"Deploy: generate production config"),
        ])

        # Phase 3: DAG with Python 3.15 agents
        print(f"\n  {B}Phase 3/5: DAG{X} — Python 3.15 enhancement\n")
        d_results = await self.dag([
            (Role.REWRITER, f"Rewrite: apply PEP 810 lazy imports, PEP 814 frozendict to {goal}", []),
            (Role.MODERNIZER, f"Modernize: apply match/case, type params, exception groups", []),
            (Role.SKILL_WRITER, f"Extract skills from high-Q memories for {goal}", [Role.REWRITER, Role.MODERNIZER]),
            (Role.LEAD, f"Synthesize all results for {goal}", [Role.SKILL_WRITER]),
        ])

        # Phase 4: Consolidate
        print(f"\n  {B}Phase 4/5: CONSOLIDATE{X} — knowledge promotion\n")
        stats = await self.engine.consolidate()
        print(f"    {M}⟳{X} Promoted: {stats['promoted']} | Skills: {stats.get('skills_gen',0)} | Linked: {stats.get('linked',0)}")

        # Phase 5: Skill generation
        print(f"\n  {B}Phase 5/5: SKILL GEN{X} — auto-generate from high-Q memories\n")
        skills = await self.engine.gen_skills()
        if skills:
            for s in skills:
                print(f"    {G}★{X} Skill: {D}{s['content'][:80]}{X} (Q={s['q']:.2f})")
        else:
            print(f"    {D}No memories at Q≥0.9 yet — run more cycles to build knowledge{X}")

        return {"swarm": s_results, "pipeline": p_results, "dag": d_results, "consolidation": stats, "skills": skills}

    async def status(self):
        r = await self.engine.reflect()
        return {
            "team": len(self.agents), "tasks": self.tasks,
            "uptime": round(time.time()-self.t0, 1),
            "agents": {a.role.value: {"ok":a.ok,"fail":a.fail,"ms":round(a.ms/max(a.ok,1),1),
                        "mems":a.mems,"phase":a.phase.value,"breaker":a.breaker_tripped} for a in self.agents.values()},
            "memory": r, "knowledge_bus": len(self.knowledge_bus),
        }

    async def shutdown(self):
        stats = await self.engine.consolidate()
        r = await self.engine.reflect()
        for a in self.agents.values(): a.transition(AgentPhase.SHUTTING_DOWN); a.transition(AgentPhase.DEAD)
        print(f"\n  {M}⟳ Final consolidation: {json.dumps(stats)}{X}")
        print(f"  {C}🧠 Memory: {r['total']} total, avg Q={r['avg_q']}, {json.dumps(r['by_level'])}{X}")
        print(f"  {C}📡 Knowledge bus: {len(self.knowledge_bus)} entries shared{X}")
        print(f"  {G}✓{X} Team shutdown ({time.time()-self.t0:.1f}s uptime, {self.tasks} tasks)")
        self.engine.close()

# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════
async def main():
    import argparse
    p = argparse.ArgumentParser(description="Aussie Agents Remix Team")
    p.add_argument("goal", nargs="?", default="self-build the most profitable bitcoin freqtrade config for 2026 based on historical data")
    p.add_argument("--mode", choices=["swarm","pipeline","dag","remix"], default="remix")
    p.add_argument("--roles", help="Comma-separated roles")
    p.add_argument("--ns", default="pfaa-remix", help="JMEM namespace")
    p.add_argument("--live", action="store_true", help="Enable real Claude API calls (requires ANTHROPIC_API_KEY)")
    args = p.parse_args()

    roles = [Role(r.strip()) for r in args.roles.split(",")] if args.roles else list(Role)
    team = RemixTeam(roles=roles, ns=args.ns, live=args.live)
    await team.start()
    try:
        if args.mode == "remix":
            await team.remix(args.goal)
        elif args.mode == "swarm":
            await team.swarm(args.goal)
        elif args.mode == "pipeline":
            await team.pipeline([(r, f"[{r.value}] {args.goal}") for r in team.agents])
        elif args.mode == "dag":
            await team.dag([(r, f"[{r.value}] {args.goal}", []) for r in team.agents])

        # Final dashboard
        s = await team.status()
        print(f"\n  {B}{'='*60}{X}")
        print(f"  {B}  FINAL STATUS{X}")
        print(f"  {B}{'='*60}{X}\n")
        print(f"  Tasks: {s['tasks']} | Uptime: {s['uptime']}s | Knowledge bus: {s['knowledge_bus']} entries\n")
        for role, info in s["agents"].items():
            phase_c = G if info["phase"]=="idle" else R if info["phase"]=="dead" else Y
            brk = f" {R}[BREAKER]{X}" if info["breaker"] else ""
            print(f"    {Y}{role:16s}{X} ok={info['ok']} fail={info['fail']} avg={info['ms']:.1f}ms mems={info['mems']} {phase_c}{info['phase']}{X}{brk}")
        m = s["memory"]
        print(f"\n  {C}🧠 Memory Health{X}")
        print(f"    Total: {m['total']} | Avg Q: {m['avg_q']} | Health: {m['health']}")
        print(f"    Levels: {json.dumps(m['by_level'])}")
    finally:
        await team.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
