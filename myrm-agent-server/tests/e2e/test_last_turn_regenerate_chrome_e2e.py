"""Chrome E2E: regenerate is offered on the latest turn's answer only (READ lane, no LLM).

Real-user flow: a chat holds two answered turns and a background-task notice appended after the second
answer. Regenerate acts on the latest turn only, so exactly one answer bubble offers it: the second
answer, not the first answer and not the notice.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.e2e.test_memory_keyword_recall_live_chrome_e2e import _attach_probe_js
from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_PAGE_TIMEOUT_MS = 180_000

_ROWS_JS = """(() => {{
  const rows = [...document.querySelectorAll('[data-message-id]')]
    .filter((el) => !el.parentElement?.closest('[data-message-id]'))
    .map((el) => ({{
      text: el.textContent ?? '',
      regenerate: el.querySelectorAll('[data-testid="message-regenerate-button"]').length,
    }}));
  return {{ ready: rows.length === {expected_rows}, rows }};
}})()"""


def _seed_conversation(api_base: str, tag: str) -> str:
    chat_id = f"e2eregen_{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(microsecond=0)

    def row(index: int, role: str, content: str, metadata: dict[str, object] | None = None) -> dict[str, object]:
        message: dict[str, object] = {
            "messageId": f"msg-{index}-{chat_id}",
            "chatId": chat_id,
            "role": role,
            "content": content,
            "createdAt": (now + timedelta(seconds=index)).isoformat(),
        }
        if metadata:
            message["metadata"] = metadata
        return message

    messages = [
        row(0, "user", f"QUESTION-ONE-{tag}"),
        row(1, "assistant", f"ANSWER-ONE-{tag}"),
        row(2, "user", f"QUESTION-TWO-{tag}"),
        row(3, "assistant", f"ANSWER-TWO-{tag}"),
        row(
            4,
            "assistant",
            f"NOTICE-{tag}",
            {"background_job": True, "job_id": "b" * 32, "pid": 4242, "status": "exited", "exit_code": 0},
        ),
    ]
    http_json(
        "POST",
        f"{api_base}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "E2E Last Turn Regenerate",
            "action_mode": "agent",
            "is_incognito": False,
            "messages": messages,
        },
    )
    return chat_id


def _row_with(rows: list[dict[str, object]], marker: str) -> dict[str, object]:
    matches = [row for row in rows if marker in str(row["text"])]
    assert len(matches) == 1, (marker, rows)
    return matches[0]


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_only_the_latest_turn_answer_offers_regenerate() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    tag = uuid.uuid4().hex[:6]
    chat_id = _seed_conversation(api_url, tag)

    target_url = f"{ui_url.rstrip('/')}/{chat_id}"
    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(target_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=target_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=120.0, page_url=target_url)
        assert bridge.get("ready") is True, bridge

        attached = wait_for_state(client, page, _attach_probe_js(chat_id), timeout_sec=120.0, page_url=target_url)
        assert attached.get("ready") is True, attached

        state = wait_for_state(client, page, _ROWS_JS.format(expected_rows=5), timeout_sec=60.0, page_url=target_url)
        rows = state["rows"]
        assert isinstance(rows, list)

        first_answer = _row_with(rows, f"ANSWER-ONE-{tag}")
        latest_answer = _row_with(rows, f"ANSWER-TWO-{tag}")
        notice = _row_with(rows, f"NOTICE-{tag}")
        assert first_answer["regenerate"] == 0, first_answer
        assert latest_answer["regenerate"] == 1, latest_answer
        assert notice["regenerate"] == 0, notice
        assert sum(int(str(row["regenerate"])) for row in rows) == 1, rows
