"""
Aussie Agents Meta-Learning Memory System — Level 5+ Self-Improving Memory

This isn't a simple key-value store. It's a FIVE-LAYER memory architecture
where each layer feeds back into the layers below, creating a self-improving
loop that gets smarter with every execution.

Memory Layers:
    L1 — EPISODIC:  Raw execution traces (what happened)
    L2 — SEMANTIC:  Extracted patterns (what works)
    L3 — STRATEGIC: Optimized phase selections (how to do it better)
    L4 — META:      Learning-rate tuning (how to learn better)
    L5 — EMERGENT:  Cross-agent knowledge synthesis (collective intelligence)

The key insight: L4 watches L3 watching L2 watching L1. When L3's
predictions improve execution speed, L4 reinforces that learning path.
When they don't, L4 adjusts the learning rate. This is genuine
meta-learning — the system learns HOW to learn.

Python 3.15 features:
    - frozendict: immutable memory snapshots for thread-safe reads
    - lazy import: numpy/stats only loaded if statistical analysis needed
    - PEP 798 unpacking: [*traces for traces in episodes] for aggregation
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any

import json
import hashlib
import statistics

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.agent import TaskResult

logger = logging.getLogger("pfaa.memory")


# ═══════════════════════════════════════════════════════════════════
# L1 — EPISODIC MEMORY: Raw execution traces
# ═══════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class Episode:
    """A single execution trace — the rawest form of memory."""
    timestamp_ns: int
    tool_name: str
    phase_used: Phase
    args_hash: str
    elapsed_us: int
    success: bool
    transitions: list[str]
    result_summary: str  # truncated result for pattern matching

    def to_frozen(self) -> frozendict:
        return frozendict(
            tool=self.tool_name,
            phase=self.phase_used.name,
            elapsed_us=self.elapsed_us,
            success=self.success,
        )


class EpisodicMemory:
    """L1: Stores raw execution episodes. Ring buffer — old memories fade."""

    def __init__(self, capacity: int = 10_000):
        self._episodes: deque[Episode] = deque(maxlen=capacity)
        self._by_tool: dict[str, deque[Episode]] = defaultdict(
            lambda: deque(maxlen=1000)
        )

    def record(self, result: TaskResult, tool_name: str, args: tuple) -> Episode:
        args_str = str(args)[:200]
        args_hash = hashlib.sha256(args_str.encode()).hexdigest()[:12]

        episode = Episode(
            timestamp_ns=time.perf_counter_ns(),
            tool_name=tool_name,
            phase_used=result.phase_used,
            args_hash=args_hash,
            elapsed_us=result.elapsed_us,
            success=not isinstance(result.result, Exception),
            transitions=result.transitions,
            result_summary=str(result.result)[:200],
        )
        self._episodes.append(episode)
        self._by_tool[tool_name].append(episode)
        return episode

    def recent(self, n: int = 100) -> list[Episode]:
        return list(self._episodes)[-n:]

    def by_tool(self, tool_name: str) -> list[Episode]:
        return list(self._by_tool.get(tool_name, []))

    @property
    def total_episodes(self) -> int:
        return len(self._episodes)


# ═══════════════════════════════════════════════════════════════════
# L2 — SEMANTIC MEMORY: Extracted patterns
# ═══════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class ToolPattern:
    """Extracted pattern about a tool's behavior."""
    tool_name: str
    avg_elapsed_us: float
    p50_elapsed_us: float
    p95_elapsed_us: float
    success_rate: float
    best_phase: Phase
    phase_performance: dict[str, float]  # phase_name → avg_elapsed_us
    sample_size: int
    last_updated_ns: int

    def confidence(self) -> float:
        """How confident are we in this pattern? (0-1)"""
        # More samples = more confidence, diminishing returns
        return min(1.0, math.log2(max(1, self.sample_size)) / 10.0)


