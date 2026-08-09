"""Eval dataset storage management.

[INPUT]
- none

[OUTPUT]
- DEFAULT_DATASETS_DIR: dataset storage root.
- get_dataset_path / get_all_datasets: dataset file discovery.
- get_eval_cases / save_eval_cases: raw JSONL read/write.

[POS]
Dataset file layer for the eval module: manages the JSONL datasets under
`.myrm/eval_datasets/`.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_DATASETS_DIR = Path(".myrm/eval_datasets")


def _dataset_sort_key(entry: dict[str, object]) -> float:
    ts = entry.get("updated_at")
    if isinstance(ts, (int, float)):
        return float(ts)
    return 0.0


def get_dataset_path(dataset_id: str | None = None) -> Path:
    """Resolve the file path for a dataset, creating the storage root if needed."""
    DEFAULT_DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    if not dataset_id or dataset_id == "default":
        path = DEFAULT_DATASETS_DIR / "default.jsonl"
        legacy_path = Path(".myrm/eval_cases.jsonl")
        if not path.exists() and legacy_path.exists():
            shutil.move(str(legacy_path), str(path))
        return path

    safe_id = "".join(c for c in dataset_id if c.isalnum() or c in ("-", "_"))
    return DEFAULT_DATASETS_DIR / f"{safe_id}.jsonl"


def get_all_datasets() -> list[dict[str, object]]:
    """List all available evaluation datasets."""
    DEFAULT_DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    datasets: list[dict[str, object]] = []

    # Ensure default exists or migrate
    get_dataset_path("default")

    for file_path in DEFAULT_DATASETS_DIR.glob("*.jsonl"):
        datasets.append(
            {
                "id": file_path.stem,
                "filename": file_path.name,
                "updated_at": file_path.stat().st_mtime,
                "size": file_path.stat().st_size,
            }
        )

    datasets.sort(key=_dataset_sort_key, reverse=True)
    return datasets


def get_eval_cases(dataset_id: str | None = None) -> str:
    """Get the raw content of the eval cases file."""
    cases_path = get_dataset_path(dataset_id)
    if not cases_path.exists():
        return ""
    try:
        with cases_path.open("r", encoding="utf-8") as f:
            return f.read()
    except Exception as exc:
        logger.warning("Failed to read eval cases: %s", exc)
        return ""


def save_eval_cases(content: str, dataset_id: str | None = None) -> bool:
    """Save the raw content to the eval cases file."""
    cases_path = get_dataset_path(dataset_id)
    try:
        cases_path.parent.mkdir(parents=True, exist_ok=True)
        with cases_path.open("w", encoding="utf-8") as f:
            f.write(content)
        return True
    except Exception as exc:
        logger.warning("Failed to save eval cases: %s", exc)
        return False
