"""Architecture test: every ``ArtifactVault`` the server opens has a chat-scoped or caller-supplied root.

A vault object is written under the chat's workspace (project bind, then the chat's own
folder, then its JIT folder), so a reader that builds ``ArtifactVault(<process root>)`` looks
in the wrong directory: the API serves 404 for files the agent just produced, and the same
mistake silently writes into the server's working directory. Which root a call site uses is
invisible to type checks and to tests that happen to run with one directory, so the choice is
pinned here.

A construction site passes when its enclosing function resolves the chat's root with
``resolve_chat_workspace_root`` / ``find_chat_workspace_root``. Anything else must be listed
in ``_ROOT_FROM_CALLER`` with the reason its root is already correct; a stale entry fails.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_APP_ROOT = Path(__file__).resolve().parent.parent.parent / "app"
_CHAT_ROOT_RESOLVERS = ("resolve_chat_workspace_root", "find_chat_workspace_root")

# (path under app/, enclosing function) -> why the root handed to ``ArtifactVault`` is right.
_ROOT_FROM_CALLER: dict[tuple[str, str], str] = {
    ("ai_agents/general_agent/mcp_vault_handler.py", "_handler"): (
        "writer inside an agent run; the run's workspace root is bound by the caller (tool_setup)"
    ),
    ("ai_agents/general_agent/tool_setup.py", "_setup_browser_tools"): (
        "writer inside an agent run; uses the run's declared workspace root, the same one the harness resolver reads"
    ),
    ("core/artifacts/listener.py", "upsert_processor_artifact"): (
        "takes workspace_root from its caller: the artifact processor passes the run's root, "
        "ensure_artifact_for_deploy passes the chat's root"
    ),
    ("core/artifacts/listener.py", "persist_artifact_event"): (
        "takes workspace_root from its caller: the artifact processor passes the run's root"
    ),
    ("services/infra/sandbox_cleanup.py", "_purge_vault_objects"): (
        "purges the exact directories being cleaned up (a session workspace, the harness directory)"
    ),
}


def _construction_sites(source: str) -> list[tuple[str, int, bool]]:
    """Return ``(function, line, resolves_chat_root)`` for each ``ArtifactVault(...)`` call."""
    tree = ast.parse(source)
    sites: list[tuple[str, int, bool]] = []

    def walk(node: ast.AST, enclosing: ast.FunctionDef | ast.AsyncFunctionDef | None) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            enclosing = node
        if isinstance(node, ast.Call):
            callee = node.func
            name = callee.id if isinstance(callee, ast.Name) else getattr(callee, "attr", None)
            if name == "ArtifactVault":
                body = ast.get_source_segment(source, enclosing) if enclosing is not None else ""
                resolves = any(resolver in (body or "") for resolver in _CHAT_ROOT_RESOLVERS)
                sites.append((enclosing.name if enclosing is not None else "<module>", node.lineno, resolves))
        for child in ast.iter_child_nodes(node):
            walk(child, enclosing)

    walk(tree, None)
    return sites


def _scan_app() -> dict[tuple[str, str], list[tuple[int, bool]]]:
    found: dict[tuple[str, str], list[tuple[int, bool]]] = {}
    for path in sorted(_APP_ROOT.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "ArtifactVault(" not in source:
            continue
        rel = path.relative_to(_APP_ROOT).as_posix()
        for function, line, resolves in _construction_sites(source):
            found.setdefault((rel, function), []).append((line, resolves))
    return found


@pytest.mark.architecture
def test_every_vault_open_resolves_the_chat_root_or_is_justified() -> None:
    unresolved = sorted(
        f"{rel}:{line} in {function}"
        for (rel, function), sites in _scan_app().items()
        if (rel, function) not in _ROOT_FROM_CALLER
        for line, resolves in sites
        if not resolves
    )
    assert not unresolved, (
        "ArtifactVault opened without a chat-scoped root. Resolve it with "
        "app.services.chat.effective_workspace.resolve_chat_workspace_root(chat_id), or list the site in "
        f"_ROOT_FROM_CALLER with the reason its root is already correct: {unresolved}"
    )


@pytest.mark.architecture
def test_justified_vault_opens_are_still_present_and_still_needed() -> None:
    found = _scan_app()
    stale = sorted(
        f"{rel}::{function}"
        for rel, function in _ROOT_FROM_CALLER
        if (rel, function) not in found or all(resolves for _, resolves in found[(rel, function)])
    )
    assert not stale, f"_ROOT_FROM_CALLER entries that no longer apply (delete them): {stale}"


@pytest.mark.architecture
def test_detector_tells_resolved_roots_from_process_roots() -> None:
    resolved = (
        "async def read(chat_id):\n    root = await resolve_chat_workspace_root(chat_id)\n    return ArtifactVault(str(root))\n"
    )
    process_rooted = "def read():\n    return ArtifactVault(os.getcwd())\n"
    qualified = "def read(root):\n    return vault_module.ArtifactVault(root)\n"

    assert _construction_sites(resolved) == [("read", 3, True)]
    assert _construction_sites(process_rooted) == [("read", 2, False)]
    assert _construction_sites(qualified) == [("read", 2, False)]
    assert _construction_sites("x = 1\n") == []
