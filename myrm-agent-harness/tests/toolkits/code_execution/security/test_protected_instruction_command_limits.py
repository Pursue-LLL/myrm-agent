"""The edges of the shell-side reading of the protected instruction files.

The write forms the reading recognises are in ``test_protected_instruction_command.py``. Verifies:
1. The limits of a lexical reading hold as documented.
2. A long line that repeats the keywords is read in linear time.
3. The threat analyzer reports the same name as the evidence of its escalation.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.toolkits.code_execution.security.protected_instruction_command import (
    protected_instruction_mutation_target as target,
)
from myrm_agent_harness.toolkits.code_execution.security.risk_classifier import CommandRiskLevel, classify_command_risk
from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import ThreatLevel, analyze_command


class TestTheReadingIsLexical:
    def test_a_copy_source_is_not_told_apart_from_its_target(self) -> None:
        assert target("cp AGENTS.md /tmp/backup.md") == "AGENTS.md"

    @pytest.mark.parametrize(
        "command",
        [
            'echo "a > AGENTS.md"',
            'git commit -m "rm AGENTS.md from docs"',
            'git commit -m "docs; move AGENTS.md notes"',
        ],
    )
    def test_the_text_of_a_quoted_argument_is_read_like_the_command_around_it(self, command: str) -> None:
        assert target(command) == "AGENTS.md"

    @pytest.mark.parametrize(
        "command",
        [
            "grep -n rm AGENTS.md > found.txt",
            "(cd repo && grep -n rm AGENTS.md)",
            "rm -rf build && grep -n rm AGENTS.md",
        ],
    )
    def test_a_search_is_taken_for_a_write_when_the_line_is_not_read_only_as_a_whole(self, command: str) -> None:
        assert classify_command_risk(command) is not CommandRiskLevel.SAFE
        assert target(command) == "AGENTS.md"

    @pytest.mark.parametrize(
        "command",
        [
            "dd of=AGENTS.md if=x",
            "perl -pi -e 's/a/b/' AGENTS.md",
            "git checkout -- AGENTS.md",
            "ln -sf x AGENTS.md",
            "install -m 644 x AGENTS.md",
            "curl -o AGENTS.md http://example.invalid/x",
            "echo x >| AGENTS.md",
            "sc AGENTS.md x",
            "ni AGENTS.md",
            "[IO.File]::WriteAllText('AGENTS.md', 'x')",
            "[System.IO.File]::Delete('AGENTS.md')",
            "if exist AGENTS.md del AGENTS.md",
            "for %f in (*.md) do del AGENTS.md",
        ],
    )
    def test_a_writer_none_of_the_forms_names_is_not_recognised(self, command: str) -> None:
        assert target(command) is None

    @pytest.mark.parametrize(
        "command",
        [
            "node - <<'JS'\nrequire('fs').writeFileSync('AGENTS.md', 'x')\nJS",
            "python3 -u - <<'PY'\nopen('AGENTS.md', 'w').write('x')\nPY",
            "ruby - <<'RB'\nFile.write('AGENTS.md', 'x')\nRB",
        ],
        ids=["node", "python-with-a-flag", "ruby"],
    )
    def test_the_program_an_interpreter_reads_from_a_heredoc_is_not_read(self, command: str) -> None:
        assert classify_command_risk(command) is not CommandRiskLevel.SAFE, "the line must reach the lexical reading"
        assert target(command) is None

    @pytest.mark.parametrize(
        "command",
        [
            "cp backdoor.md AGENT?.md",
            'cp backdoor.md "$INSTRUCTIONS"',
            "echo x > notes.md",
            "Set-Content $path x",
            "Set-Content AGENTS.md. x",
            "echo x > AGENTS~1.MD",
        ],
        ids=["glob", "variable", "symlink", "powershell-variable", "trailing-dot", "short-name"],
    )
    def test_a_file_reached_under_another_name_is_not_read(self, command: str) -> None:
        assert target(command) is None


class TestALongLineIsReadInLinearTime:
    @pytest.mark.parametrize(
        "command",
        [
            "rm x; echo '# AGENTS.md ' " + "cp mv rm tee " * 8000,
            "rm " * 30000 + "AGENTS.md.bak",
            "python " * 30000 + "write AGENTS.md.bak",
            ">" * 30000 + "AGENTS.md.bak",
            "sed -" + "i" * 24000 + "1 AGENTS.md.bak",
            "sed " * 30000 + "-i AGENTS.md.bak",
            "Set-Content " + "a," * 30000 + "AGENTS.md.bak",
            "Remove-Item " + "a\\" * 30000 + "AGENTS.md.bak",
            "del " * 30000 + "AGENTS.md.bak",
        ],
        ids=[
            "repeated-edit-commands",
            "repeated-rm",
            "repeated-interpreter",
            "repeated-redirects",
            "sed-flag-letters",
            "repeated-sed",
            "path-list",
            "backslash-segments",
            "repeated-del",
        ],
    )
    def test_a_line_that_repeats_the_keywords_is_read_within_a_second(self, command: str) -> None:
        assert classify_command_risk(command) is not CommandRiskLevel.SAFE, "the line must reach the lexical reading"
        started = time.perf_counter()

        assert target(command) is None
        assert time.perf_counter() - started < 1.0


class TestTheThreatAnalyzerReportsTheSameName:
    @pytest.mark.parametrize(
        ("command", "name"),
        [
            ("echo x > ./docs/SOUL.md", "SOUL.md"),
            ("cat notes | tee -a CLAUDE.md", "CLAUDE.md"),
            ("bash -c 'echo x >> AGENTS.md'", "AGENTS.md"),
            ("Set-Content -Path .\\docs\\SOUL.md -Value x", "SOUL.md"),
        ],
    )
    def test_the_escalation_carries_the_name_as_evidence(self, command: str, name: str) -> None:
        threats = [threat for threat in analyze_command(command) if threat.category == "protected_instruction_mutation"]

        assert threats
        assert {(threat.level, threat.evidence) for threat in threats} == {(ThreatLevel.ESCALATE, name)}

    def test_a_line_that_writes_nothing_protected_raises_no_such_escalation(self) -> None:
        threats = analyze_command("rm -rf build && cat AGENTS.md")

        assert all(threat.category != "protected_instruction_mutation" for threat in threats)
