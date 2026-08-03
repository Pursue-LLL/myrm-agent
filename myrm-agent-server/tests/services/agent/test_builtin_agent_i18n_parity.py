"""Architecture guard: server builtin agent ids must match frontend i18n keys."""

from __future__ import annotations

import re
from pathlib import Path

from app.services.agent.builtin_initializer import _BUILTIN_AGENTS

_FRONTEND_I18N_DATA = (
    Path(__file__).resolve().parents[4]
    / "myrm-agent-frontend"
    / "src"
    / "components"
    / "agent"
    / "builtin-agent-i18n-data.ts"
)

_BUILTIN_I18N_KEY_PATTERN = re.compile(r"'(builtin-[^']+)':\s*\{")


def _frontend_builtin_i18n_ids() -> set[str]:
    text = _FRONTEND_I18N_DATA.read_text(encoding="utf-8")
    return set(_BUILTIN_I18N_KEY_PATTERN.findall(text))


def test_frontend_i18n_keys_match_server_builtin_agent_ids() -> None:
    server_ids = {spec.id for spec in _BUILTIN_AGENTS}
    frontend_ids = _frontend_builtin_i18n_ids()

    missing_in_frontend = sorted(server_ids - frontend_ids)
    extra_in_frontend = sorted(frontend_ids - server_ids)

    assert missing_in_frontend == [], f"Missing frontend i18n for: {missing_in_frontend}"
    assert extra_in_frontend == [], f"Stale frontend i18n keys: {extra_in_frontend}"
