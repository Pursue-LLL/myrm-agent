"""Backend config pins applied through the chat page.

[INPUT]
- cdp_chat.support.api_client::get_e2e_api_url (POS: Where the E2E API and UI live and the loopback-only HTTP calls to them, retried under parallel load)
- cdp_chat.support.config.api_pins::_hitl_pin_retry_policy, clear_search_services_ssot, ensure_e2e_hitl_mode, ensure_e2e_onboarding_complete (POS: Pins the backend config an E2E run needs over the API: YOLO and HITL mode, onboarding complete, memory disabled, search services cleared)
- cdp_chat.support.config.page_scripts::CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS, PUT_E2E_CLEAR_SEARCH_CONFIG_JS, PUT_E2E_HITL_CONFIG_JS, PUT_E2E_YOLO_CONFIG_JS (POS: Scripts that write the pinned config through the page's own API layer and clear its offline queue)
- cdp_chat.support.config.store::fetch_config_value (POS: Global config records over the API with optimistic locking: a per-key cross-process mutex, reads and writes with bounded retry)
- dev_gate.contract::EvaluateIntent (POS: Dev Gate contract SSOT: error tokens, parallel caps and timeout budgets)

[OUTPUT]
- ensure_e2e_hitl_mode_in_browser, ensure_e2e_yolo_mode_in_browser, ensure_e2e_search_cleared_in_browser: the pins through the page
- hard_reset_e2e_hitl_mode: pin HITL, reload the UI, pin again

[POS]
Applies the same pins through the page so its config sync agrees with the backend: the PUT goes through the page, its offline queue is cleared first, and a HITL reset reloads the UI.
"""

from __future__ import annotations

import asyncio

from dev_gate.contract import EvaluateIntent

from cdp_chat.support.api_client import get_e2e_api_url
from cdp_chat.support.config.api_pins import (
    _hitl_pin_retry_policy,
    clear_search_services_ssot,
    ensure_e2e_hitl_mode,
    ensure_e2e_onboarding_complete,
)
from cdp_chat.support.config.page_scripts import (
    CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS,
    PUT_E2E_CLEAR_SEARCH_CONFIG_JS,
    PUT_E2E_HITL_CONFIG_JS,
    PUT_E2E_YOLO_CONFIG_JS,
)
from cdp_chat.support.config.store import fetch_config_value

_BROWSER_HITL_PIN_BACKOFF_SEC = 2.0


def _browser_hitl_pin_transient_failure(observed: dict[str, object]) -> bool:
    results = observed.get("results")
    if not isinstance(results, list):
        err = str(observed.get("err", ""))
        return err.startswith("put-5") or "500" in err
    for row in results:
        if not isinstance(row, dict):
            continue
        err = str(row.get("err", ""))
        if err.startswith(("put-5", "fetch-5")):
            return True
    return False


async def ensure_e2e_hitl_mode_in_browser(chat: object) -> None:
    """PUT HITL securityConfig on the bound private API and clear ConfigSync drift."""
    max_attempts, _request_timeout_sec = _hitl_pin_retry_policy()
    last_observed: dict[str, object] | None = None
    for attempt in range(1, max_attempts + 1):
        await chat.evaluate(  # type: ignore[attr-defined]
            CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS, intent=EvaluateIntent.SYNC_PROBE
        )
        raw = await chat.evaluate(  # type: ignore[attr-defined]
            PUT_E2E_HITL_CONFIG_JS, intent=EvaluateIntent.AGENT_SUBMIT
        )
        observed = raw if isinstance(raw, dict) else {"value": raw}
        if observed.get("ok") is True:
            return
        last_observed = observed
        if not _browser_hitl_pin_transient_failure(observed) or attempt >= max_attempts:
            break
        await asyncio.sleep(_BROWSER_HITL_PIN_BACKOFF_SEC * attempt)
    raise RuntimeError(f"Browser HITL pin failed: {last_observed}")


