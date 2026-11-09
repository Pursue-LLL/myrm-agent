"""Prompt budgeting data models.

[INPUT]
- (none)

[OUTPUT]
- CHARS_PER_TOKEN: the characters-per-token estimate behind every character budget of the memory block.
- BudgetedSection: a titled group of items that competes with other groups for one prompt budget.

[POS]
Prompt budgeting data models.
"""

from __future__ import annotations

from dataclasses import dataclass

# Approximate characters per token (conservative)
CHARS_PER_TOKEN = 4


@dataclass
class BudgetedSection:
    title: str
    items: list[str]
    priority: int  # Lower number = higher priority to keep
