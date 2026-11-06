"""识别会等待交互输入的命令。

[POS]
bash 预检子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interactive Command Preflight
# ---------------------------------------------------------------------------

_SCAFFOLD_MARKERS: tuple[str, ...] = (
    "create-next-app",
    "npm create ",
    "npm init",
    "pnpm create ",
    "pnpm init",
    "yarn create ",
    "yarn init",
    "bun create ",
    "bunx create-",
    "npx create-",
)

_SCAFFOLD_NON_INTERACTIVE_RE = re.compile(
    r"(?:--yes\b|(?:^|\s)-y(?:\s|$)|--skip-install\b|--defaults\b|--non-interactive\b|--ci\b)",
    re.IGNORECASE,
)

_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit\b")
_GIT_COMMIT_MSG_RE = re.compile(r"(?:\s-[a-zA-Z]*m[\s\"']|\s--message[\s=]|\s-F\s|\s--file[\s=])")
_GIT_INTERACTIVE_RE = re.compile(r"\bgit\s+(?:rebase\s+(?:-i|--interactive)|add\s+(?:-i|-p|--interactive|--patch))\b")
_POETRY_INIT_RE = re.compile(r"\bpoetry\s+init\b")


def check_interactive_command(command: str) -> str | None:
    """Detect commands that require interactive stdin and would hang.

    Returns an error message if interactive, None if safe.
    """
    lowered = command.lower()

    if any(marker in lowered for marker in _SCAFFOLD_MARKERS) and not _SCAFFOLD_NON_INTERACTIVE_RE.search(lowered):
        return (
            "This command requires interactive input (template/option selection). "
            "The bash tool cannot answer prompts. "
            "Use non-interactive flags: --yes, -y, --defaults, or specify all options inline."
        )

    if _GIT_COMMIT_RE.search(lowered) and not _GIT_COMMIT_MSG_RE.search(command):
        return (
            'git commit without -m/--message opens an editor for interactive input. Use: git commit -m "your message"'
        )

    if _GIT_INTERACTIVE_RE.search(lowered):
        return (
            "This git command opens an interactive editor/UI. The bash tool cannot handle interactive git operations."
        )

    if _POETRY_INIT_RE.search(lowered) and "--no-interaction" not in lowered:
        return "poetry init requires interactive input. Use: poetry init --no-interaction"

    return None
