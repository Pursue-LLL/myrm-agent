"""Tests for scripts/md_ref_validator.py: ref extraction, resolution, package roots and the tree scan."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_repo_root))

from scripts.md_ref_validator import (
    _discover_pkg_root,
    _extract_md_refs,
    _is_verifiable_ref,
    _path_exists,
    _progressive_paths,
    _resolve_md_ref,
    _resolve_pkg_root,
    _top_level_module_dirs,
    scan_md_refs,
)

_TOP_DIRS = frozenset(
    {
        "agent",
        "api",
        "backends",
        "core",
        "eval",
        "infra",
        "observability",
        "runtime",
        "toolkits",
        "utils",
    }
)


@pytest.mark.architecture
def test_extract_md_refs_keeps_explicit_paths_and_module_shortcuts(tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    md.write_text(
        """# Doc

See `./toolkits/errors/classifier.py` and `myrm-agent-server/app/api/curator.py`.
Module shortcut `toolkits/errors/classifier.py` is resolved via top-level dirs.
URL `https://example.com/x.py`, bare `runner.py`, and `/etc/hosts` are skipped.
""",
        encoding="utf-8",
    )
    refs = _extract_md_refs(md, _TOP_DIRS)
    assert [(ref, line) for ref, line, _ in refs] == [
        ("./toolkits/errors/classifier.py", 3),
        ("myrm-agent-server/app/api/curator.py", 3),
        ("toolkits/errors/classifier.py", 4),
    ]


@pytest.mark.architecture
def test_extract_md_refs_drops_noise_without_top_dirs(tmp_path: Path) -> None:
    """Without harness top-level dirs (cross-repo scan), module shortcuts are
    not verifiable and are dropped; only explicit refs survive."""
    md = tmp_path / "doc.md"
    md.write_text(
        """# Doc

Module shortcut `toolkits/errors/classifier.py` is not verifiable here.
Explicit `./local.py` and alias `myrm-agent-server/app/api/curator.py` survive.
""",
        encoding="utf-8",
    )
    refs = _extract_md_refs(md, frozenset())
    assert [(ref, line) for ref, line, _ in refs] == [
        ("./local.py", 4),
        ("myrm-agent-server/app/api/curator.py", 4),
    ]


@pytest.mark.architecture
def test_extract_md_refs_captures_table_row_dir(tmp_path: Path) -> None:
    md = tmp_path / "doc.md"
    md.write_text(
        """| `docker/`            | 容器构建     | `../Dockerfile`（PyPI / 预构建 wheel）；`sandbox/` 技能沙箱镜像 |
| `app/tasks/`          | 后台任务层   | 消费 harness `toolkits/tasks/` 队列 |
""",
        encoding="utf-8",
    )
    refs = _extract_md_refs(md, _TOP_DIRS)
    # The first-cell `docker/` and bare `sandbox/` are not verifiable; the
    # `../Dockerfile` cell captures the row's first-cell dir as its base, and
    # `toolkits/tasks/` is a harness module shortcut.
    assert refs == [
        ("../Dockerfile", 1, "docker"),
        ("toolkits/tasks/", 2, "app/tasks"),
    ]


@pytest.mark.architecture
def test_extract_md_refs_row_dir_uses_first_cell_only(tmp_path: Path) -> None:
    """A plain-text first cell must not borrow a later cell's backticked dir."""
    md = tmp_path / "doc.md"
    md.write_text(
        """| 容器构建   | `docker/`        | `../Dockerfile` |
| 后台任务层 | `app/tasks/`      | 消费 `toolkits/tasks/` |
""",
        encoding="utf-8",
    )
    refs = _extract_md_refs(md, _TOP_DIRS)
    # First cell is plain text -> no row_dir; explicit relative and module
    # shortcut still verified, but neither borrows a later cell's dir.
    assert refs == [
        ("../Dockerfile", 1, None),
        ("toolkits/tasks/", 2, None),
    ]


@pytest.mark.architecture
def test_progressive_paths_strips_symbol_suffixes() -> None:
    assert _progressive_paths("toolkits/mcp/schema.normalize.canonicalize_schema_for_cache") == [
        "toolkits/mcp/schema.normalize.canonicalize_schema_for_cache",
        "toolkits/mcp/schema.normalize",
        "toolkits/mcp/schema",
    ]
    # Real files with dotted names resolve unchanged (first candidate).
    assert _progressive_paths("toolkits/browser/assets/ad_domains.txt") == ["toolkits/browser/assets/ad_domains.txt"]
    assert _progressive_paths("docker/Dockerfile.official") == [
        "docker/Dockerfile.official",
        "docker/Dockerfile",
    ]
    assert _progressive_paths("agent/streaming/broadcast/ToolBroadcastBus") == [
        "agent/streaming/broadcast/ToolBroadcastBus",
        "agent/streaming/broadcast",
    ]
    assert _progressive_paths("path/utils::is_timeout_error") == [
        "path/utils::is_timeout_error",
        "path/utils",
    ]


