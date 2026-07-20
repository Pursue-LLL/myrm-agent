"""Server hook when a harness background bash job finishes.

[INPUT]
- myrm_agent_harness.api.hooks::BackgroundJobFinishResult (POS: harness finish payload)
- app.services.chat.chat_service::ChatService (POS: message persistence)
- app.services.event.app_event_bus (POS: SSE bus)
- app.services.agent.goal_wait_background_resume::maybe_resume_goal_after_background_job (POS: WAIT exit + headless resume)

[OUTPUT]
- ServerBackgroundJobFinishHandler.on_background_job_finish: append finish message → goal resume → SYSTEM_NOTIFICATION SSE

[POS]
Business orchestration for harness background bash job terminal events.
Resume runs before SSE so Goal Card refresh observes final status (ACTIVE or NEEDS_HUMAN_REVIEW).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from myrm_agent_harness.api.hooks import BackgroundJobFinishResult
from myrm_agent_harness.utils.locale import normalize_locale, resolve_locale

from app.channels.i18n.engine import channel_t
from app.services.chat.chat_service import ChatService
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

logger = logging.getLogger(__name__)


async def _resolve_user_locale() -> str:
    """Load locale from personal settings (WebUI / Tauri / sandbox user config)."""
    from app.core.channel_bridge.config_loader import load_user_configs

    try:
        configs = await load_user_configs()
        ps = configs.personal_settings_dict if configs else None
        raw_locale = ps.get("locale") if ps else None
        if not raw_locale and ps:
            raw_locale = ps.get("language")
        locale_str = str(raw_locale) if raw_locale else None
        return resolve_locale(metadata_locale=locale_str, platform_locale=None, channel=None)
    except Exception:
        logger.debug("Failed to load user locale for background job finish", exc_info=True)
        return normalize_locale(None)


def _command_preview(command: str) -> str:
    if len(command) <= 120:
        return command
    return f"{command[:117]}..."


def _format_finish_message(result: BackgroundJobFinishResult, locale: str) -> str:
    cmd_preview = _command_preview(result.command)
    exit_code_str = str(result.exit_code) if result.exit_code is not None else "null"

    if result.status == "exited" and (result.exit_code or 0) == 0:
        return channel_t(
            locale,
            "bash_bg_finish_success",
            pid=str(result.pid),
            command=cmd_preview,
        )
    if result.error_category:
        return channel_t(
            locale,
            "bash_bg_finish_with_error",
            error_category=result.error_category,
            pid=str(result.pid),
            status=result.status,
            exit_code=exit_code_str,
            command=cmd_preview,
        )
    return channel_t(
        locale,
        "bash_bg_finish_generic",
        status=result.status,
        pid=str(result.pid),
        exit_code=exit_code_str,
        command=cmd_preview,
    )


class ServerBackgroundJobFinishHandler:
    """Persists background bash job completion into the chat transcript."""

    def __init__(self) -> None:
        self._processed: set[tuple[str, str]] = set()

    def _claim_finish_once(self, result: BackgroundJobFinishResult) -> bool:
        from myrm_agent_harness.api.hooks import get_background_job_store

        if not result.job_id:
            logger.warning(
                "Background job finish missing job_id for session=%s pid=%s",
                result.session_id,
                result.pid,
            )
            return False

        store = get_background_job_store()
        if store is not None:
            record = store.get_by_job_id(result.job_id)
            if record is not None:
                if record.finish_processed:
                    return False
                if store.try_claim_finish(result.job_id):
                    return True
                if record.status == "exited":
                    return False

        dedupe_key = (result.session_id, result.job_id)
        if dedupe_key in self._processed:
            logger.debug(
                "Background job finish deduped for session=%s job_id=%s",
                result.session_id,
                result.job_id,
            )
            return False
        self._processed.add(dedupe_key)
        return True

    async def on_background_job_finish(self, result: BackgroundJobFinishResult) -> None:
        if not result.session_id:
            logger.warning("Background job finish ignored: missing session_id")
            return
        if result.status != "exited":
            return
        if not self._claim_finish_once(result):
            return
        await self._process(result)

    async def _process(self, result: BackgroundJobFinishResult) -> None:
        try:
            locale = await _resolve_user_locale()
            content = _format_finish_message(result, locale)
            title = channel_t(locale, "bash_bg_finish_title")
            message_id = f"bg_finish_{result.job_id or result.pid}"
            sent_at = datetime.now(tz=timezone.utc)

            await ChatService.append_message(
                chat_id=result.session_id,
                role="assistant",
                content=content,
                sent_at=sent_at,
                sent_timezone="UTC",
                message_id=message_id,
                extra_data={
                    "background_job": True,
                    "job_id": result.job_id,
                    "pid": result.pid,
                    "status": result.status,
                    "exit_code": result.exit_code,
                    "error_category": result.error_category,
                },
            )

            from app.services.agent.goal_wait_background_resume import (
                maybe_resume_goal_after_background_job,
            )

            await maybe_resume_goal_after_background_job(result)

            get_event_bus().publish(
                AppEvent(
                    event_type=AppEventType.SYSTEM_NOTIFICATION,
                    data={
                        "title": title,
                        "message": content,
                        "meta_data": {
                            "kind": "background_job_finish",
                            "chat_id": result.session_id,
                            "message_id": message_id,
                            "pid": result.pid,
                            "status": result.status,
                        },
                    },
                )
            )
            logger.info(
                "Background job finish recorded for chat=%s pid=%s status=%s",
                result.session_id,
                result.pid,
                result.status,
            )
        except Exception:
            logger.exception(
                "Failed to record background job finish chat=%s pid=%s",
                result.session_id,
                result.pid,
            )
