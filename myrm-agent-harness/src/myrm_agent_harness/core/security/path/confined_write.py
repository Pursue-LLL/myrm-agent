"""Writes that a link cannot redirect: new files below a trusted directory, created through descriptors.

Whoever can write a folder chooses what sits under the names the product creates in it: a symlink in place of a
directory, a link swapped in for a file between the moment its name is taken and the moment it is written, a hard link
to a file elsewhere. A write by path (``open(path, "wb")``, ``Path.mkdir(parents=True)``) follows all of them and lands
where the folder's writer chose, with the rights of the process that writes. Here every directory below the trusted
root is opened with ``O_NOFOLLOW`` relative to the one above it, a file is created exclusively below that directory's
descriptor, and the caller writes through the descriptor creation returned, so no path is looked at a second time.

[INPUT]
- (stdlib: os, stat, errno, contextlib, pathlib)

[OUTPUT]
- UnsafeDirectoryError: a directory on the way is a link, so nothing may be written below it
- ConfinedDirectory: an opened directory below the root: ``scandir``, ``create_new``, ``unlink``, ``close`` (a closed directory refuses every use)
- open_directory_beneath(root, parts, *, create) -> ConfinedDirectory — open (and create) ``root/parts`` without following a link

[POS]
Write primitive of the path-safety package, the counterpart of ``bounded_read`` for files the product creates in a
folder somebody else can also write: the decision is made on descriptors, never on a path that is looked at twice.
Where descriptors cannot anchor a directory (Windows) the names are checked one by one with ``lstat`` instead, which
refuses a link that is there but cannot close the window between that check and the use; the root itself is trusted
(the caller resolved it) and is followed.
"""

from __future__ import annotations

import contextlib
import errno
import os
import stat
from collections.abc import Iterator, Sequence
from pathlib import Path
from types import TracebackType
from typing import Self

__all__ = ("ConfinedDirectory", "UnsafeDirectoryError", "open_directory_beneath")

# A link at the final name is refused too, and the name must not exist yet: a hard link planted under the wanted name
# makes the exclusive create fail instead of opening a file that is shared with somewhere else.
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
_NEW_FILE_FLAGS = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
_NEW_FILE_MODE = 0o666  # the umask decides, as for any new file
_NEW_DIRECTORY_MODE = 0o777


class UnsafeDirectoryError(OSError):
    """A directory on the way is a link, which would send what is written below it somewhere else."""

    def __init__(self, component: str) -> None:
        super().__init__(f"{component} is a link, not a directory")
        self.component = component


def _single_name(name: str) -> str:
    """``name`` if it is one path segment: a separator or a dot name would step out of the directory it is used in."""
    if name in ("", ".", "..") or os.sep in name or (os.altsep is not None and os.altsep in name):
        raise ValueError(f"not a single path segment: {name!r}")
    return name


def _anchors_on_descriptors() -> bool:
    """Whether a directory can be held as a descriptor that later names are resolved against (read per call)."""
    return (
        os.open in os.supports_dir_fd
        and os.mkdir in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and os.scandir in os.supports_fd
    )


class ConfinedDirectory:
    """A directory below a trusted root, kept open so that swapping its name for a link later changes nothing."""

    def __init__(self, path: Path, fd: int | None) -> None:
        self.path = path  # the root and the names below it, as written: where a result says the files are
        self._fd = fd  # None where descriptors cannot anchor the directory
        self._closed = False

    def _require_open(self) -> None:
        # A closed directory has no descriptor left, which must not read as "no descriptor can anchor it": that
        # would send the next write down the path-based route, through whatever link now stands at the path.
        if self._closed:
            raise ValueError("the confined directory is closed")

    @contextlib.contextmanager
    def scandir(self) -> Iterator[Iterator[os.DirEntry[str]]]:
        """The entries of this very directory (read them with ``follow_symlinks=False``).

        Each listing reads through a descriptor opened for it: listings that shared one would cut each other short, and
        a descriptor opened before files were created can be answered with a listing older than them (seen on overlayfs,
        the usual root file system of a container). The descriptor stays open as long as the listing does, because the
        entries read their attributes through it.
        """
        self._require_open()
        if self._fd is None:
            with os.scandir(self.path) as entries:
                yield entries
            return
        listing_fd = os.open(".", _DIRECTORY_FLAGS, dir_fd=self._fd)
        try:
            with os.scandir(listing_fd) as entries:
                yield entries
        finally:
            os.close(listing_fd)

    def create_new(self, name: str) -> int:
        """A descriptor open for writing on a file created now under ``name``.

        Raises:
            FileExistsError: ``name`` exists, as a file, a link or anything else.
            ValueError: the directory is closed, or ``name`` is not a single path segment.
        """
        self._require_open()
        _single_name(name)
        if self._fd is None:
            return os.open(self.path / name, _NEW_FILE_FLAGS, _NEW_FILE_MODE)
        return os.open(name, _NEW_FILE_FLAGS, _NEW_FILE_MODE, dir_fd=self._fd)

    def unlink(self, name: str) -> None:
        """Remove the entry ``name`` of this directory (the link itself, if it is one)."""
        self._require_open()
        _single_name(name)
        if self._fd is None:
            os.unlink(self.path / name)
        else:
            os.unlink(name, dir_fd=self._fd)

    def close(self) -> None:
        """Release the descriptor; every later use of the directory raises ``ValueError``. Closing again does nothing."""
        if self._closed:
            return
        self._closed = True
        if self._fd is not None:
            os.close(self._fd)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, traceback: TracebackType | None
    ) -> None:
        self.close()


