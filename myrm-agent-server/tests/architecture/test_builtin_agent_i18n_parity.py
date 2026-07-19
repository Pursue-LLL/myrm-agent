"""Architecture test: built-in agent i18n keys match server spec ids."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_MYRM_AGENT_ROOT = _SERVER_ROOT.parent
_FRONTEND_I18N_DATA = (
    _MYRM_AGENT_ROOT
    / "myrm-agent-frontend"
    / "src"
    / "components"
    / "agent"
    / "builtin-agent-i18n-data.ts"
)

_I18N_KEY_PATTERN = re.compile(r"'((?:builtin-)[^']+)':\s*\{")


def _parse_frontend_builtin_i18n_keys() -> set[str]:
    assert _FRONTEND_I18N_DATA.is_file(), (
        f"Missing frontend i18n data file: {_FRONTEND_I18N_DATA}"
    )
    text = _FRONTEND_I18N_DATA.read_text(encoding="utf-8")
    return set(_I18N_KEY_PATTERN.findall(text))


@pytest.mark.architecture
def test_builtin_agent_i18n_keys_match_server_specs() -> None:
    from app.services.agent.builtin_agent_specs import _BUILTIN_AGENTS

    spec_ids = {spec.id for spec in _BUILTIN_AGENTS}
    i18n_keys = _parse_frontend_builtin_i18n_keys()

    missing_i18n = sorted(spec_ids - i18n_keys)
    extra_i18n = sorted(i18n_keys - spec_ids)

    assert not missing_i18n, (
        "Built-in agent specs missing frontend i18n entries: "
        f"{missing_i18n}. Update myrm-agent-frontend/src/components/agent/builtin-agent-i18n-data.ts"
    )
    assert not extra_i18n, (
        "Frontend i18n keys without matching server built-in spec: "
        f"{extra_i18n}. Remove stale keys or add specs in app/services/agent/builtin_specs/"
    )
