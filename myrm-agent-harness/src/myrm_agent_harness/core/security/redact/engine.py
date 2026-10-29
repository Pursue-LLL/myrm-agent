"""Regex-based secret redaction for tool output and logs.

Applies pattern matching to mask API keys, tokens, and credentials
before they reach the LLM context or log files. Acts as a second
defense layer complementing ``sanitize_env`` (source removal).

[INPUT]
- masking::_mask_token, masking::_mask_secret (POS: Leaf value-masking helpers of the runtime redactor)
- nested::redact_nested (POS: Shared walker of the redaction domain: bounded in depth, cuts a container that holds itself)
- bounded_replace::_replace_pattern_bounded (POS: Bounded regex replacement, the ReDoS guard of every redaction pass)
- command_patterns::_redact_command_credentials (POS: Command-line rules of the runtime redactor)
- header_patterns::_redact_secret_headers (POS: Header rules of the runtime redactor)
- patterns::_PREFIX_RE and the other compiled regexes and replacers (POS: Compiled regex patterns, keyword guard and shared value-masking helpers of the runtime redactor)
- structured_fields::_redact_json_field, structured_fields::_redact_json_escaped_field, structured_fields::_redact_repr_diagnostic_line, structured_fields::_is_secret_field_name, structured_fields::_mask_field_value (POS: structured-field detectors of the redaction engine)
- url_credentials::_DB_CONNSTR_RE, url_credentials::_URL_USERINFO_RE, url_credentials::_URL_BARE_TOKEN_RE and their replacers (POS: URL credential regexes and replacers of the runtime redactor)

[OUTPUT]
- redact_sensitive_text(text, *, source_code=False) -> str — apply all redaction patterns; ``source_code`` limits the name-based assignment passes to lines with a string literal
- redact_for_llm(value) -> str — recursive redaction of nested diagnostic values, flattened to str (LLM error formatting)
- escape_invisible_unicode(text) -> str — escape invisible chars to \\u{XXXX}
- redact_field_text(key, text, *, scan) -> str — redact the value of one named field: a credential-named field is masked whatever its shape, any other text goes through ``scan`` (the full redactor by default)
- redact_for_display(args) -> dict — redaction of every string in tool arguments for the approval UI, by field name, bounded in depth and safe on loops
- RedactingFormatter — logging.Formatter subclass for production logs

Pattern definitions live in ``patterns.py`` and its sibling rule modules; this module owns the redaction
engine (control-split guard, pipeline) and public APIs.

[POS]
Redaction pipeline and public API of the redactor; applies the pattern and
structured-field detectors to tool output, error text, logs and approval displays.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable

from .bounded_replace import _replace_pattern_bounded
from .command_patterns import _redact_command_credentials
from .header_patterns import _redact_secret_headers
from .masking import _mask_secret, _mask_token
from .nested import redact_nested
from .patterns import (
    _AUTH_HEADER_RE,
    _CLI_FLAG_RE,
    _CONTROL_CHARS_RE,
    _ENV_ASSIGN_LOWER_RE,
    _ENV_ASSIGN_RE,
    _JWT_RE,
    _PREFIX_RE,
    _PRIVATE_KEY_RE,
    _TELEGRAM_BOT_RE,
    _TOKEN_BODY_CHARS,
    _URL_QUERY_RE,
    _YAML_ASSIGN_RE,
    _redact_cli_flag,
    _redact_env_assignment,
    _redact_form_body,
    _redact_yaml_assignment,
)
from .structured_fields import (
    _JSON_ESCAPED_FIELD_RE,
    _JSON_FIELD_RE,
    _REPR_DIAGNOSTIC_LINE_RE,
    _is_secret_field_name,
    _mask_field_value,
    _redact_json_escaped_field,
    _redact_json_field,
    _redact_repr_diagnostic_line,
)
from .url_credentials import (
    _DB_CONNSTR_RE,
    _URL_BARE_TOKEN_RE,
    _URL_USERINFO_RE,
    _redact_db_connstr,
    _redact_url_userinfo,
)

_REDACT_ENABLED = True

# An assigned string literal of eight characters or more, no f-string prefix: a shorter literal or a template is
# not a credential, and the lines without one are the bulk of the false masks in source code.
_STRING_LITERAL_RE = re.compile(r"""[:=]\s*[bru]*["'][^"'\s]{8,}["']""", re.IGNORECASE)


def set_redact_enabled(enabled: bool) -> None:
    """Configure secret redaction at startup. Enabled by default."""
    global _REDACT_ENABLED
    _REDACT_ENABLED = enabled


def _redact_pem_block(block: str) -> str:
    """Redact PEM block while preserving header/footer for debugging.

    Example:
        Input:  -----BEGIN RSA PRIVATE KEY-----
                MIIEowIBAAKCAQEA...
                -----END RSA PRIVATE KEY-----
        Output: -----BEGIN RSA PRIVATE KEY-----
                ...redacted...
                -----END RSA PRIVATE KEY-----
    """
    lines = [line for line in block.splitlines() if line.strip()]
    if len(lines) < 2:
        return "***"
    return f"{lines[0]}\n...redacted...\n{lines[-1]}"


def _mask_control_split_tokens(text: str) -> str:
    """Mask tokens whose body is split by control/zero-width characters.

    A credential like ``sk-abc\\x1bdef456…`` has its token body interrupted,
    so the contiguous ``_PREFIX_RE`` cannot match it and the secret leaks
    verbatim. Strategy: build a copy with all control chars removed (the token
    is contiguous again), match on that, then mask the corresponding span in
    the *original* — but only when the original span contains solely token-body
    and control chars (a match that crosses into a different line's unrelated
    text is rejected).
    """
    control_pos = {m.start() for m in _CONTROL_CHARS_RE.finditer(text)}
    if not control_pos:
        return text
    stripped = "".join(c for i, c in enumerate(text) if i not in control_pos)
    orig_idx = [i for i in range(len(text)) if i not in control_pos]
    out = list(text)
    matches: list[tuple[int, int, str]] = []
    for m in _PREFIX_RE.finditer(stripped):
        body = m.group(1)
        start_orig = orig_idx[m.start(1)]
        end_orig = orig_idx[m.end(1) - 1] + 1
        span = text[start_orig:end_orig]
        # If a fragment inside the span already matches _PREFIX_RE on its own
        # AND the span crosses a LINE boundary (\n / \r), do NOT join: a
        # complete token at end-of-line followed by a word line
        # (``ghp_<token>\nbutton [ref=e3]``) joins into one stripped-copy match
        # and the mask would eat ``button``. For NON-newline controls (ESC,
        # ZWSP, ...) the join proceeds even when a fragment self-matches, so a
        # split token (``sk-<head>\x1b<tail>``) is masked in full.
        if ("\n" in span or "\r" in span) and _PREFIX_RE.search(span):
            continue
        # Reject matches whose original span crosses a non-token char
        # (e.g. ``sk_abc…\nTAVILY_API_KEY=…`` — the ``=`` is not part of a token
        # body, so the regex matched across unrelated lines).
        if not (
            all(c in _TOKEN_BODY_CHARS or _CONTROL_CHARS_RE.match(c) for c in span)
            and (end_orig >= len(text) or text[end_orig] != "=")
        ):
            continue
        matches.append((start_orig, end_orig, _mask_token(body)))
    for start_orig, end_orig, replacement in reversed(matches):
        out[start_orig:end_orig] = list(replacement)
    return "".join(out)


def _redact_name_assignments(text: str) -> str:
    """Mask the value of every credential-named ENV, JSON, repr-diagnostic and YAML assignment in ``text``."""
    text = _replace_pattern_bounded(text, _ENV_ASSIGN_RE, _redact_env_assignment)

    # 小写/短名 env（`db_pw=`/`openai_key=`）。`(?<![?&])` 负向后顾已阻止 URL query
    # 参数（由 _URL_QUERY_RE 处理），此处无条件执行——含 URL 的混合文本同样脱敏。
    text = _replace_pattern_bounded(text, _ENV_ASSIGN_LOWER_RE, _redact_env_assignment)

    # Credential-named fields in JSON, in JSON nested inside a JSON string, and in Python repr diagnostics
    text = _replace_pattern_bounded(text, _JSON_FIELD_RE, _redact_json_field)
    text = _replace_pattern_bounded(text, _JSON_ESCAPED_FIELD_RE, _redact_json_escaped_field)
    text = _replace_pattern_bounded(text, _REPR_DIAGNOSTIC_LINE_RE, _redact_repr_diagnostic_line)

    # Unquoted / quoted YAML-colon config（`password: secret`、`password: "hunter2!"`）。
    # 正则锚定行首且 key 字符类不含 `:`/`/`/`?`，天然不匹配 URL 行，无需全局 URL 开关。
    return _replace_pattern_bounded(text, _YAML_ASSIGN_RE, _redact_yaml_assignment)


def _redact_by_name(text: str, redact: Callable[[str], str], *, source_code: bool) -> str:
    """Run a name-based pass over ``text``; in source mode only over the lines that carry a string literal."""
    if not source_code:
        return redact(text)
    return "\n".join(redact(line) if _STRING_LITERAL_RE.search(line) else line for line in text.split("\n"))


def redact_sensitive_text(text: str, *, source_code: bool = False) -> str:
    """Apply all redaction patterns to a block of text.

    Pure function, thread-safe. Always on: no environment variable disables it, and
    ``set_redact_enabled`` is a startup/test hook with no production caller. Empty or non-string input passes through.

    ``source_code=True`` is for the text of a source file, which names credentials all the time
    (``total_api_tokens = 0``) and keeps a secret only as a string literal: the name-based passes (assignments,
    API-key and cookie headers) run on the lines that carry one, the value-shape passes and the command-line
    credential rules (``curl -u``, ``sshpass -p``) on every line.

    Key features:
    - Bounded regex replace to prevent ReDoS (OPT-1)
    - Command-line credential redaction (``curl -u/-b``, ``sshpass -p``, ``mysql -p``) first, while the command name
      is still in the text
    - Control/zero-width split-token masking before prefix matching
    - Form-urlencoded body pair-wise redaction (no parameter swallowing)
    - YAML/colon config redaction (unquoted + quoted values)
    - ENV assignment redaction with word-boundary key validation
    - PEM block special handling to preserve header/footer (OPT-3)
    - URL query parameter redaction (OPT-2)
    - CLI flag redaction (OPT-5)
    - Telegram Bot URL redaction (OPT-6)
    - Extended token prefix coverage (Groq, Slack App, Anthropic) (OPT-4)
    """
    if not text or not isinstance(text, str) or not _REDACT_ENABLED:
        return text

    # Command-line credentials (curl -u/-b, sshpass -p, mysql -p) come first: the rule is anchored on the command
    # name, which a generic pass swallows when a value touches a separator (`tool --token x;curl -u a:pw`). Like the
    # value shapes they run on every line of a source file.
    text = _redact_command_credentials(text)

    # 控制字符拆分的 token（`sk-abc\x1bdef…`）在连续 _PREFIX_RE 之前先掩码
    text = _mask_control_split_tokens(text)

    # Form-urlencoded body（`token=abc&limit=50&page=2`）：整段 k=v&k=v 时逐对脱敏，
    # 必须在 ENV 正则之前——否则 `\S+` 贪婪吞掉 `&` 分隔的后续参数并泄漏前缀
    text = _redact_form_body(text)

    # Use bounded replace for all patterns to prevent ReDoS (OPT-1)
    text = _replace_pattern_bounded(text, _PREFIX_RE, lambda m: _mask_token(m.group(1)))

    text = _redact_by_name(text, _redact_name_assignments, source_code=source_code)

    text = _replace_pattern_bounded(
        text,
        _AUTH_HEADER_RE,
        lambda m: f"{m.group(1)}{m.group(2) or ''}{_mask_token(m.group(3))}",
    )

    # PEM block special handling: preserve header/footer for debugging (OPT-3)
    text = _replace_pattern_bounded(text, _PRIVATE_KEY_RE, lambda m: _redact_pem_block(m.group(0)))

    text = _replace_pattern_bounded(text, _DB_CONNSTR_RE, _redact_db_connstr)

    # URL userinfo（`https://user:pass@host`）与 bare-token（`https://TOKEN@host`）
    text = _replace_pattern_bounded(text, _URL_USERINFO_RE, _redact_url_userinfo)
    text = _replace_pattern_bounded(
        text,
        _URL_BARE_TOKEN_RE,
        lambda m: f"{m.group(1)}{_mask_token(m.group(2))}{m.group(3)}",
    )

    # URL query parameters (OPT-2)
    text = _replace_pattern_bounded(
        text, _URL_QUERY_RE, lambda m: f"{m.group(1)}{_mask_secret(m.group(1), m.group(2))}"
    )

    # CLI flags (OPT-5)
    text = _replace_pattern_bounded(text, _CLI_FLAG_RE, _redact_cli_flag)

    # Telegram Bot URL (OPT-6)
    text = _replace_pattern_bounded(text, _TELEGRAM_BOT_RE, lambda m: f"{m.group(1)}{_mask_token(m.group(2))}")

    # API-key 风格认证头（x-api-key 等）
    text = _redact_by_name(text, _redact_secret_headers, source_code=source_code)

    # JWT token（eyJ… 无 key 上下文的裸 JWT）
    text = _replace_pattern_bounded(text, _JWT_RE, lambda m: _mask_token(m.group(0)))

    return text


class RedactingFormatter(logging.Formatter):
    """Log formatter that redacts secrets from all messages."""

    def format(self, record: logging.LogRecord) -> str:
        return redact_sensitive_text(super().format(record))


# ── Invisible Unicode escaping (approval display) ─────────────

_INVISIBLE_CODEPOINTS: frozenset[int] = frozenset(
    {
        0x200B,  # zero width space
        0x200C,  # zero width non-joiner
        0x200D,  # zero width joiner
        0xFEFF,  # byte order mark / zero width no-break space
        0x2060,  # word joiner
        0x2061,  # function application
        0x2062,  # invisible times
        0x2063,  # invisible separator
        0x2064,  # invisible plus
        0x00AD,  # soft hyphen
        0x034F,  # combining grapheme joiner
        0x061C,  # Arabic letter mark
        0x180E,  # Mongolian vowel separator
    }
)

_INVISIBLE_ESCAPE_RE = re.compile("[" + "".join(f"\\u{cp:04X}" for cp in sorted(_INVISIBLE_CODEPOINTS)) + "]")


def escape_invisible_unicode(text: str) -> str:
    r"""Replace invisible Unicode codepoints with visible ``\u{XXXX}`` escapes.

    Unlike ``content_boundary.strip_invisible_unicode`` (which removes them),
    this preserves evidence of their presence for human review in approval UIs.
    """
    if not text:
        return text
    return _INVISIBLE_ESCAPE_RE.sub(lambda m: f"\\u{{{ord(m.group()):04X}}}", text)


def redact_for_llm(value: object) -> str:
    """Redact credentials from a nested diagnostic value, flattened to a string.

    Recursively masks secret strings inside dict/list/tuple values before the
    text reaches the LLM. Keeps the exact string shape of the original nested
    structure (list-style brackets for both list and tuple containers).
    """
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if isinstance(value, dict):
        return str({k: redact_for_llm(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return str([redact_for_llm(v) for v in value])
    return str(value)


def redact_field_text(key: str, text: str, *, scan: Callable[[str], str] = redact_sensitive_text) -> str:
    """Redact ``text``, the value of the field called ``key`` (``""`` when the field has no string name).

    A value that holds no secret shape (``sessionid=…`` in ``Cookie``, a bare password) is still masked when the field
    name is a credential, since the name says what the value does not. Any other text goes through ``scan``: the full
    redactor, unless a caller that runs on every event passes a lighter one.
    """
    if _REDACT_ENABLED and _is_secret_field_name(key) and text.strip():
        return _mask_field_value(key, text)
    return scan(text)


def _display_text(key: str, text: str) -> str:
    return redact_field_text(key, escape_invisible_unicode(text))


def redact_for_display(args: dict[str, object]) -> dict[str, object]:
    """Redact tool arguments for approval UI display.

    Applies invisible Unicode escaping + secret masking to every string, by field name. A container nested deeper than
    ``nested.MAX_DEPTH`` or holding itself is replaced by a marker. Used by the approval batch processor to sanitize args
    before sending them to the frontend. The original args are preserved for actual tool execution.
    """
    result = redact_nested(args, _display_text)
    if not isinstance(result, dict):
        return args
    return result
