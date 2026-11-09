"""Log deduplication must never replace data the caller asked for, and must keep every distinct log message."""

from __future__ import annotations

import json

import pytest

from myrm_agent_harness.agent.meta_tools.bash._compression.log_compressor import LogCompressor
from myrm_agent_harness.agent.meta_tools.bash._compression.output_compressor import compress_output


def _file_listing() -> str:
    return "\n".join(f"./src/pkg{i % 7}/module{i}.py" for i in range(150))


def _json_dump() -> str:
    pods = {
        "kind": "PodList",
        "items": [
            {"name": f"svc-{i}-abcde", "ready": "1/1", "status": "Running", "restarts": i % 3, "node": f"node-{i % 3}"}
            for i in range(20)
        ],
    }
    return json.dumps(pods, indent=2)


DATA_OUTPUTS = {
    "find listing": ("find . -name '*.py'", _file_listing()),
    "grep file list": ("grep -rl TODO src", _file_listing()),
    "python json dump": ("import json\nprint(json.dumps(pods, indent=2))", _json_dump()),
    "csv rows": ("cat rows.csv", "\n".join(f"{i},user{i % 5},active,2026-11-0{i % 9 + 1}" for i in range(150))),
    "blank lines": ("echo", "\n" * 120),
}


@pytest.mark.parametrize(("command", "output"), list(DATA_OUTPUTS.values()), ids=list(DATA_OUTPUTS))
def test_data_output_reaches_the_model_unchanged(command: str, output: str) -> None:
    assert compress_output(command, output) == output
    assert LogCompressor().compress(output) is None


def test_a_few_log_lines_inside_data_do_not_make_a_log_stream() -> None:
    logs = [f"2026-11-02T08:01:09Z INFO healthcheck ok {i % 3}" for i in range(100)]
    output = "\n".join([*logs, *_file_listing().splitlines()[:60]])

    assert LogCompressor().compress(output) is None


def test_every_distinct_info_message_survives_deduplication() -> None:
    lines = ["2026-11-02T08:01:09Z INFO healthcheck ok"] * 120
    lines.insert(40, "2026-11-02T08:01:10Z INFO initializing database pool size=500")
    lines.insert(90, "2026-11-02T08:01:11Z INFO http server listening on :8080")

    result = LogCompressor().compress("\n".join(lines))

    assert result is not None
    assert "Auto-deduplicated" in result
    assert "[×120] 2026-11-02T08:01:09Z INFO healthcheck ok" in result
    assert "initializing database pool size=500" in result
    assert "http server listening on :8080" in result


def test_info_messages_are_listed_in_first_seen_order_and_capped() -> None:
    lines = [f"2026-11-02T08:01:09Z INFO step-{i:02d} finished" for i in range(40) for _ in range(6)]

    result = LogCompressor().compress("\n".join(lines))

    assert result is not None
    assert "step-00 finished" in result
    assert "step-19 finished" in result
    assert "step-20 finished" not in result
    assert "... +20 more distinct info messages" in result
    assert result.index("step-00") < result.index("step-19")


@pytest.mark.parametrize(
    "record",
    [
        "Nov  9 10:00:01 host sshd[123]: Failed password for root from 10.0.0.1 port 22",
        "INFO:root:request handled",
        "[2026-11-02 08:01:09] app.INFO: request handled",
        "2026/11/02 08:01:09 [error] 77#0: upstream timed out",
        '203.0.113.5 - - [09/Nov/2026:10:00:01 +0000] "GET /health HTTP/1.1" 200 2',
    ],
)
def test_common_log_formats_are_still_deduplicated(record: str) -> None:
    output = "\n".join([record] * 150)

    result = LogCompressor().compress(output)

    assert result is not None
    assert "Auto-deduplicated" in result
    assert "[×150]" in result
    assert len(result) < len(output)
