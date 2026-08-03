"""Co-Pilot API — run digest + session advisor.

[INPUT]
HTTP requests for run digest CRUD and advisor chat.

[OUTPUT]
JSON responses with digest data or advisor thread messages.

[POS]
Thin API layer delegating to copilot service modules.
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.core.utils.response_utils import error_response, success_response
from app.services.copilot.advisor_service import ask_advisor
from app.services.copilot.advisor_thread_store import AdvisorThreadStore
from app.services.copilot.run_digest_store import RunDigestStore

router = APIRouter()


class AdvisorAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    selection_snippet: str | None = Field(default=None, max_length=2000)


@router.get("/{chat_id}/copilot/run-digest")
async def get_run_digest(chat_id: str):
    digest = RunDigestStore.get(chat_id)
    if digest is None:
        return success_response(data={"digest": None})
    return success_response(data={"digest": digest.to_dict()})


@router.get("/{chat_id}/copilot/advisor/messages")
async def list_advisor_messages(chat_id: str):
    messages = [msg.to_dict() for msg in AdvisorThreadStore.list_messages(chat_id)]
    return success_response(data={"messages": messages})


@router.delete("/{chat_id}/copilot/advisor/messages")
async def clear_advisor_messages(chat_id: str):
    AdvisorThreadStore.clear(chat_id)
    return success_response(data={"cleared": True})


@router.post("/{chat_id}/copilot/advisor/ask")
async def advisor_ask(chat_id: str, body: AdvisorAskRequest, request: Request):
    question = body.question.strip()
    if not question:
        return error_response(message="Question cannot be empty", code=400)

    accept_lang = request.headers.get("Accept-Language", "en")

    AdvisorThreadStore.append(parent_chat_id=chat_id, role="user", content=question)
    reply, tier = await ask_advisor(
        chat_id=chat_id,
        question=question,
        selection_snippet=body.selection_snippet,
        accept_language=accept_lang,
    )
    msg = AdvisorThreadStore.append(
        parent_chat_id=chat_id,
        role="assistant",
        content=reply,
        tier=tier,
    )
    return success_response(
        data={
            "reply": reply,
            "tier": tier,
            "message": msg.to_dict(),
        }
    )
