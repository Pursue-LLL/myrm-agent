"""Onboarding insight service package.

[INPUT]
- .service: OnboardingInsightService, get_onboarding_insight_service

[OUTPUT]
- Public exports for onboarding memory services.

[POS]
Service package facade for agent onboarding insight coordination.
"""

from __future__ import annotations

from .service import OnboardingInsightService, get_onboarding_insight_service

__all__ = [
    "OnboardingInsightService",
    "get_onboarding_insight_service",
]
