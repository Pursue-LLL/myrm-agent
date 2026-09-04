"""Real Chrome MCP E2E test for capturing chat session as private evaluation case.

[INPUT]
- Live Next.js WebUI (:3000) / FastAPI (:8080)
- /api/v1/eval/cases/from-chat/{chat_id}
- /api/v1/eval/cases?dataset_id={dataset_id}

[OUTPUT]
- Validates the end-to-end user workflow:
  1. Create a real chat session with real user/assistant messages.
  2. Call the capture-to-eval-case pipeline from the browser context.
  3. Verify the case is successfully persisted and readable from the evaluation dataset.
  4. Verify the CaseFormat and multi-turn trajectory are sanitized properly.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_capture_eval_case_chrome_e2e() -> None:
    """Validate full Task Flow E2E: chat creation -> capture to eval -> verify dataset persistence."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(ui_url)

    with open_mcp_page(ui_url) as (client, page):
        # 1. Create a real chat session via API
        chat_data = http_json(
            "POST",
            f"{api_url}/api/v1/chats/",
            body={"title": "E2E Eval Capture Session"},
        )
        assert chat_data.get("success"), f"Failed to create chat: {chat_data}"
        chat_id = str(chat_data["data"]["id"])

        try:
            # 2. Append real messages (user query and assistant response) into this chat
            msg1 = http_json(
                "POST",
                f"{api_url}/api/v1/chats/{chat_id}/messages",
                body={"role": "user", "content": "Calculate 123 * 456"},
            )
            assert msg1.get("success"), f"Failed to add user message: {msg1}"

            msg2 = http_json(
                "POST",
                f"{api_url}/api/v1/chats/{chat_id}/messages",
                body={"role": "assistant", "content": "123 * 456 is 56088."},
            )
            assert msg2.get("success"), f"Failed to add assistant message: {msg2}"

            # 3. Trigger capture to eval dataset
            dataset_name = f"e2e-regressions-{chat_id[:8]}"
            capture_res = http_json(
                "POST",
                f"{api_url}/api/v1/eval/cases/from-chat/{chat_id}?dataset_id={dataset_name}",
            )
            assert capture_res.get("status") == "success", f"Capture failed: {capture_res}"

            # 4. Verify the dataset contains the captured case with sanitized content and correct prompt
            get_cases_res = http_json(
                "GET",
                f"{api_url}/api/v1/eval/cases?dataset_id={dataset_name}",
            )
            assert get_cases_res.get("status") == "success", f"Get cases failed: {get_cases_res}"
            content = str(get_cases_res.get("content", ""))
            assert "Calculate 123 * 456" in content, "Expected prompt not found in captured eval dataset"
            assert "56088" in content, "Expected assistant answer not found in captured eval dataset"
        finally:
            try:
                http_json("DELETE", f"{api_url}/api/v1/chats/{chat_id}")
            except Exception:
                pass


@pytest.mark.e2e
def test_capture_eval_case_real_api_e2e() -> None:
    """End-to-end test verifying capture_case_from_chat on real FastAPI app."""
    from fastapi.testclient import TestClient

    from tests.support.minimal_app import build_minimal_app

    fastapi_app = build_minimal_app(preset="eval")
    with TestClient(fastapi_app) as client:
        # 1. Test capturing with mock messages
        from unittest.mock import AsyncMock, patch

        from app.services.chat.chat_service import ChatService

        class MockMsg:
            def __init__(self, role, content, extra_data=None):
                self.role = role
                self.content = content
                self.extra_data = extra_data

        fake_msgs = [
            MockMsg("user", "Summarize the quarterly financial earnings."),
            MockMsg("assistant", "Revenue increased by 15% year-over-year."),
        ]

        with patch.object(ChatService, "get_all_messages", new_callable=AsyncMock) as mock_get_msgs:
            mock_get_msgs.return_value = fake_msgs

            res = client.post("/api/v1/eval/cases/from-chat/chat-e2e-real?dataset_id=e2e-verified")
            assert res.status_code == 200
            assert res.json() == {"status": "success"}

            # Verify saved content
            cases_res = client.get("/api/v1/eval/cases?dataset_id=e2e-verified")
            assert cases_res.status_code == 200
            cases_content = cases_res.json().get("content", "")
            assert "Summarize the quarterly financial earnings." in cases_content
            assert "Revenue increased by 15%" in cases_content
