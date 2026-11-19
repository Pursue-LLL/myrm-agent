"""What the model sees of a secret a background job printed.

A job's lines are kept as the program printed them; a read masks them (``output_window``), and the guardrail
middleware screens the tool result once more before the model sees it. These tests run both layers: the real registry,
the real ``bash_process_tool`` and the real ``SecurityGuardrailMiddleware``.
"""

from __future__ import annotations

import json
from typing import cast

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.meta_tools.bash._background.registry import get_background_registry
from myrm_agent_harness.agent.meta_tools.bash._background.types import OUTPUT_RING_LINES
from myrm_agent_harness.agent.meta_tools.bash.bash_process_tools import create_bash_process_tool
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeProc, wait_until
from tests.agent.meta_tools.bash.guardrail_view import shown_to_model
from tests.agent.meta_tools.bash.secret_shapes import (
    FORM_KEYS,
    KEY_KINDS,
    LINE_ONLY_FORM_KEYS,
    key_block,
    key_body,
)

pytestmark = pytest.mark.usefixtures("jobs")

_SESSION = "secrets-session"
_CONFIG: RunnableConfig = {"configurable": {"context": {"session_id": _SESSION}}}
_BODY = key_body()


async def _settled(jobs: list[FakeProc], pid: int, *, stdout: list[str], stderr: list[str] | None = None) -> None:
    """Run a job that printed these lines and ended."""
    proc = FakeProc(
        pid=pid,
        stdout=[("\n".join(stdout) + "\n").encode()] if stdout else [],
        stderr=[("\n".join(stderr) + "\n").encode()] if stderr else [],
    )
    jobs.append(proc)
    registry = get_background_registry()
    await registry.register(cast(AsyncProcessProtocol, proc), command="print-secrets", session_id=_SESSION)
    proc.finish(0)
    await wait_until(
        lambda: (info := registry.get(pid)) is not None and info.status != "running", what="the job to settle"
    )


async def _read(pid: int, *, action: str = "output", max_lines: int = 100) -> dict[str, object]:
    arguments: dict[str, object] = {"action": action, "pid": pid, "max_lines": max_lines}
    if action == "wait":
        arguments = {"action": "wait", "pid": pid, "timeout_seconds": 5}
    result = await create_bash_process_tool().ainvoke(arguments, config=_CONFIG)
    return cast(dict[str, object], result["content"])


async def _shown(
    jobs: list[FakeProc], pid: int, lines: list[str], *, action: str = "output", max_lines: int = 100
) -> str:
    """What the model is shown of a job that printed *lines*."""
    await _settled(jobs, pid, stdout=lines)
    return shown_to_model(await _read(pid, action=action, max_lines=max_lines))


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["output", "wait"])
@pytest.mark.parametrize("kind", KEY_KINDS)
async def test_a_key_block_a_job_printed_does_not_reach_the_model(jobs: list[FakeProc], kind: str, action: str) -> None:
    await _settled(jobs, 72001, stdout=["building", *key_block(kind), "done"])

    content = await _read(72001, action=action)

    # The read masks the block itself; the guardrail is a second layer and covers fewer kinds.
    read_text = json.dumps(content["stdout"])
    assert not any(part in read_text for part in _BODY)
    assert not any(part in shown_to_model(content) for part in _BODY)
    assert "building" in read_text
    assert "done" in read_text


@pytest.mark.asyncio
async def test_a_key_block_wider_than_the_lines_asked_for_does_not_reach_the_model(jobs: list[FakeProc]) -> None:
    """53 lines of key, the last 20 asked for: the opening line lies outside them, and the block is still seen whole."""
    block = key_block()
    assert len(block) == 53
    await _settled(jobs, 72002, stdout=[*block, "after the key"])

    content = await _read(72002, max_lines=20)

    # The read itself masks the block, before the guardrail has a say.
    read_text = json.dumps(content["stdout"])
    assert not any(part in read_text for part in _BODY)
    assert "...redacted..." in read_text
    assert "after the key" in read_text
    assert not any(part in shown_to_model(content) for part in _BODY)


@pytest.mark.asyncio
async def test_a_form_body_with_twenty_credential_keys_is_masked_in_every_key(jobs: list[FakeProc]) -> None:
    values = [f"val{i:02d}Zq9xK7" for i in range(len(FORM_KEYS))]
    body = "&".join(f"{key}={value}" for key, value in zip(FORM_KEYS, values, strict=True))

    await _settled(jobs, 72003, stdout=[f"{body}&lang=en"])

    content = await _read(72003)

    read_text = json.dumps(content["stdout"])
    assert [value for value in values if value in read_text] == []
    assert [value for value in values if value in shown_to_model(content)] == []
    assert "lang=en" in read_text


