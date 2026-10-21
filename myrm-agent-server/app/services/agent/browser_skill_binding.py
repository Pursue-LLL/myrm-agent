"""Peripheral browser-automation skill binding when browser is enabled.

[INPUT]
(none — pure helper)

[OUTPUT]
- BROWSER_AUTOMATION_SKILL_ID: Prebuilt skill identifier
- apply_browser_automation_skill_binding(): Merge peripheral skill binding into agent skill lists

[POS]
Server-layer skill binding helper. Keeps browser operating-loop guidance out of harness
while preserving prompt cache (peripheral / non-core skill only).
"""

from __future__ import annotations

BROWSER_AUTOMATION_SKILL_ID = "browser-automation"

_PERIPHERAL_SKILL_CONFIG: dict[str, object] = {"is_core": False}


def apply_browser_automation_skill_binding(
    skill_ids: list[str],
    skill_configs: dict[str, dict] | None,
    *,
    enable_browser: bool,
) -> tuple[list[str], dict[str, dict] | None]:
    """Attach browser-automation as a peripheral skill when browser tools are enabled."""
    if not enable_browser:
        return skill_ids, skill_configs

    merged_ids = list(skill_ids)
    if BROWSER_AUTOMATION_SKILL_ID not in merged_ids:
        merged_ids.append(BROWSER_AUTOMATION_SKILL_ID)

    merged_configs = dict(skill_configs or {})
    merged_configs.setdefault(BROWSER_AUTOMATION_SKILL_ID, dict(_PERIPHERAL_SKILL_CONFIG))
    return merged_ids, merged_configs