@pytest.mark.architecture
def test_resolve_md_ref_local_relative_and_cross_repo(tmp_path: Path) -> None:
    harness_root = tmp_path / "myrm-agent-harness"
    harness_pkg = harness_root / "src" / "myrm_agent_harness"
    (harness_root / "docs").mkdir(parents=True)
    (harness_root / "pkg").mkdir()
    (harness_pkg / "agent" / "errors").mkdir(parents=True)
    (harness_pkg / "agent" / "errors" / "classifier.py").write_text("x = 1\n", encoding="utf-8")
    (harness_pkg / "agent" / "streaming" / "broadcast").mkdir(parents=True)
    (harness_pkg / "toolkits" / "mcp" / "schema").mkdir(parents=True)
    (harness_pkg / "toolkits" / "mcp" / "schema" / "__init__.py").write_text("", encoding="utf-8")
    (harness_root / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
    (harness_root / "docs" / "docker").mkdir()
    (harness_root / "docs" / "Dockerfile").write_text("FROM scratch\n", encoding="utf-8")
    (harness_root / "docs" / "guide.md").write_text("", encoding="utf-8")

    md = harness_root / "docs" / "guide.md"
    pkg = harness_root / "src" / "myrm_agent_harness"
    assert _path_exists(harness_root / "docs", "./guide.md")
    assert _resolve_md_ref(md, "../pkg/mod.py", None, tmp_path, harness_root, pkg)
    # Module shortcut resolution order: md dir -> package root -> tests mirror.
    assert _resolve_md_ref(md, "agent/errors/classifier.py", None, tmp_path, harness_root, pkg)
    assert not _resolve_md_ref(md, "agent/errors/ghost.py", None, tmp_path, harness_root, pkg)
    # Table row dir acts as a secondary base: `../Dockerfile` under `docs/docker/`.
    assert _resolve_md_ref(md, "../Dockerfile", "docker", tmp_path, harness_root, pkg)
    # Harness shorthand drops the src/myrm_agent_harness package prefix.
    assert _resolve_md_ref(md, "myrm-agent-harness/agent/errors/classifier.py", None, tmp_path, harness_root, pkg)
    assert not _resolve_md_ref(md, "myrm-agent-harness/agent/errors/ghost.py", None, tmp_path, harness_root, pkg)
    # Cross-repo shortcut with a symbol suffix must fall through to the
    # progressive candidate (regression: early return skipped it).
    assert _resolve_md_ref(
        md,
        "myrm-agent-harness/agent/errors/classifier.py.attr",
        None,
        tmp_path,
        harness_root,
        pkg,
    )
    # Progressive resolution: dotted chain and CamelCase class suffix.
    assert _resolve_md_ref(
        md,
        "toolkits/mcp/schema.normalize.canonicalize_schema_for_cache",
        None,
        tmp_path,
        harness_root,
        pkg,
    )
    assert _resolve_md_ref(
        md,
        "agent/streaming/broadcast/ToolBroadcastBus",
        None,
        tmp_path,
        harness_root,
        pkg,
    )


@pytest.mark.architecture
def test_is_verifiable_ref_scopes_top_dirs() -> None:
    assert _is_verifiable_ref("./x.py", frozenset())
    assert _is_verifiable_ref("../x/y.py", frozenset())
    assert _is_verifiable_ref("myrm-agent-server/app/x.py", frozenset())
    assert not _is_verifiable_ref("app/services/features/x.py", frozenset())
    assert _is_verifiable_ref("toolkits/errors/classifier.py", _TOP_DIRS)
    assert not _is_verifiable_ref("toolkits/errors/classifier.py", frozenset())


@pytest.mark.architecture
def test_scan_md_refs_reports_broken_and_skips_standalone_aliases(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "real.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "sub" / "doc.md").write_text(
        "Refs: `./real.py` works, `./gone/ghost.py` broken, "
        "`myrm-agent/any/where.py` unverifiable when monorepo absent.\n",
        encoding="utf-8",
    )

    reports = scan_md_refs(tmp_path, monorepo_root=tmp_path, repo_root=tmp_path)
    assert len(reports) == 1
    broken = set(reports[0].broken_refs)
    assert ("./gone/ghost.py", 1) in broken
    # Repo alias whose first segment is missing (standalone harness) is skipped.
    assert not any(ref.startswith("myrm-agent/") for ref, _ in broken)


@pytest.mark.architecture
def test_scan_md_refs_skips_prebuilt_skills(tmp_path: Path) -> None:
    prebuilt = tmp_path / "assets" / "prebuilt_skills" / "frontend-development"
    prebuilt.mkdir(parents=True)
    (prebuilt / "SKILL.md").write_text(
        "Prebuilt utility: `cn()` function at `./lib/utils`\n",
        encoding="utf-8",
    )
    assert scan_md_refs(tmp_path, monorepo_root=tmp_path, repo_root=tmp_path) == []


@pytest.mark.architecture
def test_scan_md_refs_prunes_hidden_dirs(tmp_path: Path) -> None:
    """md refs under pruned dirs (.venv/.git/...) are not scanned."""
    venv_md = tmp_path / ".venv" / "doc.md"
    venv_md.parent.mkdir(parents=True)
    venv_md.write_text("Broken: `./ghost.py`\n", encoding="utf-8")
    assert scan_md_refs(tmp_path, monorepo_root=tmp_path, repo_root=tmp_path) == []


@pytest.mark.architecture
def test_scan_md_refs_skips_whitelisted_docs(tmp_path: Path) -> None:
    """Docs in _MD_REF_SKIP_FILES carry planning semantics (e.g. candidate
    verdict tables); their broken-looking refs must not be reported."""
    pkg = tmp_path / "src" / "myrm_agent_harness" / "eval"
    pkg.mkdir(parents=True)
    (pkg / "_ARCH.md").write_text(
        "| `toolkits/eval/` | Not an agent-callable domain capability |\n",
        encoding="utf-8",
    )
    assert scan_md_refs(tmp_path, monorepo_root=tmp_path, repo_root=tmp_path) == []


@pytest.mark.architecture
def test_scan_md_refs_skips_local_bugfix_ledgers(tmp_path: Path) -> None:
    """Bug ledgers are local-only records of code as it was when each entry was
    written; their path refs are not assertions about the current tree."""
    ledger = tmp_path / "browser" / "browser_20261107_20261113_BUGFIX_LOG.md"
    ledger.parent.mkdir(parents=True)
    ledger.write_text("Fixed in `./removed/ghost.py`\n", encoding="utf-8")
    assert scan_md_refs(tmp_path, monorepo_root=tmp_path, repo_root=tmp_path) == []


@pytest.mark.architecture
def test_discover_pkg_root_detects_repo_layouts(tmp_path: Path) -> None:
    harness = tmp_path / "harness"
    (harness / "src" / "myrm_agent_harness").mkdir(parents=True)
    assert _discover_pkg_root(harness) == harness / "src" / "myrm_agent_harness"
    server = tmp_path / "server"
    (server / "app").mkdir(parents=True)
    assert _discover_pkg_root(server) == server / "app"
    # Frontend src/ is not shortcut-scanned (TS refs carry no extension).
    frontend = tmp_path / "frontend"
    (frontend / "src").mkdir(parents=True)
    assert _discover_pkg_root(frontend) is None
    assert _discover_pkg_root(tmp_path) is None
    # When the scanned root is itself a package root, it is returned as-is.
    app_root = tmp_path / "app"
    app_root.mkdir()
    assert _discover_pkg_root(app_root) == app_root
    harness_pkg = tmp_path / "myrm_agent_harness"
    harness_pkg.mkdir()
    assert _discover_pkg_root(harness_pkg) == harness_pkg


@pytest.mark.architecture
def test_resolve_pkg_root_prefers_harness_pkg(tmp_path: Path) -> None:
    harness = tmp_path / "myrm-agent-harness"
    pkg = harness / "src" / "myrm_agent_harness"
    pkg.mkdir(parents=True)
    # Any subtree of the harness repo resolves to the harness package.
    assert _resolve_pkg_root(pkg / "agent", harness) == pkg
    assert _resolve_pkg_root(harness, harness) == pkg
    # A non-harness repo is auto-detected from its own layout.
    server = tmp_path / "myrm-agent-server"
    (server / "app").mkdir(parents=True)
    assert _resolve_pkg_root(server, harness) == server / "app"


@pytest.mark.architecture
def test_scan_md_refs_resolves_server_shortcuts(tmp_path: Path) -> None:
    """Cross-repo scan: server module shortcuts resolve against app/, comma
    enumerations are dropped, and genuinely missing paths are reported."""
    server = tmp_path / "server"
    (server / "app" / "channels" / "protocols").mkdir(parents=True)
    (server / "app" / "channels" / "protocols" / "inbound_profile.py").write_text("x = 1\n", encoding="utf-8")
    (server / "app" / "services" / "config").mkdir(parents=True)
    (server / "app" / "services" / "config" / "health_monitor.py").write_text("x = 1\n", encoding="utf-8")
    (server / "docs").mkdir()
    (server / "docs" / "guide.md").write_text(
        "`channels/protocols/inbound_profile.py` and `services/config/health_monitor` exist; "
        "`channels/ghost.py` broken; `api/voice,stt,tts` is a comma enum.\n",
        encoding="utf-8",
    )
    reports = scan_md_refs(server, monorepo_root=tmp_path, repo_root=tmp_path)
    assert len(reports) == 1
    assert reports[0].broken_refs == (("channels/ghost.py", 1),)


def test_top_level_module_dirs_excludes_cache_dirs(tmp_path: Path) -> None:
    """Module-shortcut prefixes never include cache/artifact directories."""
    (tmp_path / "agent").mkdir()
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "plain.py").write_text("x = 1\n", encoding="utf-8")
    dirs = _top_level_module_dirs(tmp_path)
    assert "agent" in dirs
    assert "__pycache__" not in dirs
