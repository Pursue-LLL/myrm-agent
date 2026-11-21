"""Tests for the encodability scrub at the start of the post-call guards.

[INPUT]
- agent.middlewares.tooling._tool_guards::run_post_call_guards (POS: the post-call phase under test)
- agent.middlewares.tooling._tool_guards.post_call::_with_encodable_content (POS: the scrub itself)
- agent.security.guards.loop_guard::LoopAction (POS: the verdict the mocked loop guard returns)

[OUTPUT]
- Fails when a tool result keeps a lone surrogate past the first guard, when text that is already encodable is copied,
  or when the scrub drops the status, the call id or the extra fields of the result.

[POS]
A tool result can carry a file name that was not valid UTF-8 (a lone surrogate in Python). The guards after the scrub
hash, persist and log the text with strict encodings, so the scrub is what keeps such a result from failing the call.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from langchain_core.messages import ToolMessage

from myrm_agent_harness.agent.middlewares.tooling._tool_guards import run_post_call_guards
from myrm_agent_harness.agent.middlewares.tooling._tool_guards.post_call import _with_encodable_content
from myrm_agent_harness.agent.security.guards.loop_guard import LoopAction

LONE = "\udcff"  # what os.fsdecode gives the byte 0xFF of a name that is not valid UTF-8
REPLACED = "\ufffd"


def _allowing_verdict() -> MagicMock:
    verdict = MagicMock()
    verdict.action = LoopAction.ALLOW
    verdict.backoff_hint = None
    return verdict


class TestRunPostCallGuards:
    @pytest.mark.asyncio
    async def test_a_lone_surrogate_in_a_result_is_replaced_before_any_guard_sees_it(self) -> None:
        loop_guard = MagicMock()
        loop_guard.record_result.return_value = _allowing_verdict()
        result = ToolMessage(content=f"files: caf\u00e9-{LONE}.txt", name="list_names", tool_call_id="c1")

        out = await run_post_call_guards(
            result,
            "list_names",
            "c1",
            {},
            loop_guard=loop_guard,
            loop_verdict=_allowing_verdict(),
            steering_token=None,
        )

        assert isinstance(out, ToolMessage)
        assert out.content == f"files: caf\u00e9-{REPLACED}.txt"
        assert out.status == "success"
        assert loop_guard.record_result.call_args.args[2] == out.content
        out.content.encode("utf-8")


class TestWithEncodableContent:
    def test_an_encodable_string_result_is_returned_as_the_same_object(self) -> None:
        result = ToolMessage(content="".join(["h\u00e9llo ", "w\u00f6rld"]), tool_call_id="c1")

        assert _with_encodable_content(result) is result

    def test_encodable_blocks_are_returned_as_the_same_object(self) -> None:
        result = ToolMessage(content=[{"type": "text", "text": "plain"}, "bare string"], tool_call_id="c1")

        assert _with_encodable_content(result) is result

    def test_a_text_block_is_replaced_and_every_other_block_is_kept(self) -> None:
        image = {"type": "image_url", "image_url": {"url": "https://example.test/a.png"}}
        result = ToolMessage(
            content=[{"type": "text", "text": f"a{LONE}"}, image, {"type": "text", "text": "fine"}, "bare string"],
            tool_call_id="c1",
        )

        out = _with_encodable_content(result)

        assert out.content == [
            {"type": "text", "text": f"a{REPLACED}"},
            image,
            {"type": "text", "text": "fine"},
            "bare string",
        ]
        assert out.content[1] is result.content[1]
        assert result.content[0] == {"type": "text", "text": f"a{LONE}"}

    def test_the_rest_of_the_result_survives(self) -> None:
        result = ToolMessage(
            content=f"x{LONE}",
            name="list_names",
            tool_call_id="c1",
            status="error",
            additional_kwargs={"error_category": "io"},
            artifact={"path": "a"},
        )

        out = _with_encodable_content(result)

        assert out is not result
        assert (out.name, out.tool_call_id, out.status, out.additional_kwargs, out.artifact) == (
            "list_names",
            "c1",
            "error",
            {"error_category": "io"},
            {"path": "a"},
        )
