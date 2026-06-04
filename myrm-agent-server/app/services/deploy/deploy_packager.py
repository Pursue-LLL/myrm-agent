"""Collect artifact files for Vercel deployment.

[INPUT]
- pathlib.Path (POS: artifact vault object paths)

[OUTPUT]
- DeployFile: dataclass for a single deployable file
- collect_deploy_files: read file or directory into deploy payload

[POS]
Server business layer — packages vault/workspace artifacts for third-party hosting.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

TEXT_EXTENSIONS = frozenset(
    {
        ".html",
        ".htm",
        ".css",
        ".js",
        ".mjs",
        ".cjs",
        ".json",
        ".txt",
        ".md",
        ".svg",
        ".xml",
        ".wasm",
    }
)

MAX_SINGLE_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024


@dataclass(frozen=True)
class DeployFile:
    path: str
    content: str
    encoding: Literal["utf-8", "base64"] = "utf-8"


def _normalize_entry_name(path: Path, obj_path: Path) -> str:
    if path.is_file() and obj_path.is_file():
        if path.suffix.lower() in {".html", ".htm"}:
            return "index.html"
        return path.name
    return path.relative_to(obj_path).as_posix()


def _read_file_entry(file_path: Path, entry_name: str, total_bytes: int) -> tuple[DeployFile, int]:
    raw = file_path.read_bytes()
    next_total = total_bytes + len(raw)
    if len(raw) > MAX_SINGLE_FILE_BYTES:
        raise ValueError(f"File too large for deploy: {entry_name} ({len(raw)} bytes)")
    if next_total > MAX_TOTAL_BYTES:
        raise ValueError(f"Total deploy payload exceeds limit ({MAX_TOTAL_BYTES} bytes)")

    if file_path.suffix.lower() in TEXT_EXTENSIONS:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            encoded = base64.b64encode(raw).decode("ascii")
            return DeployFile(path=entry_name, content=encoded, encoding="base64"), next_total
        return DeployFile(path=entry_name, content=text, encoding="utf-8"), next_total

    encoded = base64.b64encode(raw).decode("ascii")
    return DeployFile(path=entry_name, content=encoded, encoding="base64"), next_total


def collect_deploy_files(obj_path: Path) -> dict[str, DeployFile]:
    """Read a vault file or directory into a deployable file map."""
    if not obj_path.exists():
        raise FileNotFoundError(f"Missing artifact path: {obj_path}")

    files: dict[str, DeployFile] = {}
    total_bytes = 0

    if obj_path.is_file():
        entry_name = _normalize_entry_name(obj_path, obj_path)
        deploy_file, total_bytes = _read_file_entry(obj_path, entry_name, total_bytes)
        files[entry_name] = deploy_file
        return files

    if obj_path.is_dir():
        for file_path in sorted(obj_path.rglob("*")):
            if not file_path.is_file():
                continue
            entry_name = _normalize_entry_name(file_path, obj_path)
            deploy_file, total_bytes = _read_file_entry(file_path, entry_name, total_bytes)
            files[entry_name] = deploy_file
        if not files:
            raise ValueError("Artifact directory contains no deployable files")
        return files

    raise ValueError("Invalid artifact physical format")
