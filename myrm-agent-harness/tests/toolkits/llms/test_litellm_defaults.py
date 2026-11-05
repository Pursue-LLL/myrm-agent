"""LiteLLM runs without a process-wide response cache.

LiteLLM's response cache is keyed by model and messages, not by API key or endpoint. With it on, the answer of one provider
stands in for every other key or endpoint that is asked the same question, so a health check or a settings probe reports
a mistyped key as healthy. A caller that wants a recorded answer asks for one explicitly (``memo_run``, an embedding cache).
"""

from __future__ import annotations

import litellm

from myrm_agent_harness.toolkits.llms import config as _production_defaults  # noqa: F401  # applies the defaults on import


def test_the_llm_toolkit_installs_no_response_cache() -> None:
    assert litellm.cache is None
