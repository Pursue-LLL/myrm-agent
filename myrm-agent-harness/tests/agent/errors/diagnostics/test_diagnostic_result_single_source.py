"""A diagnosis is assembled from the locale catalogue in exactly one place.

[INPUT]
- src/myrm_agent_harness/**/*.py: every call that constructs ``DiagnosticResult``

[OUTPUT]
- Fails when a ``DiagnosticResult`` is constructed anywhere but ``catalog_result.py``, or when that builder no longer
  constructs one (so the single allowed site cannot rot).

[POS]
Architecture guard for the diagnostics catalogue: a result written by hand carries wording that no locale, placeholder
or wording guard ever scans, so a new error family could ship copy that skips all of them. The scan sees direct
construction, also through an import alias or a module attribute; a copy made with ``dataclasses.replace`` is not
construction and is not caught.
"""

from __future__ import annotations

import ast
from pathlib import Path

import myrm_agent_harness

_PACKAGE = Path(myrm_agent_harness.__file__).parent
_RESULT_TYPE = "DiagnosticResult"
_THE_BUILDER = Path("agent/errors/diagnostics/catalog_result.py")


def _names_the_type_is_called_by(tree: ast.Module) -> set[str]:
    aliases = {
        alias.asname
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
        if alias.name == _RESULT_TYPE and alias.asname
    }
    return {_RESULT_TYPE, *aliases}


def _is_construction(node: ast.AST, names: set[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    callee = node.func
    return (isinstance(callee, ast.Name) and callee.id in names) or (
        isinstance(callee, ast.Attribute) and callee.attr == _RESULT_TYPE
    )


def _construction_sites(root: Path) -> set[Path]:
    """The source files under ``root``, as relative paths, that construct a ``DiagnosticResult``."""
    sites: set[Path] = set()
    for path in root.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if _RESULT_TYPE not in source:  # a call needs the name, directly or in the import it is aliased from
            continue
        tree = ast.parse(source)
        names = _names_the_type_is_called_by(tree)
        if any(_is_construction(node, names) for node in ast.walk(tree)):
            sites.add(path.relative_to(root))
    return sites


def test_the_catalogue_builder_is_the_only_place_that_constructs_a_diagnostic_result() -> None:
    assert _construction_sites(_PACKAGE) == {_THE_BUILDER}


def test_the_scan_finds_direct_aliased_and_qualified_construction_and_ignores_a_mere_mention(tmp_path: Path) -> None:
    call = '(error_type="a", user_message="b", resolution_steps=[], locale="en")\n'
    (tmp_path / "pkg").mkdir()
    (tmp_path / "direct.py").write_text("from x import DiagnosticResult\nDiagnosticResult" + call)
    (tmp_path / "aliased.py").write_text("from x import DiagnosticResult as Result\nResult" + call)
    (tmp_path / "qualified.py").write_text("import x\nx.DiagnosticResult" + call)
    (tmp_path / "pkg" / "nested.py").write_text("from x import DiagnosticResult\nDiagnosticResult" + call)
    (tmp_path / "annotation_only.py").write_text(
        "from x import DiagnosticResult\n\n\ndef f(r: DiagnosticResult) -> DiagnosticResult:\n    return r\n"
    )

    assert _construction_sites(tmp_path) == {
        Path("direct.py"),
        Path("aliased.py"),
        Path("qualified.py"),
        Path("pkg/nested.py"),
    }
