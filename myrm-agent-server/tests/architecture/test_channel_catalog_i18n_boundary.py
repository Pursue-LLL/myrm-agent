"""Architecture tests: server channel JSON catalog boundary.

Server-side channel JSON catalogs must stay free of harness error-diagnostic
keys. Harness LLM diagnostics are rendered by the harness itself from its own
bundled catalog (`myrm_agent_harness.agent.errors.diagnostics.i18n`) and flow
to channels via ``diagnostic_result`` — duplicating those keys in the server
catalog created a dead fork that silently drifted.

These guards enforce the SSOT contract:
1. Server JSON catalogs contain ONLY the allowlisted channel keys.
2. All server JSON locale files expose identical key sets.
3. Server JSON catalogs never overlap the harness diagnostics catalog.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[4]

_SERVER_LOCALES_DIR = _REPO_ROOT / "myrm-agent" / "myrm-agent-server" / "app" / "channels" / "i18n" / "locales"
_HARNESS_LOCALES_DIR = (
    _REPO_ROOT / "myrm-agent-harness" / "src" / "myrm_agent_harness" / "agent" / "errors" / "diagnostics" / "i18n" / "locales"
)

# Every key in the server JSON catalog must be listed here. Channel messages
# living in `.ftl` files are out of scope for this catalog.
_SERVER_CATALOG_ALLOWLIST: frozenset[str] = frozenset(
    {
        "stuck_task_timeout_user_message",
        "risk_outbound_blocked",
        "risk_inbound_blocked",
    }
)

_SERVER_LOCALE_NAMES = ("en", "zh-CN", "ja", "zh-TW", "ko", "de")


def _flat_keys(data: dict[str, object]) -> set[str]:
    """Return dotted key paths of a (possibly nested) JSON catalog."""
    keys: set[str] = set()

    def walk(node: dict[str, object], prefix: str = "") -> None:
        for key, value in node.items():
            full = f"{prefix}.{key}" if prefix else key
            keys.add(full)
            if isinstance(value, dict):
                walk(value, full)

    walk(data)
    return keys


def _load_locale(locales_dir: Path, name: str) -> dict[str, object] | None:
    path = locales_dir / f"{name}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.architecture
def test_server_json_catalog_keys_within_allowlist() -> None:
    """Server JSON catalogs must not accumulate unreferenced keys."""
    for name in _SERVER_LOCALE_NAMES:
        data = _load_locale(_SERVER_LOCALES_DIR, name)
        assert data is not None, f"Missing server locale JSON: {name}.json"
        unknown = _flat_keys(data) - _SERVER_CATALOG_ALLOWLIST
        assert not unknown, (
            f"[{name}] Server JSON catalog contains keys outside the allowlist: "
            f"{sorted(unknown)}. Channel messages belong in `.ftl`; LLM error "
            f"diagnostics belong in the harness catalog."
        )


@pytest.mark.architecture
def test_server_json_locales_share_identical_key_sets() -> None:
    """Every server locale must expose the exact same channel keys."""
    key_sets: dict[str, set[str]] = {}
    for name in _SERVER_LOCALE_NAMES:
        data = _load_locale(_SERVER_LOCALES_DIR, name)
        assert data is not None, f"Missing server locale JSON: {name}.json"
        key_sets[name] = _flat_keys(data)

    reference, reference_keys = next(iter(key_sets.items()))
    for name, keys in key_sets.items():
        missing = reference_keys - keys
        extra = keys - reference_keys
        assert not missing and not extra, (
            f"Key mismatch between {reference} and {name}: missing={sorted(missing)}, extra={sorted(extra)}"
        )


@pytest.mark.architecture
def test_server_json_catalog_has_no_harness_diagnostic_overlap() -> None:
    """LLM error diagnostics are the harness catalog's job; never fork them."""
    harness_locales = _HARNESS_LOCALES_DIR
    if not harness_locales.exists():
        pytest.skip(f"Harness source not checked out: {harness_locales}")

    for name in _SERVER_LOCALE_NAMES:
        harness_data = _load_locale(harness_locales, name)
        if harness_data is None:
            continue
        server_data = _load_locale(_SERVER_LOCALES_DIR, name)
        assert server_data is not None, f"Missing server locale JSON: {name}.json"
        overlap = _flat_keys(server_data) & _flat_keys(harness_data)
        assert not overlap, (
            f"[{name}] Server JSON catalog duplicates harness diagnostics keys: "
            f"{sorted(overlap)}. Delete them — harness renders its own diagnostics."
        )
