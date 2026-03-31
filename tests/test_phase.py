"""Phase enum and phase transitions test suite."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from agent_setup_cli.core.phase import Phase, Transition, TRANSITIONS


class TestPhaseEnum:
    def test_all_phases_exist(self):
        assert Phase.VAPOR is not None
        assert Phase.LIQUID is not None
        assert Phase.SOLID is not None

    def test_phases_are_distinct(self):
        phases = [Phase.VAPOR, Phase.LIQUID, Phase.SOLID]
        assert len(set(phases)) == 3

    def test_spawn_cost_ordering(self):
        """VAPOR < LIQUID < SOLID in spawn cost."""
        assert Phase.VAPOR.spawn_cost_us < Phase.LIQUID.spawn_cost_us
        assert Phase.LIQUID.spawn_cost_us < Phase.SOLID.spawn_cost_us

    def test_spawn_cost_values(self):
        assert Phase.VAPOR.spawn_cost_us == 1
        assert Phase.LIQUID.spawn_cost_us == 10
        assert Phase.SOLID.spawn_cost_us == 1000

    def test_parallelism_vapor(self):
        assert "cooperative" in Phase.VAPOR.parallelism
        assert "I/O" in Phase.VAPOR.parallelism

    def test_parallelism_liquid(self):
        assert "preemptive" in Phase.LIQUID.parallelism
        assert "CPU" in Phase.LIQUID.parallelism

    def test_parallelism_solid(self):
        assert "isolated" in Phase.SOLID.parallelism
        assert "process" in Phase.SOLID.parallelism

    def test_all_phases_have_parallelism(self):
        for phase in Phase:
            assert isinstance(phase.parallelism, str)
            assert len(phase.parallelism) > 0

    def test_all_phases_have_spawn_cost(self):
        for phase in Phase:
            assert isinstance(phase.spawn_cost_us, int)
            assert phase.spawn_cost_us > 0


class TestTransition:
    def test_transition_is_named_tuple(self):
        t = Transition(Phase.VAPOR, Phase.LIQUID, "test reason")
        assert t.from_phase == Phase.VAPOR
        assert t.to_phase == Phase.LIQUID
        assert t.reason == "test reason"

    def test_transition_unpacking(self):
        t = Transition(Phase.SOLID, Phase.VAPOR, "done")
        from_p, to_p, reason = t
        assert from_p == Phase.SOLID
        assert to_p == Phase.VAPOR
        assert reason == "done"


class TestTransitionsTable:
    def test_all_six_transitions_exist(self):
        expected = {"condense", "freeze", "melt", "evaporate", "sublimate", "deposit"}
        assert set(TRANSITIONS.keys()) == expected

    def test_condense_vapor_to_liquid(self):
        t = TRANSITIONS["condense"]
        assert t.from_phase == Phase.VAPOR
        assert t.to_phase == Phase.LIQUID

    def test_freeze_liquid_to_solid(self):
        t = TRANSITIONS["freeze"]
        assert t.from_phase == Phase.LIQUID
        assert t.to_phase == Phase.SOLID

    def test_melt_solid_to_liquid(self):
        t = TRANSITIONS["melt"]
        assert t.from_phase == Phase.SOLID
        assert t.to_phase == Phase.LIQUID

    def test_evaporate_liquid_to_vapor(self):
        t = TRANSITIONS["evaporate"]
        assert t.from_phase == Phase.LIQUID
        assert t.to_phase == Phase.VAPOR

    def test_sublimate_vapor_to_solid(self):
        t = TRANSITIONS["sublimate"]
        assert t.from_phase == Phase.VAPOR
        assert t.to_phase == Phase.SOLID

    def test_deposit_solid_to_vapor(self):
        t = TRANSITIONS["deposit"]
        assert t.from_phase == Phase.SOLID
        assert t.to_phase == Phase.VAPOR

    def test_all_transitions_have_reasons(self):
        for name, t in TRANSITIONS.items():
            assert isinstance(t.reason, str)
            assert len(t.reason) > 0, f"Transition {name} has empty reason"

    def test_reverse_pairs_exist(self):
        """Each forward transition should have a reverse path."""
        forward_pairs = {(t.from_phase, t.to_phase) for t in TRANSITIONS.values()}
        reverse_pairs = {(t.to_phase, t.from_phase) for t in TRANSITIONS.values()}
        # Every from->to should have a to->from somewhere
        assert forward_pairs == reverse_pairs

    def test_all_phases_reachable(self):
        """Every phase should be reachable from every other phase (directly or indirectly)."""
        adjacency = {}
        for t in TRANSITIONS.values():
            adjacency.setdefault(t.from_phase, set()).add(t.to_phase)
        for start in Phase:
            reachable = set()
            frontier = {start}
            while frontier:
                current = frontier.pop()
                reachable.add(current)
                for neighbor in adjacency.get(current, set()):
                    if neighbor not in reachable:
                        frontier.add(neighbor)
            assert reachable == set(Phase), f"Not all phases reachable from {start}"
