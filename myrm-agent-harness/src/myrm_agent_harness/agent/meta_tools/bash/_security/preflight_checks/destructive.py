"""拦截破坏性命令（重置、递归删除、清理等）。

[POS]
bash 预检子包的一部分；由 __init__.py 聚合导出。
"""

from __future__ import annotations

import logging
import re

from myrm_agent_harness.agent.meta_tools.bash._security.shell_parse import extract_shell_c_payload
from myrm_agent_harness.core.security.redact import command_preview

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Destructive Command Preflight
# ---------------------------------------------------------------------------

_DESTRUCTIVE_COMMAND_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\bgit\s+reset\s+--(?:hard|merge)\b", re.IGNORECASE),
        "git reset --hard / --merge",
    ),
    (
        re.compile(
            r"\bgit\s+checkout\s+(?:-[a-zA-Z]+\s+|--force\s+)*(?:--\s+)?\.(?:[\s;&|]|$)",
            re.IGNORECASE,
        ),
        "git checkout .",
    ),
    (
        re.compile(
            r"\bgit\s+restore\s+(?:[^\n;&|]*\s+)?(?:\.|\*)(?:[\s;&|]|$)",
            re.IGNORECASE,
        ),
        "git restore . / *",
    ),
    (
        re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*[fdx]", re.IGNORECASE),
        "git clean -fd / -xdf",
    ),
    (
        re.compile(
            r"\brm\s+-[a-zA-Z]*[rf][a-zA-Z]*\s+(?:\*|\.|\/|\.\/)(?:[\s;&|]|$)",
            re.IGNORECASE,
        ),
        "rm -rf * / . / /",
    ),
)


def _strip_quotes_for_destructive_check(text: str) -> str:
    """Strip quoted literals so harmless mentions in echo/grep pass without false alarms."""
    cleaned = re.sub(r"\\.", " ", text)
    cleaned = re.sub(r"'[^']*'", "''", cleaned)
    cleaned = re.sub(r'"[^"]*"', '""', cleaned)
    return cleaned


def _detect_destructive_tokens(segment: str) -> str | None:
    """Token-based semantic detection to catch flag permutations and argument displacement."""
    tokens = segment.strip().split()
    if not tokens:
        return None

    # Git command inspection
    if "git" in tokens:
        git_idx = tokens.index("git")
        args = tokens[git_idx + 1 :]
        if args:
            subcmd_idx = 0
            while subcmd_idx < len(args) and args[subcmd_idx].startswith("-"):
                if args[subcmd_idx] in ("-C", "-c", "--git-dir", "--work-tree") and subcmd_idx + 1 < len(args):
                    subcmd_idx += 2
                else:
                    subcmd_idx += 1

            if subcmd_idx < len(args):
                subcmd = args[subcmd_idx]
                sub_args = args[subcmd_idx + 1 :]

                if subcmd == "reset":
                    for arg in sub_args:
                        if arg in ("--hard", "--merge"):
                            return f"git reset {arg}"

                elif subcmd == "checkout":
                    target_tokens = set(sub_args)
                    if "." in target_tokens and "-b" not in sub_args and "-B" not in sub_args:
                        return "git checkout ."

                elif subcmd == "restore":
                    target_tokens = set(sub_args)
                    if "." in target_tokens or "*" in target_tokens:
                        return "git restore ."

                elif subcmd == "clean":
                    flags: set[str] = set()
                    for arg in sub_args:
                        if arg.startswith("-") and not arg.startswith("--"):
                            flags.update(arg[1:])
                        elif arg in ("--force", "-f"):
                            flags.add("f")
                    if "f" in flags and ("d" in flags or "x" in flags):
                        return "git clean -fd"

    # rm command inspection
    if "rm" in tokens:
        rm_idx = tokens.index("rm")
        if (
            rm_idx == 0
            or tokens[rm_idx - 1] in ("sudo", "env", "xargs", "do", "then")
            or any(t == "xargs" for t in tokens[:rm_idx])
        ):
            rm_args = tokens[rm_idx + 1 :]
            rm_flags: set[str] = set()
            targets: list[str] = []
            for arg in rm_args:
                if arg == "--":
                    continue
                if arg.startswith("-") and not arg.startswith("--"):
                    rm_flags.update(arg[1:])
                elif arg in ("--recursive", "-r", "-R"):
                    rm_flags.add("r")
                elif arg in ("--force", "-f"):
                    rm_flags.add("f")
                else:
                    targets.append(arg)

            if "r" in rm_flags and "f" in rm_flags:
                for t in targets:
                    if t in ("*", ".", "/", "./", "./*", ".*"):
                        return f"rm -rf {t}"

    return None


def evaluate_high_impact_command(command: str) -> tuple[bool, str | None, str]:
    """Evaluate whether a shell command constitutes a high-impact irreversible workspace operation.

    Returns:
        tuple of (is_high_impact, pattern_label, risk_category)
    """
    candidates = [command]
    if payload := extract_shell_c_payload(command):
        candidates.append(payload)

    for candidate in candidates:
        sanitized = _strip_quotes_for_destructive_check(candidate)

        # 1. Fast regex scan
        for pattern, pattern_label in _DESTRUCTIVE_COMMAND_PATTERNS:
            if pattern.search(sanitized):
                category = "WORKSPACE_PURGE" if "rm -rf" in pattern_label else "UNCOMMITTED_RESET"
                return True, pattern_label, category

        # 2. Token-based semantic scan for displaced flags and permutations
        segments = re.split(r"[;&|\n]+", sanitized)
        for segment in segments:
            if detected := _detect_destructive_tokens(segment):
                category = "WORKSPACE_PURGE" if "rm -rf" in detected else "UNCOMMITTED_RESET"
                return True, detected, category

    return False, None, "SAFE"


def check_destructive_commands(command: str) -> None:
    """Block destructive commands that irreversibly wipe workspace state.

    Raises:
        ToolError: If destructive workspace command is detected.
    """
    from myrm_agent_harness.utils.errors import ToolError

    is_high_impact, detected_label, category = evaluate_high_impact_command(command)
    if is_high_impact and detected_label:
        logger.warning(
            "Destructive workspace command blocked (%s): %s in %s",
            category,
            detected_label,
            command_preview(command, 100),
        )
        raise ToolError(
            f"Command blocked (destructive workspace command): Detected '{detected_label}' in command '{command.strip()}'. "
            "Destructive commands that permanently discard uncommitted changes or wipe workspace files are prohibited. "
            "If the user explicitly requested resetting the workspace, please ask the user for confirmation.",
            user_hint=(
                f"Destructive command '{detected_label}' is prohibited to protect uncommitted changes. "
                "Inspect errors and resolve issues without wiping the workspace. "
                "If you need to discard changes in a specific file, use git checkout -- <file> or target the specific file."
            ),
            diagnostic_info={
                "destructive_command_prohibited": True,
                "command_label": detected_label,
                "risk_category": category,
            },
        )
