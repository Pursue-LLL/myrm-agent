"""Eval report persistence.

[INPUT]
- none

[OUTPUT]
- DEFAULT_REPORTS_DIR: single-profile eval report storage root.
- get_latest_report_summary / get_all_report_summaries: report readers.

[POS]
Report file layer for the eval module: reads summary and historical reports
for the standard eval suite.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import cast

logger = logging.getLogger(__name__)

DEFAULT_REPORTS_DIR = Path(".myrm/eval_reports")


def get_latest_report_summary(
    reports_dir: Path | None = None,
) -> dict[str, object] | None:
    """Get the summary from the latest evaluation report."""
    reports_dir = reports_dir or DEFAULT_REPORTS_DIR
    latest_path = reports_dir / "latest.jsonl"

    if not latest_path.exists():
        return None

    try:
        with latest_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
            if not lines:
                return None
            raw = json.loads(lines[0])
            if not isinstance(raw, dict):
                return None
            data = cast(dict[str, object], {str(k): v for k, v in raw.items()})
            if data.get("type") == "summary":
                cases_list: list[object] = []
                data["cases"] = cases_list
                for line in lines[1:]:
                    if line.strip():
                        cases_list.append(json.loads(line))
                return data
    except Exception as exc:
        logger.warning("Failed to read latest eval report: %s", exc)

    return None


def get_all_report_summaries(
    reports_dir: Path | None = None,
) -> list[dict[str, object]]:
    """Get summaries of all historical evaluation reports, sorted by timestamp descending."""
    reports_dir = reports_dir or DEFAULT_REPORTS_DIR
    if not reports_dir.exists():
        return []

    summaries = []
    report_files = list(reports_dir.glob("eval_report_*.jsonl"))
    report_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    for report_path in report_files:
        try:
            with report_path.open("r", encoding="utf-8") as f:
                first_line = f.readline()
                if first_line:
                    data = json.loads(first_line)
                    if data.get("type") == "summary":
                        filename = report_path.name
                        ts_str = filename.replace("eval_report_", "").replace(
                            ".jsonl", ""
                        )
                        try:
                            data["timestamp"] = int(ts_str)
                        except ValueError:
                            data["timestamp"] = int(report_path.stat().st_mtime)
                        data["filename"] = filename
                        summaries.append(data)
        except Exception as exc:
            logger.warning("Failed to read report %s: %s", report_path, exc)

    return summaries
