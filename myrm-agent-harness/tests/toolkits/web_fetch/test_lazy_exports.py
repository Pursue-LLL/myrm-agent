"""The web_fetch packages load their engine and HTML pipeline on first access, not when a submodule is imported."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

import myrm_agent_harness
from myrm_agent_harness.toolkits import web_fetch
from myrm_agent_harness.toolkits.web_fetch import processing
from myrm_agent_harness.toolkits.web_fetch.engine import FailedResult, FetchEngine, SuccessResult
from myrm_agent_harness.toolkits.web_fetch.processing.pipeline import ContentPipeline

_SOURCE_ROOT = Path(myrm_agent_harness.__file__).resolve().parents[1]


def _run_fresh_interpreter(code: str) -> str:
    """Stdout of ``code`` run in a new interpreter, so what other tests imported cannot hide an eager import."""
    env = {**os.environ, "PYTHONPATH": str(_SOURCE_ROOT)}
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env, timeout=120
    )
    return result.stdout.strip()


def test_importing_spill_leaves_the_engine_and_the_html_parser_unloaded() -> None:
    code = (
        "import sys\n"
        "import myrm_agent_harness.toolkits.web_fetch.processing.spill\n"
        "watched = ('bs4', 'myrm_agent_harness.toolkits.web_fetch.engine',"
        " 'myrm_agent_harness.toolkits.web_fetch.processing.pipeline')\n"
        "print([name for name in watched if name in sys.modules])\n"
    )

    assert _run_fresh_interpreter(code) == "[]"


def test_global_instance_is_created_once_when_threads_ask_together() -> None:
    code = (
        "import threading\n"
        "import myrm_agent_harness.toolkits.web_fetch as package\n"
        "from myrm_agent_harness.toolkits.web_fetch.engine import FetchEngine\n"
        "created = []\n"
        "original = FetchEngine.__init__\n"
        "def counting(self, *args, **kwargs):\n"
        "    created.append(1)\n"
        "    original(self, *args, **kwargs)\n"
        "FetchEngine.__init__ = counting\n"
        "seen = []\n"
        "barrier = threading.Barrier(8)\n"
        "def grab():\n"
        "    barrier.wait()\n"
        "    seen.append(id(package.web_fetch_tools))\n"
        "threads = [threading.Thread(target=grab) for _ in range(8)]\n"
        "for thread in threads:\n"
        "    thread.start()\n"
        "for thread in threads:\n"
        "    thread.join()\n"
        "print(len(created), len(set(seen)))\n"
    )

    assert _run_fresh_interpreter(code) == "1 1"


def test_engine_names_resolve_to_the_engine_package_objects() -> None:
    assert web_fetch.FetchEngine is FetchEngine
    assert web_fetch.SuccessResult is SuccessResult
    assert web_fetch.FailedResult is FailedResult


def test_global_instance_is_a_fetch_engine_and_stays_the_same_object() -> None:
    assert isinstance(web_fetch.web_fetch_tools, FetchEngine)
    assert web_fetch.web_fetch_tools is web_fetch.web_fetch_tools


def test_content_pipeline_resolves_to_the_pipeline_module_object() -> None:
    assert processing.ContentPipeline is ContentPipeline


@pytest.mark.parametrize("package", [web_fetch, processing])
def test_unknown_name_raises_attribute_error(package: ModuleType) -> None:
    unknown = "missing_name"

    with pytest.raises(AttributeError, match=f"has no attribute '{unknown}'"):
        getattr(package, unknown)