class SemanticMemory:
    """L2: Extracts and maintains patterns from episodic memory."""

    def __init__(self):
        self._patterns: dict[str, ToolPattern] = {}

    def extract(self, episodic: EpisodicMemory) -> dict[str, ToolPattern]:
        """Re-extract all patterns from episodic memory."""
        tool_names = set()
        for ep in episodic.recent(10_000):
            tool_names.add(ep.tool_name)

        for tool_name in tool_names:
            episodes = episodic.by_tool(tool_name)
            if len(episodes) < 2:
                continue

            elapsed_values = [ep.elapsed_us for ep in episodes]
            successes = sum(1 for ep in episodes if ep.success)

            # Performance by phase
            phase_perf: dict[str, list[int]] = defaultdict(list)
            for ep in episodes:
                phase_perf[ep.phase_used.name].append(ep.elapsed_us)

            phase_avg = {
                phase: statistics.mean(times)
                for phase, times in phase_perf.items()
            }

            # Find best phase
            best_phase_name = min(phase_avg, key=phase_avg.get)
            best_phase = Phase[best_phase_name]

            sorted_elapsed = sorted(elapsed_values)
            p50_idx = len(sorted_elapsed) // 2
            p95_idx = int(len(sorted_elapsed) * 0.95)

            pattern = ToolPattern(
                tool_name=tool_name,
                avg_elapsed_us=statistics.mean(elapsed_values),
                p50_elapsed_us=sorted_elapsed[p50_idx],
                p95_elapsed_us=sorted_elapsed[min(p95_idx, len(sorted_elapsed) - 1)],
                success_rate=successes / len(episodes),
                best_phase=best_phase,
                phase_performance=phase_avg,
                sample_size=len(episodes),
                last_updated_ns=time.perf_counter_ns(),
            )
            self._patterns[tool_name] = pattern

        return dict(self._patterns)

    def get_pattern(self, tool_name: str) -> ToolPattern | None:
        return self._patterns.get(tool_name)

    def recommend_phase(self, tool_name: str) -> Phase | None:
        """Based on observed patterns, recommend the best phase for a tool."""
        pattern = self._patterns.get(tool_name)
        if pattern is None or pattern.confidence() < 0.3:
            return None  # not enough data
        return pattern.best_phase


# ═══════════════════════════════════════════════════════════════════
# L3 — STRATEGIC MEMORY: Phase selection optimization
# ═══════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class PhaseStrategy:
    """Learned strategy for phase selection."""
    tool_name: str
    default_phase: Phase
    override_phase: Phase | None  # learned better phase
    confidence: float
    speedup_factor: float  # how much faster the override is
    times_applied: int = 0
    times_improved: int = 0

    @property
    def effectiveness(self) -> float:
        if self.times_applied == 0:
            return 0.0
        return self.times_improved / self.times_applied


class StrategicMemory:
    """L3: Learns optimal phase selection strategies."""

    def __init__(self):
        self._strategies: dict[str, PhaseStrategy] = {}
        self._prediction_log: deque[tuple[str, Phase, Phase, bool]] = deque(maxlen=1000)

    def learn(self, semantic: SemanticMemory) -> dict[str, PhaseStrategy]:
        """Derive phase strategies from semantic patterns."""
        for tool_name, pattern in semantic._patterns.items():
            if pattern.confidence() < 0.3:
                continue

            # Check if a different phase is significantly better
            if len(pattern.phase_performance) < 2:
                continue

            # Find the declared default phase vs. empirically best phase
            sorted_phases = sorted(
                pattern.phase_performance.items(), key=lambda x: x[1]
            )
            best_name, best_time = sorted_phases[0]
            worst_name, worst_time = sorted_phases[-1]

            if best_time > 0 and worst_time / best_time > 1.2:
                # 20%+ improvement — worth learning
                speedup = worst_time / best_time
                strategy = PhaseStrategy(
                    tool_name=tool_name,
                    default_phase=Phase[worst_name],
                    override_phase=Phase[best_name],
                    confidence=pattern.confidence(),
                    speedup_factor=speedup,
                )
                self._strategies[tool_name] = strategy
                logger.info(
                    "L3 learned: %s runs %.1fx faster in %s vs %s",
                    tool_name, speedup, best_name, worst_name,
                )

        return dict(self._strategies)

    def prune_stale(self, async_tool_names: set[str]) -> list[str]:
        """Remove strategies for async tools (VAPOR↔LIQUID is meaningless for them).

        These strategies were learned before the exploration fix that locked
        async tools to their declared phase. They show inflated speedups
        (e.g., 963x) because they measured run_in_executor overhead, not
        a real phase difference.
        """
        pruned = []
        for name in list(self._strategies.keys()):
            if name in async_tool_names:
                del self._strategies[name]
                pruned.append(name)
        return pruned

    def predict_phase(self, tool_name: str) -> Phase | None:
        """Predict the optimal phase for a tool based on learned strategies."""
        strategy = self._strategies.get(tool_name)
        if strategy is None:
            return None
        if strategy.confidence < 0.5:
            return None
        return strategy.override_phase

    def record_prediction(
        self, tool_name: str, predicted: Phase, actual_best: Phase, improved: bool
    ) -> None:
        """Record whether a prediction led to improvement."""
        self._prediction_log.append((tool_name, predicted, actual_best, improved))
        strategy = self._strategies.get(tool_name)
        if strategy:
            strategy.times_applied += 1
            if improved:
                strategy.times_improved += 1


