"""The seed fingerprint changes with everything a sync reads from the seeds, and with nothing it ignores.

[INPUT]
- app.core.skills.prebuilt_sync_state (POS: seed layout rules, fingerprint, record of the last complete sync)

[OUTPUT]
- Coverage that the fingerprint is stable, that any seed, SKILL.md or bundle file change moves it, that files and
  directories the sync skips do not, and that the stream is framed so a different split of the same bytes differs

[POS]
Server tests. A fingerprint that missed an input would let a start reuse a sync that is out of date for the seeds it
ships; one that moved on an ignored file would only cost a full reconciliation.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from app.core.skills.prebuilt_sync_state import iter_bundle_files, iter_seed_dirs, seeds_fingerprint


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def seeds(tmp_path: Path) -> Path:
    root = tmp_path / "seeds"
    for name in ("alpha", "beta"):
        _write(root / name / "SKILL.md", f"---\nname: {name}\n---\n# {name}\n")
        _write(root / name / "scripts" / "run.sh", f"echo {name}\n")
    return root


def test_fingerprint_is_stable_for_the_same_seeds(seeds: Path) -> None:
    assert seeds_fingerprint(seeds) == seeds_fingerprint(seeds)


CHANGES: dict[str, Callable[[Path], None]] = {
    "SKILL.md edited": lambda root: _write(root / "alpha" / "SKILL.md", "---\nname: alpha\n---\n# edited\n"),
    "bundle file edited": lambda root: _write(root / "alpha" / "scripts" / "run.sh", "echo edited\n"),
    "bundle file added": lambda root: _write(root / "alpha" / "scripts" / "more.sh", "echo more\n"),
    "bundle file removed": lambda root: (root / "alpha" / "scripts" / "run.sh").unlink(),
    "bundle file moved": lambda root: (root / "alpha" / "scripts" / "run.sh").rename(root / "alpha" / "run.sh"),
    "seed added": lambda root: _write(root / "gamma" / "SKILL.md", "---\nname: gamma\n---\n"),
    "seed renamed": lambda root: (root / "beta").rename(root / "delta"),
    "seed removed": lambda root: shutil.rmtree(root / "beta"),
}


@pytest.mark.parametrize("change", CHANGES.values(), ids=CHANGES.keys())
def test_fingerprint_moves_with_every_input_the_sync_reads(seeds: Path, change: Callable[[Path], None]) -> None:
    before = seeds_fingerprint(seeds)

    change(seeds)

    assert seeds_fingerprint(seeds) != before


IGNORED: dict[str, Callable[[Path], None]] = {
    "hidden file in a seed": lambda root: _write(root / "alpha" / ".DS_Store", "noise"),
    "private file in a seed": lambda root: _write(root / "alpha" / "_notes.md", "scratch"),
    "file in a private directory of a seed": lambda root: _write(root / "alpha" / "_private" / "x.txt", "scratch"),
    "private seed directory": lambda root: _write(root / "_template" / "SKILL.md", "---\nname: t\n---\n"),
    "hidden seed directory": lambda root: _write(root / ".cache" / "SKILL.md", "---\nname: c\n---\n"),
    "directory without a SKILL.md": lambda root: _write(root / "orphan" / "scripts" / "x.sh", "echo x\n"),
    "loose file next to the seeds": lambda root: _write(root / "README.txt", "not a seed"),
}


@pytest.mark.parametrize("change", IGNORED.values(), ids=IGNORED.keys())
def test_fingerprint_ignores_what_the_sync_skips(seeds: Path, change: Callable[[Path], None]) -> None:
    before = seeds_fingerprint(seeds)

    change(seeds)

    assert seeds_fingerprint(seeds) == before


# Two seed sets whose fields, concatenated without lengths, spell the same bytes: the second set's single SKILL.md
# contains the name and content that the first set keeps in a separate field.
SAME_BYTES_SPLIT_DIFFERENTLY: dict[str, tuple[dict[str, str], dict[str, str]]] = {
    "a bundle file spelled out in the SKILL.md": (
        {"a/SKILL.md": "head", "a/tail.txt": "x"},
        {"a/SKILL.md": "headtail.txtx"},
    ),
    "the next seed spelled out in the SKILL.md": (
        {"a/SKILL.md": "x", "b/SKILL.md": "y"},
        {"a/SKILL.md": "xbSKILL.mdy"},
    ),
}


@pytest.mark.parametrize(("first", "second"), SAME_BYTES_SPLIT_DIFFERENTLY.values(), ids=SAME_BYTES_SPLIT_DIFFERENTLY.keys())
def test_fingerprint_separates_the_same_bytes_split_differently(
    tmp_path: Path, first: dict[str, str], second: dict[str, str]
) -> None:
    for name, files in (("first", first), ("second", second)):
        for relative, text in files.items():
            _write(tmp_path / name / relative, text)

    assert seeds_fingerprint(tmp_path / "first") != seeds_fingerprint(tmp_path / "second")


def test_seed_and_bundle_walks_apply_the_same_rules_the_sync_uses(seeds: Path) -> None:
    _write(seeds / "alpha" / ".hidden", "x")
    _write(seeds / "alpha" / "_private" / "y.txt", "y")
    _write(seeds / "_template" / "SKILL.md", "t")

    assert [d.name for d in iter_seed_dirs(seeds)] == ["alpha", "beta"]
    assert [relative for _, relative in iter_bundle_files(seeds / "alpha")] == ["scripts/run.sh"]
