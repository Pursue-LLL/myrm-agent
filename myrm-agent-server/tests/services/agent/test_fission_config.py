"""Tests for swarm fission server configuration helpers."""

from __future__ import annotations

from app.services.agent.fission_config import max_parallel_from_engine_params


def test_max_parallel_from_engine_params_default() -> None:
    assert max_parallel_from_engine_params(None) == 3


def test_max_parallel_from_engine_params_clamped() -> None:
    assert max_parallel_from_engine_params({"max_parallel_fission": 5}) == 5
    assert max_parallel_from_engine_params({"max_parallel_fission": 99}) == 5
    assert max_parallel_from_engine_params({"max_parallel_fission": "4"}) == 4
