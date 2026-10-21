"""Tests for workspace organize service."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.files.organize.apply import apply_organize_plan, rollback_organize_job
from app.services.files.organize.types import OrganizeJobStatus, OrganizePlan, OrganizePlanItem, OrganizePreset
from app.services.files.organize.validation import validate_organize_plan
from app.services.files.organize.wikilink import rewrite_wikilinks_in_tree


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    scope = root / "inbox"
    scope.mkdir(parents=True)
    (scope / "a.md").write_text("# A\n\n[[b]]", encoding="utf-8")
    (scope / "b.md").write_text("# B", encoding="utf-8")
    (scope / "shot.png").write_bytes(b"\x89PNG")
    return root


def test_validate_accepts_clean_plan(workspace: Path) -> None:
    plan = OrganizePlan(
        scope_root="inbox",
        preset=OrganizePreset.PROJECT,
        items=[
            OrganizePlanItem(src="inbox/a.md", dst="inbox/docs/a.md", reason="md to docs"),
            OrganizePlanItem(src="inbox/b.md", dst="inbox/docs/b.md", reason="md to docs"),
        ],
    )
    issues = validate_organize_plan(str(workspace), plan)
    assert issues == []


def test_validate_rejects_dst_exists(workspace: Path) -> None:
    plan = OrganizePlan(
        scope_root="inbox",
        items=[
            OrganizePlanItem(
                src="inbox/a.md",
                dst="inbox/b.md",
                reason="collision with existing",
            ),
        ],
    )
    issues = validate_organize_plan(str(workspace), plan)
    assert any(issue.code == "dst_exists" for issue in issues)


def test_validate_rejects_duplicate_src(workspace: Path) -> None:
    plan = OrganizePlan(
        scope_root="inbox",
        items=[
            OrganizePlanItem(src="inbox/a.md", dst="inbox/docs/a.md", reason="first"),
            OrganizePlanItem(src="inbox/a.md", dst="inbox/archive/a.md", reason="duplicate src"),
        ],
    )
    issues = validate_organize_plan(str(workspace), plan)
    assert any(issue.code == "duplicate_src" for issue in issues)


def test_apply_dry_run(workspace: Path) -> None:
    plan = OrganizePlan(
        scope_root="inbox",
        items=[
            OrganizePlanItem(
                src="inbox/shot.png",
                dst="inbox/images/shot.png",
                reason="images together",
            ),
        ],
    )
    result = apply_organize_plan(str(workspace), plan, dry_run=True)
    assert result.issues == []
    assert result.applied_count == 1
    assert not (workspace / "inbox" / "images" / "shot.png").exists()


def test_apply_and_rollback(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_DATA_DIR", str(workspace / "data"))
    plan = OrganizePlan(
        scope_root="inbox",
        items=[
            OrganizePlanItem(
                src="inbox/shot.png",
                dst="inbox/images/shot.png",
                reason="images together",
            ),
        ],
    )
    applied = apply_organize_plan(str(workspace), plan, dry_run=False)
    assert applied.job_id is not None
    assert (workspace / "inbox" / "images" / "shot.png").is_file()
    assert not (workspace / "inbox" / "shot.png").exists()

    rollback = rollback_organize_job(applied.job_id or "")
    assert rollback.applied_count == 1
    assert (workspace / "inbox" / "shot.png").is_file()


def test_mtime_mismatch_blocks_apply(workspace: Path) -> None:
    plan = OrganizePlan(
        scope_root="inbox",
        items=[
            OrganizePlanItem(
                src="inbox/a.md",
                dst="inbox/docs/a.md",
                reason="move md",
                src_mtime_ns=1,
            ),
        ],
    )
    result = apply_organize_plan(str(workspace), plan, dry_run=True)
    assert any(issue.code == "mtime_mismatch" for issue in result.issues)


def test_wikilink_rewrite_when_stem_changes(workspace: Path) -> None:
    (workspace / "inbox" / "foo.md").write_text("# Foo", encoding="utf-8")
    (workspace / "inbox" / "index.md").write_text("See [[foo]]", encoding="utf-8")
    moved = [
        (
            str(workspace / "inbox" / "foo.md"),
            str(workspace / "inbox" / "docs" / "bar.md"),
        ),
    ]
    (workspace / "inbox" / "docs").mkdir(parents=True)
    (workspace / "inbox" / "docs" / "bar.md").write_text("# Bar", encoding="utf-8")
    (workspace / "inbox" / "foo.md").unlink()

    updated = rewrite_wikilinks_in_tree(str(workspace), moved)
    assert updated == 1
    assert "[[bar]]" in (workspace / "inbox" / "index.md").read_text(encoding="utf-8")


def test_rollback_restores_files_and_wikilinks(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_DATA_DIR", str(workspace / "data"))
    (workspace / "inbox" / "foo.md").write_text("# Foo", encoding="utf-8")
    (workspace / "inbox" / "index.md").write_text("See [[foo]]", encoding="utf-8")
    plan = OrganizePlan(
        scope_root="inbox",
        items=[
            OrganizePlanItem(
                src="inbox/foo.md",
                dst="inbox/docs/bar.md",
                reason="group docs",
            ),
        ],
    )
    applied = apply_organize_plan(str(workspace), plan, dry_run=False)
    assert "[[bar]]" in (workspace / "inbox" / "index.md").read_text(encoding="utf-8")

    rollback_organize_job(applied.job_id or "")
    assert (workspace / "inbox" / "foo.md").is_file()
    assert "[[foo]]" in (workspace / "inbox" / "index.md").read_text(encoding="utf-8")


def test_partial_rollback_status(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MYRM_DATA_DIR", str(workspace / "data"))
    plan = OrganizePlan(
        scope_root="inbox",
        items=[
            OrganizePlanItem(
                src="inbox/shot.png",
                dst="inbox/images/shot.png",
                reason="images together",
            ),
        ],
    )
    applied = apply_organize_plan(str(workspace), plan, dry_run=False)
    (workspace / "inbox" / "images" / "shot.png").unlink()
    result = rollback_organize_job(applied.job_id or "")
    assert result.job_status == OrganizeJobStatus.PARTIAL_ROLLBACK
    assert result.applied_count == 0
