"""Command rewriting service.

Transforms commands for code execution (workspace path rewriting).

[INPUT]
- core.security.shell_command_lexer::iter_syntax_chars (POS: the one reading of a shell command line)

[OUTPUT]
- CommandRewriter: Stateless command rewriter; the workspace root it puts into a POSIX shell command is quoted
  where the shell reads it as plain text and the root needs it.

[POS]
Command rewriting service.
"""

import logging
import re
from collections.abc import Callable
from pathlib import Path

from myrm_agent_harness.core.security.shell_command_lexer import iter_syntax_chars

logger = logging.getLogger(__name__)

# The container-convention root /workspace, where a shell takes it as a path of its own. Nothing path-like may
# precede it: a word character, ``.``, ``~``, ``)``, ``}`` or ``]`` makes it the tail of ``/home/me/workspace``,
# ``./workspace``, ``~/workspace`` or ``$(pwd)/workspace``, and NUL ends a protected real workspace path. The glued
# value of a one-letter option (``-I/workspace/include``) is the exception. Nothing name-like may follow it
# (``/workspace2`` is another directory). A colon may stand on either side, so that every entry of
# ``PYTHONPATH=/workspace/a:/workspace/b`` is rewritten.
_WORKSPACE_ROOT = re.compile(r"""(?:(?<![\w.~)}\]\x00])|(?<=\s-[A-Za-z]))/workspace(?=/|$|[\s'";&|)`:])""")

# A root of only letters, digits and these characters is one literal word to a POSIX shell, in a brace list too:
# quoting it changes nothing. The comma is left out: it splits ``{/workspace/a,/workspace/b}`` at the root's own comma.
_INERT_PUNCTUATION = frozenset("_./@%+=:-")
# The body of a heredoc is text the shell never splits into words, while the command line before it is. One quoting
# rule cannot serve both, and a lexical scan does not know where the body starts.
_HEREDOC = re.compile(r"(?<!<)<<(?!<)")


def _is_inert(root: str) -> bool:
    return all(char.isalnum() or char in _INERT_PUNCTUATION for char in root)


def _single_quote(text: str) -> str:
    """``text`` as one single-quoted word, also where ``shlex.quote`` would leave it bare (a comma)."""
    return "'" + text.replace("'", "'\"'\"'") + "'"


def _replacement(protected: str, root: str, *, posix_shell: bool) -> Callable[[re.Match[str]], str]:
    """Return what each ``/workspace`` match in ``protected`` becomes.

    The root as it is, except where a POSIX shell reads the match as plain text and the root needs quoting: there it
    is quoted, so it stays one word and its characters never run as shell code.
    """
    if not posix_shell or _is_inert(root) or _HEREDOC.search(protected):
        return lambda _match: root
    plain_text = {index for index, _ in iter_syntax_chars(protected)}
    quoted = _single_quote(root)
    return lambda match: quoted if match.start() in plain_text else root


class CommandRewriter:
    """Stateless command rewriter.

    Resolves /workspace paths to actual working directories.
    """

    def rewrite_workspace_paths(self, command: str, workspace_path: Path | None, *, posix_shell: bool) -> str:
        """Rewrite /workspace paths in commands to the actual working directory.

        AI agents may use the container-convention path /workspace.
        This method resolves those to the actual workspace path.

        Handled patterns: ``cd /workspace``, ``/workspace/file.txt``, ``-I/workspace/include``, etc.
        Only a /workspace that stands as a path of its own is replaced; a directory merely called workspace
        (``~/workspace``, ``./workspace``, ``/home/me/workspace``) stays as typed.

        The match is lexical: nothing is expanded the way the shell would. A /workspace behind a glob
        (``*/workspace``), a backtick substitution or a quoted variable (``"$HOME"/workspace``), and the container
        side of a mapping (``-v $(pwd):/workspace``, ``scp host:/workspace/x``), are taken for the root. One
        followed by a wildcard, a comma or a brace (``/workspace*``, ``/workspace,/tmp``, ``{/tmp,/workspace}``)
        stays as typed.

        The path is spliced into the shell's text, so ``posix_shell`` (a bash or sh reads the command) decides how.
        A root with a space, comma, parenthesis, ``&``, ``;``, ``$`` or apostrophe is quoted wherever the shell reads
        the match as plain text: the folder stays one word, in a brace list too, and its name never runs as code. The
        root goes in as typed where quotes already enclose the match (a root that holds that quote character, ``$``,
        a backtick or a backslash still breaks out there), in a command with a heredoc operator, and for any other
        shell (PowerShell and cmd have quoting rules of their own, which are not applied). A match inside the quotes
        of ``bash -c '...'`` or ``eval "..."`` is one of those: the inner shell reads the typed root as plain text
        again, so a root with a space splits there.

        The resolved workspace path itself is protected before rewriting, so a
        command that already contains the real workspace (e.g. eval graders
        addressing ``{workspace}`` where the cache layout ends in ``/workspace``)
        is never re-expanded into a duplicated path.
        """
        if not workspace_path:
            return command

        workspace_str = str(workspace_path)

        placeholders: list[str] = []

        def _protect(match: re.Match[str]) -> str:
            token = f"\x00wbws{len(placeholders)}\x00"
            placeholders.append(match.group(0))
            return token

        protected = re.sub(re.escape(workspace_str), _protect, command)

        new_command, rewritten = _WORKSPACE_ROOT.subn(
            _replacement(protected, workspace_str, posix_shell=posix_shell), protected
        )

        for index, real in enumerate(placeholders):
            new_command = new_command.replace(f"\x00wbws{index}\x00", real)

        if rewritten:
            logger.warning(" [CommandRewriter] Rewrote /workspace paths (%d)", rewritten)

        return new_command
