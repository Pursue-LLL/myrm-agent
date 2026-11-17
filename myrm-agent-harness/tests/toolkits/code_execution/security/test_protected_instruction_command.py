"""Which protected instruction file a shell command line writes.

The shell tools and the file tools protect the same files: the names are the protected-path rules, and a command line
is read for the forms that write one. Verifies:
1. Every rule the file tools enforce is recognised in every write form, under the rule's own spelling.
2. A line is judged command by command: a read beside an unrelated write is not a write, and a write beside a read is.
3. A longer file name is another file (``AGENTS.md.bak``), as for the file tools.
4. The limits of a lexical reading hold as documented.
5. A long line that repeats the keywords is read in linear time.
6. The threat analyzer reports the same name as the evidence of its escalation.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.core.security.path.rules import PROTECTED_INSTRUCTION_PATTERNS, is_protected_instruction_file
from myrm_agent_harness.toolkits.code_execution.security.protected_instruction_command import (
    protected_instruction_mutation_target,
)
from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import ThreatLevel, analyze_command

target = protected_instruction_mutation_target


def example_path(rule: str) -> str:
    """A path *rule* protects: the file a name rule spells, a file inside the directory a directory rule spells."""
    path = rule.removeprefix("**/").replace("/**", "/example.md")
    assert is_protected_instruction_file(path), path
    return path


PATHS = sorted({example_path(rule) for rule in PROTECTED_INSTRUCTION_PATTERNS})
# One command line per write form, with the path it writes left open.
WRITE_FORMS = (
    "echo x > {path}",
    "echo x >> {path}",
    "echo x >{path}",
    "echo x 2> {path}",
    "echo x > ./sub/dir/{path}",
    "echo x > '{path}'",
    'echo x > "{path}"',
    "cd repo && echo x > {path}",
    "cat notes | tee {path}",
    "tee -a {path}",
    "cp backdoor.md {path}",
    "mv draft.md {path}",
    "rm -f {path}",
    "truncate -s 0 {path}",
    "sed -i 's/a/b/' {path}",
    "sed -i.bak 's/a/b/' {path}",
    "node -e \"require('fs').writeFileSync('{path}', 'x')\"",
    "ruby -e \"File.write('{path}', 'x')\"",
)


class TestEveryProtectedRuleIsRecognised:
    @pytest.mark.parametrize("form", WRITE_FORMS)
    @pytest.mark.parametrize("path", PATHS)
    def test_a_write_form_naming_the_path_is_a_write_to_a_protected_name(self, path: str, form: str) -> None:
        name = target(form.format(path=path))

        assert name is not None
        assert is_protected_instruction_file(name)
        assert name.lower() in path.lower()

    @pytest.mark.parametrize(
        ("command", "name"),
        [
            ("echo x > ./docs/SOUL.md", "SOUL.md"),
            ("echo x >> agents.md", "agents.md"),
            ("echo x > /abs/path/MEMORY.md", "MEMORY.md"),
            ("echo x > docs/.cursor/rules/a.md", ".cursor/rules"),
            ("rm -rf .cursor/rules", ".cursor/rules"),
            ("echo x > .claude/CLAUDE.md", ".claude/CLAUDE.md"),
            ("cp a .github/copilot-instructions.md", ".github/copilot-instructions.md"),
        ],
    )
    def test_the_name_is_the_rule_spelling_whatever_surrounds_it(self, command: str, name: str) -> None:
        assert target(command) == name


class TestALineIsReadCommandByCommand:
    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf build && cat AGENTS.md",
            "cp a.txt b.txt && head SOUL.md",
            "mv old.log new.log | grep AGENTS.md",
            "ls docs; cat AGENTS.md",
            "cat AGENTS.md > out.txt",
            "cat AGENTS.md | tee out.txt",
            "grep -n rule .cursorrules > found.txt",
            "rm a.txt || echo AGENTS.md",
            "cat AGENTS.md\nrm build.log",
        ],
    )
    def test_a_read_beside_an_unrelated_write_is_not_a_write(self, command: str) -> None:
        assert target(command) is None

    @pytest.mark.parametrize(
        ("command", "name"),
        [
            ("echo ok && sed -i 's/a/b/' AGENTS.md", "AGENTS.md"),
            ("ls; echo x > SOUL.md", "SOUL.md"),
            ("cat notes | tee MEMORY.md", "MEMORY.md"),
            ("rm build.log\nsed -i 's/a/b/' SOUL.md", "SOUL.md"),
            ("(echo x > AGENTS.md)", "AGENTS.md"),
            ("cat <<'EOF' > AGENTS.md\nhello\nEOF", "AGENTS.md"),
        ],
    )
    def test_a_write_beside_a_read_is_a_write(self, command: str, name: str) -> None:
        assert target(command) == name

    def test_a_command_continued_onto_the_next_line_is_one_command(self) -> None:
        assert target("cp backdoor.md \\\n  AGENTS.md") == "AGENTS.md"

    @pytest.mark.parametrize(
        "command", ["", "   ", "ls", "cat AGENTS.md", "head -n 20 SOUL.md", "git diff -- AGENTS.md"]
    )
    def test_a_line_that_writes_nothing_protected_is_not_a_write(self, command: str) -> None:
        assert target(command) is None


class TestAnotherFileIsNotProtected:
    @pytest.mark.parametrize(
        "command",
        [
            "echo x > AGENTS.md.bak",
            "echo x > .cursorrules.bak",
            "echo x > MEMORY.md~",
            "echo x > myagents.md",
            "cp a AGENTS.md.bak",
            "rm src/cursor_rules.py",
            "rm -rf .github/workflows",
            "echo x > .cursor/other.md",
            "ls .cursor",
            "cat .claude/notes.md",
        ],
    )
    def test_a_longer_name_or_a_neighbouring_path_is_another_file(self, command: str) -> None:
        assert target(command) is None


class TestTheReadingIsLexical:
    def test_a_copy_source_is_not_told_apart_from_its_target(self) -> None:
        assert target("cp AGENTS.md /tmp/backup.md") == "AGENTS.md"

    @pytest.mark.parametrize("command", ['echo "a > AGENTS.md"', 'git commit -m "rm AGENTS.md from docs"'])
    def test_the_text_of_a_quoted_argument_is_read_like_the_command_around_it(self, command: str) -> None:
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
        ],
    )
    def test_a_writer_none_of_the_forms_names_is_not_recognised(self, command: str) -> None:
        assert target(command) is None


class TestALongLineIsReadInLinearTime:
    @pytest.mark.parametrize(
        "command",
        [
            "echo '# AGENTS.md ' " + "cp mv rm tee " * 8000,
            "rm " * 30000 + "AGENTS.md.bak",
            "python " * 30000 + "write AGENTS.md.bak",
            ">" * 30000 + "AGENTS.md.bak",
        ],
        ids=["repeated-edit-commands", "repeated-rm", "repeated-interpreter", "repeated-redirects"],
    )
    def test_a_line_that_repeats_the_keywords_is_read_within_a_second(self, command: str) -> None:
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
        ],
    )
    def test_the_escalation_carries_the_name_as_evidence(self, command: str, name: str) -> None:
        threats = [threat for threat in analyze_command(command) if threat.category == "protected_instruction_mutation"]

        assert threats
        assert {(threat.level, threat.evidence) for threat in threats} == {(ThreatLevel.ESCALATE, name)}

    def test_a_line_that_writes_nothing_protected_raises_no_such_escalation(self) -> None:
        threats = analyze_command("rm -rf build && cat AGENTS.md")

        assert all(threat.category != "protected_instruction_mutation" for threat in threats)
