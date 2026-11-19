"""Which protected instruction file a shell command line writes.

The names are the protected-path rules the file tools enforce, and a command line is read for the forms that write one.
Verifies:
1. Every rule the file tools enforce is recognised in every write form, under the rule's own spelling, whether the form
   is spelled for a POSIX shell, as a PowerShell cmdlet or cmd command, or with a Windows path.
2. A line is judged command by command: a read beside an unrelated write is not a write, and a write beside a read is.
3. A longer file name is another file (``AGENTS.md.bak``), as for the file tools.
4. A command the read-only classifier judges SAFE writes nothing, and no write form is one it judges SAFE.

The limits of the reading, its cost on a long line and the analyzer's report of the name are in
``test_protected_instruction_command_limits.py``.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.core.security.path.rules import PROTECTED_INSTRUCTION_PATTERNS, is_protected_instruction_file
from myrm_agent_harness.toolkits.code_execution.security.protected_instruction_command import (
    protected_instruction_mutation_target,
)
from myrm_agent_harness.toolkits.code_execution.security.risk_classifier import CommandRiskLevel, classify_command_risk

target = protected_instruction_mutation_target


def example_path(rule: str) -> str:
    """A path *rule* protects: the file a name rule spells, a file inside the directory a directory rule spells."""
    path = rule.removeprefix("**/").replace("/**", "/example.md")
    assert is_protected_instruction_file(path), path
    return path


def windows_spelling(path: str) -> str:
    """*path* as a Windows shell spells it: backslashes between the segments."""
    return path.replace("/", "\\")


def assert_names_a_protected_file(name: str | None, path: str) -> None:
    """*name* is the rule spelling of the protected file *path* belongs to."""
    assert name is not None
    assert is_protected_instruction_file(name)
    assert name.lower() in path.lower()


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
    "echo x >& {path}",
    'echo x > "my docs/{path}"',
    "echo x >> 'my docs/{path}'",
    "echo x > my\\ docs/{path}",
    "sed -E -i '' 's/a/b/' {path}",
    "sed -n -i 's/a/b/' {path}",
    "sed -e 's/a/b/' -i {path}",
    "sed --in-place 's/a/b/' {path}",
    "sed 's/a/b/' {path} -i",
    "(cd repo && cp backdoor.md {path})",
    "(cd repo && mv draft.md {path})",
    "(cd repo && tee {path})",
    "echo $(cp backdoor.md {path})",
    "echo `rm {path}`",
    "out=$(rm -f {path})",
)

# The same operations as PowerShell cmdlets and cmd commands.
WINDOWS_WRITE_FORMS = (
    "Set-Content -Path {path} -Value x",
    "Add-Content {path} x",
    "'x' | Out-File {path}",
    "Clear-Content {path}",
    "Remove-Item {path}",
    "Copy-Item backdoor.md {path}",
    "Move-Item draft.md {path}",
    "Rename-Item draft.md {path}",
    "New-Item {path}",
    "Set-Content -Path (Join-Path repo '{path}') -Value x",
    "Set-Content -Path old.md,{path} -Value x",
    "Remove-Item {path},old.md",
    "cd repo; del {path}",
    "del {path}",
    "erase {path}",
    "copy backdoor.md {path}",
    "move draft.md {path}",
    "ren draft.md {path}",
    "rename draft.md {path}",
    "(cd repo && copy backdoor.md {path})",
    "cmd /c del {path}",
    'cmd.exe /d /c "copy backdoor.md {path}"',
    'powershell -NoProfile -Command "del {path}"',
    'powershell -NoProfile -ExecutionPolicy Bypass -Command "del {path}"',
    'pwsh -c "Set-Content {path} x"',
    'cmd /c "cd repo && del {path}"',
    'powershell -c "cd repo; copy backdoor.md {path}"',
    "if (Test-Path {path}) {{ del {path} }}",
    "(del {path})",
)

# Forms whose path is spelled with backslashes: relative, drive-qualified, quoted.
WINDOWS_PATH_FORMS = (
    "echo x > .\\{path}",
    "echo x >> C:\\work\\{path}",
    'echo x > "C:\\work\\{path}"',
    'echo x > "C:\\Users\\John Smith\\{path}"',
    "cp backdoor.md .\\{path}",
    "rm -f C:\\work\\{path}",
    "tee C:\\work\\{path}",
    "Set-Content -Path .\\{path} -Value x",
    "Copy-Item backdoor.md 'C:\\work\\{path}'",
    "Remove-Item C:\\work\\{path}",
    "del C:\\work\\{path}",
)

ALL_WRITE_FORMS = WRITE_FORMS + WINDOWS_WRITE_FORMS + WINDOWS_PATH_FORMS


class TestEveryProtectedRuleIsRecognised:
    @pytest.mark.parametrize("form", WRITE_FORMS)
    @pytest.mark.parametrize("path", PATHS)
    def test_a_write_form_naming_the_path_is_a_write_to_a_protected_name(self, path: str, form: str) -> None:
        assert_names_a_protected_file(target(form.format(path=path)), path)

    @pytest.mark.parametrize("form", WINDOWS_WRITE_FORMS)
    @pytest.mark.parametrize("path", PATHS)
    def test_a_powershell_or_cmd_write_is_a_write_whichever_way_its_path_is_spelled(self, path: str, form: str) -> None:
        for spelled in (path, windows_spelling(path)):
            assert_names_a_protected_file(target(form.format(path=spelled)), path)

    @pytest.mark.parametrize("form", WINDOWS_PATH_FORMS)
    @pytest.mark.parametrize("path", PATHS)
    def test_backslashes_separate_path_segments_as_they_do_for_the_file_tools(self, path: str, form: str) -> None:
        assert_names_a_protected_file(target(form.format(path=windows_spelling(path))), path)

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
            'echo x > "my docs/AGENTS.md.bak"',
            'echo x > "my docs/" AGENTS.md',
            "echo x > out.txt AGENTS.md",
        ],
    )
    def test_a_longer_name_or_a_neighbouring_path_is_another_file(self, command: str) -> None:
        assert target(command) is None

    def test_a_backslash_that_escapes_a_space_keeps_the_name_part_of_a_longer_file(self) -> None:
        assert target("cp backdoor.md AGENTS.md\\ copy") is None


class TestACommandThatOnlyReadsIsNotAWrite:
    @pytest.mark.parametrize(
        "command",
        [
            "grep -n rm AGENTS.md",
            "grep -c tee SOUL.md",
            "grep -rn 'sed -i' AGENTS.md",
            'grep -n "cp " .cursor/rules/example.md',
            "rg tee CLAUDE.md",
            "rg -n 'cp|mv|rm' AGENTS.md",
            "rg --files-with-matches truncate MEMORY.md",
            "git grep -n 'rm ' -- AGENTS.md",
            "cd repo && grep -n mv AGENTS.md",
        ],
    )
    def test_a_search_whose_argument_spells_an_edit_command_writes_nothing(self, command: str) -> None:
        assert classify_command_risk(command) is CommandRiskLevel.SAFE
        assert target(command) is None

    @pytest.mark.parametrize(
        "command",
        [
            "Get-Content AGENTS.md",
            "Get-Content .\\AGENTS.md -Tail 20",
            "Get-Item .\\CLAUDE.md",
            "Test-Path .cursor\\rules",
            "Select-String -Path AGENTS.md -Pattern rm",
            "Get-Content AGENTS.md | Select-String move",
            "type AGENTS.md",
            "dir AGENTS.md",
            "findstr copy AGENTS.md",
        ],
    )
    def test_a_windows_read_writes_nothing(self, command: str) -> None:
        assert target(command) is None

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -m 'move AGENTS.md notes'",
            "npm run copy -- AGENTS.md",
            "cargo run -- erase AGENTS.md",
            "python tidy.py --rename AGENTS.md",
            "cmd /c echo copy AGENTS.md",
            "pwsh -File copy.ps1 AGENTS.md",
            "powershell -ExecutionPolicy Bypass -File copy.ps1 AGENTS.md",
            "copy-docs.sh AGENTS.md",
        ],
    )
    def test_a_cmd_alias_is_the_command_itself_not_a_word_among_the_arguments(self, command: str) -> None:
        assert target(command) is None

    @pytest.mark.parametrize(
        ("command", "name"),
        [
            ("grep -n rm AGENTS.md && rm AGENTS.md", "AGENTS.md"),
            ("rg tee CLAUDE.md; tee CLAUDE.md", "CLAUDE.md"),
            ("grep -n rm SOUL.md && sed -i 's/a/b/' SOUL.md", "SOUL.md"),
        ],
    )
    def test_the_same_words_in_a_command_that_writes_are_a_write(self, command: str, name: str) -> None:
        assert target(command) == name


class TestNoWriteFormIsOneTheReadOnlyClassifierApproves:
    """The reading asks the classifier first, so a write form it called SAFE would pass the floor unseen."""

    @pytest.mark.parametrize("form", ALL_WRITE_FORMS)
    def test_a_write_form_is_never_judged_safe(self, form: str) -> None:
        for path in PATHS:
            for spelled in (path, windows_spelling(path)):
                command = form.format(path=spelled)
                assert classify_command_risk(command) is not CommandRiskLevel.SAFE, command
