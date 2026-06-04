"""GUI-driven lazy install of optional channel dependencies."""

from __future__ import annotations

import importlib
import logging

from myrm_agent_harness.runtime.lazy_deps import FeatureUnavailable, ensure

from app.channels.providers.registry import clear_cache
from app.channels.types import ChannelIssue

logger = logging.getLogger(__name__)

_CHANNEL_FEATURES: dict[str, tuple[str, ...]] = {
    "matrix": ("platform.matrix",),
}


def _features_for_channel(channel_name: str, issues: list[ChannelIssue]) -> tuple[str, ...]:
    base = _CHANNEL_FEATURES.get(channel_name, ())
    if channel_name == "matrix":
        extra: list[str] = []
        for issue in issues:
            fix = issue.fix or ""
            if "matrix-e2ee" in fix:
                extra.append("platform.matrix-e2ee")
                break
        return (*base, *extra)
    return base


def _reload_matrix_imports() -> None:
    import app.channels.providers.matrix.channel as matrix_channel

    importlib.reload(matrix_channel)


def install_channel_dependencies(channel_name: str, issues: list[ChannelIssue]) -> tuple[bool, str]:
    """Install lazy-deps for ``channel_name`` based on current diagnostic issues."""
    features = _features_for_channel(channel_name, issues)
    if not features:
        return False, f"Channel {channel_name!r} has no lazy-install mapping"

    errors: list[str] = []
    for feature in features:
        try:
            ensure(feature, prompt=False)
        except FeatureUnavailable as exc:
            errors.append(str(exc))

    if channel_name == "matrix":
        clear_cache()
        _reload_matrix_imports()

    if errors:
        return False, "; ".join(errors)
    return True, "Dependencies installed"
