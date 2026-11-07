"""Star-import tests for scripts.module_reachability_engine: a shim forwards a used name to its definer.

Every case builds a synthetic package under ``tmp_path`` (root name ``pkg``) so the tests are
hermetic and fast; they neither import the harness nor read its tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts.module_reachability_engine import analyze
from tests.support.reachability_trees import dead, package


def test_star_shim_forwards_a_used_name_to_the_module_that_defines_it(tmp_path: Path) -> None:
    root = package(
        tmp_path,
        {
            "core/redact/__init__.py": "from .view import redact_file_text\nfrom .engine import redact\n",
            "core/redact/view.py": "def redact_file_text() -> None: ...\n",
            "core/redact/engine.py": "def redact() -> None: ...\n",
            "agent/shim.py": "from pkg.core.redact import *\n",
            "api/consumer.py": "from pkg.agent.shim import redact_file_text\n\nredact_file_text()\n",
        },
    )
    assert dead(analyze(root)) == {"core/redact/engine"}


def test_star_shim_chain_forwards_through_every_link(tmp_path: Path) -> None:
    root = package(
        tmp_path,
        {
            "core/redact/__init__.py": "from .view import redact_file_text\n",
            "core/redact/view.py": "def redact_file_text() -> None: ...\n",
            "agent/inner.py": "from pkg.core.redact import *\n",
            "agent/outer.py": "from .inner import *\n",
            "api/consumer.py": "from pkg.agent.outer import redact_file_text\n\nredact_file_text()\n",
        },
    )
    assert dead(analyze(root)) == set()


def test_star_import_cycle_terminates(tmp_path: Path) -> None:
    root = package(
        tmp_path,
        {
            "agent/ping.py": "from pkg.agent.pong import *\n",
            "agent/pong.py": "from pkg.agent.ping import *\n",
            "api/consumer.py": "from pkg.agent.ping import missing\n",
        },
    )
    assert dead(analyze(root)) == set()
