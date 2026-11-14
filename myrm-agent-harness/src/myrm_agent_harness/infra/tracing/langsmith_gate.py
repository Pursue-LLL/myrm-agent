"""LangSmith trace upload and the zero-egress gate.

[INPUT]
- os.environ: the ``LANGSMITH_TRACING*`` / ``LANGCHAIN_TRACING*`` switches LangChain reads
- infra.tracing.otlp.config::env_flag (POS: the one reading of a truthy environment switch)
- langsmith.utils::get_env_var (POS: LangChain's cached environment reader)

[OUTPUT]
- langsmith_tracing_requested: whether the environment switches LangSmith tracing on
- block_langsmith_tracing: switch it off for this process; True when it was on

[POS]
While one of these switches is on, LangChain uploads the inputs and outputs of every run to LangSmith through
its own client. That path never meets the OTLP target checks or the privacy guard, so the zero-egress policy
(``MYRM_LOCAL_TRACE_ONLY``) closes it separately: ``setup_tracing`` calls ``block_langsmith_tracing`` first.
"""

from __future__ import annotations

import logging
import os

from myrm_agent_harness.infra.tracing.otlp.config import env_flag

logger = logging.getLogger(__name__)

# Every name LangSmith resolves its tracing switch from (``LANGSMITH_*`` and the older ``LANGCHAIN_*``).
LANGSMITH_TRACING_SWITCHES = (
    "LANGSMITH_TRACING_V2",
    "LANGCHAIN_TRACING_V2",
    "LANGSMITH_TRACING",
    "LANGCHAIN_TRACING",
)


def langsmith_tracing_requested() -> bool:
    """True when the environment switches LangSmith tracing on."""
    return any(env_flag(name) for name in LANGSMITH_TRACING_SWITCHES)


def block_langsmith_tracing() -> bool:
    """Switch LangSmith tracing off for this process; True when the environment had it on.

    Every switch is set to ``false`` because LangSmith takes the first one that is set. The values it
    already read are cached, so the cache is cleared for the change to be seen.
    """
    requested = langsmith_tracing_requested()
    if requested:
        for name in LANGSMITH_TRACING_SWITCHES:
            os.environ[name] = "false"
        _forget_cached_switches()
        logger.warning("Local-trace-only mode active: LangSmith tracing switched off")
    return requested


def _forget_cached_switches() -> None:
    try:
        from langsmith.utils import get_env_var
    except ImportError:
        return
    get_env_var.cache_clear()  # type: ignore[attr-defined]  # an lru_cache wrapper whose overloads hide the attribute
