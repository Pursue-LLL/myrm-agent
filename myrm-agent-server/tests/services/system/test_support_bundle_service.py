"""The support bundle must build from the real collectors and never carry a credential.

Only the slow, environment-bound collaborators are replaced (settings, the Doctor probes,
the agent store); every collector, the redaction and the zip assembly run for real.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import time
import zipfile
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.backends.profiles.types import AgentProfile
from myrm_agent_harness.observability.diagnostics.protocols import HealthReport

from app.config.settings import DatabaseSettings
from app.core.infra.health.health_snapshot import HealthSnapshot
from app.services.system.support_bundle_service import (
    _MAX_BYTES_PER_EVENT_LOG,
    _MAX_BYTES_PER_TRACE_LINE,
    SupportBundleService,
    _newest_whole_events,
    _read_log_tail,
)

_MODULE = "app.services.system.support_bundle_service"
_SECRET = "sk-proj-Ab3dEf6hIj9kLm2nOp5qRs8tUv1wXy4zA7bC0dE3fG6hJ9kL"
_PROMPT = "PRIVATE-PROMPT-TEXT"

_SNAPSHOT = HealthSnapshot(
    harness_reports=(
        HealthReport(component_name="BrowserToolkit", status="warn", message="Browser is slow", detail=f"api_key={_SECRET}"),
    ),
    server_reports=(HealthReport(component_name="Database", status="pass", message="Database is reachable"),),
)
_PROFILE = AgentProfile(
    id="writer",
    display_name="Writer",
    model="test-model",
    max_iterations=20,
    skills=["pdf", "xlsx"],
    tools_allowed=["web_search"],
    system_prompt=_PROMPT,
    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
)


def _jsonl_pad(size: int) -> str:
    """One valid JSONL line of exactly ``size`` bytes."""
    return '{"pad":"' + "x" * (size - 11) + '"}\n'


def _secret_line() -> str:
    return json.dumps({"event": "tool_call", "args": {"api_key": _SECRET}}) + "\n"


def _event(seq: int, event_type: str, payload_size: int = 0) -> str:
    """One event line shaped like the event log writes it, with a payload of ``payload_size`` characters."""
    event = {"seq": seq, "ts": 1790000000.0 + seq, "type": event_type, "sid": "s1", "data": {"output": "p" * payload_size}}
    return json.dumps(event, ensure_ascii=False) + "\n"


@pytest.fixture
def event_logs(tmp_path: Path) -> Iterator[Path]:
    """Settings pointing at a temp state dir, a fixed Doctor snapshot and a one-agent store."""
    logs = tmp_path / "event_logs"
    logs.mkdir()
    database = DatabaseSettings.model_construct(
        _fields_set=None, state_dir=str(tmp_path), event_log_dir=str(logs), checkpointer_mode="", database_url=""
    )
    with (
        patch(f"{_MODULE}.get_settings", return_value=SimpleNamespace(database=database)),
        patch(f"{_MODULE}.collect_health_snapshot", new=AsyncMock(return_value=_SNAPSHOT)),
        patch(f"{_MODULE}.AgentService.get_agent_list", new=AsyncMock(return_value=([_PROFILE], 1))),
    ):
        yield logs


async def _build(**options: bool) -> dict[str, str]:
    data = await SupportBundleService.build_bundle_zip(**options)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        return {name: archive.read(name).decode("utf-8") for name in archive.namelist()}


async def test_every_section_is_collected_for_real(event_logs: Path) -> None:
    (event_logs / "session.jsonl").write_text(_jsonl_pad(100), encoding="utf-8")

    files = await _build()

    assert set(files) == {
        "MANIFEST.json",
        "system_info.json",
        "doctor_health.json",
        "active_profiles.json",
        "traces/session.jsonl",
    }
    system_info = json.loads(files["system_info.json"])
    assert {"platform", "deploy_mode", "disk_metrics"} <= set(system_info)
    assert (system_info["checkpointer_mode"], system_info["graph_store"]) == ("sqlite", "sqlite")
    doctor = json.loads(files["doctor_health.json"])
    assert [r["component_name"] for r in doctor["harness"]] == ["BrowserToolkit"]
    assert [r["component_name"] for r in doctor["server"]] == ["Database"]
    assert json.loads(files["active_profiles.json"]) == [
        {
            "id": "writer",
            "display_name": "Writer",
            "model": "test-model",
            "max_iterations": 20,
            "built_in": False,
            "no_builtin_tools": False,
            "created_at": "2026-01-01T00:00:00+00:00",
            "tools_allowed": ["web_search"],
            "skills_count": 2,
        }
    ]


async def test_system_info_reports_the_configured_storage_backends(event_logs: Path) -> None:
    configured = DatabaseSettings.model_construct(
        _fields_set=None,
        state_dir=str(event_logs.parent),
        event_log_dir=str(event_logs),
        checkpointer_mode="memory",
        database_url="postgresql://db.internal/myrm",
    )

    with patch(f"{_MODULE}.get_settings", return_value=SimpleNamespace(database=configured)):
        system_info = await SupportBundleService.collect_system_info()

    assert (system_info["checkpointer_mode"], system_info["graph_store"]) == ("memory", "age")


async def test_sections_can_be_left_out(event_logs: Path) -> None:
    (event_logs / "session.jsonl").write_text(_jsonl_pad(100), encoding="utf-8")

    files = await _build(include_traces=False, include_profiles=False)

    assert set(files) == {"MANIFEST.json", "system_info.json", "doctor_health.json"}


async def test_no_credential_or_prompt_reaches_any_file(event_logs: Path) -> None:
    (event_logs / "session.jsonl").write_text(_secret_line(), encoding="utf-8")

    files = await _build()

    for name, content in files.items():
        assert _SECRET not in content, name
        assert _SECRET[-24:] not in content, name
        assert _PROMPT not in content, name


async def test_a_session_cookie_in_command_output_never_reaches_the_bundle(event_logs: Path) -> None:
    stdout = "> GET /api HTTP/1.1\n> Cookie: sessionid=Zk3fQ9xLm2Pq7Rt1; csrftoken=Vb8nWc4Yd6Xe0Aj5\n< HTTP/1.1 200 OK"
    event = {"seq": 1, "type": "bash_command_executed", "data": {"stdout": stdout, "stderr": ""}}
    (event_logs / "session.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    files = await _build()

    assert "Zk3fQ9xL" not in files["traces/session.jsonl"]
    assert json.loads(files["traces/session.jsonl"])["data"]["stdout"] == "> GET /api HTTP/1.1\n> Cookie: ***\n< HTTP/1.1 200 OK"


async def test_a_slow_doctor_degrades_its_section_without_failing_the_bundle(event_logs: Path) -> None:
    async def never_in_time() -> HealthSnapshot:
        await asyncio.sleep(1)
        return _SNAPSHOT

    with patch(f"{_MODULE}.collect_health_snapshot", new=never_in_time), patch(f"{_MODULE}._COLLECTION_TIMEOUT_SECONDS", 0.01):
        files = await _build()

    assert "TimeoutError" in json.loads(files["doctor_health.json"])["error"]
    assert json.loads(files["active_profiles.json"])[0]["id"] == "writer"


@pytest.mark.parametrize("room_left", [1, 15, 45, 100])
def test_a_line_that_does_not_fit_the_budget_is_left_out_whole(event_logs: Path, room_left: int) -> None:
    secret_line = _secret_line()
    assert room_left < len(secret_line)
    full_lines = 7
    last_line = _MAX_BYTES_PER_EVENT_LOG - room_left - full_lines * _MAX_BYTES_PER_TRACE_LINE
    log = _jsonl_pad(512) + secret_line + _jsonl_pad(_MAX_BYTES_PER_TRACE_LINE) * full_lines + _jsonl_pad(last_line)
    (event_logs / "session.jsonl").write_text(log, encoding="utf-8")

    content = SupportBundleService.collect_recent_event_traces()["session.jsonl"]

    assert "api_key" not in content
    assert _SECRET[:12] not in content
    assert 0 < len(content.encode("utf-8")) <= _MAX_BYTES_PER_EVENT_LOG
    assert all(json.loads(line) for line in content.splitlines())


def test_an_oversized_newest_event_leaves_the_earlier_history_in_place(event_logs: Path) -> None:
    huge_prompt = _event(3, "llm_request", payload_size=_MAX_BYTES_PER_EVENT_LOG)
    (event_logs / "session.jsonl").write_text(_event(1, "tool_start") + _event(2, "tool_end") + huge_prompt, encoding="utf-8")

    lines = [json.loads(line) for line in SupportBundleService.collect_recent_event_traces()["session.jsonl"].splitlines()]

    assert [line["seq"] for line in lines] == [1, 2, 3]
    assert lines[2] == {
        "seq": 3,
        "ts": 1790000003.0,
        "type": "llm_request",
        "omitted_bytes": len(huge_prompt.encode("utf-8")) - 1,
    }


def test_a_secret_inside_an_oversized_event_never_reaches_the_bundle(event_logs: Path) -> None:
    event = json.loads(_event(1, "llm_request"))
    event["data"]["prompt"] = "x" * 100 + _SECRET + "y" * _MAX_BYTES_PER_TRACE_LINE
    (event_logs / "session.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    content = SupportBundleService.collect_recent_event_traces()["session.jsonl"]

    assert _SECRET[:12] not in content
    assert "xxxxxxxx" not in content
    assert json.loads(content)["type"] == "llm_request"


def test_an_oversized_line_that_is_not_an_event_leaves_only_its_size(event_logs: Path) -> None:
    (event_logs / "session.jsonl").write_text("z" * (_MAX_BYTES_PER_TRACE_LINE + 1) + "\n", encoding="utf-8")

    content = SupportBundleService.collect_recent_event_traces()["session.jsonl"]

    assert json.loads(content) == {"omitted_bytes": _MAX_BYTES_PER_TRACE_LINE + 1}


def test_a_field_too_long_to_be_a_name_is_not_copied_into_the_marker(event_logs: Path) -> None:
    event = json.loads(_event(1, "t" * 500, payload_size=_MAX_BYTES_PER_TRACE_LINE))
    (event_logs / "session.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")

    marker = json.loads(SupportBundleService.collect_recent_event_traces()["session.jsonl"])

    assert set(marker) == {"seq", "ts", "omitted_bytes"}


def test_a_long_log_keeps_the_newest_whole_events_within_the_budget(event_logs: Path) -> None:
    events = [_event(seq, "tool_end", payload_size=2000) for seq in range(1, 101)]
    (event_logs / "session.jsonl").write_text("".join(events), encoding="utf-8")

    content = SupportBundleService.collect_recent_event_traces()["session.jsonl"]

    kept = len(content.encode("utf-8")) // len(events[0].encode("utf-8"))
    assert 0 < kept < len(events)
    assert content == "".join(events[-kept:])
    assert (
        len(content.encode("utf-8")) <= _MAX_BYTES_PER_EVENT_LOG < len(content.encode("utf-8")) + len(events[0].encode("utf-8"))
    )


def test_the_budget_counts_bytes_not_characters(event_logs: Path) -> None:
    events = [json.dumps({"seq": seq, "data": "中" * 2000}, ensure_ascii=False) + "\n" for seq in range(1, 31)]
    (event_logs / "session.jsonl").write_text("".join(events), encoding="utf-8")

    content = SupportBundleService.collect_recent_event_traces()["session.jsonl"]

    assert len(content.encode("utf-8")) <= _MAX_BYTES_PER_EVENT_LOG
    assert len(content) < _MAX_BYTES_PER_EVENT_LOG // 2
    assert content.endswith(events[-1])


def test_an_unterminated_last_line_is_not_published(event_logs: Path) -> None:
    complete = _event(1, "tool_end")
    (event_logs / "session.jsonl").write_text(complete + '{"seq": 2, "data": {"api_key": "sk-proj-Ab3dEf6hIj9', encoding="utf-8")

    assert SupportBundleService.collect_recent_event_traces()["session.jsonl"] == complete


def test_a_line_separator_character_inside_an_event_does_not_split_it(event_logs: Path) -> None:
    line = json.dumps({"seq": 1, "data": "first\u2028second\x0bthird"}, ensure_ascii=False) + "\n"
    (event_logs / "session.jsonl").write_text(line, encoding="utf-8")

    assert SupportBundleService.collect_recent_event_traces()["session.jsonl"] == line


def test_a_log_within_the_budget_is_kept_whole(event_logs: Path) -> None:
    log = _jsonl_pad(200) * 3
    (event_logs / "session.jsonl").write_text(log, encoding="utf-8")

    assert SupportBundleService.collect_recent_event_traces()["session.jsonl"] == log


def test_only_the_end_of_a_very_long_log_is_looked_at(event_logs: Path) -> None:
    events = [_event(seq, "tool_end", payload_size=300) for seq in range(1, 21)]
    (event_logs / "session.jsonl").write_text("".join(events), encoding="utf-8")
    window = len(events[0].encode("utf-8")) * 3 + 5  # all 20 events would fit the budget, only the last 3 are in the window

    with patch(f"{_MODULE}._TRACE_SCAN_BYTES", window):
        content = SupportBundleService.collect_recent_event_traces()["session.jsonl"]

    assert content == "".join(events[-3:])


@pytest.mark.parametrize("window", [600, 601, 10_000])
def test_a_log_no_longer_than_the_window_is_read_whole(tmp_path: Path, window: int) -> None:
    log = tmp_path / "session.jsonl"
    log.write_text(_jsonl_pad(200) * 3, encoding="utf-8")

    assert _read_log_tail(log, window) == _jsonl_pad(200) * 3


def test_a_longer_log_is_read_from_the_first_whole_line_inside_the_window(tmp_path: Path) -> None:
    lines = [_event(seq, "tool_end", payload_size=50) for seq in range(1, 41)]
    log = tmp_path / "session.jsonl"
    log.write_text("".join(lines), encoding="utf-8")
    window = len(lines[0].encode("utf-8")) * 5 + 17  # starts inside the sixth line from the end

    tail = _read_log_tail(log, window)

    assert tail == "".join(lines[-5:])


def test_a_window_that_starts_on_a_line_boundary_keeps_that_line(tmp_path: Path) -> None:
    lines = [_jsonl_pad(100) for _ in range(10)]
    log = tmp_path / "session.jsonl"
    log.write_text("".join(lines), encoding="utf-8")

    assert _read_log_tail(log, 300) == "".join(lines[-3:])


@pytest.mark.parametrize("offset_into_character", [0, 1, 2])
def test_a_window_that_starts_inside_a_multibyte_character_does_not_leave_damage(
    tmp_path: Path, offset_into_character: int
) -> None:
    line = json.dumps({"seq": 1, "data": "中" * 50}, ensure_ascii=False) + "\n"
    log = tmp_path / "session.jsonl"
    log.write_text(line * 20, encoding="utf-8")
    window = len(line.encode("utf-8")) * 3 + line.encode("utf-8").index("中".encode("utf-8")) + offset_into_character

    tail = _read_log_tail(log, window)

    assert tail == line * 3


@pytest.mark.parametrize("ending", ["\n", ""])
def test_a_window_inside_one_very_long_line_yields_nothing(tmp_path: Path, ending: str) -> None:
    log = tmp_path / "session.jsonl"
    log.write_text("z" * 5_000 + ending, encoding="utf-8")

    assert _read_log_tail(log, 1_000) == ""


async def test_collecting_the_traces_does_not_stall_the_event_loop(event_logs: Path) -> None:
    (event_logs / "session.jsonl").write_text(_event(1, "tool_end"), encoding="utf-8")

    def as_slow_as_a_full_size_log(text: str, max_bytes: int) -> str:
        time.sleep(0.4)  # the masking of ten full-size logs took seconds of CPU on a loaded machine
        return _newest_whole_events(text, max_bytes)

    stalls: list[float] = []

    async def heartbeat() -> None:
        last = time.perf_counter()
        while True:
            await asyncio.sleep(0.01)
            now = time.perf_counter()
            stalls.append(now - last)
            last = now

    beat = asyncio.create_task(heartbeat())
    await asyncio.sleep(0.05)
    with patch(f"{_MODULE}._newest_whole_events", new=as_slow_as_a_full_size_log):
        files = await _build()
    await asyncio.sleep(0.05)  # lets the heartbeat report a stall that ended with the build
    beat.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await beat

    assert "traces/session.jsonl" in files
    assert max(stalls) < 0.2