@pytest.mark.asyncio
async def test_a_form_body_between_other_lines_is_masked_in_every_key(jobs: list[FakeProc]) -> None:
    """The form-body rule reads a line that stands alone: a window of several lines is masked line by line first."""
    values = [f"val{i:02d}Zq9xK7" for i in range(len(LINE_ONLY_FORM_KEYS))]
    body = "&".join(f"{key}={value}" for key, value in zip(LINE_ONLY_FORM_KEYS, values, strict=True))

    await _settled(jobs, 72010, stdout=["building", f"{body}&lang=en", "done"])

    content = await _read(72010)

    read_text = json.dumps(content["stdout"])
    assert [value for value in values if value in read_text] == []
    assert "lang=en" in read_text
    assert "done" in read_text


@pytest.mark.asyncio
async def test_a_key_block_masking_folds_into_fewer_lines_is_not_counted_as_missing(jobs: list[FakeProc]) -> None:
    """55 lines printed and all in the window: the masked view has fewer, and not one of the 55 is left out."""
    await _settled(jobs, 72011, stdout=["before", *key_block(), "after"])

    content = await _read(72011)

    assert len(cast(list[str], content["stdout"])) < 55
    assert content["dropped"] is False
    assert "omitted_lines" not in content


@pytest.mark.asyncio
async def test_a_json_pair_split_over_two_lines_does_not_reach_the_model(jobs: list[FakeProc]) -> None:
    await _settled(jobs, 72004, stdout=["{", '  "client_secret":', '    "s3cr3t-value-0123456789"', "}"])

    content = await _read(72004)

    assert "s3cr3t-value-0123456789" not in json.dumps(content["stdout"])
    assert "s3cr3t-value-0123456789" not in shown_to_model(content)


@pytest.mark.asyncio
async def test_the_stderr_stream_is_masked_like_stdout(jobs: list[FakeProc]) -> None:
    await _settled(jobs, 72005, stdout=[], stderr=key_block())

    content = await _read(72005)

    assert not any(part in shown_to_model(content) for part in _BODY)
    assert "...redacted..." in json.dumps(content["stderr"])


@pytest.mark.asyncio
async def test_a_progress_message_built_from_a_line_with_a_secret_does_not_carry_it(jobs: list[FakeProc]) -> None:
    line = 'MYRM_PROGRESS {"percent": 40, "message": "uploading with password=hunter2hunter2"}'
    await _settled(jobs, 72006, stdout=[line])

    listed = await create_bash_process_tool().ainvoke({"action": "list"}, config=_CONFIG)
    info = get_background_registry().get(72006)

    assert info is not None
    assert info.last_progress is not None
    assert "hunter2hunter2" not in json.dumps(info.last_progress)
    assert "hunter2hunter2" not in json.dumps(listed["content"])


# The shapes below reach the model today: neither the redaction engine nor the guardrail has a rule for them. Each test
# states what must hold; it fails as an unexpected pass the day a rule masks the shape, and the marker is then removed.
_NO_RULE = "no redaction rule covers this shape"


@pytest.mark.xfail(strict=True, reason=_NO_RULE)
@pytest.mark.asyncio
async def test_a_pgp_key_block_does_not_reach_the_model(jobs: list[FakeProc]) -> None:
    shown = await _shown(jobs, 72007, key_block("PGP PRIVATE KEY BLOCK"))

    assert not any(part in shown for part in _BODY)


@pytest.mark.xfail(strict=True, reason=_NO_RULE)
@pytest.mark.asyncio
async def test_a_key_block_cut_before_its_end_does_not_reach_the_model(jobs: list[FakeProc]) -> None:
    shown = await _shown(jobs, 72008, key_block()[:-1])

    assert not any(part in shown for part in _BODY)


@pytest.mark.xfail(strict=True, reason=_NO_RULE)
@pytest.mark.asyncio
async def test_the_end_of_a_key_block_whose_opening_line_left_the_window_does_not_reach_the_model(
    jobs: list[FakeProc],
) -> None:
    printed = [*key_block(body=_BODY[:4]), *(f"progress {i}" for i in range(OUTPUT_RING_LINES - 5))]
    assert len(printed) == OUTPUT_RING_LINES + 1

    shown = await _shown(jobs, 72009, printed, max_lines=OUTPUT_RING_LINES)

    assert not any(part in shown for part in _BODY[:4])
