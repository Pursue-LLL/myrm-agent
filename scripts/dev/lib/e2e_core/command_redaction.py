"""Command-line redaction for rows that name the process behind a load spike.

[INPUT]
- a ps ``command`` column: argv joined by single spaces, so quoting is lost

[OUTPUT]
- redact_command(command, *, keep_arguments, home) -> str: a label that is safe to store

[POS]
The recorder's aggregate rows never carry a command line. A hotspot row has to name the
process that burned the CPU, and a command line is where tokens, keys, URLs with passwords and
inline code end up. With ``keep_arguments`` off only the program (the app bundle and process
type for Electron helpers) survives. With it on, arguments stay readable (test targets,
module names, ports) except: values of secret-named options and assignments, credential
headers, URL userinfo and secret query parameters, token-shaped strings, long opaque strings
(letters and digits, no path separators), and the program text after ``python -c`` or
``node -e``. The home directory prints as ``~``. This is a filter for local diagnostics, not a
guarantee: a secret that matches none of these shapes is kept.
"""

from __future__ import annotations

import os
import re
from collections.abc import Callable
from typing import Final

_REDACTED: Final = "<redacted>"
_MAX_TOKEN: Final = 100
_MAX_COMMAND: Final = 300
# Characters of one value (or of a bare command) the query-string and app-bundle patterns
# inspect: both backtrack quadratically on a long run (measured: 20k characters take 0.2 s,
# 40k take 0.7 s), so a pathological argv would otherwise stall the recorder.
_MAX_SCAN: Final = 1024
_MIN_OPAQUE_LENGTH: Final = 24
_MIN_PREFIXED_SECRET_LENGTH: Final = 12

_SECRET_NAME: Final = re.compile(
    r"token|secret|passw|pwd|key|auth|cookie|credential|bearer|signature|session",
    re.IGNORECASE,
)
_ASSIGNMENT: Final = re.compile(r"(-{0,2}[A-Za-z_][\w.-]*)=(.*)", re.DOTALL)
_HEADER_NAME: Final = re.compile(r"[A-Za-z][\w-]*:")
_AUTH_SCHEME: Final = re.compile(r"bearer|basic|digest|token", re.IGNORECASE)
_URL_USERINFO: Final = re.compile(r"(?<!\w)(\w+://)[^/@\s]+@")
_QUERY_SECRET: Final = re.compile(
    r"([?&;#][\w.-]*(?:token|secret|key|pass|auth|sig)[\w.-]*=)[^&\s#]*",
    re.IGNORECASE,
)
_TOKEN_PREFIX: Final = re.compile(
    r"(?:sk-|sk_|ghp_|gho_|ghu_|ghs_|github_pat_|glpat-|xox[abprs]-|AKIA[0-9A-Z]|eyJ"
    r"|pk_live|rk_live)"
)
_OPAQUE: Final = re.compile(r"[A-Za-z0-9_+=-]+")
_APP_BUNDLE: Final = re.compile(r"([^/]+\.app)/Contents/")
_PROCESS_TYPE: Final = re.compile(r"(?:^|\s)--type=([a-z][a-z-]{0,23})(?=\s|$)")

# Interpreter options come before the program: an option only counts there, so
# ``next dev -p 19460`` keeps its port while ``node -p "..."`` loses its code. Each option is
# (kind, text attached to it): "code" takes program text, "module" ends the options, "valued"
# takes one value that is not program text.
_PYTHON_ARGUMENT_OPTIONS: Final = {
    "c": "code",
    "m": "module",
    "W": "valued",
    "X": "valued",
}
_NODE_CODE: Final = frozenset({"-e", "--eval", "-p", "--print", "-pe", "-ep"})
_NODE_VALUED: Final = frozenset(
    {
        "-r",
        "--require",
        "--import",
        "--loader",
        "--experimental-loader",
        "-C",
        "--conditions",
    }
)
# pytest-xdist workers are execnet gateways whose whole program text is this line.
_EXECNET_BOOTSTRAP: Final = "import sys;exec(eval(sys.stdin.readline()))"


