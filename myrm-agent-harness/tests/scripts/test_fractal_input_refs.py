"""Unit tests for scripts.fractal_input_refs and its wiring into scripts.check_fractal_docs.

Every case builds a synthetic package ``pkg`` under ``tmp_path``, so the tests are hermetic and
neither import nor read the harness tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts import check_fractal_docs
from scripts.fractal_input_refs import dangling_input_references

_PRUNED = frozenset({"__pycache__"})
_HEADER_LINES = 120
_BASE = {
    "__init__.py": "",
    "util/__init__.py": "",
    "util/helper.py": "VALUE = 1\n",
    "core/__init__.py": "",
    "core/deep/leaf.py": "VALUE = 1\n",
}


def _module(*input_lines: str) -> str:
    """A module whose header lists ``input_lines`` under ``[INPUT]``; the first one is on line 4."""
    body = "\n".join(input_lines)
    return f'"""Module.\n\n[INPUT]\n{body}\n\n[OUTPUT]\n- X: y\n\n[POS]\nz\n"""\n'


def _package(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "pkg"
    for rel, text in {**_BASE, **files}.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


def _scan(root: Path) -> list[tuple[str, int, str]]:
    found = dangling_input_references(root, pruned_dirs=_PRUNED, header_lines=_HEADER_LINES)
    return [(ref.path.name, ref.line, ref.target) for ref in found]


def _dangling(tmp_path: Path, *input_lines: str, extra: dict[str, str] | None = None) -> list[tuple[int, str]]:
    """``(line, target)`` of every dangling reference in a module that lists ``input_lines``."""
    root = _package(tmp_path, {"core/user.py": _module(*input_lines), **(extra or {})})
    return [(line, target) for name, line, target in _scan(root) if name == "user.py"]


def test_reference_to_an_existing_module_resolves(tmp_path: Path) -> None:
    assert _dangling(tmp_path, "- util.helper::VALUE (POS: x)") == []


def test_abbreviated_reference_resolves_when_it_is_a_path_suffix(tmp_path: Path) -> None:
    lines = ("- helper::VALUE", "- deep.leaf::VALUE", "- core.deep.leaf::VALUE")

    assert _dangling(tmp_path, *lines) == []


def test_reference_to_a_package_directory_resolves(tmp_path: Path) -> None:
    assert _dangling(tmp_path, "- util::helper", "- core.deep::leaf") == []


def test_leading_package_name_is_optional(tmp_path: Path) -> None:
    assert _dangling(tmp_path, "- pkg.util.helper::VALUE", "- pkg.util.gone::X") == [(5, "pkg.util.gone")]


def test_dangling_reference_is_reported_with_its_line(tmp_path: Path) -> None:
    found = _dangling(tmp_path, "- util.gone::X", "- util.helper::VALUE", "- core.moved.leaf::X")

    assert found == [(4, "util.gone"), (6, "core.moved.leaf")]


def test_a_path_that_is_not_a_suffix_does_not_resolve(tmp_path: Path) -> None:
    # ``helper`` exists, but under ``util``: it is never ``core.helper``.
    assert _dangling(tmp_path, "- core.helper::VALUE") == [(4, "core.helper")]


def test_leading_dots_do_not_change_what_a_reference_names(tmp_path: Path) -> None:
    lines = ("- .helper::VALUE", "- ..util.helper::VALUE", "- .util.gone::X", "- ...core.deep.nope::X")

    assert _dangling(tmp_path, *lines) == [(6, ".util.gone"), (7, "...core.deep.nope")]


def test_a_reference_whose_first_segment_is_not_in_the_package_is_not_checked(tmp_path: Path) -> None:
    lines = ("- pydantic::BaseModel", "- langchain_core.messages::HumanMessage", "- asyncio.tasks::Task", "- gone::X")

    assert _dangling(tmp_path, *lines) == []


def test_stdlib_modules_that_share_a_first_party_name_are_not_checked(tmp_path: Path) -> None:
    found = _dangling(tmp_path, "- logging.handlers::RotatingFileHandler", extra={"logging/__init__.py": ""})

    assert found == []


def test_third_party_packages_that_share_a_first_party_name_are_not_checked(tmp_path: Path) -> None:
    extra = {"mcp/__init__.py": "", "acp/__init__.py": "", "other/__init__.py": ""}

    found = _dangling(tmp_path, "- mcp.types::Tool", "- acp.schema::HttpMcpServer", "- other.types::Tool", extra=extra)

    assert found == [(6, "other.types")]


@pytest.mark.parametrize(
    "block_end",
    ["[OUTPUT]\n- util.gone::X\n", "[POS]\nutil.gone::X\n", '"""\nVALUE = """\n- util.gone::X\n"""\n'],
    ids=["output", "pos", "closing-quotes"],
)
def test_the_input_block_ends_at_the_next_section_or_the_closing_quotes(tmp_path: Path, block_end: str) -> None:
    root = _package(tmp_path, {"core/user.py": f'"""Module.\n\n[INPUT]\n- util.helper::VALUE\n{block_end}'})

    assert _scan(root) == []


