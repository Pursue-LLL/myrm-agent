"""Wire-encodability of the messages of one request: no string value UTF-8 cannot encode leaves the process.

Python hands a file name or output that was not valid UTF-8 back as text holding lone surrogates (``os.fsdecode`` maps
an undecodable byte to ``U+DC80``..``U+DCFF``). Such a string cannot be encoded, so the HTTP client raises while it
builds the request body and the provider SDK reports an opaque server error. The conversation history is re-sent on every
model call, so one such string breaks every later call of that conversation, whatever the model is asked.

[INPUT]
- (none — stdlib only: re)

[OUTPUT]
- replace_lone_surrogates: rewrite every unencodable string value of the wire messages of one request (nested in dicts and lists) to ``U+FFFD``, in place

[POS]
Last pure step of the message funnel of ``ChatLiteLLM``, run before the outbound guard so a policy sees the text that is
actually sent. A string that is already encodable is left as the same object, so the request bytes (and with them the
provider prompt cache) do not change for any ordinary history.
"""

from __future__ import annotations

import re

_LONE_SURROGATE = re.compile("[\ud800-\udfff]")
_REPLACEMENT = "\ufffd"


def _encodable(text: str) -> str:
    """*text* itself when UTF-8 can encode it, else a copy with each lone surrogate replaced."""
    if text.isascii():
        return text
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        return _LONE_SURROGATE.sub(_REPLACEMENT, text)
    return text


def _scrub(value: object) -> object:
    """*value* with every string inside it made encodable; containers are rewritten in place and returned."""
    if isinstance(value, str):
        return _encodable(value)
    if isinstance(value, dict):
        for key, item in value.items():
            cleaned = _scrub(item)
            if cleaned is not item:
                value[key] = cleaned
    elif isinstance(value, list):
        for index, item in enumerate(value):
            cleaned = _scrub(item)
            if cleaned is not item:
                value[index] = cleaned
    return value


def replace_lone_surrogates(message_dicts: list[dict[str, object]]) -> None:
    """Make every string value of the wire messages encodable as UTF-8, replacing each lone surrogate with ``U+FFFD``.

    Dict keys and tuples are not visited.
    """
    _scrub(message_dicts)
