"""Command rewriting service.

Transforms commands for code execution (workspace path rewriting).

[INPUT]
- core.security.redact::command_preview (POS: masked, cut command for a log line)

[OUTPUT]
- CommandRewriter: Stateless command rewriter.

[POS]
Command rewriting service.
"""

import logging
import re
from pathlib import Path

from myrm_agent_harness.core.security.redact import command_preview

logger = logging.getLogger(__name__)

# The container-convention root /workspace, where a shell takes it as a path of its own. Nothing path-like may
# precede it: a word character, ``.``, ``~``, ``)``, ``}`` or ``]`` makes it the tail of ``/home/me/workspace``,
# ``./workspace``, ``~/workspace`` or ``$(pwd)/workspace``, and NUL ends a protected real workspace path. The glued
# value of a one-letter option (``-I/workspace/include``) is the exception. Nothing name-like may follow it
# (``/workspace2`` is another directory). A colon may stand on either side, so that every entry of
# ``PYTHONPATH=/workspace/a:/workspace/b`` is rewritten.
_WORKSPACE_ROOT = re.compile(r"""(?:(?<![\w.~)}\]\x00])|(?<=\s-[A-Za-z]))/workspace(?=/|$|[\s'";&|)`:])""")


class CommandRewriter:
    """Stateless command rewriter.

    Resolves /workspace paths to actual working directories.
    """

    def rewrite_workspace_paths(self, command: str, workspace_path: Path | None) -> str:
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

        new_command = _WORKSPACE_ROOT.sub(workspace_str.replace("\\", "\\\\"), protected)

        for index, real in enumerate(placeholders):
            new_command = new_command.replace(f"\x00wbws{index}\x00", real)

        if new_command != command:
            logger.warning(f" [CommandRewriter] Rewrote /workspace paths: {command_preview(new_command, 100)}")

        return new_command
