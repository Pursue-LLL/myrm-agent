"""Tests for ToolNameFuzzyRepairer: alias mapping, case and separator normalization, suffix strip and fuzzy threshold."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.tool_validation import ToolNameFuzzyRepairer

VALID_TOOLS = frozenset({"read_file", "write_file", "execute_bash", "git_commit", "search_codebase"})


@pytest.fixture
def fuzzy_repairer() -> ToolNameFuzzyRepairer:
    alias_map = {
        "bash": "execute_bash",
        "readfile": "read_file",
        "writefile": "write_file",
    }
    return ToolNameFuzzyRepairer(alias_map=alias_map, similarity_threshold=0.82)


def test_registered_name_is_returned_unchanged(fuzzy_repairer: ToolNameFuzzyRepairer) -> None:
    assert fuzzy_repairer.repair_name("read_file", set(VALID_TOOLS)) == "read_file"


def test_case_separator_and_alias_variants_are_repaired(fuzzy_repairer: ToolNameFuzzyRepairer) -> None:
    assert fuzzy_repairer.repair_name("READ_FILE", set(VALID_TOOLS)) == "read_file"
    assert fuzzy_repairer.repair_name("read-file", set(VALID_TOOLS)) == "read_file"
    assert fuzzy_repairer.repair_name("bash", set(VALID_TOOLS)) == "execute_bash"


def test_unknown_names_are_not_repaired(fuzzy_repairer: ToolNameFuzzyRepairer) -> None:
    assert fuzzy_repairer.repair_name("launch_rocket_hyperdrive", set(VALID_TOOLS)) is None
    assert fuzzy_repairer.repair_name("hallucinated_tool_xyz", set(VALID_TOOLS)) is None


def test_suffix_hallucination_is_repaired_to_the_registered_tool() -> None:
    """A model that appends an implementation-ish suffix must still reach the real tool.

    Measured on a live run: the model emitted ``todo_write_tool`` while the registered
    name is ``todo_write``. The extra word dilutes the fuzzy ratio to 0.76, below the 0.82 threshold,
    so the call was rejected, the model retried with the same wrong name and the turn ended with
    three strikes and no reply. The exact suffix rule repairs it without touching the threshold.
    """
    valid = frozenset({"todo_write", "kanban_show", "read_file"})
    repairer = ToolNameFuzzyRepairer(similarity_threshold=0.82)

    assert repairer.repair_name("todo_write_tool", set(valid)) == "todo_write"
    assert repairer.repair_name("todo_write_tool_call", set(valid)) == "todo_write"
    assert repairer.repair_name("read_file_tool", set(valid)) == "read_file"
    # A name whose stripped form is not a registered tool must not be repaired by the suffix rule.
    assert repairer.repair_name("todo_write_tool_v2", set(valid)) is None