# ═══════════════════════════════════════════════════════════════════
# L4 — META-MEMORY: Learning how to learn
# ═══════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class MetaInsight:
    """An insight about the learning process itself."""
    category: str  # e.g., "learning_rate", "pattern_quality", "strategy_drift"
    observation: str
    adjustment: str
    timestamp_ns: int
    confidence: float


class MetaMemory:
    """
    L4: Meta-learning — observes L3's predictions and adjusts learning behavior.

    This layer watches:
    - Are L3's phase predictions improving execution speed?
    - Is the learning rate appropriate? (too fast = noisy, too slow = slow)
    - Are patterns stable or drifting? (workload changes)
    - Should we trust old episodes or weight recent ones more?
    """

    def __init__(self):
        self._insights: deque[MetaInsight] = deque(maxlen=500)
        self._learning_rate: float = 0.1  # EMA decay factor
        self._pattern_stability: dict[str, float] = {}  # tool → stability score
        self._prediction_accuracy_window: deque[bool] = deque(maxlen=100)

    def observe(self, strategic: StrategicMemory) -> list[MetaInsight]:
        """Observe L3's performance and generate meta-insights."""
        insights: list[MetaInsight] = []
        now = time.perf_counter_ns()

        # 1. Check prediction accuracy trend
        recent_predictions = list(strategic._prediction_log)[-50:]
        if len(recent_predictions) >= 10:
            accuracy = sum(1 for _, _, _, ok in recent_predictions if ok) / len(recent_predictions)
            self._prediction_accuracy_window.append(accuracy > 0.5)

            if accuracy < 0.3:
                insight = MetaInsight(
                    category="prediction_quality",
                    observation=f"L3 prediction accuracy dropped to {accuracy:.0%}",
                    adjustment="Increasing learning rate to adapt faster",
                    timestamp_ns=now,
                    confidence=0.8,
                )
                self._learning_rate = min(0.5, self._learning_rate * 1.5)
                insights.append(insight)

            elif accuracy > 0.8:
                insight = MetaInsight(
                    category="prediction_quality",
                    observation=f"L3 predictions are {accuracy:.0%} accurate",
                    adjustment="Decreasing learning rate to stabilize",
                    timestamp_ns=now,
                    confidence=0.9,
                )
                self._learning_rate = max(0.01, self._learning_rate * 0.8)
                insights.append(insight)

        # 2. Check strategy effectiveness
        for tool_name, strategy in strategic._strategies.items():
            if strategy.times_applied >= 5:
                eff = strategy.effectiveness
                if eff < 0.3:
                    insight = MetaInsight(
                        category="strategy_drift",
                        observation=f"Strategy for {tool_name} only {eff:.0%} effective",
                        adjustment="Resetting strategy — workload may have changed",
                        timestamp_ns=now,
                        confidence=0.7,
                    )
                    insights.append(insight)
                elif eff > 0.9:
                    insight = MetaInsight(
                        category="strategy_stable",
                        observation=f"Strategy for {tool_name} is {eff:.0%} effective",
                        adjustment="Strategy is mature — reducing update frequency",
                        timestamp_ns=now,
                        confidence=0.95,
                    )
                    insights.append(insight)

        for insight in insights:
            self._insights.append(insight)
            logger.info("L4 Meta: [%s] %s → %s", insight.category, insight.observation, insight.adjustment)

        return insights

    @property
    def learning_rate(self) -> float:
        return self._learning_rate

    @property
    def recent_insights(self) -> list[MetaInsight]:
        return list(self._insights)[-20:]


# ═══════════════════════════════════════════════════════════════════
# L5 — EMERGENT MEMORY: Cross-agent collective intelligence
# ═══════════════════════════════════════════════════════════════════

@dataclass(slots=True)
class EmergentKnowledge:
    """Knowledge that emerges from observing multiple agents collectively."""
    pattern: str
    agents_observed: int
    consensus_confidence: float
    discovery_ns: int
    description: str


