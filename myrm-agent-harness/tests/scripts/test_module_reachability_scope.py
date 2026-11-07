"""Scope tests for scripts.module_reachability_engine: which files are units, roots and evidence.

Every case builds a synthetic package under ``tmp_path`` (root name ``pkg``) so the tests are
hermetic and fast; they neither import the harness nor read its tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.module_reachability_engine import analyze, classify
from tests.support.reachability_trees import dead, package


def test_every_top_level_directory_is_in_scope_except_root_dirs(tmp_path: Path) -> None:
    files = {
        "toolkits/lonely.py": "X = 1\n",
        "backends/__init__.py": "",
        "backends/used.py": "def run() -> None: ...\n",
        "api/consumer.py": "from pkg.backends.used import run\n\nrun()\n",
        "plugins/loader.py": "from pkg.toolkits.lonely import X\n\nprint(X)\n",
    }
    root = package(tmp_path, files)
    assert dead(analyze(root)) == {"toolkits/lonely", "plugins/loader"}
    assert dead(analyze(root, root_dirs=("api", "plugins"))) == set()


def test_nested_file_is_judged_on_its_own_not_with_its_package(tmp_path: Path) -> None:
    root = package(
        tmp_path,
        {
            "agent/engine/bundle/__init__.py": "",
            "agent/engine/bundle/inner.py": "def run() -> None: ...\n",
            "agent/engine/bundle/deep/__init__.py": "",
            "agent/engine/bundle/deep/orphan.py": "def lost() -> None: ...\n",
            "agent/standalone.py": "def go() -> None: ...\n",
            "api/consumer.py": "from pkg.agent.engine.bundle.inner import run\n",
        },
    )
    report = analyze(root)
    assert set(report.units) == {"agent/engine/bundle/inner", "agent/engine/bundle/deep/orphan", "agent/standalone"}
    assert report.units["agent/engine/bundle/inner"].lines >= 2
    assert dead(report) == {"agent/engine/bundle/deep/orphan", "agent/standalone"}


def test_root_dir_matches_by_path_prefix(tmp_path: Path) -> None:
    root = package(
        tmp_path,
        {
            "toolkits/builtin/script.py": "from pkg.toolkits.helper import run\n\nrun()\n",
            "toolkits/builtin_extra/script.py": "X = 1\n",
            "toolkits/helper.py": "def run() -> None: ...\n",
        },
    )
    assert dead(analyze(root)) == {"toolkits/builtin/script", "toolkits/builtin_extra/script", "toolkits/helper"}
    assert dead(analyze(root, root_dirs=("api", "toolkits/builtin"))) == {"toolkits/builtin_extra/script"}


def test_generated_directory_is_neither_unit_nor_evidence(tmp_path: Path) -> None:
    """A generator lists every module of a directory; counting that list would keep each of them alive."""
    root = package(
        tmp_path,
        {
            "api/guard.py": "from pkg.runtime.guard._generated.manifest import MODULES\n\nprint(MODULES)\n",
            "runtime/guard/_generated/manifest.py": 'MODULES = ("pkg.agent.engine.listed",)\n',
            "agent/engine/listed.py": "class Listed: ...\n",
        },
    )
    report = analyze(root)
    assert set(report.units) == {"agent/engine/listed"}
    assert dead(report) == {"agent/engine/listed"}


def test_scope_classification() -> None:
    assert classify(("agent", "__init__.py")) == ("root", None)
    assert classify(("agent", "engine", "bundle", "deep", "__init__.py")) == ("root", None)
    assert classify(("agent", "engine", "__main__.py")) == ("root", None)
    assert classify(("agent", "engine", "bundle", "__main__.py")) == ("root", None)
    assert classify(("cli.py",)) == ("root", None)
    assert classify(("api", "routes", "chat.py")) == ("root", None)
    assert classify(("toolkits", "memory", "store.py")) == ("unit", "toolkits/memory/store")
    assert classify(("core", "standalone.py")) == ("unit", "core/standalone")
    assert classify(("runtime", "context", "engine.py")) == ("unit", "runtime/context/engine")
    assert classify(("runtime", "context", "bundle", "deep", "mod.py")) == ("unit", "runtime/context/bundle/deep/mod")
    assert classify(("channels", "providers", "slack.py"), root_dirs=("channels",)) == ("root", None)
    assert classify(("toolkits", "builtin", "x", "t.py"), root_dirs=("toolkits/builtin",)) == ("root", None)
    assert classify(("toolkits", "builtin_extra", "t.py"), root_dirs=("toolkits/builtin",)) == (
        "unit",
        "toolkits/builtin_extra/t",
    )
