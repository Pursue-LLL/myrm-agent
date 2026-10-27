"""BoundedScratchpad keeps what the next run needs and nothing more: a metric cap, field limits and a byte budget."""

from __future__ import annotations

import json
from pathlib import Path

from myrm_agent_harness.toolkits.cron.continuity.scratchpad import BoundedScratchpad


def _stored(directory: Path, job_id: str = "job-1") -> dict[str, str]:
    return json.loads((directory / f"{job_id}.scratchpad.json").read_text(encoding="utf-8"))


def test_only_the_first_twenty_metrics_are_kept_in_order(tmp_path: Path) -> None:
    pad = BoundedScratchpad(tmp_path)
    metrics = {f"m{i:02d}": str(i) for i in range(35)}

    assert pad.save("job-1", last_metrics=metrics) is True

    assert list(_stored(tmp_path)) == [f"metric_m{i:02d}" for i in range(20)]


def test_fewer_metrics_than_the_cap_are_all_kept(tmp_path: Path) -> None:
    pad = BoundedScratchpad(tmp_path)

    pad.save("job-1", last_metrics={"errors": "3", "p99_ms": "120"})

    assert _stored(tmp_path) == {"metric_errors": "3", "metric_p99_ms": "120"}


def test_a_metric_name_is_cut_to_32_characters_and_its_value_to_64(tmp_path: Path) -> None:
    pad = BoundedScratchpad(tmp_path)

    pad.save("job-1", last_metrics={"k" * 50: "v" * 100})

    assert _stored(tmp_path) == {"metric_" + "k" * 32: "v" * 64}


def test_a_long_summary_is_cut_to_500_characters(tmp_path: Path) -> None:
    pad = BoundedScratchpad(tmp_path)

    pad.save("job-1", last_summary="S" * 800)

    assert _stored(tmp_path) == {"last_summary": "S" * 500}


def test_a_summary_over_the_byte_budget_shrinks_to_200_characters(tmp_path: Path) -> None:
    """Multi-byte text is measured in bytes: 500 characters of CJK are 1500 bytes, over the 1 KB budget."""
    pad = BoundedScratchpad(tmp_path)

    pad.save("job-1", last_summary="汉" * 500)

    assert _stored(tmp_path) == {"last_summary": "汉" * 200}