class EmergentMemory:
    """
    L5: Synthesizes knowledge across all agents — collective intelligence.

    Detects patterns like:
    - "When tool X runs after tool Y, it's 40% faster" (temporal coupling)
    - "Tools A, B, C always run together" (task clustering)
    - "Phase transitions cost more than staying in-phase" (efficiency rules)
    - "This workload pattern repeats every N executions" (cyclical behavior)
    """

    def __init__(self):
        self._knowledge: list[EmergentKnowledge] = []
        self._tool_cooccurrence: dict[tuple[str, str], int] = defaultdict(int)
        self._sequence_patterns: dict[tuple[str, ...], int] = defaultdict(int)

    def synthesize(self, episodic: EpisodicMemory) -> list[EmergentKnowledge]:
        """Analyze episodic memory for emergent patterns.

        Fixed: uses ALL episodes (not just last 1000), resets counters
        each cycle to avoid stale accumulation, and deduplicates discoveries.
        """
        discoveries: list[EmergentKnowledge] = []
        now = time.perf_counter_ns()
        episodes = episodic.recent(10000)  # use all available

        if len(episodes) < 10:
            return discoveries

        # Reset counters each cycle for fresh analysis
        self._tool_cooccurrence.clear()
        self._sequence_patterns.clear()
        existing_descriptions = {k.description for k in self._knowledge}

        # 1. Tool co-occurrence patterns
        window_size = 5
        for i in range(len(episodes) - window_size):
            window = episodes[i:i + window_size]
            tools_in_window = [ep.tool_name for ep in window]
            for j, t1 in enumerate(tools_in_window):
                for t2 in tools_in_window[j + 1:]:
                    pair = tuple(sorted([t1, t2]))
                    self._tool_cooccurrence[pair] += 1

        # Find strongly co-occurring tools
        if self._tool_cooccurrence:
            max_count = max(self._tool_cooccurrence.values())
            for pair, count in self._tool_cooccurrence.items():
                if count > max_count * 0.5 and count >= 10:
                    discoveries.append(EmergentKnowledge(
                        pattern="tool_coupling",
                        agents_observed=count,
                        consensus_confidence=count / max_count,
                        discovery_ns=now,
                        description=f"{pair[0]} and {pair[1]} frequently co-occur ({count} times)",
                    ))

        # 2. Sequential patterns (bigrams)
        for i in range(len(episodes) - 1):
            bigram = (episodes[i].tool_name, episodes[i + 1].tool_name)
            self._sequence_patterns[bigram] += 1

        # Find common sequences
        for sequence, count in self._sequence_patterns.items():
            if count >= 5:
                discoveries.append(EmergentKnowledge(
                    pattern="sequence",
                    agents_observed=count,
                    consensus_confidence=min(1.0, count / 20.0),
                    discovery_ns=now,
                    description=f"{sequence[0]} → {sequence[1]} occurs {count} times",
                ))

        # 3. Phase transition cost analysis
        transition_costs: dict[str, list[int]] = defaultdict(list)
        no_transition_costs: dict[str, list[int]] = defaultdict(list)
        for ep in episodes:
            if ep.transitions:
                transition_costs[ep.tool_name].append(ep.elapsed_us)
            else:
                no_transition_costs[ep.tool_name].append(ep.elapsed_us)

        for tool_name in set(transition_costs) & set(no_transition_costs):
            with_t = statistics.mean(transition_costs[tool_name])
            without_t = statistics.mean(no_transition_costs[tool_name])
            if with_t > without_t * 1.3 and len(transition_costs[tool_name]) >= 3:
                overhead = (with_t - without_t) / without_t * 100
                discoveries.append(EmergentKnowledge(
                    pattern="transition_overhead",
                    agents_observed=len(transition_costs[tool_name]),
                    consensus_confidence=0.7,
                    discovery_ns=now,
                    description=(
                        f"Phase transitions add {overhead:.0f}% overhead to {tool_name}. "
                        f"Consider pre-selecting the optimal phase."
                    ),
                ))

        # Deduplicate against existing knowledge
        new_discoveries = [d for d in discoveries if d.description not in existing_descriptions]
        self._knowledge.extend(new_discoveries)
        return new_discoveries

    @property
    def all_knowledge(self) -> list[EmergentKnowledge]:
        return list(self._knowledge)


# ═══════════════════════════════════════════════════════════════════
# UNIFIED MEMORY SYSTEM — Integrates all 5 layers
# ═══════════════════════════════════════════════════════════════════

