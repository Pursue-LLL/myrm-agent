"""Channel `.ftl` locale key parity tests.

The channel locale catalog is the single source of truth for every user-visible
system message (busy acks, topic/workspace bindings, progress labels, deliverable
notes). Missing keys silently degrade a locale to another language through the
BCP 47 fallback chain, so a gap in e.g. `ja.ftl` shows English (or Simplified
Chinese) to Japanese users.

These guards enforce structural and behavioral consistency across all locale
files:

1. Every locale file exposes the exact same key set as the `en.ftl` reference.
2. Every key's placeholder set (`{ $var }` references) matches across locales;
   a missing or mistyped placeholder renders as a bare key name or truncated
   text through the Fluent engine, which never raises.
3. Every `{...}` reference is legal Fluent syntax (a `$`-prefixed variable, a
   function like `{NUMBER($var)}`, a `-`-prefixed term, or a string literal
   like `{ "**" }`). Bare identifiers such as `{seconds:.0f}` are invalid and
   silently break the whole message.
4. Every message renders successfully with sample arguments. This catches
   runtime failures a static scan cannot — e.g. a multiline pattern whose first
   line starts with a selector character (`*`/`[`) parses as a broken entry and
   the engine returns the bare key name verbatim.
5. Every key is reachable from production code. A translated key with no call
   site is dead weight that must still be maintained across every locale; the
   `cmd_*`/`cat_*` help keys are validated against the live command registry
   in both directions — an orphaned key and a registered command missing its
   translation both break /help.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_LOCALES_DIR = (
    Path(__file__).resolve().parents[3]
    / "app"
    / "channels"
    / "i18n"
    / "locales"
)

_APP_DIR = Path(__file__).resolve().parents[3] / "app"

_REFERENCE_LOCALE = "en"

# A message key is a bare identifier (letters/digits/underscore/hyphen)
# terminated by ' =' at column 0. Continuation lines are indented and belong
# to the same message, so only lines starting at column 0 count as keys.
_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+) =")

# Legal Fluent in-message references:
# - variable:    { $seconds } / {$seconds}
# - function:    {NUMBER($seconds)} / {SELECT(...)}
# - term:        {-brand} / {brand}
_VAR_RE = re.compile(r"\{ ?\$([A-Za-z_][A-Za-z0-9_]*) ?\}")
_FUNC_RE = re.compile(r"\{[A-Z][A-Z0-9_]*\([^{}]*\) ?\}")
_TERM_RE = re.compile(r"\{-?[A-Za-z_][A-Za-z0-9_.-]* ?\}")

# A Fluent string literal, e.g. `{ "**" }` or `{ '[' }`.  Used to escape
# markdown-leading characters (`*`, `[`) at the start of an indented line,
# which are otherwise reserved selector syntax in multiline patterns.
_LITERAL_RE = re.compile(r"\{ ?['\"][^'\"]{1,8}['\"] ?\}")

# Any `{...}` group that matches none of the legal shapes above (e.g. the
# bare-identifier `{seconds:.0f}`) breaks the whole Fluent message.
_ILLEGAL_RE = re.compile(r"\{[^}]*\}")


def _locale_names() -> tuple[str, ...]:
    """Every `.ftl` file present; new languages join the parity check automatically."""
    return tuple(sorted(path.stem for path in _LOCALES_DIR.glob("*.ftl")))


def _message_bodies(locale: str) -> dict[str, str]:
    """Parse a locale file into ``{message key: full body}``.

    Fluent continuation lines are indented and belong to the previous key, so a
    message body may span several lines until the next column-0 key line.
    """
    path = _LOCALES_DIR / f"{locale}.ftl"
    assert path.exists(), f"Missing locale file: {path}"
    keys: dict[str, str] = {}
    current_key: str | None = None
    body_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _KEY_RE.match(line)
        if match:
            if current_key is not None:
                keys[current_key] = "\n".join(body_lines)
            current_key, body_lines = match.group(1), [line.split("=", 1)[1]]
        elif current_key is not None and line.startswith(" "):
            body_lines.append(line)
    if current_key is not None:
        keys[current_key] = "\n".join(body_lines)
    return keys


def _placeholders(body: str) -> frozenset[str]:
    """Variable names referenced by a message body, e.g. `seconds` for `{ $seconds }`."""
    return frozenset(_VAR_RE.findall(body))


def _illegal_references(body: str) -> list[str]:
    """All `{...}` groups in a body that are not valid Fluent references."""
    return [
        ref
        for ref in (match.group(0).strip() for match in _ILLEGAL_RE.finditer(body))
        if not (
            _VAR_RE.fullmatch(ref)
            or _FUNC_RE.fullmatch(ref)
            or _TERM_RE.fullmatch(ref)
            or _LITERAL_RE.fullmatch(ref)
        )
    ]


@pytest.mark.architecture
def test_ftl_locales_share_identical_key_sets() -> None:
    """Every channel locale must expose the exact same message keys."""
    locales = _locale_names()
    assert _REFERENCE_LOCALE in locales, (
        f"Reference locale {_REFERENCE_LOCALE}.ftl missing under {_LOCALES_DIR}"
    )
    key_sets = {locale: frozenset(_message_bodies(locale)) for locale in locales}
    reference_keys = key_sets[_REFERENCE_LOCALE]

    for locale, keys in key_sets.items():
        missing = reference_keys - keys
        extra = keys - reference_keys
        assert not missing and not extra, (
            f"FTL key mismatch between {_REFERENCE_LOCALE} and {locale}: "
            f"missing={sorted(missing)}, extra={sorted(extra)}. Missing keys "
            f"silently fall back to another language via BCP 47; add the "
            f"translation in {locale}.ftl."
        )


@pytest.mark.architecture
def test_ftl_locales_share_identical_placeholders() -> None:
    """The same message must reference the same variables in every locale.

    A locale that drops a `{ $var }` renders incomplete text, and one that
    mistypes a variable name renders the bare key through the Fluent engine —
    neither case raises, so only this parity guard catches it.
    """
    locales = _locale_names()
    assert _REFERENCE_LOCALE in locales, (
        f"Reference locale {_REFERENCE_LOCALE}.ftl missing under {_LOCALES_DIR}"
    )
    bodies_by_locale = {locale: _message_bodies(locale) for locale in locales}
    reference = bodies_by_locale[_REFERENCE_LOCALE]

    for locale, bodies in bodies_by_locale.items():
        for key, body in reference.items():
            ref_placeholders = _placeholders(body)
            locale_placeholders = _placeholders(bodies[key])
            assert ref_placeholders == locale_placeholders, (
                f"Placeholder mismatch for `{key}` between {_REFERENCE_LOCALE} "
                f"and {locale}: reference={sorted(ref_placeholders)}, "
                f"{locale}={sorted(locale_placeholders)}. Missing or mistyped "
                f"variables silently render a bare key or truncated text."
            )


@pytest.mark.architecture
def test_ftl_locales_have_only_legal_references() -> None:
    """Every `{...}` group must be a valid Fluent reference.

    Bare identifiers like `{seconds:.0f}` (no `$` prefix) are not valid Fluent
    and cause the entire message to render as its key name.
    """
    for locale in _locale_names():
        for key, body in _message_bodies(locale).items():
            illegal = _illegal_references(body)
            assert not illegal, (
                f"[{locale}] `{key}` contains invalid Fluent references: {illegal}. "
                f"Use `{{ $var }}`, a function like `{{NUMBER($var)}}`, a `-`-prefixed "
                f"term, or a string literal like `{{ \"**\" }}`."
            )


def _source_files() -> list[Path]:
    """Every `.py` file under ``app/`` except generated/packaging paths."""
    return [
        p
        for p in _APP_DIR.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _referenced_keys() -> frozenset[str]:
    """Keys referenced as string literals anywhere in production source.

    Slash-command help text is looked up dynamically as ``cmd_<name>`` /
    ``cat_<category>`` in :func:`CommandRegistry.help_lines`, so those keys are
    validated against the live registry below rather than a literal scan.
    """
    keys = frozenset(_message_bodies(_REFERENCE_LOCALE))
    referenced: set[str] = set()
    for path in _source_files():
        text = path.read_text(encoding="utf-8")
        for key in keys:
            if f'"{key}"' in text or f"'{key}'" in text:
                referenced.add(key)
    return frozenset(referenced)


@pytest.mark.architecture
def test_ftl_locales_have_no_orphaned_keys() -> None:
    """Every message key must be reachable from production code.

    A key that exists in every locale but is never called renders nothing — it
    is dead weight that still has to be maintained (translated, kept in sync)
    across all four files.  ``cmd_*``/``cat_*`` are generated at runtime from
    ``SYSTEM_COMMANDS`` so they are validated through the registry in both
    directions: an orphaned ``cmd_*`` key (registered but never rendered) and
    a registered command missing its translation both break /help.
    """
    from app.channels.routing.command_defs import SYSTEM_COMMANDS

    keys = frozenset(_message_bodies(_REFERENCE_LOCALE))
    referenced = _referenced_keys()

    dynamic = {
        f"cmd_{cmd.name}" for cmd in SYSTEM_COMMANDS
    } | {
        f"cat_{cmd.category.replace(' ', '_')}" for cmd in SYSTEM_COMMANDS
    }

    orphaned = sorted(keys - referenced - dynamic)
    assert not orphaned, (
        f"Orphaned channel message keys: {orphaned}. These keys are translated "
        f"but never referenced by production code — either wire them up or "
        f"delete them from every locale file."
    )

    missing_cmd = sorted(
        f"cmd_{cmd.name}" for cmd in SYSTEM_COMMANDS if f"cmd_{cmd.name}" not in keys
    )
    missing_cat = sorted(
        f"cat_{cmd.category.replace(' ', '_')}"
        for cmd in SYSTEM_COMMANDS
        if f"cat_{cmd.category.replace(' ', '_')}" not in keys
    )
    assert not missing_cmd and not missing_cat, (
        f"Registered slash commands missing translations: "
        f"{missing_cmd + missing_cat}. The /help list falls back to the raw "
        f"English description for these commands; add the key to every locale "
        f"file."
    )


# Sample values used by the render-level guard.  Every message placeholder gets
# a value so the Fluent engine is forced to actually format the message instead
# of silently returning the bare key name.
_RENDER_SAMPLES: dict[str, str | int] = {
    "agent_id": "agent-1",
    "agent_label": "General",
    "aliases": "g,gen",
    "always_count": 1,
    "approve_count": 1,
    "attempt": 2,
    "bound_at": "2026-08-09",
    "bound_label": "bound",
    "cmd": "status",
    "command": "ls -la",
    "constraint": "no rm",
    "count": 3,
    "created_at": "2026-08-09",
    "daily_limit": 100,
    "description": "desc",
    "duration": "1m",
    "elapsed": "5",
    "emoji": "x",
    "error": "err",
    "error_category": "cat",
    "exit_code": 1,
    "filename": "a.txt",
    "files": 2,
    "from_agent": "A",
    "goal": "g",
    "hour": 2,
    "id": 1,
    "index": 0,
    "items": 2,
    "last_activity": "now",
    "max": 10,
    "max_pending": 3,
    "max_retries": 3,
    "max_turns": 5,
    "message_count": 10,
    "minutes": 5,
    "model_name": "gpt-4o",
    "name": "test",
    "objective": "task",
    "parts": 2,
    "pid": 123,
    "position": 1,
    "preview": "prev",
    "reason": "why",
    "reject_count": 0,
    "result": "ok",
    "scope": "chat",
    "seconds": 12,
    "session_id": "s1",
    "size": "1.5MB",
    "stage": "step",
    "status": "running",
    "steps": "a\nb",
    "style": "s",
    "target": "t",
    "task_id": "t1",
    "text": "text",
    "timeout": 30,
    "title": "t",
    "to_agent": "B",
    "today_cost": "$0.5",
    "tokens_saved": 100,
    "topic_hint": "hint",
    "total_calls": 5,
    "total_tokens": 1000,
    "total_usd": "$1",
    "turns": 3,
    "usage_pct": "50%",
    "used": 50,
    "workspace": "ws",
    "workspace_label": "（workdir）",
}


@pytest.mark.architecture
def test_ftl_messages_never_render_bare_keys() -> None:
    """Rendering a message with sample arguments must never produce a bare key.

    The structural guards above catch *static* issues, but a structurally valid
    message can still fail at render time — e.g. a multiline pattern whose first
    line starts with a selector character (`*`/`[`) parses as a broken entry and
    the Fluent engine returns the key name verbatim.  This guard formats every
    key in every locale and asserts the engine actually resolved it.
    """
    from app.channels.i18n import channel_t

    locales = _locale_names()
    assert _REFERENCE_LOCALE in locales
    reference = _message_bodies(_REFERENCE_LOCALE)

    for locale in locales:
        bodies = _message_bodies(locale)
        assert reference.keys() == bodies.keys()
        for key, body in bodies.items():
            placeholders = _placeholders(body)
            args = {name: _RENDER_SAMPLES[name] for name in placeholders}
            rendered = channel_t(locale, key, **args)
            assert rendered != key and rendered != "", (
                f"[{locale}] `{key}` rendered to {rendered!r} with args "
                f"{args}. Multiline patterns whose first line starts with `*` "
                f"or `[` fail to parse; escape them as `{{ \"**\" }}`/`{{ \"[\" }}`."
            )
