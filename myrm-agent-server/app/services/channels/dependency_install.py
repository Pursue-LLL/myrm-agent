"""GUI-driven lazy install of optional channel dependencies.

[INPUT]
- myrm_agent_harness.runtime.lazy_deps::ensure, feature_missing (POS: Allowlisted venv lazy install)
- app.channels.providers.registry::get_channel_spec, clear_cache (POS: Central channel provider registry)

[OUTPUT]
- install_channel_dependencies: pip-install optional SDK wheels for a channel
- ensure_channel_dependencies_ready: Preflight before enable/toggle

[POS]
Server business layer for Settings one-click channel SDK installation.
"""

from __future__ import annotations

import importlib
import logging
from pathlib import Path

from filelock import FileLock, Timeout
from myrm_agent_harness.runtime.lazy_deps import FeatureUnavailable, ensure, feature_missing

from app.channels.providers.registry import clear_cache
from app.channels.types import ChannelIssue, IssueKind
from app.config.settings import settings

logger = logging.getLogger(__name__)

_INSTALL_LOCK_PATH = Path(settings.database.state_dir) / ".channel_dependency_install.lock"

# Modules to reload after installing SDK wheels (import-time guards refresh).
_CHANNEL_RELOAD_MODULES: dict[str, tuple[str, ...]] = {
    "matrix": ("app.channels.providers.matrix.channel",),
    "discord": ("app.channels.providers.discord.channel",),
    "feishu": (
        "app.channels.providers.feishu.channel",
        "app.channels.providers.feishu.ws_transport",
    ),
}


def _resolve_lazy_features(channel_name: str, issues: list[ChannelIssue]) -> tuple[str, ...]:
    """Map channel + diagnostic issues to harness lazy_deps feature keys."""
    from app.channels.providers.registry import get_channel_spec

    spec = get_channel_spec(channel_name)
    if spec is None or not spec.sdk_package:
        return ()

    pkg = spec.sdk_package.lower()
    features: list[str] = []
    if pkg == "mautrix":
        features.append("platform.matrix")
        for issue in issues:
            if issue.kind == IssueKind.DEPENDENCY and "matrix-e2ee" in (issue.fix or ""):
                features.append("platform.matrix-e2ee")
                break
    elif pkg == "discord.py":
        features.append("platform.discord")
    elif pkg == "lark-oapi":
        features.append("platform.feishu")
    return tuple(features)


def _features_need_install(features: tuple[str, ...]) -> bool:
    return any(feature_missing(feature) for feature in features)


def _reload_channel_modules(channel_name: str) -> None:
    for module_name in _CHANNEL_RELOAD_MODULES.get(channel_name, ()):
        module = importlib.import_module(module_name)
        importlib.reload(module)


def _run_install(features: tuple[str, ...]) -> tuple[bool, str]:
    errors: list[str] = []
    for feature in features:
        try:
            ensure(feature, prompt=False)
        except FeatureUnavailable as exc:
            errors.append(str(exc))
    if errors:
        return False, "; ".join(errors)
    return True, "Dependencies installed"


def install_channel_dependencies(channel_name: str, issues: list[ChannelIssue]) -> tuple[bool, str]:
    """Install lazy-deps for ``channel_name`` based on diagnostics."""
    features = _resolve_lazy_features(channel_name, issues)
    if not features:
        return False, f"Channel {channel_name!r} has no lazy-install mapping"

    _INSTALL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    lock = FileLock(str(_INSTALL_LOCK_PATH), timeout=300)
    try:
        with lock:
            ok, message = _run_install(features)
    except Timeout:
        return False, "Another dependency install is in progress; try again shortly"

    if ok:
        clear_cache()
        _reload_channel_modules(channel_name)
    return ok, message


def ensure_channel_dependencies_ready(channel_name: str, issues: list[ChannelIssue]) -> tuple[bool, str]:
    """Ensure optional deps are present before enabling a channel (no-op if already satisfied)."""
    features = _resolve_lazy_features(channel_name, issues)
    if not features or not _features_need_install(features):
        return True, ""
    return install_channel_dependencies(channel_name, issues)
