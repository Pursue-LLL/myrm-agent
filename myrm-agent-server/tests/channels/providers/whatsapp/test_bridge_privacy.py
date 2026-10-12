"""The WhatsApp bridge must not write message content or account identities to its output streams.

The host logs every bridge stderr line (INFO, or ERROR when the line mentions "error"), and stdout carries the
JSON event protocol, so a console call that interpolates a value either leaks it into the server log or
corrupts the stream. Only fixed text is allowed.
"""

from __future__ import annotations

import re

from app.channels.providers.whatsapp.helpers import _BRIDGE_SCRIPT

_CONSOLE_CALL = re.compile(r"console\.\w+\(|process\.stderr\.write\(")
_FIXED_TEXT_CALL = re.compile(r"""(?:console\.\w+|process\.stderr\.write)\(\s*(["'])[^"'`$\\]*\1\s*\)\s*;""")


def _calls_with_dynamic_arguments(source: str) -> list[str]:
    return [line.strip() for line in source.splitlines() if _CONSOLE_CALL.search(line) and not _FIXED_TEXT_CALL.search(line)]


def test_detector_flags_values_and_template_strings() -> None:
    sample = "\n".join(
        [
            "console.error('Connection OPEN', selfJid);",
            "console.error(`message: ${text}`);",
            "process.stderr.write(JSON.stringify(event));",
            "console.error('Connection open');",
        ]
    )

    assert _calls_with_dynamic_arguments(sample) == [
        "console.error('Connection OPEN', selfJid);",
        "console.error(`message: ${text}`);",
        "process.stderr.write(JSON.stringify(event));",
    ]


def test_bridge_script_writes_only_fixed_text_to_the_console() -> None:
    assert _calls_with_dynamic_arguments(_BRIDGE_SCRIPT.read_text(encoding="utf-8")) == []


def test_baileys_logger_stays_silent() -> None:
    assert 'pino({ level: "silent" })' in _BRIDGE_SCRIPT.read_text(encoding="utf-8")
