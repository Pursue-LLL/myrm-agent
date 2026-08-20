"""Chrome E2E: chat message → wiki pending compound via live API."""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_api_url,
    http_json,
    prepare_e2e_ui_session,
)


def _seed_compound_chat(
    api_url: str,
    *,
    is_incognito: bool = False,
) -> tuple[str, str, str]:
    chat_id = f"e2e-compound-chat-{uuid.uuid4().hex[:12]}"
    user_id = f"e2e-compound-user-{uuid.uuid4().hex[:8]}"
    assistant_id = f"e2e-compound-asst-{uuid.uuid4().hex[:8]}"
    created_at = datetime.now(UTC).replace(microsecond=0)
    user_created = created_at.isoformat()
    assistant_created = (created_at + timedelta(seconds=1)).isoformat()

    http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/chats/",
        {
            "chat_id": chat_id,
            "title": "E2E Wiki Compound Chat",
            "action_mode": "agent",
            "is_incognito": is_incognito,
            "messages": [
                {
                    "messageId": user_id,
                    "chatId": chat_id,
                    "role": "user",
                    "content": "What is continuous integration?",
                    "createdAt": user_created,
                },
                {
                    "messageId": assistant_id,
                    "chatId": chat_id,
                    "role": "assistant",
                    "content": "Continuous integration automates testing on every change.",
                    "createdAt": assistant_created,
                },
            ],
        },
    )
    return chat_id, user_id, assistant_id


def _compound_post(
    api_url: str,
    *,
    chat_id: str,
    message_id: str,
    concept_name: str,
    expected_statuses: frozenset[int] = frozenset({200}),
) -> dict[str, object]:
    payload = http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/wiki/compound",
        {
            "concept_name": concept_name,
            "source_chat": chat_id,
            "source_message": message_id,
        },
        expected_statuses=expected_statuses,
    )
    assert isinstance(payload, dict)
    return payload


def _run_compound_api_assertions(api_url: str) -> None:
    chat_id, _user_id, assistant_id = _seed_compound_chat(api_url)
    concept_name = f"ChatCompounds/2026-08/e2e-{uuid.uuid4().hex[:8]}"

    pending_before = http_json("GET", f"{api_url.rstrip('/')}/api/v1/wiki/pending")
    assert isinstance(pending_before, dict)
    pending_count_before = len(pending_before.get("pending_edits", []))

    compound = _compound_post(
        api_url,
        chat_id=chat_id,
        message_id=assistant_id,
        concept_name=concept_name,
    )
    assert compound.get("success") is True
    pending_edit_id = compound.get("pending_edit_id")
    assert isinstance(pending_edit_id, int) and pending_edit_id > 0

    pending_after = http_json("GET", f"{api_url.rstrip('/')}/api/v1/wiki/pending")
    assert isinstance(pending_after, dict)
    edits = pending_after.get("pending_edits")
    assert isinstance(edits, list)
    assert len(edits) >= pending_count_before + 1
    matched = next(
        (item for item in edits if isinstance(item, dict) and item.get("id") == pending_edit_id),
        None,
    )
    assert matched is not None, pending_after
    proposed = str(matched.get("proposed_content") or "")
    assert "What is continuous integration?" in proposed
    assert "Continuous integration automates testing on every change." in proposed
    assert assistant_id in proposed

    duplicate_status = None
    try:
        _compound_post(
            api_url,
            chat_id=chat_id,
            message_id=assistant_id,
            concept_name=f"{concept_name}-dup",
        )
    except RuntimeError as exc:
        if "returned 409" in str(exc):
            duplicate_status = 409
        else:
            raise
    assert duplicate_status == 409


def _run_compound_approve_concept_provenance(api_url: str) -> None:
    """Full loop: compound → approve → publish → get_concept returns provenance."""
    chat_id, _user_id, assistant_id = _seed_compound_chat(api_url)
    concept_name = f"ChatCompounds/2026-08/closure-{uuid.uuid4().hex[:8]}"

    compound = _compound_post(
        api_url,
        chat_id=chat_id,
        message_id=assistant_id,
        concept_name=concept_name,
    )
    assert compound.get("success") is True
    pending_edit_id = compound.get("pending_edit_id")
    assert isinstance(pending_edit_id, int) and pending_edit_id > 0

    approved = http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/wiki/pending/{pending_edit_id}/approve",
        {},
    )
    assert approved.get("success") is True

    concept = http_json(
        "GET",
        f"{api_url.rstrip('/')}/api/v1/wiki/concepts/{concept_name}",
    )
    assert concept.get("source_chat") == chat_id, concept
    assert concept.get("source_message") == assistant_id, concept


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_compound_live_api_stages_pending() -> None:
    """POST /wiki/compound on live stack, assert pending edit appears."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    _run_compound_api_assertions(api_url)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_compound_live_api_rejects_incognito_chat() -> None:
    """Incognito chats must not compound into wiki (403 incognito_forbidden)."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    chat_id, _user_id, assistant_id = _seed_compound_chat(api_url, is_incognito=True)
    detail = _compound_post(
        api_url,
        chat_id=chat_id,
        message_id=assistant_id,
        concept_name=f"ChatCompounds/2026-08/incognito-{uuid.uuid4().hex[:8]}",
        expected_statuses=frozenset({403}),
    )
    assert detail.get("detail", {}).get("code") == "incognito_forbidden"


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_compound_live_api_rejects_user_message_role() -> None:
    """Only assistant messages can be compounded (422 invalid_role)."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    chat_id, user_id, _assistant_id = _seed_compound_chat(api_url)
    detail = _compound_post(
        api_url,
        chat_id=chat_id,
        message_id=user_id,
        concept_name=f"ChatCompounds/2026-08/user-role-{uuid.uuid4().hex[:8]}",
        expected_statuses=frozenset({422}),
    )
    assert detail.get("detail", {}).get("code") == "invalid_role"


@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_compound_approve_publishes_provenance() -> None:
    """Full loop on live stack: compound → approve → publish → get_concept provenance."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    _run_compound_approve_concept_provenance(api_url)
