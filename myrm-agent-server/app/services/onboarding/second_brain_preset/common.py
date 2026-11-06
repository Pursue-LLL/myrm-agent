"""[INPUT]
- .common (POS: shared constants and preset state)

[OUTPUT]
- SecondBrainPresetError, _ApplyMutation, _load_template_data, _normalize_locale, _load_preset_state, _save_preset_state, _clear_preset_state

[POS]
Second Brain preset: constants, errors, preset state persistence and template loading.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import yaml

from app.core.cron.adapters.setup import get_cron_manager as get_cron_manager
from app.services.agent.template_utils import PREBUILT_AGENTS_DIR
from app.services.config.service import config_service
from app.services.onboarding.schemas import (
    SecondBrainPresetState,
)

logger = logging.getLogger(__name__)

_CONFIG_KEY = "secondBrainPreset"

_TEMPLATE_ID = "second_brain_assistant"

_CRON_JOB_NAME = "Second Brain · Read-it-Later"

_CRON_DELTA_JOB_NAME = "Second Brain · Wiki Morning Delta"

_CRON_MAINTAIN_JOB_NAME = "Second Brain · Wiki Maintenance"

_USER_ID = "default"

_DEVICE_ID = "second-brain-preset"

_REQUIRED_TOOLS = frozenset({"memory", "wiki", "cron"})


class SecondBrainPresetError(Exception):
    """Preset apply failed with a user-visible message."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@dataclass(slots=True)
class _ApplyMutation:
    created_agent_id: str | None = None
    created_cron_job_ids: tuple[str, ...] = ()


def _load_template_data() -> dict[str, object]:
    file_path = os.path.join(PREBUILT_AGENTS_DIR, f"{_TEMPLATE_ID}.yaml")
    if not os.path.isfile(file_path):
        msg = f"Second Brain template missing: {_TEMPLATE_ID}"
        raise FileNotFoundError(msg)
    with open(file_path, encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict) or not data:
        msg = "Second Brain template is empty"
        raise ValueError(msg)
    return data


def _normalize_locale(accept_language: str | None) -> str:
    if accept_language and "zh" in accept_language.lower():
        return "zh"
    return "en"


async def _load_preset_state() -> SecondBrainPresetState | None:
    record = await config_service.get(_CONFIG_KEY)
    if record is None:
        return None
    try:
        return SecondBrainPresetState.model_validate(record.value)
    except Exception:
        logger.warning("Invalid secondBrainPreset config; treating as unset")
        return None


async def _save_preset_state(state: SecondBrainPresetState) -> None:
    await config_service.set(
        config_key=_CONFIG_KEY,
        value=state.model_dump(mode="json"),
        device_id=_DEVICE_ID,
    )


async def _clear_preset_state() -> None:
    await config_service.delete(_CONFIG_KEY)
