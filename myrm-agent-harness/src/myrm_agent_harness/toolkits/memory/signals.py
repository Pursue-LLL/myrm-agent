"""Context signal calculation for memory retrieval scoring.


[INPUT]
- memory.types::{BaseMemory, MemoryType} (POS: memory data models)

[OUTPUT]
- SignalCalculator: Normalized [0,1] signal factors (recency, importance, preference, rating, confidence)
- get_default_half_life: Default half-life per memory type
- get_default_signal_weights: Default signal weight profiles, including each type's fixed prior

[POS]
Context signal calculator for memory retrieval scoring. Provides normalized [0,1] factors
for recency, importance, preference, rating and confidence. All signals are independent
and composable via weighted geometric mean. Recall counts are deliberately not a signal: every
returned hit is stamped, so a count measures exposure, and ranking on it would keep showing
whatever was shown first. Only the opt-in gravity decay (off by default) lets the count into
the recency term.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.types import BaseMemory, MemoryType


class SignalCalculator:
    """Calculates normalized context signals for memory scoring."""

    @staticmethod
    def recency_factor(memory: BaseMemory, half_life_days: float) -> float:
        """Calculate time-based recency factor using exponential decay.

        Args:
            memory: Memory object with created_at field
            half_life_days: Days until factor decays to 0.5 (0 = no decay)

        Returns:
            Factor in [0, 1] where 1 = just created, 0.5 = half_life old
        """
        if half_life_days <= 0:
            return 1.0
        if not hasattr(memory, "created_at"):
            return 1.0

        now = datetime.now(UTC)
        created = memory.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=UTC)
        age_days = (now - created).days
        if age_days < 0:
            return 1.0

        return math.exp(-math.log(2) * age_days / half_life_days)

    @staticmethod
    def gravity_decay_factor(
        memory: BaseMemory,
        gravity: float = 1.8,
        time_scale_hours: float = 24.0,
        interaction_weight: float = 0.15,
        quality_weight: float = 0.25,
    ) -> float:
        """Calculate continuous gravity decay factor using power-law model.

        Evaluates age with sub-hour precision, boosting items with higher
        access_count (interactions) and higher rating/importance (quality).

        Args:
            memory: Memory object with created_at, access_count, and rating fields.
            gravity: Power-law decay exponent.
            time_scale_hours: Scaling factor for elapsed hours.
            interaction_weight: Boost weight per interaction/access.
            quality_weight: Boost weight for quality rating.

        Returns:
            Continuous positive factor in (0.0, +inf).
        """
        if not hasattr(memory, "created_at"):
            return 1.0

        created = memory.created_at
        interactions = getattr(memory, "access_count", 0) or 0
        rating = getattr(memory, "rating", 0.0) or 0.0
        importance = getattr(memory, "importance_score", 0.0) or 0.0
        quality = max(rating, importance)

        from myrm_agent_harness.toolkits.memory.strategies.gravity_decay import (
            GravityDecayConfig,
            compute_gravity_decay,
        )

        cfg = GravityDecayConfig(
            gravity=gravity,
            time_scale_hours=time_scale_hours,
            interaction_weight=interaction_weight,
            quality_weight=quality_weight,
        )
        return compute_gravity_decay(
            created,
            interactions=interactions,
            quality_score=quality,
            config=cfg,
        )

    @staticmethod
    def importance_factor(memory: BaseMemory) -> float:
        """Extract importance factor from memory.

        Args:
            memory: Memory object with optional importance field

        Returns:
            Factor in [0, 1], defaults to 0.5 if not present
        """
        return max(0.0, min(1.0, getattr(memory, "importance", 0.5)))

    @staticmethod
    def preference_factor(memory: BaseMemory) -> float:
        """Extract preference strength factor from memory.

        Args:
            memory: Memory object with optional preference_strength field

        Returns:
            Factor in [0, 1], defaults to 0.0 if not present
        """
        return max(0.0, min(1.0, getattr(memory, "preference_strength", 0.0)))

    @staticmethod
    def rating_factor(memory: BaseMemory) -> float:
        """Extract user feedback rating factor from memory.

        Args:
            memory: Memory object with optional user_rating field

        Returns:
            Factor in [0, 1], defaults to 0.5 (neutral) if not present
        """
        return max(0.0, min(1.0, getattr(memory, "user_rating", 0.5)))

    @staticmethod
    def confidence_factor(memory: BaseMemory) -> float:
        """Extract confidence factor from memory.

        Args:
            memory: Memory object with optional confidence field

        Returns:
            Factor in [0, 1], defaults to 1.0 if not present
        """
        return max(0.0, min(1.0, getattr(memory, "confidence", 1.0)))

    @staticmethod
    def temporal_proximity_factor(
        memory: BaseMemory, reference_time: datetime | None = None, threshold_hours: float = 24.0
    ) -> float:
        """Calculate temporal proximity to reference time (MemPalace enhancement).

        Gives extra boost to memories created close to the reference time.
        Different from recency_factor: proximity is relative to query time,
        recency is relative to current time.

        Args:
            memory: Memory object with created_at/timestamp field
            reference_time: Reference time (defaults to now)
            threshold_hours: Hours within which proximity boost applies

        Returns:
            Proximity factor in [0, 1] where 1 = same time, 0 = beyond threshold
        """
        if reference_time is None:
            reference_time = datetime.now(UTC)

        memory_time = getattr(memory, "timestamp", None) or getattr(memory, "created_at", None)
        if not memory_time:
            return 0.0

        if memory_time.tzinfo is None:
            memory_time = memory_time.replace(tzinfo=UTC)
        if reference_time.tzinfo is None:
            reference_time = reference_time.replace(tzinfo=UTC)

        delta_hours: float = abs((memory_time - reference_time).total_seconds()) / 3600.0
        if delta_hours >= threshold_hours:
            return 0.0

        return 1.0 - (delta_hours / threshold_hours)


def get_default_signal_weights(memory_type: MemoryType) -> dict[str, float]:
    """Get type-specific signal weights for geometric mean scoring.

    Each profile sums to 1.0. ``type_prior`` is the exponent of a constant signal, so it is a fixed
    per-type discount (none for profile, small for semantic and claim, largest for episodic and
    procedural) that does not depend on the individual memory.

    Args:
        memory_type: Memory type

    Returns:
        Signal name to weight mapping
    """
    weights = {
        "PROFILE": {
            "semantic": 0.20,
            "recency": 0.00,
            "type_prior": 0.00,
            "importance": 0.25,
            "preference": 0.45,
            "rating": 0.10,
        },
        "SEMANTIC": {
            "semantic": 0.65,
            "recency": 0.10,
            "type_prior": 0.05,
            "importance": 0.08,
            "preference": 0.00,
            "rating": 0.12,
        },
        "CLAIM": {
            "semantic": 0.55,
            "recency": 0.18,
            "type_prior": 0.05,
            "importance": 0.12,
            "preference": 0.00,
            "rating": 0.10,
        },
        "EPISODIC": {
            "semantic": 0.40,
            "recency": 0.25,
            "type_prior": 0.12,
            "importance": 0.08,
            "preference": 0.00,
            "rating": 0.15,
        },
        "PROCEDURAL": {
            "semantic": 0.30,
            "recency": 0.00,
            "type_prior": 0.12,
            "importance": 0.45,
            "preference": 0.00,
            "rating": 0.13,
        },
    }
    return weights.get(memory_type.upper(), weights["SEMANTIC"])


def get_default_half_life(memory_type: MemoryType) -> float:
    """Get type-specific recency decay half-life.

    Args:
        memory_type: Memory type

    Returns:
        Half-life in days (0 = no decay)
    """
    half_lives = {
        "PROFILE": 0.0,
        "SEMANTIC": 30.0,
        "CLAIM": 14.0,
        "EPISODIC": 7.0,
        "PROCEDURAL": 0.0,
    }
    return half_lives.get(memory_type.upper(), 30.0)