def _clip(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _looks_opaque(value: str) -> bool:
    """A long run of letters and digits with no path or module structure: a key, not a name."""
    return (
        len(value) >= _MIN_OPAQUE_LENGTH
        and _OPAQUE.fullmatch(value) is not None
        and any(char.isdigit() for char in value)
        and any(char.isalpha() for char in value)
    )


def _scrub_value(value: str, home: str) -> str:
    value = value[:_MAX_SCAN]
    if (
        _TOKEN_PREFIX.match(value) is not None
        and len(value) >= _MIN_PREFIXED_SECRET_LENGTH
    ):
        return _REDACTED
    value = _URL_USERINFO.sub(rf"\1{_REDACTED}@", value)
    value = _QUERY_SECRET.sub(rf"\1{_REDACTED}", value)
    if _looks_opaque(value):
        return _REDACTED
    if len(home) > 1:
        value = value.replace(home, "~")
    return _clip(value, _MAX_TOKEN)


def _scrub_assignment(token: str, home: str) -> str | None:
    match = _ASSIGNMENT.fullmatch(token)
    if match is None:
        return None
    name, value = match.groups()
    if _SECRET_NAME.search(name):
        return f"{name}={_REDACTED}"
    if not value.strip("="):
        # "word==" is a base64 word with its padding, not a name with an empty value.
        return _scrub_value(token, home)
    return f"{name}={_scrub_value(value, home)}"


def _python_option(token: str) -> tuple[str, str] | None:
    """A single-dash cluster whose first argument-taking letter decides it: ``-c``, ``-Bc``, ``-Xdev``."""
    if len(token) < 2 or token[0] != "-" or token[1] == "-":
        return None
    for position, letter in enumerate(token[1:], start=2):
        kind = _PYTHON_ARGUMENT_OPTIONS.get(letter)
        if kind is not None:
            return kind, token[position:]
    return None


def _node_option(token: str) -> tuple[str, str] | None:
    name, _, attached = token.partition("=")
    if name in _NODE_CODE:
        return "code", attached
    if token in _NODE_VALUED:
        return "valued", ""
    return None


def _option_reader(executable: str) -> Callable[[str], tuple[str, str] | None] | None:
    """The reader of an interpreter's program-text options; None for any other program."""
    if executable.lower().startswith("python"):
        return _python_option
    if executable == "node":
        return _node_option
    return None


def _code_label(program_text: str) -> str:
    if program_text == _EXECNET_BOOTSTRAP:
        return "<execnet-worker>"
    return f"<code {len(program_text)} chars>"


def _scrub_arguments(tokens: list[str], home: str) -> list[str]:
    executable = os.path.basename(tokens[0])
    out = [executable]
    read_option = _option_reader(executable)
    in_options = read_option is not None
    redact_next = False
    skip_next = False
    for index, token in enumerate(tokens[1:], start=1):
        option = read_option(token) if read_option is not None and in_options else None
        if redact_next:
            out.append(_REDACTED)
            # The credential follows the scheme word of "Authorization: Bearer <credential>".
            redact_next = _AUTH_SCHEME.fullmatch(token) is not None
        elif skip_next:
            out.append(_scrub_value(token, home))
            skip_next = False
        elif option is not None:
            kind, attached = option
            if kind == "code":
                text = " ".join([attached, *tokens[index + 1 :]]).strip()
                flag = token[: len(token) - len(attached)].rstrip("=")
                out.extend((flag, _code_label(text)))
                break
            out.append(token)
            if kind == "module":
                in_options = False
            else:
                skip_next = not attached
        elif (scrubbed := _scrub_assignment(token, home)) is not None:
            out.append(scrubbed)
        elif token.startswith("-"):
            out.append(token)
            redact_next = _SECRET_NAME.search(token) is not None
        elif _HEADER_NAME.fullmatch(token) and _SECRET_NAME.search(token):
            out.append(token)
            redact_next = True
        else:
            in_options = False
            out.append(_scrub_value(token, home))
        if len(" ".join(out)) > _MAX_COMMAND:
            break
    return out


def _bare_label(command: str, program: str) -> str:
    bundle = _APP_BUNDLE.search(command)
    label = bundle.group(1) if bundle else os.path.basename(program)
    process_type = _PROCESS_TYPE.search(command)
    return f"{label} [{process_type.group(1)}]" if process_type else label


def redact_command(command: str, *, keep_arguments: bool, home: str) -> str:
    """A storable label for ``command``; ``home`` is printed as ``~``."""
    tokens = command.split()
    if not tokens:
        return ""
    if not keep_arguments:
        return _bare_label(command[:_MAX_SCAN], tokens[0][:_MAX_SCAN])
    return _clip(" ".join(_scrub_arguments(tokens, home)), _MAX_COMMAND)
