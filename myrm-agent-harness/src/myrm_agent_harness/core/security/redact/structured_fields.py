"""Secret-named field masking for structured text.

Masks the value of a credential-named field when it appears as a JSON member
(``"clientSecret": "..."``), as a JSON member inside a JSON-encoded string
(``{"output": "{\\"api_key\\": \\"...\\"}"}``, the shape of a wrapped tool
result), or as a Python mapping ``repr`` entry on the lines where interpreters
print diagnostics (pytest assertion introspection, final exception lines).

One key policy serves all three. A field name is a credential when it is one of
the bare credential words (``token``, ``secret``, ``bearer``, ``authorization``,
``cookie`` ... and the variables known by name, ``sshpass`` and ``mysql_pwd``),
or ends in an unambiguous credential noun (``api key``, ``client secret``,
``refresh token``, ``secret access key``, ``password``, ``passphrase`` ...)
in any spelling: snake, kebab, dotted, camel or Pascal case. Bare ``token`` and
``secret`` are not matched as suffixes, so pagination cursors such as
``nextPageToken``, identifiers such as ``file_token`` and metadata such as
``token_count`` stay readable.

Channel credential nouns (``app secret``, ``signing secret``, ``bot token``,
``verification token``) are credential names too, but locale files key their form
labels by them (``"feishuAppSecret": "App Secret"``), so a field named by one of
them keeps a plain label: letters of any script separated by spaces, ``-`` or
``_``, no digits, and a single word shorter than 20 characters. Credentials
normally carry digits or run longer; the residual is a passphrase made of words
and, rarely, a random URL-safe base64 value that happens to hold no digit.

[INPUT]
- masking::_mask_secret (POS: Leaf value-masking helpers of the runtime redactor)
- patterns::_is_env_reference, patterns::_CREDENTIAL_VARIABLE_NAMES (POS: Compiled regex patterns, keyword guard and shared value-masking helpers of the runtime redactor)

[OUTPUT]
- ``_JSON_FIELD_RE`` / ``_redact_json_field`` - plain JSON member (group 1 = quoted key, group 2 = value)
- ``_JSON_ESCAPED_FIELD_RE`` / ``_redact_json_escaped_field`` - JSON member inside a JSON-encoded string
- ``_REPR_DIAGNOSTIC_LINE_RE`` / ``_redact_repr_diagnostic_line`` - Python repr entries on diagnostic lines
- ``is_secret_field_name`` - the shared key policy
- ``_mask_field_value`` - value masking of the three detectors (a password or passphrase is hidden completely; variable references and plain labels stay readable)

[POS]
Structured-field detectors of the redaction engine; consumed by ``engine.py``
and by ``agent/skills/security/content_sanitizer.py`` (plain JSON rule).
"""

from __future__ import annotations

import re

from .masking import _mask_secret
from .patterns import _CREDENTIAL_VARIABLE_NAMES, _is_env_reference

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
        *_CREDENTIAL_VARIABLE_NAMES,
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
        rf"pass{_SEP}phrase",
    )
)

# Channel credential nouns: also the keys of form labels in locale files, so their values pass ``_PLAIN_LABEL_RE``.
_CHANNEL_NOUNS = "|".join(
    (
        rf"app{_SEP}secret",
        rf"signing{_SEP}secret",
        rf"(?:bot|verification){_SEP}token",
    )
)

# The prefix is bounded so a long run of name characters cannot make matching quadratic.
_PREFIX = r"[A-Za-z0-9_.\-]{0,48}?"
_FIELD_NAME = rf"(?:{_BARE_NAMES}|{_PREFIX}(?:{_SUFFIX_NOUNS}|{_CHANNEL_NOUNS}))"
_FIELD_NAME_RE = re.compile(_FIELD_NAME, re.IGNORECASE)
# Names that are credentials whatever their value; a credential name outside it is a channel credential name.
_ALWAYS_SECRET_NAME_RE = re.compile(rf"(?:{_BARE_NAMES}|{_PREFIX}(?:{_SUFFIX_NOUNS}))", re.IGNORECASE)

