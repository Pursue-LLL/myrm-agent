"""Architecture test: ``pytest -n N`` never starts more xdist workers than the configured cap.

Each xdist worker is its own Python process, so memory grows with ``-n`` (measured: ``-n 10`` on ``tests/api/memory`` peaked
at about 3.6 GB of resident memory, about 1.9 GB with the cap). The cap is ``--maxprocesses`` in ``pyproject.toml``
``addopts``. xdist documents that option only for ``-n auto|logical``; capping an explicit ``-n N`` is its current
implementation behavior, so a config grep proves nothing. These tests parse the project's real pytest configuration
in-process and call xdist's own ``pytest_cmdline_main`` to read the worker list it would start (``config.option.tx``: one
entry per worker).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

_PYPROJECT = Path(__file__).resolve().parent.parent.parent / "pyproject.toml"


def _parse(pytester: pytest.Pytester, *args: str) -> pytest.Config:
    # An explicit path keeps ``testpaths`` (absent under the pytester root) from raising a configuration warning.
    return pytester.parseconfig("-c", str(_PYPROJECT), "--rootdir", str(pytester.path), *args, str(pytester.path))


def _workers(pytester: pytest.Pytester, *args: str) -> int:
    config = _parse(pytester, *args)
    # Only xdist's own implementation: the full hook chain would also run the session.
    impls = config.hook.pytest_cmdline_main.get_hookimpls()
    (xdist_impl,) = (impl for impl in impls if impl.plugin_name == "xdist")
    xdist_impl.function(config)
    return len(config.option.tx)


def _cap(pytester: pytest.Pytester) -> int:
    cap = _parse(pytester).option.maxprocesses
    assert cap, "pyproject.toml addopts must cap xdist workers with --maxprocesses"
    return int(cap)


def test_explicit_worker_request_is_capped(pytester: pytest.Pytester) -> None:
    cap = _cap(pytester)
    assert _workers(pytester, "-n", str(cap + 6)) == cap


def test_cap_can_be_raised_on_purpose(pytester: pytest.Pytester) -> None:
    cap = _cap(pytester)
    assert _workers(pytester, "-n", str(cap + 6), f"--maxprocesses={cap + 2}") == cap + 2


def test_probe_sees_the_cap_disappear_with_addopts_cleared(pytester: pytest.Pytester) -> None:
    # ``-o addopts=`` is the known way around the cap; it also proves the probe reacts to the cap being absent.
    cap = _cap(pytester)
    assert _workers(pytester, "-o", "addopts=", "-n", str(cap + 6)) == cap + 6
