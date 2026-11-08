"""Download storage — where saved downloads live: their names, the directory's quota, and the copy from the browser.

[INPUT]
- patchright.async_api::Download (POS: Patchright download object)
- core.security.path::open_directory_beneath, ConfinedDirectory, UnsafeDirectoryError (POS: exclusive file creation below a trusted directory, decided on descriptors so no link redirects it)
- session.download.config::DownloadConfig (POS: where a download manager keeps files, how much, for how long, and which kinds)
- session.download.errors::DownloadError (POS: the error of a download that is not kept)
- session.download.records::DownloadResult (POS: the shapes the download manager, its storage and the session-level download APIs exchange)

[OUTPUT]
- DownloadStorage: saves one browser download into the downloads directory under a unique, sanitized name, within the directory's quota
- sanitize_filename: a suggested file name as one safe path segment of bounded length

[POS]
The disk side of the download domain. The browser has finished a download when it is looked at: its own copy is read
from the path it reports, so the size is known before a byte is copied and a file that is empty, too large or over the
quota is refused without being written. The sandboxed agent can write the workspace this folder lives in, so a save
never trusts a name below the workspace root: the directory is opened without following a link, the file is created
exclusively below it and written only through the descriptor that creation returned. A name is claimed by that
exclusive create, so downloads that save at the same moment never pick the same one; the quota (file count and total
bytes) is read from the directory itself, because chat sessions share it and an in-memory count would only know one of
them; the directory is created, and made to ignore itself in version control, by the first save, so a workspace that
never downloads gets nothing. A file that is not kept is removed on every failure, refusal and cancellation; only a
process that dies in the middle of a copy can leave a partial file.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.core.security.path import ConfinedDirectory, UnsafeDirectoryError, open_directory_beneath

from .config import DownloadConfig
from .errors import DownloadError
from .records import DownloadResult

if TYPE_CHECKING:
    from patchright.async_api import Download

_FILENAME_SANITIZE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_IGNORE_FILE_NAME = ".gitignore"
_MIB = 1024 * 1024
# A copy moves one chunk per thread hop: the event loop never waits on the disk, a cancelled save stops at the next
# chunk, and the chunk is all the memory a copy holds.
_COPY_CHUNK_BYTES = 4 * _MIB
# A hostile page chooses the extension too, so only this much of it is quoted in a reason.
_QUOTED_EXTENSION_LENGTH = 16
# File systems cap a name at 255 bytes (not characters); the room left is for the " (n)" that makes a name unique.
_MAX_NAME_BYTES = 200
_MAX_EXTENSION_BYTES = 16


def _within_name_limit(name: str) -> str:
    """``name`` cut at a character boundary to ``_MAX_NAME_BYTES`` UTF-8 bytes, keeping a short extension."""
    if len(name.encode()) <= _MAX_NAME_BYTES:
        return name
    stem, extension = os.path.splitext(name)
    if len(extension.encode()) > _MAX_EXTENSION_BYTES:  # a long tail after a dot is part of the name, not a type
        stem, extension = name, ""
    room = _MAX_NAME_BYTES - len(extension.encode())
    return (stem.encode()[:room].decode(errors="ignore").rstrip(". ") or "download") + extension


def sanitize_filename(name: str) -> str:
    """A suggested file name as one path segment without traversal or characters a file system rejects."""
    name = Path(name).name
    name = _FILENAME_SANITIZE_RE.sub("_", name)
    return _within_name_limit(name.strip(". ") or "download")


def _ignore_directory(directory: ConfinedDirectory) -> None:
    """Make version control skip the directory and everything in it: the workspace may be a project under it."""
    # An ignore file that is there already stays as its owner wrote it; one that cannot be written is no reason to refuse
    with contextlib.suppress(OSError), os.fdopen(directory.create_new(_IGNORE_FILE_NAME), "wb") as ignore_file:
        ignore_file.write(b"*\n")


class DownloadStorage:
    """The downloads directory of one download manager."""

    def __init__(self, config: DownloadConfig) -> None:
        self._config = config

    async def save(self, download: Download) -> DownloadResult:
        """Copy a finished download out of the browser under a unique, sanitized name.

        Raises:
            DownloadError: the file type is not allowed, the directory is full or cannot be used, the file is empty
                or too large, or the browser could not finish it. Nothing is left behind in any of these cases.
        """
        name = sanitize_filename(download.suggested_filename)
        extension = Path(name).suffix.lower().lstrip(".")
        if extension and extension not in self._config.allowed_extensions:
            raise DownloadError(f'file type ".{extension[:_QUOTED_EXTENSION_LENGTH]}" is not allowed')
        with self._open_directory() as directory:
            self._check_quota(directory, incoming=1)  # a full folder refuses before the body is waited for
            source = await self._finished_file(download)
            size = self._checked_size(source)
            self._check_quota(directory, incoming=size)
            file_name = await self._copy(source, directory, name)
        return DownloadResult(
            url=download.url,
            path=str(directory.path / file_name),
            file_name=file_name,
            file_size=size,
            file_type=extension or None,
        )

    def _open_directory(self) -> ConfinedDirectory:
        """The downloads directory, created on first use, reached from the workspace root without following a link."""
        config = self._config
        below_root = config.downloads_dir.relative_to(config.confined_to).parts
        try:
            directory = open_directory_beneath(config.confined_to, below_root)
        except UnsafeDirectoryError as e:
            raise DownloadError(
                f"the downloads folder {config.downloads_dir} cannot be used because {e.component} is a link; "
                "replace it with a real folder",
                detail=str(e),
            ) from e
        except OSError as e:
            raise DownloadError("the downloads folder cannot be opened", detail=str(e)) from e
        _ignore_directory(directory)
        return directory

    @staticmethod
    def _usage(directory: ConfinedDirectory) -> tuple[int, int]:
        """The files and bytes the directory holds now."""
        files = total_bytes = 0
        try:
            with directory.scandir() as entries:
                for entry in entries:
                    with contextlib.suppress(OSError):  # a file removed meanwhile is simply not counted
                        if entry.name != _IGNORE_FILE_NAME and entry.is_file(follow_symlinks=False):
                            total_bytes += entry.stat(follow_symlinks=False).st_size
                            files += 1
        except OSError as e:
            raise DownloadError("the downloads folder cannot be read", detail=str(e)) from e
        return files, total_bytes

    def _check_quota(self, directory: ConfinedDirectory, incoming: int) -> None:
        """Refuse when ``incoming`` more bytes in one more file would take the directory over its quota."""
        files, total_bytes = self._usage(directory)
        if files >= self._config.max_files or total_bytes + incoming > self._config.max_total_mb * _MIB:
            raise self._full()

    def _full(self) -> DownloadError:
        config = self._config
        return DownloadError(
            f"the downloads folder is full (at most {config.max_files} files or {config.max_total_mb} MB); "
            f"delete files you no longer need in {config.downloads_dir}, then try again"
        )

    async def _finished_file(self, download: Download) -> Path:
        """The browser's own finished copy of the download, once it is complete (within the configured time).

        Needs a browser this process launched or attached to; a remote ``connect()`` reports no local path.
        """
        try:
            return Path(await asyncio.wait_for(download.path(), timeout=self._config.download_timeout_s))
        except TimeoutError as e:
            raise DownloadError(f"saving did not finish within {self._config.download_timeout_s:g} s") from e
        except Exception as e:
            failure = None
            with contextlib.suppress(Exception):
                failure = await download.failure()
            raise DownloadError("the browser could not save the file", detail=f"{e} (failure={failure})") from e

    def _checked_size(self, source: Path) -> int:
        """The size of the finished file, once it is known to be a file with content that fits the file limit."""
        try:
            size = source.stat().st_size
        except OSError as e:
            raise DownloadError("the downloaded file disappeared", detail=str(e)) from e
        if size == 0:
            raise DownloadError("the downloaded file is empty")
        if size > self._config.max_file_size_mb * _MIB:
            raise DownloadError(f"the file is larger than {self._config.max_file_size_mb} MB")
        return size

    async def _copy(self, source: Path, directory: ConfinedDirectory, name: str) -> str:
        """Copy ``source`` into a new file of ``directory`` and return the name the file got."""
        file_name, fd = self._claim(directory, name)
        try:
            await self._write(source, fd)
        except BaseException as e:
            with contextlib.suppress(OSError):
                directory.unlink(file_name)
            if isinstance(e, OSError):
                raise DownloadError("the file could not be copied into the downloads folder", detail=str(e)) from e
            raise
        return file_name

    @staticmethod
    def _claim(directory: ConfinedDirectory, name: str) -> tuple[str, int]:
        """Create a new file under a name no other download holds: that name, and the descriptor to write it through.

        The mode is the one a new file gets (the umask decides). A taken name gets ``" (n)"`` before its extension.
        """
        stem, suffix = os.path.splitext(name)
        counter = 0
        while True:
            candidate = name if counter == 0 else f"{stem} ({counter}){suffix}"
            try:
                return candidate, directory.create_new(candidate)
            except FileExistsError:
                counter += 1
            except OSError as e:
                raise DownloadError("the file cannot be created in the downloads folder", detail=str(e)) from e

    @staticmethod
    async def _write(source: Path, fd: int) -> None:
        """Copy ``source`` into ``fd``, which this closes; the loop never blocks on a chunk."""
        with os.fdopen(fd, "wb") as target, source.open("rb") as reader:
            while chunk := await asyncio.to_thread(reader.read, _COPY_CHUNK_BYTES):
                await asyncio.to_thread(target.write, chunk)
