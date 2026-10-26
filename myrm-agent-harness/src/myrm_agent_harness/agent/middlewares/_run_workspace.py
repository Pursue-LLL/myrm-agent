"""The workspace a run's middlewares read session state from.

[INPUT]
- langgraph.runtime::Runtime (POS: the per-run object a middleware hook receives; its ``context`` is the run context)

[OUTPUT]
- run_workspace: the run's ``workspace_path`` from its LangGraph ``Runtime`` context

[POS]
Single place that knows where a run's workspace lives in the ``Runtime`` a middleware hook receives
(``setup_workspace`` puts ``workspace_path`` in the run context), shared by todo focus injection and
CompletionGuard so neither re-derives the shape.
"""

from __future__ import annotations


def run_workspace(runtime: object) -> str | None:
    """Return the ``workspace_path`` in the runtime's context, or None.

    ``runtime`` is the LangGraph ``Runtime`` handed to a middleware hook, or None when the hook was called
    without one.
    """
    context = getattr(runtime, "context", None)
    if not isinstance(context, dict):
        return None
    workspace = context.get("workspace_path")
    return str(workspace) if workspace else None
