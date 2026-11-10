"""XML tool-call tag interception for streamed text

[INPUT]
- (stdlib only)

[OUTPUT]
- XmlStreamBuffer: State machine buffer for intercepting DSML tags across streaming chunks.

[POS]
Keeps provider-emitted pseudo tool-call markup (DSML, ``<tool_call>``, ``<invoke>``) out of the text a stream yields,
including a tag that arrives split across chunks. The stream mixins own one buffer per text channel.
"""

from __future__ import annotations

import re


class XmlStreamBuffer:
    """State machine buffer for intercepting DSML tags across streaming chunks.

    Prevents DSML tags (like <｜DSML｜tool_calls> or <｜｜DSML｜｜tool_calls>) from
    leaking into the yielded stream by buffering text when a potential tag is detected.
    """

    __slots__ = (
        "buffer",
        "end_tag_pattern",
        "is_swallowing",
        "start_tag_pattern",
    )

    def __init__(self) -> None:
        self.buffer: str = ""
        self.is_swallowing: bool = False

        self.start_tag_pattern = re.compile(
            r"^(?:<[｜|]+DSML[｜|]+tool_calls>|<tool_call>|<invoke(?:\s+name=[\"'][^\"']*[\"'])?>)"
        )
        self.end_tag_pattern = re.compile(r"(?:</[｜|]+DSML[｜|]+tool_calls>|</tool_call>|</invoke>)")

    def _is_prefix_of_start_tag(self, s: str) -> bool:
        if not s.startswith("<"):
            return False
        if s == "<":
            return True

        clean_s = s.replace("｜", "").replace("|", "")
        if "<DSMLtool_calls>".startswith(clean_s):
            return True
        if "<DSMLinvoke".startswith(clean_s):
            return True

        if "<tool_call>".startswith(s):
            return True

        if "<invoke".startswith(s):
            return True

        return bool(re.match(r"^<invoke(?:\s+(?:n(?:a(?:m(?:e(?:=(?:[\"'][^\"']*[\"']?)?)?)?)?)?)?)?$", s))

    def process(self, text: str) -> str:
        if not text:
            return ""

        if self.is_swallowing:
            self.buffer += text
            match = self.end_tag_pattern.search(self.buffer)
            if match:
                end_pos = match.end()
                remaining = self.buffer[end_pos:]
                self.buffer = ""
                self.is_swallowing = False
                return self.process(remaining)
            return ""

        self.buffer += text
        pos = self.buffer.find("<")

        if pos == -1:
            res = self.buffer
            self.buffer = ""
            return res

        safe_text = self.buffer[:pos]
        potential_tag = self.buffer[pos:]

        match = self.start_tag_pattern.search(potential_tag)
        if match:
            self.is_swallowing = True
            self.buffer = potential_tag
            return safe_text + self.process("")

        if self._is_prefix_of_start_tag(potential_tag):
            self.buffer = potential_tag
            return safe_text

        self.buffer = potential_tag[1:]
        return safe_text + "<" + self.process("")

    def flush(self) -> str:
        res = self.buffer if not self.is_swallowing else ""
        self.buffer = ""
        self.is_swallowing = False
        return res