def _is_link_at(parent_fd: int, name: str) -> bool:
    try:
        return stat.S_ISLNK(os.lstat(name, dir_fd=parent_fd).st_mode)
    except OSError:
        return False


def _open_directory_at(parent_fd: int, name: str) -> int:
    """Open the directory ``name`` of ``parent_fd``; a link there, dangling or not, is refused."""
    try:
        return os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
    except OSError as e:
        # ``O_NOFOLLOW`` on a link fails with ELOOP or ENOTDIR, the same errors a plain file gives
        if e.errno in (errno.ELOOP, errno.ENOTDIR) and _is_link_at(parent_fd, name):
            raise UnsafeDirectoryError(name) from e
        raise


def _open_child(parent_fd: int, name: str, create: bool) -> int:
    try:
        return _open_directory_at(parent_fd, name)
    except FileNotFoundError:
        if not create:
            raise
    with contextlib.suppress(FileExistsError):  # a download saving at the same moment created it first
        os.mkdir(name, _NEW_DIRECTORY_MODE, dir_fd=parent_fd)
    return _open_directory_at(parent_fd, name)  # a link swapped in since is refused here, not followed


def _descend(root: Path, parts: Sequence[str], create: bool) -> int:
    fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        for part in parts:
            child = _open_child(fd, _single_name(part), create)
            os.close(fd)
            fd = child
    except BaseException:
        os.close(fd)
        raise
    return fd


def _walk(root: Path, parts: Sequence[str], create: bool) -> Path:
    """The fallback where descriptors cannot anchor a directory: each name is checked with ``lstat`` before it is used."""
    current = root
    for part in parts:
        current = current / _single_name(part)
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            if not create:
                raise
            with contextlib.suppress(FileExistsError):
                os.mkdir(current, _NEW_DIRECTORY_MODE)
            info = os.lstat(current)
        if stat.S_ISLNK(info.st_mode) or os.path.isjunction(current):
            raise UnsafeDirectoryError(part)
        if not stat.S_ISDIR(info.st_mode):
            raise NotADirectoryError(errno.ENOTDIR, os.strerror(errno.ENOTDIR), str(current))
    return current


def open_directory_beneath(root: Path, parts: Sequence[str], *, create: bool = True) -> ConfinedDirectory:
    """Open ``root/parts`` without following a link below ``root``, creating the missing directories when ``create``.

    ``root`` is trusted: it must be absolute and already resolved by the caller, and it is followed. Every name of
    ``parts`` must be a single path segment. The caller closes the result (it is a context manager).

    Raises:
        UnsafeDirectoryError: a name of ``parts`` is a link.
        NotADirectoryError: a name of ``parts`` is a file.
        FileNotFoundError: a directory is missing and ``create`` is false.
        ValueError: ``root`` is not absolute, or a name of ``parts`` is not a single path segment.
        OSError: any other failure of the file system (permissions, a full disk).
    """
    if not root.is_absolute():
        raise ValueError(f"the trusted root must be an absolute path: {root}")
    if _anchors_on_descriptors():
        fd = _descend(root, parts, create)
        return ConfinedDirectory(root.joinpath(*parts), fd)
    return ConfinedDirectory(_walk(root, parts, create), None)
