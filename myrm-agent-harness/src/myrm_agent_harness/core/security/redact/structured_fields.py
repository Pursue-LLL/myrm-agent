"""Secret-named field masking for structured text.

Masks the value of a credential-named field when it appears as a JSON member
(``"clientSecret": "..."``), as a JSON member inside a JSON-encoded string
(``{"output": "{\\"api_key\\": \\"...\\"}"}``, the shape of a wrapped tool
result), or as a Python mapping ``repr`` entry on the lines where interpreters
print diagnostics (pytest assertion introspection, final exception lines).

One key policy serves all three. A field name is a credential when it is one of
the bare credential words (``token``, ``secret``, ``bearer``, ``authorization``,
``cookie`` ...), or ends in an unambiguous credential noun (``api key``,
``client secret``, ``refresh token``, ``secret access key``, ``password`` ...)
in any spelling: snake, kebab, dotted, camel or Pascal case. Bare ``token`` and
``secret`` are not matched as suffixes, so pagination cursors such as
``nextPageToken``, identifiers such as ``file_token`` and metadata such as
``token_count`` stay readable. Channel credential names (``appSecret``,
``bot_token``, ``signing_secret`` ...) are deliberately absent: Myrm's own
locale files key their form labels by those names, and a label such as
``"feishuAppSecret": "App Secret"`` would be masked in every file an agent reads.

[INPUT]
- patterns::_mask_token (value masking shared by every redactor), _is_env_reference (a variable reference is no secret)

[OUTPUT]
- ``_JSON_FIELD_RE`` / ``_redact_json_field`` - plain JSON member (group 1 = quoted key, group 2 = value)
- ``_JSON_ESCAPED_FIELD_RE`` / ``_redact_json_escaped_field`` - JSON member inside a JSON-encoded string
- ``_REPR_DIAGNOSTIC_LINE_RE`` / ``_redact_repr_diagnostic_line`` - Python repr entries on diagnostic lines
- ``_is_secret_field_name`` - the shared key policy

[POS]
Structured-field detectors of the redaction engine; consumed by ``engine.py``
and by ``agent/skills/security/content_sanitizer.py`` (plain JSON rule).
"""

from __future__ import annotations

import re

from .patterns import _is_env_reference, _mask_token

_SEP = r"[-_.]?"

# Whole-name credentials: matched only when they are the entire field name.
_BARE_NAMES = "|".join(
    (
        "token",
        "secret",
        "bearer",
        rf"(?:proxy{_SEP})?authorization",
        rf"(?:set{_SEP})?cookie",
        rf"secret{_SEP}value",
        rf"raw{_SEP}secret",
        rf"secret{_SEP}input",
        rf"key{_SEP}material",
    )
)

# Credential nouns that may follow any prefix (``stripeSecretKey``, ``x-api-key``, ``BRAVE_API_KEY``).
_SUFFIX_NOUNS = "|".join(
    (
        rf"api{_SEP}(?:key|token)",
        rf"(?:secret|private){_SEP}key",
        rf"secret{_SEP}access{_SEP}key",
        rf"client{_SEP}secret",
        rf"(?:access|refresh|id|auth|session|bearer){_SEP}token",
        "password",
        "passwd",
    )
)

# The prefix is bounded so a long run of name characters cannot make matching quadratic.
_FIELD_NAME = rf"(?:{_BARE_NAMES}|[A-Za-z0-9_.\-]{{0,48}}?(?:{_SUFFIX_NOUNS}))"
_FIELD_NAME_RE = re.compile(_FIELD_NAME, re.IGNORECASE)

# JSON string values accept ``\"`` escapes so ``{"password": "my\"secret"}`` is captured whole.
_JSON_FIELD_RE = re.compile(rf'("{_FIELD_NAME}")\s*:\s*"((?:[^"\\\\]|\\.)*)"', re.IGNORECASE)

# Inside a JSON-encoded string every quote is backslash-escaped; the backreference keeps the key's and the
# value's escape depth equal, which covers any nesting depth.
_JSON_ESCAPED_FIELD_RE = re.compile(rf'((\\+)"{_FIELD_NAME}\2")\s*:\s*\2"([^"\\]+)\2"', re.IGNORECASE)

# Python ``repr`` entries are only masked on diagnostic lines, so source code shown by ``cat`` keeps its literals.
_REPR_FIELD_RE = re.compile(r"'([A-Za-z_]\w*)'(\s*:\s*)(?:'((?:\\.|[^'\\])+)'|\"((?:\\.|[^\"\\])+)\")")
_REPR_DIAGNOSTIC_LINE_RE = re.compile(
    r"^([ \t]*E[ \t]{2,}|(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*(?:Error|Exception|Warning):[ \t]*)(.*)$",
    re.MULTILINE,
)


def _is_secret_field_name(name: str) -> bool:
    """Whether ``name`` (unquoted, any spelling) names a credential field."""
    return _FIELD_NAME_RE.fullmatch(name) is not None


def _mask_field_value(value: str) -> str:
    """Mask a credential field's value; a variable reference such as ``${API_KEY}`` is a name, not a secret."""
    return value if _is_env_reference(value) else _mask_token(value)


def _redact_json_field(m: re.Match[str]) -> str:
    """Replacement for ``_JSON_FIELD_RE``; an empty value is left as is, since "not set" is no secret and a reader needs it."""
    if not m.group(2).strip():
        return m.group(0)
    return f'{m.group(1)}: "{_mask_field_value(m.group(2))}"'


def _redact_json_escaped_field(m: re.Match[str]) -> str:
    """Replacement for ``_JSON_ESCAPED_FIELD_RE``; the escape depth of the original is preserved."""
    escape = m.group(2)
    return f'{m.group(1)}: {escape}"{_mask_field_value(m.group(3))}{escape}"'


def _redact_repr_field(m: re.Match[str]) -> str:
    """Mask one ``'key': 'value'`` repr entry when ``key`` names a credential."""
    key, sep, single, double = m.group(1), m.group(2), m.group(3), m.group(4)
    if not _is_secret_field_name(key):
        return m.group(0)
    if single is not None:
        return f"'{key}'{sep}'{_mask_field_value(single)}'"
    return f"'{key}'{sep}\"{_mask_field_value(double)}\""


def _redact_repr_diagnostic_line(m: re.Match[str]) -> str:
    """Replacement for ``_REPR_DIAGNOSTIC_LINE_RE``: mask the repr entries in the line body."""
    return m.group(1) + _REPR_FIELD_RE.sub(_redact_repr_field, m.group(2))