class MemorySystem:
    """
    The unified 5-layer memory system.

    Feedback loop:
        L1 (episodes) → L2 (patterns) → L3 (strategies) → L4 (meta) → L5 (emergent)
              ↑                                                              │
              └──────────────── influences future episodes ─────────────────┘
    """

    def __init__(self, episodic_capacity: int = 10_000):
        self.l1_episodic = EpisodicMemory(capacity=episodic_capacity)
        self.l2_semantic = SemanticMemory()
        self.l3_strategic = StrategicMemory()
        self.l4_meta = MetaMemory()
        self.l5_emergent = EmergentMemory()
        self._update_interval = 50  # re-learn every N episodes
        self._episodes_since_update = 0
        # Names of async tools — strategies for these are pruned
        # because VAPOR↔LIQUID are identical for coroutines
        self._async_tool_names: set[str] = set()

    def register_async_tools(self, names: set[str]) -> None:
        """Register tool names that are async (coroutine functions).
        Strategies for these tools will be pruned during learning."""
        self._async_tool_names = names

    def record(self, result: TaskResult, tool_name: str, args: tuple) -> Episode:
        """Record an execution and trigger learning if needed."""
        episode = self.l1_episodic.record(result, tool_name, args)
        self._episodes_since_update += 1

        if self._episodes_since_update >= self._update_interval:
            self._learn_cycle()
            self._episodes_since_update = 0

        return episode

    def _learn_cycle(self) -> None:
        """Run one full learning cycle across all layers."""
        logger.debug("Memory learning cycle starting...")

        # L1 → L2: Extract patterns from episodes
        self.l2_semantic.extract(self.l1_episodic)

        # L2 → L3: Derive strategies from patterns
        self.l3_strategic.learn(self.l2_semantic)

        # Prune stale strategies for async tools
        # (VAPOR↔LIQUID is identical for async fns — no real phase difference)
        self.l3_strategic.prune_stale(self._async_tool_names)

        # L3 → L4: Meta-observe strategy effectiveness
        insights = self.l4_meta.observe(self.l3_strategic)

        # L1 → L5: Synthesize emergent knowledge
        emergent = self.l5_emergent.synthesize(self.l1_episodic)

        if insights:
            logger.info("L4 generated %d meta-insights", len(insights))
        if emergent:
            logger.info("L5 discovered %d emergent patterns", len(emergent))

    def recommend_phase(self, tool_name: str) -> Phase | None:
        """Get the best phase recommendation from all memory layers."""
        # L3 strategic recommendation (learned from experience)
        strategic = self.l3_strategic.predict_phase(tool_name)
        if strategic:
            return strategic

        # L2 semantic recommendation (statistical best)
        semantic = self.l2_semantic.recommend_phase(tool_name)
        if semantic:
            return semantic

        return None

    def force_learn(self) -> None:
        """Force a learning cycle (useful for testing)."""
        self._learn_cycle()

    def status(self) -> dict[str, Any]:
        return {
            "l1_episodes": self.l1_episodic.total_episodes,
            "l2_patterns": len(self.l2_semantic._patterns),
            "l3_strategies": len(self.l3_strategic._strategies),
            "l4_learning_rate": self.l4_meta.learning_rate,
            "l4_insights": len(self.l4_meta.recent_insights),
            "l5_knowledge": len(self.l5_emergent.all_knowledge),
            "update_interval": self._update_interval,
        }

    def dump(self) -> dict[str, Any]:
        """Full memory dump for persistence."""
        return {
            "status": self.status(),
            "patterns": {
                name: {
                    "avg_us": p.avg_elapsed_us,
                    "p50_us": p.p50_elapsed_us,
                    "p95_us": p.p95_elapsed_us,
                    "success_rate": p.success_rate,
                    "best_phase": p.best_phase.name,
                    "confidence": p.confidence(),
                    "samples": p.sample_size,
                }
                for name, p in self.l2_semantic._patterns.items()
            },
            "strategies": {
                name: {
                    "default": s.default_phase.name,
                    "override": s.override_phase.name if s.override_phase else None,
                    "speedup": s.speedup_factor,
                    "effectiveness": s.effectiveness,
                }
                for name, s in self.l3_strategic._strategies.items()
            },
            "meta_insights": [
                {
                    "category": i.category,
                    "observation": i.observation,
                    "adjustment": i.adjustment,
                }
                for i in self.l4_meta.recent_insights
            ],
            "emergent_knowledge": [
                {
                    "pattern": k.pattern,
                    "description": k.description,
                    "confidence": k.consensus_confidence,
                }
                for k in self.l5_emergent.all_knowledge[-20:]
            ],
        }
