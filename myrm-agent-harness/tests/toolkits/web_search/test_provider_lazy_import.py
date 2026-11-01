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

import subprocess
import sys

_REST_MODULE = "myrm_agent_harness.toolkits.web_search.providers.rest_search"


def _run(probe: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True, check=False)


def test_importing_the_toolkit_loads_neither_litellm_nor_the_rest_client() -> None:
    result = _run(
        "import sys; "
        "from myrm_agent_harness.toolkits.web_search import WebSearchTools; "
        "assert 'litellm' not in sys.modules; "
        f"assert '{_REST_MODULE}' not in sys.modules"
    )
    assert result.returncode == 0, result.stderr


def test_rest_search_loads_on_first_access() -> None:
    result = _run(
        "import sys; "
        "from myrm_agent_harness.toolkits.web_search.providers import RestSearch; "
        "assert RestSearch.__name__ == 'RestSearch'; "
        "assert 'litellm' not in sys.modules; "
        f"assert '{_REST_MODULE}' in sys.modules"
    )
    assert result.returncode == 0, result.stderr