# A label is words of letters (any script) joined by spaces, ``-`` or ``_``; a lone word must be short, since a
# credential never looks like ``Signing`` but can be a long run of letters.
_PLAIN_LABEL_RE = re.compile(r"[^\W\d_]{1,19}|[^\W\d_]+(?:[\s_-]+[^\W\d_]+)+")

# JSON string values accept ``\"`` escapes so ``{"password": "my\"secret"}`` is captured whole.
_JSON_FIELD_RE = re.compile(rf'("{_FIELD_NAME}")\s*:\s*"((?:[^"\\\\]|\\.)*)"', re.IGNORECASE)

# Inside a JSON-encoded string every quote is backslash-escaped; the backreference keeps the key's and the
# value's escape depth equal, which covers any nesting depth. A match starts where the run of backslashes starts,
# so a long run costs one attempt instead of one per offset.
_JSON_ESCAPED_FIELD_RE = re.compile(rf'((?<!\\)(\\+)"{_FIELD_NAME}\2")\s*:\s*\2"([^"\\]+)\2"', re.IGNORECASE)

# Python ``repr`` entries are only masked on diagnostic lines, so source code shown by ``cat`` keeps its literals.
_REPR_FIELD_RE = re.compile(r"'([A-Za-z_]\w*)'(\s*:\s*)(?:'((?:\\.|[^'\\])+)'|\"((?:\\.|[^\"\\])+)\")")
_REPR_DIAGNOSTIC_LINE_RE = re.compile(
    r"^([ \t]*E[ \t]{2,}|(?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*(?:Error|Exception|Warning):[ \t]*)(.*)$",
    re.MULTILINE,
)


def is_secret_field_name(name: str) -> bool:
    """Whether ``name`` (unquoted, any spelling) names a credential field."""
    return _FIELD_NAME_RE.fullmatch(name) is not None


def _mask_field_value(name: str, value: str) -> str:
    """Mask the value of the credential field ``name``.

    A variable reference such as ``${API_KEY}`` is a name, not a secret, and a channel credential field holding a
    plain label (``"appSecret": "App Secret"``) is a form label. The rest is masked by ``_mask_secret``.
    """
    if _is_env_reference(value):
        return value
    if _PLAIN_LABEL_RE.fullmatch(value) and _ALWAYS_SECRET_NAME_RE.fullmatch(name) is None:
        return value
    return _mask_secret(name, value)


def _unquoted(quoted_key: str) -> str:
    """The key of a JSON member without its quotes and escape backslashes (plain or JSON-encoded)."""
    return quoted_key.strip('"\\')


def _redact_json_field(m: re.Match[str]) -> str:
    """Replacement for ``_JSON_FIELD_RE``; an empty value is left as is, since "not set" is no secret and a reader needs it."""
    if not m.group(2).strip():
        return m.group(0)
    return f'{m.group(1)}: "{_mask_field_value(_unquoted(m.group(1)), m.group(2))}"'


def _redact_json_escaped_field(m: re.Match[str]) -> str:
    """Replacement for ``_JSON_ESCAPED_FIELD_RE``; the escape depth of the original is preserved."""
    escape = m.group(2)
    return f'{m.group(1)}: {escape}"{_mask_field_value(_unquoted(m.group(1)), m.group(3))}{escape}"'


def _redact_repr_field(m: re.Match[str]) -> str:
    """Mask one ``'key': 'value'`` repr entry when ``key`` names a credential."""
    key, sep, single, double = m.group(1), m.group(2), m.group(3), m.group(4)
    if not is_secret_field_name(key):
        return m.group(0)
    if single is not None:
        return f"'{key}'{sep}'{_mask_field_value(key, single)}'"
    return f"'{key}'{sep}\"{_mask_field_value(key, double)}\""


def _redact_repr_diagnostic_line(m: re.Match[str]) -> str:
    """Replacement for ``_REPR_DIAGNOSTIC_LINE_RE``: mask the repr entries in the line body."""
    return m.group(1) + _REPR_FIELD_RE.sub(_redact_repr_field, m.group(2))