async def ensure_e2e_yolo_mode_in_browser(chat: object) -> None:
    """PUT YOLO securityConfig on private+shared API and clear ConfigSync drift."""
    max_attempts, _request_timeout_sec = _hitl_pin_retry_policy()
    last_observed: dict[str, object] | None = None
    for attempt in range(1, max_attempts + 1):
        await chat.evaluate(  # type: ignore[attr-defined]
            CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS, intent=EvaluateIntent.SYNC_PROBE
        )
        raw = await chat.evaluate(  # type: ignore[attr-defined]
            PUT_E2E_YOLO_CONFIG_JS, intent=EvaluateIntent.AGENT_SUBMIT
        )
        observed = raw if isinstance(raw, dict) else {"value": raw}
        if observed.get("ok") is True:
            return
        last_observed = observed
        if not _browser_hitl_pin_transient_failure(observed) or attempt >= max_attempts:
            break
        await asyncio.sleep(_BROWSER_HITL_PIN_BACKOFF_SEC * attempt)
    raise RuntimeError(f"Browser YOLO pin failed: {last_observed}")


async def ensure_e2e_search_cleared_in_browser(
    chat: object,
    *,
    api_url: str | None = None,
    recv_timeout_sec: float = 45.0,
    max_attempts: int = 2,
) -> None:
    """Clear searchServices: Python SSOT first, then browser mirror (PUT retry + verify fallback)."""
    resolved = (api_url or get_e2e_api_url()).rstrip("/")
    recv_timeout = min(60.0, max(10.0, float(recv_timeout_sec)))
    attempts = max(1, int(max_attempts))
    python_ssot_timeout = min(20.0, recv_timeout)
    await asyncio.wait_for(
        asyncio.to_thread(clear_search_services_ssot, api_url=resolved),
        timeout=python_ssot_timeout,
    )
    await chat.evaluate(  # type: ignore[attr-defined]
        CLEAR_E2E_CONFIG_OFFLINE_QUEUE_JS,
        intent=EvaluateIntent.SYNC_PROBE,
    )
    last_err: object = None
    for attempt in range(attempts):
        try:
            raw = await chat.evaluate(  # type: ignore[attr-defined]
                PUT_E2E_CLEAR_SEARCH_CONFIG_JS,
                intent=EvaluateIntent.AGENT_SUBMIT,
            )
        except TimeoutError as exc:
            last_err = exc
            if attempt + 1 >= attempts:
                raise
            await asyncio.sleep(1.5 * (attempt + 1))
            continue
        observed = raw if isinstance(raw, dict) else {"value": raw}
        if observed.get("ok") is True:
            return
        last_err = observed
        if attempt + 1 < attempts:
            await asyncio.sleep(1.0)
            continue
        break
    # Last resort: Python SSOT still empty → accept FE mirror failure only if verify holds.
    value = await asyncio.wait_for(
        asyncio.to_thread(fetch_config_value, "searchServices", api_url=resolved),
        timeout=python_ssot_timeout,
    )
    configs = value.get("searchServiceConfigs")
    if configs == []:
        return
    raise RuntimeError(
        f"Browser search clear failed: {last_err}; persisted={value!r}; api={resolved}"
    )


async def hard_reset_e2e_hitl_mode(
    chat: object,
    *,
    api_url: str,
    page_url: str,
) -> None:
    """Pin HITL on API, reload UI to reset ConfigSync cache, then pin again."""
    ensure_e2e_hitl_mode(api_url=api_url)
    ensure_e2e_onboarding_complete(api_url=api_url)
    await ensure_e2e_hitl_mode_in_browser(chat)
    await chat.cdp("Page.reload", recv_timeout=120.0)  # type: ignore[attr-defined]
    await chat.bootstrap(page_url, timeout_sec=120.0)  # type: ignore[attr-defined]
    ensure_e2e_hitl_mode(api_url=api_url)
    ensure_e2e_onboarding_complete(api_url=api_url)
    await ensure_e2e_hitl_mode_in_browser(chat)
