"""The keys the browser may keep in clear text are exactly the keys the server stores unsealed.

[POS]
tests/architecture/test_offline_persistable_keys_parity.py

[INPUT]
- myrm-agent-frontend/src/services/config/offlinePersistableKeys.ts: OFFLINE_PERSISTABLE_CONFIG_KEYS
- myrm-agent-frontend/src/services/config/types.ts: ALL_CONFIG_KEYS
- app.services.config.encryption: SENSITIVE_CONFIG_KEYS

[OUTPUT]
- Fails when a key the server seals could be written to ``localStorage`` in clear text, or when a key the server stores
  unsealed would silently stop surviving a reload.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.services.config.encryption import SENSITIVE_CONFIG_KEYS

_CONFIG_DIR = Path(__file__).resolve().parents[3] / "myrm-agent-frontend" / "src" / "services" / "config"
_PERSISTABLE_TS = _CONFIG_DIR / "offlinePersistableKeys.ts"
_TYPES_TS = _CONFIG_DIR / "types.ts"
_SKIP_WITHOUT_FRONTEND = pytest.mark.skipif(
    not _PERSISTABLE_TS.is_file(), reason="frontend sources are not part of this checkout"
)

_PERSISTABLE_RE = re.compile(r"OFFLINE_PERSISTABLE_CONFIG_KEYS[^=]*=\s*new Set<ConfigKey>\(\[(?P<body>[^\]]*)\]")
_ALL_KEYS_RE = re.compile(r"ALL_CONFIG_KEYS[^=]*=\s*\[(?P<body>[^\]]*)\]")


def _quoted_keys(source: Path, pattern: re.Pattern[str]) -> set[str]:
    match = pattern.search(source.read_text(encoding="utf-8"))
    assert match is not None, f"key list not found in {source.name}"
    return set(re.findall(r"'(\w+)'", match.group("body")))


@_SKIP_WITHOUT_FRONTEND
def test_no_sealed_key_can_be_written_to_browser_storage() -> None:
    leaked = _quoted_keys(_PERSISTABLE_TS, _PERSISTABLE_RE) & SENSITIVE_CONFIG_KEYS

    assert not leaked, f"offlinePersistableKeys.ts lists keys the server seals: {sorted(leaked)}"


@_SKIP_WITHOUT_FRONTEND
def test_every_key_the_server_stores_unsealed_is_listed() -> None:
    unsealed = _quoted_keys(_TYPES_TS, _ALL_KEYS_RE) - SENSITIVE_CONFIG_KEYS
    listed = _quoted_keys(_PERSISTABLE_TS, _PERSISTABLE_RE)

    assert listed == unsealed, (
        "offlinePersistableKeys.ts must list exactly the frontend config keys that are not in SENSITIVE_CONFIG_KEYS; "
        f"missing: {sorted(unsealed - listed)}, extra: {sorted(listed - unsealed)}"
    )
