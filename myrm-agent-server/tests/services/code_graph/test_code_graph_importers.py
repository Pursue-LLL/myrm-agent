"""Tests for the ``importers`` action: what the Python extractor records and which imports a query finds.

[INPUT]
- app.services.code_graph.ast_extractor (POS: Python source to symbols, calls and import statements)
- app.services.code_graph.service::CodeGraphService (POS: incremental directory index and graph queries)
- app.services.code_graph.agent_tool (POS: agent-facing code graph tool and its conditional mount)

[OUTPUT]
- pytest suite: relative imports are recorded under the module they name (and skipped when they climb above the
  index root), a query finds the importers of a module in flat and src layouts under either spelling, relative and
  absolute alike, a name inside a module narrows the answer, a package is found through its submodules and by the
  names ``resolve`` gives what its ``__init__.py`` defines, the answer is case-sensitive and cuts at dot boundaries,
  and a name shared by several modules is reported as such with every candidate searched.

[POS]
myrm-agent-server/tests/services/code_graph/test_code_graph_importers.py
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest
from myrm_agent_harness.runtime.paths.execution_paths import PERSISTENT_ROOT_ENV

from app.services.code_graph.agent_tool import create_code_graph_tool
from app.services.code_graph.ast_extractor import PythonAstExtractor
from app.services.code_graph.import_alignment import MAX_SCOPE_MODULES
from app.services.code_graph.service import CodeGraphService


def _write(root: Path, rel: str, text: str) -> None:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def _recorded(path: str, source: str) -> list[str]:
    extractor = PythonAstExtractor(path, source)
    assert extractor.extract() is True
    return [edge.imported_symbol for edge in extractor.imports]


def _importers(root: Path, tmp_path: Path, query: str) -> list[str]:
    """Paths of the files that import ``query``, sorted, one entry per import statement."""
    service = CodeGraphService(tmp_path / "graph.db")
    service.index_directory(root)
    return [str(row["file_path"]) for row in service.importers(query)]


@pytest.mark.parametrize(
    ("path", "source", "expected"),
    [
        ("pkg/sub/mod.py", "from . import sibling", ["pkg.sub.sibling"]),
        ("pkg/sub/mod.py", "from .shared import tool", ["pkg.sub.shared.tool"]),
        ("pkg/sub/mod.py", "from .. import uncle", ["pkg.uncle"]),
        ("pkg/sub/mod.py", "from ..cousins.deep import leaf", ["pkg.cousins.deep.leaf"]),
        ("pkg/sub/mod.py", "from ... import top_level", ["top_level"]),
        ("pkg/sub/mod.py", "from .... import beyond", []),
        ("pkg/__init__.py", "from .core import run", ["pkg.core.run"]),
        ("pkg/__init__.py", "from . import settings", ["pkg.settings"]),
        ("src/pkg/mod.py", "from . import util", ["src.pkg.util"]),
        ("mod.py", "from . import x\nfrom .y import z", ["x", "y.z"]),
        ("pkg/mod.py", "from a.b import c\nimport d.e", ["a.b.c", "d.e"]),
    ],
)
def test_a_relative_import_is_recorded_under_the_module_it_names(path: str, source: str, expected: list[str]) -> None:
    assert _recorded(path, source) == expected


def test_a_relative_import_keeps_its_alias() -> None:
    extractor = PythonAstExtractor("pkg/mod.py", "from . import helpers as aid")
    extractor.extract()

    assert [(edge.imported_symbol, edge.alias) for edge in extractor.imports] == [("pkg.helpers", "aid")]


def test_importers_find_absolute_and_relative_imports_of_a_flat_layout_module(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root, "pkg/__init__.py", "")
    _write(root, "pkg/util.py", "def helper():\n    return 1\n")
    _write(root, "pkg/a.py", "from pkg import util\n")
    _write(root, "pkg/b.py", "from . import util\n")
    _write(root, "pkg/c.py", "from .util import helper\n")
    _write(root, "pkg/d.py", "import pkg.util\n")
    _write(root, "pkg/near_miss.py", "import pkg.utility\nfrom pkg import utilities\nfrom pkg import UTIL\n")

    assert _importers(root, tmp_path, "pkg.util") == ["pkg/a.py", "pkg/b.py", "pkg/c.py", "pkg/d.py"]


@pytest.mark.parametrize("query", ["pkg.util", "src.pkg.util"])
def test_importers_find_a_src_layout_module_under_either_spelling(tmp_path: Path, query: str) -> None:
    root = tmp_path / "ws"
    _write(root, "src/pkg/__init__.py", "")
    _write(root, "src/pkg/util.py", "def helper():\n    return 1\n")
    _write(root, "src/pkg/sibling.py", "from . import util\n")
    _write(root, "tests/test_util.py", "from pkg.util import helper\n")
    _write(root, "tests/test_other.py", "from pkg.other import thing\n")

    assert _importers(root, tmp_path, query) == ["src/pkg/sibling.py", "tests/test_util.py"]


def test_a_name_inside_a_module_narrows_the_answer(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root, "src/pkg/util.py", "def helper():\n    return 1\n\ndef other():\n    return 2\n")
    _write(root, "a.py", "from pkg.util import helper\n")
    _write(root, "b.py", "from pkg.util import other\n")
    _write(root, "c.py", "from pkg.util import helper_two\n")

    assert _importers(root, tmp_path, "pkg.util.helper") == ["a.py"]
    assert _importers(root, tmp_path, "util.helper") == ["a.py"]


def test_a_package_is_found_through_what_is_imported_from_it(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root, "pkg/__init__.py", "from .core import Thing\n")
    _write(root, "pkg/core.py", "class Thing:\n    pass\n")
    _write(root, "a.py", "import pkg\n")
    _write(root, "b.py", "from pkg import Thing\n")
    _write(root, "c.py", "from pkg.core import Thing\n")

    assert _importers(root, tmp_path, "pkg") == ["a.py", "b.py", "c.py", "pkg/__init__.py"]
    assert _importers(root, tmp_path, "pkg.core") == ["c.py", "pkg/__init__.py"]


@pytest.mark.parametrize("layout", ["", "src/"])
def test_importers_accept_the_names_resolve_gives_what_a_package_defines(tmp_path: Path, layout: str) -> None:
    root = tmp_path / "ws"
    _write(root, f"{layout}pkg/__init__.py", "class Thing:\n    pass\n")
    _write(root, "a.py", "from pkg import Thing\n")
    _write(root, "b.py", "import pkg\n")
    service = CodeGraphService(tmp_path / "graph.db")
    service.index_directory(root)
    symbol = str(service.resolve("Thing")[0]["qualified_name"])
    package = symbol.removesuffix(".Thing")

    assert package.endswith(".__init__")
    assert [row["file_path"] for row in service.importers(symbol)] == ["a.py"]
    assert [row["file_path"] for row in service.importers(package)] == ["a.py", "b.py"]


def test_importers_are_case_sensitive(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root, "pkg/util.py", "def helper():\n    return 1\n")
    _write(root, "a.py", "from pkg import util\n")

    assert _importers(root, tmp_path, "Pkg.util") == []


def test_a_local_module_does_not_take_the_imports_of_a_third_party_package_with_its_name(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root, "app/redis.py", "def connect():\n    return None\n")
    _write(root, "worker.py", "import redis\n")
    _write(root, "main.py", "from app import redis\n")

    assert _importers(root, tmp_path, "app.redis") == ["main.py"]


def test_a_name_shared_by_two_modules_is_reported_with_both_candidates(tmp_path: Path) -> None:
    root = tmp_path / "ws"
    _write(root, "a/models.py", "class A:\n    pass\n")
    _write(root, "b/models.py", "class B:\n    pass\n")
    _write(root, "x.py", "from a.models import A\n")
    _write(root, "y.py", "from b.models import B\n")
    service = CodeGraphService(tmp_path / "graph.db")
    service.index_directory(root)

    assert service.importer_scope("models").modules == ("a.models", "b.models")
    assert [row["file_path"] for row in service.importers("models")] == ["x.py", "y.py"]
    assert service.importer_scope("a.models").modules == ("a.models",)
    assert [row["file_path"] for row in service.importers("a.models")] == ["x.py"]


@pytest.fixture
def persistent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(PERSISTENT_ROOT_ENV, str(tmp_path / "persistent"))
    return tmp_path


async def _notes(root: Path, query: str) -> list[str]:
    result = await create_code_graph_tool(root).ainvoke({"action": "importers", "query": query})
    return cast(list[str], json.loads(str(result["content"])).get("notes", []))


async def test_the_answer_lists_the_modules_a_shared_name_fits(persistent: Path) -> None:
    root = persistent / "ws"
    for package in ("a", "b", "c", "d", "e", "f"):
        _write(root, f"{package}/models.py", "class M:\n    pass\n")
    _write(root, "x.py", "from a.models import M\n")

    shared = [note for note in await _notes(root, "models") if "modules fit this name" in note]
    narrowed = [note for note in await _notes(root, "a.models") if "modules fit this name" in note]

    assert shared == [
        "6 modules fit this name (a.models, b.models, c.models, d.models, e.models, ...), "
        "so rows may import any of them: use the full module name to narrow."
    ]
    assert narrowed == []


async def test_the_answer_says_when_only_the_first_candidates_were_searched(persistent: Path) -> None:
    root = persistent / "ws"
    for index in range(MAX_SCOPE_MODULES + 1):
        _write(root, f"pkg{index:03d}/models.py", "class M:\n    pass\n")

    notes = [note for note in await _notes(root, "models") if "modules fit this name" in note]

    assert len(notes) == 1
    assert notes[0].startswith(f"{MAX_SCOPE_MODULES + 1} modules fit this name")
    assert notes[0].endswith(f"Only the first {MAX_SCOPE_MODULES} are searched.")
