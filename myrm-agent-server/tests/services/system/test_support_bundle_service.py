"""The support bundle must build from the real collectors and never carry a credential.

Only the slow, environment-bound collaborators are replaced (settings, the Doctor probes,
the agent store); every collector, the redaction and the zip assembly run for real.
"""

from __future__ import annotations

import asyncio
import io
import json
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
    _TRACE_OMITTED_NOTICE,
    SupportBundleService,
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


def _log_whose_window_starts_inside_the_secret(offset: int) -> str:
    """A JSONL log whose newest ``_MAX_BYTES_PER_EVENT_LOG`` bytes begin ``offset`` bytes into the secret value."""
    secret_line = _secret_line()
    window_part_of_secret_line = len(secret_line) - (secret_line.index(_SECRET) + offset)
    return _jsonl_pad(512) + secret_line + _jsonl_pad(_MAX_BYTES_PER_EVENT_LOG - window_part_of_secret_line)


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
    assert {"platform", "deploy_mode", "disk_metrics"} <= set(json.loads(files["system_info.json"]))
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


async def test_a_slow_doctor_degrades_its_section_without_failing_the_bundle(event_logs: Path) -> None:
    async def never_in_time() -> HealthSnapshot:
        await asyncio.sleep(1)
        return _SNAPSHOT

    with patch(f"{_MODULE}.collect_health_snapshot", new=never_in_time), patch(f"{_MODULE}._COLLECTION_TIMEOUT_SECONDS", 0.01):
        files = await _build()

    assert "error" in json.loads(files["doctor_health.json"])
    assert json.loads(files["active_profiles.json"])[0]["id"] == "writer"


@pytest.mark.parametrize("offset", [6, 15, 30, 45])
def test_a_window_starting_inside_a_secret_publishes_neither_fragment_nor_partial_line(event_logs: Path, offset: int) -> None:
    (event_logs / "session.jsonl").write_text(_log_whose_window_starts_inside_the_secret(offset), encoding="utf-8")

    content = SupportBundleService.collect_recent_event_traces()["session.jsonl"]

    assert _SECRET[offset:] not in content
    assert len(content.encode("utf-8")) <= _MAX_BYTES_PER_EVENT_LOG
    assert all(json.loads(line) for line in content.splitlines())


def test_one_event_larger_than_the_window_is_reported_instead_of_published(event_logs: Path) -> None:
    one_huge_event = json.dumps({"event": "tool_result", "output": "y" * 100 + _SECRET + "z" * _MAX_BYTES_PER_EVENT_LOG}) + "\n"
    (event_logs / "session.jsonl").write_text(one_huge_event, encoding="utf-8")

    assert SupportBundleService.collect_recent_event_traces()["session.jsonl"] == _TRACE_OMITTED_NOTICE


def test_a_log_within_the_window_is_kept_whole(event_logs: Path) -> None:
    log = _jsonl_pad(200) * 3
    (event_logs / "session.jsonl").write_text(log, encoding="utf-8")

    assert SupportBundleService.collect_recent_event_traces()["session.jsonl"] == log


def test_a_window_that_starts_on_a_line_boundary_keeps_every_line(event_logs: Path) -> None:
    newest_line = _jsonl_pad(_MAX_BYTES_PER_EVENT_LOG)
    (event_logs / "session.jsonl").write_text(_jsonl_pad(512) + newest_line, encoding="utf-8")

    assert SupportBundleService.collect_recent_event_traces()["session.jsonl"] == newest_line
