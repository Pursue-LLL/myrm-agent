"""Desktop trust stores — workspace persistence for approvals and denials.

[INPUT]
- app.ai_agents.desktop_control.registry::_DENY_FILE (POS: approval ledger constants)
- app.ai_agents.desktop_control.gate::DesktopControlGate (POS: runtime permission callback; lazy import, live-gate enumeration only)

[OUTPUT]
- list_trusted_desktop_apps / revoke_trusted_desktop_app: merged live-gate plus on-disk trust management
- load_denied_keys: operator persistent-denial file reader (workspace scope)
- trust_store_workspace_roots: workspace-root discovery across live gates,
  harness layout, and fallback root

[POS]
Server-layer desktop trust persistence. Owns every workspace file touch for
desktop approvals; runtime policy stays in gate.py.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Collection
from pathlib import Path
from typing import TypedDict

from app.ai_agents.desktop_control.registry import _DENY_FILE

logger = logging.getLogger(__name__)

_APPROVAL_DIR = ".agent/desktop_control"
_APPROVAL_FILE = "approved_apps.json"


class TrustedAppRecord(TypedDict):
    trust_key: str
    display_name: str
    app_id: str
    scope: str


def _add_root(roots: list[Path], seen: set[str], candidate: Path | None) -> None:
    if candidate is None:
        return
    resolved = str(candidate.expanduser().resolve())
    if resolved in seen:
        return
    seen.add(resolved)
    roots.append(Path(resolved))


def trust_store_workspace_roots(*, live_roots: Collection[Path | None], fallback_root: str | None) -> list[Path]:
    """Collect chat/agent workspace roots that may hold approved_apps.json."""
    roots: list[Path] = []
    seen: set[str] = set()
    for candidate in live_roots:
        _add_root(roots, seen, candidate)

    try:
        from app.config.settings import get_settings

        harness_dir = Path(get_settings().database.harness_dir)
        if harness_dir.is_dir():
            # approved_apps.json only ever lives at
            # {workspace_root}/.agent/desktop_control/approved_apps.json, and
            # harness workspaces use a two-level layout (e.g.
            # harness/workspaces/chat_*/...). Probe that bounded layout with
            # os.scandir: the harness dir can contain tens of thousands of files.
            def _collect(root: str) -> None:
                try:
                    with os.scandir(root) as entries:
                        for entry in entries:
                            if not entry.is_dir(follow_symlinks=False):
                                continue
                            agent_dir = os.path.join(entry.path, _APPROVAL_DIR)
                            if os.path.isdir(agent_dir) and os.path.isfile(os.path.join(agent_dir, _APPROVAL_FILE)):
                                _add_root(roots, seen, Path(entry.path))
                except OSError:
                    return

            try:
                collections = [entry.path for entry in os.scandir(harness_dir) if entry.is_dir(follow_symlinks=False)]
            except OSError:
                collections = []
            for collection in collections:
                agent_dir = os.path.join(collection, _APPROVAL_DIR)
                if os.path.isdir(agent_dir) and os.path.isfile(os.path.join(agent_dir, _APPROVAL_FILE)):
                    _add_root(roots, seen, Path(collection))
                else:
                    _collect(collection)
    except Exception as exc:
        logger.warning("Failed to scan harness desktop trust stores: %s", exc)

    if fallback_root:
        _add_root(roots, seen, Path(fallback_root))

    return roots


def _live_workspace_roots() -> list[Path | None]:
    from app.ai_agents.desktop_control.gate import DesktopControlGate

    return [gate._workspace_root for gate in DesktopControlGate._live_gates]


def approval_path_for(workspace_root: str | None) -> Path | None:
    if workspace_root is None:
        return None
    return Path(workspace_root) / _APPROVAL_DIR / _APPROVAL_FILE


def deny_path_for(workspace_root: str | None) -> Path | None:
    if workspace_root is None:
        return None
    return Path(workspace_root) / _APPROVAL_DIR / _DENY_FILE


def load_denied_keys(*, workspace_root: str | None) -> set[str]:
    """Read operator persistent denials (workspace scope).

    Format: {"denied": ["<trust_key>", ...]}. Unknown shapes read as empty.
    """
    denied: set[str] = set()
    path = deny_path_for(workspace_root)
    if path is None or not path.is_file():
        return denied
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Failed to load desktop deny file: %s", exc)
        return denied
    entries = raw.get("denied", []) if isinstance(raw, dict) else []
    if not isinstance(entries, list):
        return denied
    for key in entries:
        if isinstance(key, str) and key.strip():
            denied.add(key.strip())
    return denied


def list_trusted_desktop_apps(*, workspace_root: str | None) -> list[TrustedAppRecord]:
    from app.ai_agents.desktop_control.gate import DesktopControlGate

    merged: dict[str, TrustedAppRecord] = {}
    for gate in list(DesktopControlGate._live_gates):
        for record in gate.list_trusted_apps():
            merged[record["trust_key"]] = record
    for root in trust_store_workspace_roots(live_roots=_live_workspace_roots(), fallback_root=workspace_root):
        for record in _disk_trusted_apps_for_workspace(str(root)):
            merged.setdefault(record["trust_key"], record)
    return sorted(merged.values(), key=lambda item: item["display_name"].lower())


def _disk_trusted_apps_for_workspace(workspace_root: str) -> list[TrustedAppRecord]:
    from app.ai_agents.desktop_control.gate import DesktopControlGate

    gate = DesktopControlGate(
        workspace_root=workspace_root,
        auto_grant=False,
        register_live=False,
    )
    return gate.list_trusted_apps()


def revoke_trusted_desktop_app(*, workspace_root: str | None, trust_key: str) -> bool:
    from app.ai_agents.desktop_control.gate import DesktopControlGate

    for gate in list(DesktopControlGate._live_gates):
        if gate.revoke_trusted_app(trust_key):
            return True
    for root in trust_store_workspace_roots(live_roots=_live_workspace_roots(), fallback_root=workspace_root):
        disk_gate = DesktopControlGate(
            workspace_root=str(root),
            auto_grant=False,
            register_live=False,
        )
        if disk_gate.revoke_trusted_app(trust_key):
            return True
    return False
