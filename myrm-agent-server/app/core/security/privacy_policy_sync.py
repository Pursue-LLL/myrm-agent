"""Publishes the persisted privacy settings to the harness as the process-wide privacy policy.

[INPUT]
- app.core.security.privacy_settings::privacy_policy_from_settings (POS: Business-layer reader of the persisted personal settings for privacy protection: the switch, actions, custom rules and deep-scan choice, for runs the server starts itself and for requests that carry only some of them. Local-model routing stays request-only.)
- app.services.config.service::config_service (POS: 管理用户配置的存储和同步，支持版本控制（乐观锁）和批量同步)
- myrm_agent_harness.api.security::set_process_privacy_policy (POS: Wire-level half of the privacy layer: the guardrail middleware covers the agent loop, this guard covers every other ChatLiteLLM call.)

[OUTPUT]
- sync_privacy_policy: publish the policy a personalSettings value describes (None clears it)
- apply_privacy_policy_from_db: load the saved personalSettings at startup and publish its policy

[POS]
Server-side bridge from the personal settings to the harness outbound privacy guard. A model call with no agent run
(chat title, suggestions, offline compaction, meeting notes, memory extraction) has no request to carry the privacy
settings; the guard reads this policy instead. The server serves one user, so one process-wide policy is the user's.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

from myrm_agent_harness.api.security import set_process_privacy_policy

from app.core.security.privacy_settings import privacy_policy_from_settings

logger = logging.getLogger(__name__)


def sync_privacy_policy(personal_settings: Mapping[str, object] | None) -> None:
    """Publish the policy *personal_settings* describes; protection off (or no settings) clears it."""
    policy = privacy_policy_from_settings(personal_settings)
    set_process_privacy_policy(policy)
    logger.debug("[Privacy] Process-wide policy %s", "published" if policy else "cleared")


async def apply_privacy_policy_from_db() -> None:
    """Publish the policy of the saved personal settings; run once at startup, before any model call."""
    from app.services.config.service import config_service

    record = await config_service.get("personalSettings")
    value = record.value if record is not None else None
    sync_privacy_policy(value if isinstance(value, dict) else None)
