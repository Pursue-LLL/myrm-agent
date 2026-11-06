"""A script saved to a file that imports an MCP skill is a tool call, in the checklist as much as inline.

Writing it is not work that needs a test run, and running it is neither proof for other code nor a failed check
held against the run once the model fetched the data another way.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard import CompletionGuard, reset_completion_guard
from myrm_agent_harness.agent.middlewares.completion.completion_guard.checklist import (
    CriticalCause,
    assess_checklist,
    build_checklist,
    find_last_successful_verification_command,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.verification import without_skill_scripts
from myrm_agent_harness.agent.security.guards.loop_guard import CallRecord, VerificationCategory
from tests.support.call_records import FAIL, OK, call, shell, write
from tests.support.completion_guard_harness import LOOP_GUARD_PATCH, make_state, reasons_of

TEST = VerificationCategory.TEST

SKILL_SCRIPT = (
    "import asyncio\nfrom skills.mcp_kubernetes_skill import list_namespaces\n\nasyncio.run(list_namespaces())\n"
)
PLAIN_SCRIPT = "def add(a, b):\n    return a + b\n\nprint(add(1, 2))\n"
INLINE_FETCH = (
    "import asyncio\nfrom skills.mcp_kubernetes_skill import list_deployments\nasyncio.run(list_deployments())"
)


def probe_written() -> CallRecord:
    return write("/w/probe.py", content=SKILL_SCRIPT)


class TestASavedSkillScriptIsNotJudgedAsCode:
    def test_its_failed_runs_do_not_hold_the_answer_back_once_the_data_came_another_way(self) -> None:
        records = [
            probe_written(),
            shell("cd /w && python3 probe.py 2>&1 | head -60", FAIL, TEST),
            shell("cd /w && python probe.py", FAIL, TEST),
            shell(INLINE_FETCH),
        ]

        assert assess_checklist(records).causes == frozenset()

    def test_its_passing_run_is_not_a_proof_of_other_code(self) -> None:
        records = [
            write("/w/app.py", content=PLAIN_SCRIPT),
            probe_written(),
            shell("cd /w && python3 probe.py", OK, TEST),
        ]

        assert assess_checklist(records).causes == {CriticalCause.UNVERIFIED_CODE}

    def test_it_is_not_a_command_the_independent_re_run_could_repeat(self) -> None:
        records = [probe_written(), shell("cd /w && python3 probe.py", OK, TEST)]

        assert find_last_successful_verification_command(records) is None

    def test_a_written_skill_script_alone_asks_for_no_verification(self) -> None:
        checklist, critical = build_checklist([probe_written()])

        assert not critical
        assert "Files were modified" not in checklist


class TestRealCodeIsStillHeldToItsChecks:
    def test_a_failing_run_of_the_code_the_run_wrote_still_holds_the_answer_back(self) -> None:
        records = [probe_written(), write("/w/app.py", content=PLAIN_SCRIPT), shell("python3 app.py", FAIL, TEST)]

        assert assess_checklist(records).causes == {CriticalCause.FAILED_VERIFICATION}

    def test_a_passing_run_of_that_code_still_proves_it(self) -> None:
        records = [write("/w/app.py", content=PLAIN_SCRIPT), shell("python3 app.py", OK, TEST)]

        assert assess_checklist(records).causes == frozenset()

    def test_the_same_file_name_in_another_directory_is_not_taken_for_the_skill_script(self) -> None:
        records = [
            write("/w/a/probe.py", content=SKILL_SCRIPT),
            write("/w/b/probe.py", content=PLAIN_SCRIPT),
            shell("cd /w/b && python3 probe.py", FAIL, TEST),
        ]

        assert assess_checklist(records).causes == {CriticalCause.FAILED_VERIFICATION}

    def test_a_document_that_quotes_a_skill_import_is_still_a_write(self) -> None:
        records = [write("/w/NOTES.md", content=SKILL_SCRIPT), call("web_fetch_tool", "https://x", FAIL)]

        assert assess_checklist(records).causes == {CriticalCause.UNRESOLVED_FAILURE}


class TestWhichRunsAreTheSavedScript:
    @pytest.mark.parametrize(
        "command",
        [
            "python3 probe.py",
            "python probe.py",
            "python3 ./probe.py",
            "cd /w && python3 probe.py",
            "cd /w && python3 -u probe.py 2>&1 | head -60",
            "python3 /w/probe.py",
            "FOO=1 python3 /w/probe.py",
            "cd /tmp && python3 /w/probe.py",
        ],
    )
    def test_a_run_of_the_file_is_dropped(self, command: str) -> None:
        run = shell(command, OK, TEST)

        assert without_skill_scripts([probe_written(), run]) == []

    @pytest.mark.parametrize(
        "command",
        [
            "python3 other.py",
            "cd /w/sub && python3 probe.py",
            "python3 -m pytest probe.py",
            "python3 -c 'print(1)'",
            "cat probe.py",
            "pytest",
        ],
    )
    def test_anything_else_stays(self, command: str) -> None:
        run = shell(command, OK, TEST)

        assert without_skill_scripts([probe_written(), run]) == [run]

    def test_a_script_written_with_a_relative_path_is_found_by_its_absolute_run(self) -> None:
        run = shell("python3 /w/probe.py", OK, TEST)

        assert without_skill_scripts([write("probe.py", content=SKILL_SCRIPT), run]) == []

    def test_a_run_before_any_write_of_the_file_is_not_the_skill_script(self) -> None:
        run = shell("python3 /w/probe.py", FAIL, TEST)

        assert without_skill_scripts([run, probe_written()]) == [run]

    def test_a_later_write_that_drops_the_import_brings_the_file_back(self) -> None:
        plain = write("/w/probe.py", content=PLAIN_SCRIPT)
        run = shell("cd /w && python3 probe.py", FAIL, TEST)

        assert without_skill_scripts([probe_written(), plain, run]) == [plain, run]

    def test_records_without_a_skill_script_are_returned_unchanged(self) -> None:
        records = [write("/w/app.py", content=PLAIN_SCRIPT), shell("python3 app.py", FAIL, TEST), shell(INLINE_FETCH)]

        assert without_skill_scripts(records) == records

    def test_a_non_python_file_that_imports_a_skill_is_kept(self) -> None:
        notes = write("/w/notes.txt", content=SKILL_SCRIPT)

        assert without_skill_scripts([notes]) == [notes]


class TestTheGuardLetsTheAnswerThrough:
    """The held-back answer of a run that saved a skill script and fetched the data inline is the failure this removes."""

    def setup_method(self) -> None:
        reset_completion_guard()

    @staticmethod
    async def verdict(window: list[CallRecord]) -> dict[str, object] | None:
        messages = [
            HumanMessage(content="compare the staging and prod images"),
            AIMessage(content="checkout-web lags."),
        ]
        with patch(LOOP_GUARD_PATCH) as loop_guard:
            loop_guard.return_value.recorded_calls.return_value = window
            return await CompletionGuard().aafter_model(make_state(messages), None)

    @pytest.mark.asyncio
    async def test_failed_runs_of_the_saved_skill_script_do_not_hold_the_answer_back(self) -> None:
        window = [
            probe_written(),
            shell("cd /w && python3 probe.py 2>&1 | head -60", FAIL, TEST),
            shell("cd /w && python probe.py", FAIL, TEST),
            shell(INLINE_FETCH),
        ]

        assert await self.verdict(window) is None

    @pytest.mark.asyncio
    async def test_failed_runs_of_code_the_run_wrote_still_do(self) -> None:
        window = [write("/w/app.py", content=PLAIN_SCRIPT), shell("python3 app.py", FAIL, TEST)]

        assert reasons_of(await self.verdict(window)).verification
