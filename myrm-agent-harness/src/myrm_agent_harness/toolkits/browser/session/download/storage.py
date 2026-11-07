"""Download storage — where saved downloads live: their names, the directory's quota, and the copy from the browser.

[INPUT]
- patchright.async_api::Download (POS: Patchright download object)
- session.download.config::DownloadConfig (POS: where a download manager keeps files, how much, for how long, and which kinds)
- session.download.errors::DownloadError (POS: the error of a download that is not kept)
- session.download.records::DownloadResult (POS: the shapes the download manager, its storage and the session-level download APIs exchange)

[OUTPUT]
- DownloadStorage: saves one browser download into the downloads directory under a unique, sanitized name, within the directory's quota
- sanitize_filename: a suggested file name as one safe path segment

[POS]
The disk side of the download domain. A name is claimed with ``O_EXCL`` before the browser writes to it, so downloads
that save at the same moment never pick the same one; the quota (file count and total bytes) is read from the
directory itself, because chat sessions share it and an in-memory count would only know one of them; the directory is
created, and made to ignore itself in version control, by the first claim, so a workspace that never downloads gets
nothing. Whatever is not kept leaves no file behind: a claim is released on every failure, refusal and cancellation.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from .config import DownloadConfig
from .errors import DownloadError
from .records import DownloadResult

if TYPE_CHECKING:
    from patchright.async_api import Download

_FILENAME_SANITIZE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_IGNORE_FILE_NAME = ".gitignore"
_MIB = 1024 * 1024
# A hostile page chooses the extension too, so only this much of it is quoted in a reason.
_QUOTED_EXTENSION_LENGTH = 16


def sanitize_filename(name: str) -> str:
    """Sanitize filename to prevent directory traversal and invalid characters."""
    name = Path(name).name
    name = _FILENAME_SANITIZE_RE.sub("_", name)
    return name.strip(". ") or "download"


def _ignore_directory(directory: Path) -> None:
    """Make version control skip the directory and everything in it: the workspace may be a project under it."""
    ignore_file = directory / _IGNORE_FILE_NAME
    if not ignore_file.exists():
        with contextlib.suppress(OSError):
            ignore_file.write_text("*\n", encoding="utf-8")


class DownloadStorage:
    """The downloads directory of one download manager."""

    def __init__(self, config: DownloadConfig) -> None:
        self._config = config

    async def save(self, download: Download) -> DownloadResult:
        """Copy a download out of the browser under a unique, sanitized name.

        Raises:
            DownloadError: the file type is not allowed, the directory is full, the file is too large, or the
                browser could not write it. Nothing is left behind in any of these cases.
        """
        name = sanitize_filename(download.suggested_filename)
        extension = Path(name).suffix.lower().lstrip(".")
        if extension and extension not in self._config.allowed_extensions:
            raise DownloadError(f'file type ".{extension[:_QUOTED_EXTENSION_LENGTH]}" is not allowed')
        files, total_bytes = self._usage()
        if files >= self._config.max_files or total_bytes >= self._config.max_total_mb * _MIB:
            raise self._full()

        path = self._claim_name(name)
        try:
            await self._copy(download, path)
            size = self._checked_size(path)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return DownloadResult(
            url=download.url, path=str(path), file_name=path.name, file_size=size, file_type=extension or None
        )

    def _usage(self) -> tuple[int, int]:
        """The files and bytes the directory holds now (a directory that does not exist yet holds none)."""
        files = total_bytes = 0
        try:
            with os.scandir(self._config.downloads_dir) as entries:
                for entry in entries:
                    with contextlib.suppress(OSError):  # a file removed meanwhile is simply not counted
                        if entry.name != _IGNORE_FILE_NAME and entry.is_file(follow_symlinks=False):
                            total_bytes += entry.stat(follow_symlinks=False).st_size
                            files += 1
        except (FileNotFoundError, NotADirectoryError):
            pass  # the first claim creates the directory, or reports why it cannot
        except OSError as e:
            raise DownloadError("the downloads folder cannot be read", detail=str(e)) from e
        return files, total_bytes

    def _full(self) -> DownloadError:
        config = self._config
        return DownloadError(
            f"the downloads folder is full (at most {config.max_files} files or {config.max_total_mb} MB); "
            f"delete files you no longer need in {config.downloads_dir}, then try again"
        )

    def _claim_name(self, name: str) -> Path:
        """Create an empty file under a name no other download holds, and return its path.

        The browser overwrites it. The mode is the one a new file gets (the umask decides), which is also what the
        browser's own copy ends up with, since it keeps the mode of the file it overwrites.
        """
        directory = self._config.downloads_dir
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise DownloadError("the downloads folder cannot be created", detail=str(e)) from e
        _ignore_directory(directory)

        stem, suffix = os.path.splitext(name)
        counter = 0
        while True:
            candidate = directory / (name if counter == 0 else f"{stem} ({counter}){suffix}")
            try:
                os.close(os.open(candidate, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o666))
            except FileExistsError:
                counter += 1
            except OSError as e:
                raise DownloadError("the file cannot be created in the downloads folder", detail=str(e)) from e
            else:
                return candidate

    async def _copy(self, download: Download, path: Path) -> None:
        """Have the browser write the download to ``path``, within the configured time."""
        try:
            await asyncio.wait_for(download.save_as(str(path)), timeout=self._config.download_timeout_s)
        except TimeoutError as e:
            raise DownloadError(f"saving did not finish within {self._config.download_timeout_s:g} s") from e
        except Exception as e:
            failure = None
            with contextlib.suppress(Exception):
                failure = await download.failure()
            raise DownloadError("the browser could not save the file", detail=f"{e} (failure={failure})") from e

    def _checked_size(self, path: Path) -> int:
        """The size of the saved file, once it is known to fit the file limit and the directory's quota."""
        try:
            size = path.stat().st_size
        except OSError as e:
            raise DownloadError("the saved file disappeared", detail=str(e)) from e
        if size > self._config.max_file_size_mb * _MIB:
            raise DownloadError(f"the file is larger than {self._config.max_file_size_mb} MB")
        if self._usage()[1] > self._config.max_total_mb * _MIB:
            raise self._full()
        return size
