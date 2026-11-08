"""Importing the web search toolkit stays light: no model library and no REST client until first use.

[INPUT]
- myrm_agent_harness.toolkits.web_search: public toolkit facade
- myrm_agent_harness.toolkits.web_search.providers: provider package with lazy ``RestSearch``

[OUTPUT]
- Regression guard for the startup contract that the search client loads on first access, not on import.

[POS]
Unit tests mirroring src/myrm_agent_harness/toolkits/web_search/providers/__init__.py.
"""

from __future__ import annotations

import importlib
import subprocess
import sys

import pytest

_REST_MODULE = "myrm_agent_harness.toolkits.web_search.providers.rest_search"
_TRANSPORT_MODULE = "myrm_agent_harness.toolkits.llms.transport"


def _run(probe: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False)


def test_importing_the_toolkit_loads_neither_the_model_transport_nor_the_rest_client() -> None:
    result = _run(
        "import sys; "
        "from myrm_agent_harness.toolkits.web_search import WebSearchTools; "
        f"assert '{_TRANSPORT_MODULE}' not in sys.modules; "
        f"assert '{_REST_MODULE}' not in sys.modules"
    )
    assert result.returncode == 0, result.stderr


def test_rest_search_loads_on_first_access() -> None:
    result = _run(
        "import sys; "
        "from myrm_agent_harness.toolkits.web_search.providers import RestSearch; "
        "assert RestSearch.__name__ == 'RestSearch'; "
        f"assert '{_TRANSPORT_MODULE}' not in sys.modules; "
        f"assert '{_REST_MODULE}' in sys.modules"
    )
    assert result.returncode == 0, result.stderr


_TOOLKIT = "myrm_agent_harness.toolkits.web_search"
_PROVIDERS = f"{_TOOLKIT}.providers"


@pytest.mark.parametrize(
    ("package", "name", "home"),
    [
        (_TOOLKIT, "RestSearch", _REST_MODULE),
        (_TOOLKIT, "SearchServiceConfig", f"{_PROVIDERS}.web_searcher"),
        (_TOOLKIT, "WebSearchTools", f"{_TOOLKIT}.engine"),
        (_PROVIDERS, "RestSearch", _REST_MODULE),
    ],
)
def test_a_lazy_name_is_the_class_of_its_home_module_and_is_cached(
    monkeypatch: pytest.MonkeyPatch, package: str, name: str, home: str
) -> None:
    module = importlib.import_module(package)
    monkeypatch.delitem(vars(module), name, raising=False)  # forces the module-level __getattr__

    resolved = getattr(module, name)

    assert resolved is getattr(importlib.import_module(home), name)
    assert vars(module)[name] is resolved, "the next lookup must not go through __getattr__ again"


@pytest.mark.parametrize("package", [_TOOLKIT, _PROVIDERS])
def test_an_unknown_name_is_an_attribute_error(package: str) -> None:
    with pytest.raises(AttributeError, match="has no attribute 'NotAThing'"):
        importlib.import_module(package).NotAThing  # noqa: B018 - the access itself is what raises
