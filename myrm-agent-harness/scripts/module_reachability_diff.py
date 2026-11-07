"""Diff mode of the module-reachability gate: a change may not leave a unit without a production consumer.

The absolute gate fails while any unit is unwired, which in-flight work keeps true for long stretches.
Diff mode stays enforceable regardless: a unit fails only when it is dead now and was not dead at the
merge-base with a reference revision, so it names exactly the units a change orphans or adds unwired.
"Now" is the working tree as it lies on disk, untracked files included: the verdict covers committed
changes only on a clean checkout, which is what CI runs.

There is no baseline file and no allowlist. The comparison tree is rebuilt from git on every run, from
every input of the analysis (the package, the downstream trees it counts as consumers, its
``pyproject.toml``), so a unit is "already dead" only because it really was dead at the merge-base, and a
consumer the change removes is gone at the head only. Whatever cannot be established (not a git tree,
unknown revision, no common ancestor, an input missing at the base or outside the git tree) raises
``BaseUnavailableError``; callers must fail closed instead of passing silently.
"""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from scripts.module_reachability_engine import Report, Unit

_GIT_TIMEOUT_SECONDS = 120

# Maps a path of the working tree to the same path inside the tree being analysed.
Locate = Callable[[Path], Path]
# Builds the report of one tree; every input is read through ``Locate``.
Analyse = Callable[[Locate], Report]


class BaseUnavailableError(RuntimeError):
    """The comparison revision could not be established; the gate must fail closed."""


@dataclass(frozen=True)
class DiffResult:
    base: str
    introduced: tuple[Unit, ...]
    preexisting: int


def _git(repo: Path, *args: str) -> bytes:
    try:
        done = subprocess.run(["git", *args], cwd=repo, capture_output=True, timeout=_GIT_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BaseUnavailableError(f"git {args[0]} could not run: {exc}") from exc
    if done.returncode != 0:
        raise BaseUnavailableError(f"git {args[0]} failed: {done.stderr.decode(errors='replace').strip()}")
    return done.stdout


def _repository_root(path: Path) -> Path:
    directory = path if path.is_dir() else path.parent
    return Path(_git(directory, "rev-parse", "--show-toplevel").decode().strip())


def _repo_relative(repo: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo).as_posix()
    except ValueError as exc:
        raise BaseUnavailableError(f"{path} is outside the git tree {repo}") from exc


def _merge_base(repo: Path, rev: str) -> str:
    if rev.startswith("-"):
        raise BaseUnavailableError(f"not a revision: {rev!r}")
    return _git(repo, "merge-base", "HEAD", rev).decode().strip()


def _extract(repo: Path, rev: str, paths: Sequence[str], destination: Path) -> None:
    archive = _git(repo, "archive", "--format=tar", rev, "--", *paths)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
        tar.extractall(destination, filter="data")


def introduced_dead(head: Report, base: Report) -> tuple[Unit, ...]:
    """Units dead in ``head`` that were not dead in ``base`` (new, or left without a consumer)."""
    already_dead = {unit.key for unit in base.dead}
    return tuple(unit for unit in head.dead if unit.key not in already_dead)


def diff_against(head: Report, inputs: Sequence[Path], rev: str, analyse: Analyse) -> DiffResult:
    """Compare ``head`` with the analysis of the same ``inputs`` at the merge-base of ``HEAD`` and ``rev``.

    ``inputs`` are every file and directory the analysis reads. They are extracted from the base revision
    into a scratch tree that keeps their repository-relative layout, and ``analyse`` reads them through
    its ``Locate`` argument, so base and head are analysed under the same rules.
    """
    repo = _repository_root(inputs[0].resolve())
    base = _merge_base(repo, rev)
    with tempfile.TemporaryDirectory(prefix="reachability-base-") as scratch:
        scratch_root = Path(scratch)
        _extract(repo, base, [_repo_relative(repo, path) for path in inputs], scratch_root)
        base_report = analyse(lambda path: scratch_root / _repo_relative(repo, path))
    if not base_report.units:
        raise BaseUnavailableError(f"no engine units found at {base[:10]}")
    introduced = introduced_dead(head, base_report)
    return DiffResult(base=base, introduced=introduced, preexisting=len(head.dead) - len(introduced))
