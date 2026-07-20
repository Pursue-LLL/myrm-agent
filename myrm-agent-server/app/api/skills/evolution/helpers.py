"""Evolution API helpers shared by router modules."""

from __future__ import annotations


def _evolution_lineage_id(evolution_id: str) -> str:
    return f"evolution:{evolution_id}"