@pytest.mark.parametrize(
    ("filler_lines", "expected"),
    [(_HEADER_LINES - 1, [("user.py", _HEADER_LINES + 1, "util.gone")]), (_HEADER_LINES, [])],
    ids=["opens-on-the-last-header-line", "opens-one-line-too-late"],
)
def test_the_input_block_must_open_within_the_header_lines(
    tmp_path: Path, filler_lines: int, expected: list[tuple[str, int, str]]
) -> None:
    text = "VALUE = 1\n" * filler_lines + "[INPUT]\n- util.gone::X\n[OUTPUT]\n"
    root = _package(tmp_path, {"core/user.py": text})

    assert _scan(root) == expected


def test_only_lines_shaped_like_a_reference_are_read(tmp_path: Path) -> None:
    lines = (
        "* util.gone::X",
        "util.gone2::Y",
        "- (none)",
        "- os",
        "- Some prose that mentions util.gone3::Z",
        "- infra/gone.py::W",
    )

    assert _dangling(tmp_path, *lines) == [(4, "util.gone"), (5, "util.gone2")]


def test_pruned_directories_are_not_scanned(tmp_path: Path) -> None:
    root = _package(tmp_path, {"__pycache__/stale.py": _module("- util.gone::X")})

    assert _scan(root) == []


def test_findings_come_in_path_then_line_order(tmp_path: Path) -> None:
    root = _package(
        tmp_path,
        {
            "util/b.py": _module("- util.gone_b::X"),
            "util/a.py": _module("- util.gone_a::X", "- util.gone_a2::Y"),
        },
    )

    assert _scan(root) == [("a.py", 4, "util.gone_a"), ("a.py", 5, "util.gone_a2"), ("b.py", 4, "util.gone_b")]


def _with_arch_docs(root: Path) -> Path:
    for directory in (root, *(path for path in root.rglob("*") if path.is_dir())):
        if any(directory.glob("*.py")):
            (directory / "_ARCH.md").write_text("# arch\n", encoding="utf-8")
    return root


def test_cli_exits_with_the_reference_bit_and_names_each_reference(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _with_arch_docs(_package(tmp_path, {"core/user.py": _module("- util.gone::X")}))

    code = check_fractal_docs.main(["--package-root", str(root)])

    assert code == 8
    err = capsys.readouterr().err
    assert "pkg/core/user.py:4: util.gone" in err
    assert "naming a module that does not exist" in err


def test_cli_exit_code_is_the_sum_of_every_kind_of_violation(tmp_path: Path) -> None:
    root = _with_arch_docs(_package(tmp_path, {"core/user.py": _module("- util.gone::X")}))
    (root / "util" / "_ARCH.md").unlink()

    assert check_fractal_docs.main(["--package-root", str(root)]) == 2 + 8


def test_cli_on_a_clean_tree_exits_zero(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _with_arch_docs(_package(tmp_path, {"core/user.py": _module("- util.helper::VALUE")}))

    assert check_fractal_docs.main(["--package-root", str(root)]) == 0
    assert "OK (directory _ARCH.md + resolvable [INPUT] references)." in capsys.readouterr().out
