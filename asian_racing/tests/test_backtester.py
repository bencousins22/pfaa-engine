"""
Unit tests for the backtester module.
"""

from __future__ import annotations

import numpy as np
import pytest

from asian_racing.src.backtester import (
    _kelly_fraction,
    _edge_filter,
    _get_takeout,
    KELLY_FRACTION,
)


class TestKellyFraction:
    def test_no_edge(self):
        """No edge should return zero stake."""
        assert _kelly_fraction(0.1, 5.0) == 0.0  # p*SP = 0.5 < 1

    def test_positive_edge(self):
        """Positive edge should return positive stake."""
        f = _kelly_fraction(0.3, 5.0)  # p*SP = 1.5, edge = 0.5
        assert f > 0
        assert f <= KELLY_FRACTION

    def test_capped_at_quarter_kelly(self):
        """Stake should never exceed quarter Kelly."""
        f = _kelly_fraction(0.9, 10.0)
        assert f <= KELLY_FRACTION

    def test_zero_probability(self):
        assert _kelly_fraction(0.0, 5.0) == 0.0

    def test_odds_at_one(self):
        assert _kelly_fraction(0.5, 1.0) == 0.0


class TestEdgeFilter:
    def test_sufficient_edge(self):
        """p * (SP+1) >= 1.05 should pass."""
        assert _edge_filter(0.2, 6.0)  # 0.2 * 7 = 1.4

    def test_insufficient_edge(self):
        """p * (SP+1) < 1.05 should fail."""
        assert not _edge_filter(0.1, 3.0)  # 0.1 * 4 = 0.4


class TestTakeout:
    def test_hk_takeout(self):
        assert _get_takeout("HK") == 0.175

    def test_jra_takeout(self):
        assert _get_takeout("JRA") == 0.20

    def test_default_takeout(self):
        assert _get_takeout("UNKNOWN") == 0.20
