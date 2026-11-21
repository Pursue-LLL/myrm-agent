"""Spend governance and action-digest primitives for Agent Commerce.

[INPUT]
- hashlib, hmac, json: Standard cryptographic and serialization libraries
- core.security.shell_command_lexer::read_commands (POS: Shared lexical layer of the shell command security checks)

[OUTPUT]
- parse_spend_amount: Extract normalized amount and currency from tool arguments
- is_financial_or_spend_tool: Detect if tool invocation represents a financial transaction
- is_shell_execution_tool: Determine whether a tool call represents a shell or bash execution primitive
- is_irreversible_social_action: Detect if action is socially irreversible (git push, package publish, external notify)
- compute_action_digest: Cryptographic HMAC-SHA256 digest of tool + args + amount
- verify_action_digest: Timing-attack safe verification of action digest
- DEFAULT_SPEND_SALT: Default HMAC salt of the action digest
- SpendPolicy: Data model for per-action and session spending caps
- compute_script_content_hash: SHA-256 of a script file on disk
- extract_script_file_target: Find the script file a tool call would execute
- verify_script_file_integrity: Detect a script that changed after approval (TOCTOU)

[POS]
Foundational Agent Commerce governance module in core/security/.
Zero-overhead, pure deterministic algorithms ensuring YOLO-proof financial safety.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from myrm_agent_harness.core.security.shell_command_lexer import read_commands

logger = logging.getLogger(__name__)

DEFAULT_SPEND_SALT = "myrm-agent-spend-hmac-salt"

_SPEND_TOOL_KEYWORDS = frozenset(
    {
        "charge",
        "payment",
        "payout",
        "transfer",
        "purchase",
        "buy",
        "checkout",
        "stripe",
        "alipay",
        "wechat_pay",
        "paypal",
        "billing",
        "withdraw",
    }
)


_IRREVERSIBLE_SOCIAL_TOOLS = frozenset(
    {
        "channel_notify",
        "channel_notify_tool",
        "artifact_publish",
    }
)

_SHELL_TOOL_NAMES = frozenset(
    {
        "shell_exec",
        "bash",
        "terminal",
        "code_interpreter",
        "bash_code_execute_tool",
    }
)


# Program -> the sub-command words that push or publish work to a shared place and cannot be taken back.
_IRREVERSIBLE_SUBCOMMANDS: Final[dict[str, frozenset[str]]] = {
    "git": frozenset({"push"}),
    "npm": frozenset({"publish"}),
    "pnpm": frozenset({"publish"}),
    "yarn": frozenset({"publish"}),
    "twine": frozenset({"upload"}),
    "docker": frozenset({"push"}),
    "podman": frozenset({"push"}),
}
# ``gh release create`` and ``gh pr merge``: an object word, then an action word.
_GH_OBJECTS: Final = frozenset({"release", "pr"})
_GH_ACTIONS: Final = frozenset({"create", "merge"})
# How many words after the program a sub-command is looked for: options may sit between them (``git -C dir push``).
_SUBCOMMAND_WINDOW: Final = 7


def is_shell_execution_tool(tool_name: str, permission_type: str | None = None) -> bool:
    """Determine whether a tool call represents a shell or bash execution primitive."""
    if permission_type in ("shell_exec", "code_interpreter"):
        return True
    lower_name = tool_name.lower().strip()
    return (
        lower_name in _SHELL_TOOL_NAMES
        or "bash" in lower_name
        or "shell" in lower_name
        or lower_name.startswith("terminal")
    )


def _runs_irreversible_command(command_words: Sequence[str]) -> bool:
    """Whether one command names an irreversible program and sub-command, with options allowed in between."""
    words = [word.lower() for word in command_words]
    for index, word in enumerate(words):
        following = words[index + 1 : index + 1 + _SUBCOMMAND_WINDOW]
        if word == "gh":
            # An object word and the word after it; the action word may sit one past the window.
            pairs = zip(following, words[index + 2 :], strict=False)
            if any(obj in _GH_OBJECTS and action in _GH_ACTIONS for obj, action in pairs):
                return True
        elif not _IRREVERSIBLE_SUBCOMMANDS.get(word, frozenset()).isdisjoint(following):
            return True
    return False


def is_irreversible_social_action(tool_name: str, args: dict[str, object] | None = None) -> bool:
    """Determine if a tool call constitutes a socially irreversible external action.

    Socially irreversible actions (e.g. git push, public channel notification, package publishing)
    cannot be rolled back once dispatched into external collaborative environments. A shell line is read command
    by command, so the verb of one command is found whatever joins it to the next (``git push; echo done``).
    """
    lower_name = tool_name.lower().strip()
    if lower_name in _IRREVERSIBLE_SOCIAL_TOOLS:
        return True

    if is_shell_execution_tool(lower_name) and isinstance(args, dict):
        raw_cmd = str(args.get("command") or args.get("cmd") or args.get("code") or args.get("script") or "").strip()
        return any(_runs_irreversible_command(command.words) for command in read_commands(raw_cmd))

    return False


def is_financial_or_spend_tool(tool_name: str, args: dict[str, object] | None = None) -> bool:
    """Determine if a tool call constitutes a financial spending action."""
    lower_name = tool_name.lower()
    for kw in _SPEND_TOOL_KEYWORDS:
        if kw in lower_name:
            return True

    return bool(
        isinstance(args, dict)
        and any(k in args for k in ("amount", "total_amount", "charge_amount", "price_cents", "unit_amount"))
    )


def parse_spend_amount(args: dict[str, object] | None) -> tuple[float | None, str | None]:
    """Extract normalized numerical amount and currency from tool arguments."""
    if not isinstance(args, dict):
        return None, None

    currency = str(args.get("currency") or "USD").upper().strip()

    # Common amount fields
    for field in (
        "amount",
        "total_amount",
        "charge_amount",
        "price_cents",
        "unit_amount",
        "amount_cents",
        "price",
        "cost",
        "value",
    ):
        if field in args and args[field] is not None:
            try:
                raw_val = float(str(args[field]))
                # Special handling for stripe-like cent representations if explicitly flagged
                if "cent" in field or (currency == "USD" and "cents" in str(args.get("unit", "")).lower()):
                    return raw_val / 100.0, currency
                return raw_val, currency
            except (ValueError, TypeError):
                continue

    return None, None


def _canonical_json(data: object) -> str:
    """Produce deterministic JSON representation for cryptographic signing."""
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str)


def compute_action_digest(
    tool_name: str,
    args: dict[str, object] | None,
    secret_salt: str = DEFAULT_SPEND_SALT,
) -> str:
    """Compute HMAC-SHA256 signature binding tool_name and exact arguments."""
    canonical_args = _canonical_json(args if isinstance(args, dict) else {})
    amount, currency = parse_spend_amount(args)
    payload = f"{tool_name}:{amount}:{currency}:{canonical_args}".encode()
    return hmac.new(secret_salt.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def verify_action_digest(
    tool_name: str,
    args: dict[str, object] | None,
    expected_digest: str,
    secret_salt: str = DEFAULT_SPEND_SALT,
) -> bool:
    """Verify action digest against tool arguments with constant-time comparison."""
    if not expected_digest:
        return False
    computed = compute_action_digest(tool_name, args, secret_salt=secret_salt)
    return hmac.compare_digest(computed, expected_digest)


@dataclass(frozen=True, slots=True)
class SpendPolicy:
    """Policy constraints for agent financial operations."""

    per_action_cap: float = 50.0
    session_cap: float = 200.0
    enabled: bool = True
    currency: str = "USD"

    def is_action_allowed(self, amount: float | None, current_session_spent: float = 0.0) -> tuple[bool, str]:
        """Check if proposed spend complies with policy caps."""
        if not self.enabled:
            return True, "Spend policy disabled"

        if amount is None or amount <= 0:
            return True, "No positive financial spend detected"

        if amount > self.per_action_cap:
            return (
                False,
                f"Amount ({amount:.2f} {self.currency}) exceeds per-action cap ({self.per_action_cap:.2f} {self.currency})",
            )

        if (current_session_spent + amount) > self.session_cap:
            return False, (
                f"Total session spend ({current_session_spent + amount:.2f} {self.currency}) "
                f"exceeds session cap ({self.session_cap:.2f} {self.currency})"
            )

        return True, "Within spend policy caps"


# ============================================================================
# Script Content Integrity & TOCTOU Protection (§19 ApprovedScriptsChangePrevention)
# ============================================================================

_SCRIPT_EXTENSIONS = frozenset(
    {
        ".sh",
        ".bash",
        ".zsh",
        ".py",
        ".pyw",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".rb",
        ".pl",
        ".php",
    }
)

_INTERPRETER_TOKENS = frozenset(
    {
        "bash",
        "sh",
        "zsh",
        "python",
        "python3",
        "node",
        "bun",
        "deno",
        "ruby",
        "perl",
    }
)


def compute_script_content_hash(target_path: str) -> str | None:
    """Compute deterministic SHA-256 hash of a script file on disk.

    Returns None if file does not exist, is not a regular file, or cannot be read.
    """
    from pathlib import Path

    try:
        p = Path(target_path).resolve()
        if not p.is_file():
            return None
        hasher = hashlib.sha256()
        with p.open("rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        return hasher.hexdigest()
    except (OSError, PermissionError) as exc:
        logger.debug("Failed computing script hash for %s: %s", target_path, exc)
        return None


def extract_script_file_target(tool_name: str, args: dict[str, object] | None) -> str | None:
    """Extract candidate script file path from tool arguments if applicable.

    Inspects common tool arguments: 'script_path', 'file_path', 'path', or shell commands
    like `bash ./run.sh` or `python script.py`.
    """
    import os
    from pathlib import Path

    if not isinstance(args, dict):
        return None

    # 1. Direct argument fields
    for field in ("script_path", "script", "file_path", "file"):
        val = args.get(field)
        if isinstance(val, str) and val.strip():
            candidate = val.strip()
            _, ext = os.path.splitext(candidate)
            if ext.lower() in _SCRIPT_EXTENSIONS and os.path.isfile(candidate):
                return str(Path(candidate).resolve())

    # 2. Inspect shell commands: `python deploy.py`, `bash ./scripts/run.sh`
    cmd_val = args.get("command") or args.get("cmd") or args.get("code")
    if isinstance(cmd_val, str) and cmd_val.strip():
        cmd_str = cmd_val.strip()
        tokens = [word for command in read_commands(cmd_str) for word in command.words]
        if len(tokens) >= 2 and tokens[0].lower() in _INTERPRETER_TOKENS:
            for token in tokens[1:]:
                if token.startswith("-"):
                    continue
                _, ext = os.path.splitext(token)
                if ext.lower() in _SCRIPT_EXTENSIONS and os.path.isfile(token):
                    return str(Path(token).resolve())

        # Direct executable invocation: `./run.sh`
        if len(tokens) >= 1:
            first = tokens[0]
            _, ext = os.path.splitext(first)
            if ext.lower() in _SCRIPT_EXTENSIONS and os.path.isfile(first):
                return str(Path(first).resolve())

    return None


def verify_script_file_integrity(file_path: str, expected_hash: str) -> tuple[bool, str]:
    """Verify that script file on disk matches expected cryptographic SHA-256 hash.

    Returns (is_valid, reason).
    """
    if not expected_hash:
        return True, ""

    current_hash = compute_script_content_hash(file_path)
    if current_hash is None:
        return False, f"Script file '{file_path}' no longer exists or is unreadable"

    if current_hash != expected_hash:
        return (
            False,
            f"Script file '{file_path}' content was altered after approval. "
            f"Expected SHA-256 '{expected_hash[:16]}...', current '{current_hash[:16]}...'. "
            "Execution blocked to prevent TOCTOU script substitution.",
        )

    return True, ""
