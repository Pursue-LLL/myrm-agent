"""Unit test for WorkspaceBoundaryService.

[INPUT]
- ResolvePathRequest, EvaluateAccessRequest, ParseMarkdownLinksRequest, DesktopRevealVerifyRequest.

[OUTPUT]
- Verified behavior of workspace boundary service.

[POS]
- Server unit test layer.
"""

from __future__ import annotations

from pathlib import Path

from app.schemas.workspace_boundary import (
    DesktopRevealVerifyRequest,
    EvaluateAccessRequest,
    ParseMarkdownLinksRequest,
    ResolvePathRequest,
)
from app.services.security.workspace_boundary_service import (
    WorkspaceBoundaryService,
)


def test_service_resolve_and_evaluate_file(tmp_path: Path) -> None:
    ws_dir = tmp_path / "my_workspace"
    ws_dir.mkdir()
    target_file = ws_dir / "app.py"
    target_file.write_text("print('hello')", encoding="utf-8")

    service = WorkspaceBoundaryService(default_roots=(str(ws_dir),))

    # Resolve legitimate file
    res = service.resolve_path(
        ResolvePathRequest(target="app.py", custom_root=str(ws_dir))
    )
    assert res.verdict == "ALLOWED"
    assert res.is_inside_workspace is True
    assert res.can_launch is True
    assert res.can_read is True

    # Evaluate LAUNCH action
    eval_res = service.evaluate_access(
        EvaluateAccessRequest(
            target="app.py",
            action="LAUNCH_DEFAULT_APP",
            custom_root=str(ws_dir),
        )
    )
    assert eval_res.verdict == "ALLOWED"
    assert eval_res.can_launch is True


def test_service_markdown_parsing_and_desktop_reveal(tmp_path: Path) -> None:
    ws_dir = tmp_path / "my_workspace"
    ws_dir.mkdir()
    doc_file = ws_dir / "spec.md"
    doc_file.write_text("# Spec", encoding="utf-8")

    service = WorkspaceBoundaryService(default_roots=(str(ws_dir),))

    # Markdown parsing
    md_content = f"Here is the [spec]({doc_file.resolve()}) and [web](https://myrm.dev)"
    parse_resp = service.parse_markdown_links(
        ParseMarkdownLinksRequest(markdown_text=md_content, custom_root=str(ws_dir))
    )
    assert parse_resp.total_links == 1
    assert parse_resp.links[0].verdict == "ALLOWED"

    # Desktop reveal verify
    reveal_resp = service.verify_desktop_reveal(
        DesktopRevealVerifyRequest(target="spec.md", custom_root=str(ws_dir))
    )
    assert reveal_resp.allowed is True
    assert str(doc_file.resolve()) in reveal_resp.sanitized_path

    # Missing file desktop reveal rejection
    reveal_fail = service.verify_desktop_reveal(
        DesktopRevealVerifyRequest(target="nonexistent.md", custom_root=str(ws_dir))
    )
    assert reveal_fail.allowed is False
    assert len(reveal_fail.error_message) > 0
