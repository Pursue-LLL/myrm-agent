"""Evaluation Capture Module.

[INPUT]
- myrm_agent_harness.eval.builder::extract_case_from_trajectory
- app.services.chat.chat_service::ChatService
- app.core.eval.service::save_eval_cases, get_eval_cases

[OUTPUT]
- capture_case_from_chat: Extract EvalCase from a chat session and append it.

[POS]
Provides the business logic to capture a user's successful chat session
into a reusable evaluation benchmark.
"""

from __future__ import annotations

import dataclasses
import json
import logging

from myrm_agent_harness.eval.builder import extract_case_from_trajectory

from app.core.eval.service import get_eval_cases, save_eval_cases
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)


async def capture_case_from_chat(chat_id: str, dataset_id: str | None = None) -> bool:
    """Capture a chat session into an evaluation case.

    Extracts message history and tool calls from the chat session, converts them
    to a MultiTurnEvalCase using the Harness primitive, and saves it to the
    sandbox's eval_cases.jsonl.
    """
    messages = await ChatService.get_all_messages(chat_id)
    if not messages:
        logger.warning(f"No messages found for chat_id={chat_id}")
        return False

    trajectory: list[dict[str, object]] = []
    tools_called = []

    for msg in messages:
        # Check if message has extra_data representing tool calls
        if msg.extra_data and isinstance(msg.extra_data, dict):
            if "tool_calls" in msg.extra_data:
                tool_calls = msg.extra_data["tool_calls"]
                if isinstance(tool_calls, list):
                    for tool_call in tool_calls:
                        if isinstance(tool_call, dict):
                            tools_called.append(tool_call)
                        elif hasattr(tool_call, "model_dump"):
                            tools_called.append(tool_call.model_dump())
                        elif dataclasses.is_dataclass(tool_call) and not isinstance(tool_call, type):
                            tools_called.append(dataclasses.asdict(tool_call))
                        elif hasattr(tool_call, "__dict__"):
                            tools_called.append(tool_call.__dict__)
                        elif hasattr(tool_call, "name"):
                            tools_called.append({"name": tool_call.name})

        trajectory.append({"role": msg.role, "content": msg.content})

    chat_meta = await ChatService.get_chat_metadata(chat_id)
    profile_id = chat_meta.agent_id if chat_meta and chat_meta.agent_id else "default"

    multi_turn_case = extract_case_from_trajectory(
        messages=trajectory, tools_called=list(tools_called), metadata={"chat_id": chat_id, "profile_id": profile_id}
    )

    current_content = get_eval_cases(dataset_id)

    new_case_dict = dataclasses.asdict(multi_turn_case)
    new_line = json.dumps(new_case_dict, ensure_ascii=False)

    if current_content:
        if not current_content.endswith("\n"):
            current_content += "\n"
        new_content = current_content + new_line + "\n"
    else:
        new_content = new_line + "\n"

    success = save_eval_cases(new_content, dataset_id)
    if success:
        logger.info(f"Successfully captured chat {chat_id} to eval cases (profile: {profile_id})")
    return success
