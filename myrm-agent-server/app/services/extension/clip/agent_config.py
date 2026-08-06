"""Browser extension wiki clip agent scope (UserConfig SSOT).

[INPUT]
- app.services.config.service::ConfigService (POS: UserConfig persistence)

[OUTPUT]
- get_extension_clip_agent_config / set_extension_clip_agent_config

[POS]
app.services.extension.clip — sync clip target agent between WebUI and MV3 extension.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.config.service import ConfigService

_CONFIG_KEY = "extensionClipAgent"
_CLIP_AGENT_DEVICE_ID = "webui"


@dataclass(frozen=True, slots=True)
class ExtensionClipAgentConfig:
    agent_id: str | None = None
    web_ui_origin: str | None = None


def _parse_config(raw: object) -> ExtensionClipAgentConfig:
    if not isinstance(raw, dict):
        return ExtensionClipAgentConfig()
    agent_raw = raw.get("agent_id")
    origin_raw = raw.get("web_ui_origin")
    agent_id = agent_raw.strip() if isinstance(agent_raw, str) and agent_raw.strip() else None
    web_ui_origin = (
        origin_raw.rstrip("/") if isinstance(origin_raw, str) and origin_raw.strip() else None
    )
    return ExtensionClipAgentConfig(agent_id=agent_id, web_ui_origin=web_ui_origin)


async def get_extension_clip_agent_config() -> ExtensionClipAgentConfig:
    service = ConfigService()
    record = await service.get(_CONFIG_KEY)
    if record is None:
        return ExtensionClipAgentConfig()
    return _parse_config(record.value)


async def set_extension_clip_agent_config(
    *,
    agent_id: str | None,
    web_ui_origin: str | None,
) -> ExtensionClipAgentConfig:
    service = ConfigService()
    normalized = ExtensionClipAgentConfig(
        agent_id=agent_id.strip() if agent_id and agent_id.strip() else None,
        web_ui_origin=web_ui_origin.rstrip("/")
        if web_ui_origin and web_ui_origin.strip()
        else None,
    )
    payload: dict[str, object] = {
        "agent_id": normalized.agent_id,
        "web_ui_origin": normalized.web_ui_origin,
    }
    await service.set(_CONFIG_KEY, payload, _CLIP_AGENT_DEVICE_ID)
    return normalized
