"""[INPUT]
- myrm_agent_harness.api.security::hardened_git_argv (POS: hardened git argument builder)
- ..context::MentionContext (POS: per-turn accumulation state)
- ..xml (POS: XML fragment and inline budget primitives)

[OUTPUT]
- git_staged_part / git_diff_part: @staged and @diff handlers

[POS]
Git-backed @ references. Both handlers read a diff and emit either the diff or an honest
"nothing staged/unstaged" marker; the byte ceiling stays identical to the other handlers.
"""

from __future__ import annotations

import logging
import subprocess

from myrm_agent_harness.api.security import hardened_git_argv

from ...models import MentionReferenceRequest
from ..context import MentionContext
from ..xml import _MENTION_MAX_TOTAL_BYTES, _format_size, _xml_metadata, _xml_part

logger = logging.getLogger(__name__)


def _get_git_staged_diff(workspace_dir: str) -> str:
    """Get git staged diff (git diff --cached) for current workspace.

    Returns empty string if not a git repo, or if no staged changes, or on error.
    """
    try:
        result = subprocess.run(
            hardened_git_argv(("diff", "--cached"), repo_dir=workspace_dir),
            cwd=workspace_dir,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        logger.debug("git diff --cached returned %d: %s", result.returncode, result.stderr)
    except subprocess.TimeoutExpired:
        logger.warning("git diff --cached timeout (30s) in %s", workspace_dir)
    except FileNotFoundError:
        logger.debug("git command not found")
    except Exception as e:
        logger.debug("Failed to get git staged diff: %s", e)
    return ""


async def git_staged_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    diff_content = _get_git_staged_diff(ctx.workspace_real)
    if diff_content:
        diff_bytes = len(diff_content.encode("utf-8"))
        if ctx.total_bytes + diff_bytes <= _MENTION_MAX_TOTAL_BYTES:
            ctx.parts.append(_xml_part("@staged", "git-diff", diff_content))
            ctx.total_bytes += diff_bytes
        else:
            ctx.parts.append(
                _xml_metadata(
                    "@staged",
                    "git-diff",
                    f"Diff too large ({_format_size(diff_bytes)})",
                )
            )
    else:
        ctx.parts.append('<mentioned_file path="@staged" type="git-diff">No staged changes</mentioned_file>')


async def git_diff_part(ref: MentionReferenceRequest, ctx: MentionContext) -> None:
    try:
        result = subprocess.run(
            hardened_git_argv(("diff",), repo_dir=ctx.workspace_real),
            cwd=ctx.workspace_real,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            diff_content = result.stdout.strip()
            diff_bytes = len(diff_content.encode("utf-8"))
            if ctx.total_bytes + diff_bytes <= _MENTION_MAX_TOTAL_BYTES:
                ctx.parts.append(_xml_part("@diff", "git-diff", diff_content))
                ctx.total_bytes += diff_bytes
            else:
                ctx.parts.append(
                    _xml_metadata(
                        "@diff",
                        "git-diff",
                        f"Diff too large ({_format_size(diff_bytes)})",
                    )
                )
        else:
            ctx.parts.append('<mentioned_file path="@diff" type="git-diff">No unstaged changes</mentioned_file>')
    except Exception as e:
        logger.debug("Failed to get git diff: %s", e)
        ctx.parts.append('<mentioned_file path="@diff" error="git diff failed"/>')
