"""The ``cron_manage`` add action decides, for every ``create_job`` parameter, whether it sets it.

A parameter the action leaves out is silently lost for every job created through the tool, a blueprint's value
included. So a parameter added to ``CronManager.create_job`` has to be either forwarded by ``_do_add`` or named
here with the reason the tool does not offer it.
"""

from __future__ import annotations

import ast
import inspect
import textwrap

from myrm_agent_harness.toolkits.cron.cron_agent_actions import _do_add
from myrm_agent_harness.toolkits.cron.manager import CronManager

# Tuning the model is not offered; a job created through the tool runs with the defaults.
_TUNING_LEFT_TO_DEFAULTS = {
    "max_retries",
    "retry_backoff_ms",
    "misfire_grace_seconds",
    "cooldown_seconds",
    "run_retention_days",
    "delete_after_run",
}

# Bound to a job from the app's job editor and the project it belongs to, not by the model.
_SET_IN_THE_APP = {
    "acceptance_criteria",
    "allowed_roots",
    "project_id",
    "workflow_template_id",
    "workflow_template_args",
}


def _keywords_add_passes_to_create_job() -> set[str]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(_do_add)))
    return {
        keyword.arg
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "create_job"
        for keyword in node.keywords
        if keyword.arg is not None
    }


def test_every_create_job_parameter_is_forwarded_by_add_or_named_as_not_offered() -> None:
    create_job_parameters = set(inspect.signature(CronManager.create_job).parameters) - {"self"}

    not_forwarded = create_job_parameters - _keywords_add_passes_to_create_job()

    assert not_forwarded == _TUNING_LEFT_TO_DEFAULTS | _SET_IN_THE_APP, (
        "create_job takes a parameter the add action neither forwards nor lists as not offered "
        f"(or a listed one is now forwarded): {sorted(not_forwarded ^ (_TUNING_LEFT_TO_DEFAULTS | _SET_IN_THE_APP))}"
    )


def test_add_forwards_only_parameters_create_job_takes() -> None:
    create_job_parameters = set(inspect.signature(CronManager.create_job).parameters)

    assert _keywords_add_passes_to_create_job() <= create_job_parameters
