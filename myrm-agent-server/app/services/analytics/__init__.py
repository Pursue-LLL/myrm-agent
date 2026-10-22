"""Analytics domain services.

[INPUT]
- app.services.analytics.roi_service::RoiAnalyticsService, RoiMetricsSnapshot

[OUTPUT]
- RoiAnalyticsService, RoiMetricsSnapshot, HighYieldRoutineSpec, CategorySavingsItem, WeeklyDigestSpec

[POS]
app/services/analytics/__init__.py - Facade for analytics domain.
"""

from .roi_service import (
    RoiAnalyticsService,
    RoiMetricsSnapshot,
    HighYieldRoutineSpec,
    CategorySavingsItem,
    WeeklyDigestSpec,
)

__all__ = [
    "RoiAnalyticsService",
    "RoiMetricsSnapshot",
    "HighYieldRoutineSpec",
    "CategorySavingsItem",
    "WeeklyDigestSpec",
]
