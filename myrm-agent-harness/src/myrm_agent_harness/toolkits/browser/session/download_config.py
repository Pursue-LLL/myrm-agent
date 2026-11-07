"""Download configuration — where a download manager keeps files, how much, for how long, and which kinds.

[INPUT]
- infra.data_dir::resolve_data_dir (POS: Single entry point for the Myrm state root; harness and server code derive every state path from it)

[OUTPUT]
- DownloadConfig: frozen settings of a download manager (directory, size limit, timeout, concurrency, allowed extensions)

[POS]
Download settings, kept apart from the manager that applies them. ``BrowserSession`` takes a ``DownloadConfig`` to turn
download support on: with one the session runs a download manager, without one it has none and its browser contexts
accept no download at all.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from myrm_agent_harness.infra.data_dir import resolve_data_dir

_DEFAULT_ALLOWED_EXTENSIONS: frozenset[str] = frozenset(
    {
        "pdf",
        "csv",
        "xlsx",
        "xls",
        "doc",
        "docx",
        "ppt",
        "pptx",
        "txt",
        "json",
        "xml",
        "zip",
        "gz",
        "tar",
        "rar",
        "7z",
        "md",
        "html",
        "htm",
        "rtf",
        "odt",
        "ods",
        "odp",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "svg",
        "webp",
        "mp3",
        "mp4",
        "wav",
        "avi",
        "mkv",
        "webm",
        "py",
        "js",
        "ts",
        "java",
        "cpp",
        "c",
        "rs",
        "go",
        "yaml",
        "yml",
        "toml",
        "ini",
        "cfg",
        "conf",
        "log",
        "sql",
        "db",
        "sqlite",
        "bak",
    }
)


@dataclass(frozen=True)
class DownloadConfig:
    """Download configuration."""

    downloads_dir: Path = field(default_factory=lambda: resolve_data_dir() / "downloads")
    max_file_size_mb: int = 100
    download_timeout_s: float = 60.0
    max_concurrent_downloads: int = 3
    allowed_extensions: frozenset[str] = _DEFAULT_ALLOWED_EXTENSIONS
