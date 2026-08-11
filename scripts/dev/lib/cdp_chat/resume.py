"""ResumeTurnContract STREAM_CONVERGE executor (R93).

[INPUT]
resume_turn_contract constants · caller-supplied API resume/poll callbacks

[OUTPUT]
execute_resume_turn_stream_converge → bool (DONE reached)

[POS]
Dev Gate layer — consumes agent-stream outside MUX evaluate.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from resume_turn_contract import (
    RESUME_BUSY_BACKOFF_SEC,
    RESUME_DONE_POLL_TIMEOUT_SEC,
    RESUME_REINTERRUPT_MAX_ROUNDS,
    RESUME_STREAM_CONVERGE_TIMEOUT_SEC,
)

ResumeViaApiFn = Callable[..., dict[str, object]]
WaitApiDoneFn = Callable[..., Awaitable[bool]]
ReleaseUiSseFn = Callable[[], Awaitable[None]]
OnSessionBusyFn = Callable[[], Awaitable[None]]
LogFn = Callable[[str], None]


async def execute_resume_turn_stream_converge(
    *,
    api_base: str,
    chat_id: str,
    message_id: str,
    resume_via_api: ResumeViaApiFn,
    wait_api_done: WaitApiDoneFn,
    release_ui_sse: ReleaseUiSseFn | None = None,
    on_session_busy: OnSessionBusyFn | None = None,
    log: LogFn | None = None,
    max_rounds: int = RESUME_REINTERRUPT_MAX_ROUNDS,
    stream_timeout_sec: float = RESUME_STREAM_CONVERGE_TIMEOUT_SEC,
    done_poll_timeout_sec: float = RESUME_DONE_POLL_TIMEOUT_SEC,
) -> bool:
    """Run API resume + re-interrupt loop until DONE or rounds exhausted."""
    _log = log or (lambda _msg: None)
    resume_msg_id = message_id.strip()
    if not chat_id.strip() or not resume_msg_id:
        return False

    for reint_round in range(1, max_rounds + 1):
        if release_ui_sse is not None:
            await release_ui_sse()
        _log(
            f"ResumeTurnContract STREAM_CONVERGE round={reint_round}/{max_rounds} "
            f"chatId={chat_id} msgId={resume_msg_id}"
        )
        resume_result = await asyncio.to_thread(
            resume_via_api,
            api_base=api_base,
            chat_id=chat_id,
            message_id=resume_msg_id,
            timeout_sec=stream_timeout_sec,
        )
        _log(f"ResumeTurnContract STREAM_CONVERGE result: {resume_result}")
        if resume_result.get("done") is True:
            return True
        if resume_result.get("ok") is not True:
            error_text = str(resume_result.get("error") or "")
            if "409" in error_text and reint_round < max_rounds:
                if on_session_busy is not None:
                    await on_session_busy()
                await asyncio.sleep(RESUME_BUSY_BACKOFF_SEC)
                continue
            return False
        if resume_result.get("re_interrupted") is True:
            if resume_result.get("done") is True:
                return True
            next_mid = str(
                resume_result.get("resume_msg_id") or resume_msg_id or ""
            ).strip()
            if next_mid:
                resume_msg_id = next_mid
            if reint_round < max_rounds:
                if release_ui_sse is not None:
                    await release_ui_sse()
                if on_session_busy is not None:
                    await on_session_busy()
                else:
                    await asyncio.sleep(5.0)
                continue
            return await wait_api_done(
                chat_id,
                api_url=api_base,
                timeout_sec=done_poll_timeout_sec,
            )
        return await wait_api_done(
            chat_id,
            api_url=api_base,
            timeout_sec=done_poll_timeout_sec,
        )
    return False
