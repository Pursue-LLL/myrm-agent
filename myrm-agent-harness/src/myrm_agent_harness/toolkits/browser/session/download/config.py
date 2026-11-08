"""Download configuration — where a download manager keeps files, how much, for how long, and which kinds.

[OUTPUT]
- DownloadConfig: frozen settings of a download manager (directory and the trusted root it lives below, size limits, quota, timeout, concurrency, allowed extensions, the policy for downloads a page starts)
- PageStartedPolicy: decides whether a download a page started by itself may be kept

[POS]
Download settings, kept apart from the manager that applies them. ``BrowserSession`` takes a ``DownloadConfig`` to turn
download support on: with one the session runs a download manager, without one it has none and its browser contexts
accept no download at all.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

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


# Called with the address a download the page started by itself came from (the page's own address for one it built
# itself); only a True answer lets it be kept. A page starts downloads without any call the agent made, so there is no
# moment to ask anybody: the policy has to decide beforehand.
type PageStartedPolicy = Callable[[str], bool]


@dataclass(frozen=True)
class DownloadConfig:
    """Download configuration.

    ``confined_to`` is the root the caller trusts (absolute and resolved, like the workspace folder): ``downloads_dir``
    lies below it, and every directory and file below the root is created without following a link, because whoever
    can write the root can plant one. ``max_concurrent_downloads`` bounds the saves in progress at once. ``max_files``
    and ``max_total_mb`` cap what the downloads directory holds. They are read from the directory itself, so they
    hold across sessions that share it; downloads saving at the same moment can overshoot them by what they save
    together. ``admit_page_started`` left ``None`` lets every download that passes the address check be kept.
    """

    downloads_dir: Path
    confined_to: Path
    max_file_size_mb: int = 100
    download_timeout_s: float = 60.0
    max_concurrent_downloads: int = 3
    allowed_extensions: frozenset[str] = _DEFAULT_ALLOWED_EXTENSIONS
    max_files: int = 200
    max_total_mb: int = 1024
    admit_page_started: PageStartedPolicy | None = None

    def __post_init__(self) -> None:
        if not self.confined_to.is_absolute():
            raise ValueError(f"confined_to must be an absolute path: {self.confined_to}")
        if not self.downloads_dir.is_relative_to(self.confined_to) or ".." in self.downloads_dir.parts:
            raise ValueError(f"downloads_dir {self.downloads_dir} must lie below confined_to {self.confined_to}")
