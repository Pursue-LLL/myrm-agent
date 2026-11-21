"""A multi-line command result as the model is shown it once the real guardrail middleware has screened it.

The tool result reaches the guardrail as JSON text, where each line break is the two characters backslash and ``n``.
Lines that hold no space (names in a listing, a header and a value) must not read as one random-looking token, and a
secret that is masked must take no neighbouring line with it.
"""

from __future__ import annotations

import json

from tests.agent.meta_tools.bash.guardrail_view import shown_to_model

# What `ls -la` printed in a workspace while a command ran: the shell session's script is listed too.
_LISTING = "\n".join(
    [
        "/work",
        "total 40",
        "drwxr-xr-x@ 6 user  staff    192 Nov 18 18:52 .",
        "drwxr-xr-x@ 5 user  staff    160 Nov 18 18:52 ..",
        "drwxr-xr-x@ 3 user  staff     96 Nov 18 18:52 .myrm",
        "-rwx------@ 1 user  staff  11559 Nov 18 18:52 .myrm_exec_6bd1b0fd795043be89d374bedb731800.sh",
        "-rw-r--r--@ 1 user  staff     12 Nov 18 18:52 hello.txt",
        "-rw-r--r--@ 1 user  staff    825 Nov 18 18:52 usage_ledger.jsonl",
        "---",
        "HELLO383506",
        "---",
        "Python 3.13.13",
    ]
)


def test_a_workspace_listing_reaches_the_model_whole() -> None:
    result = {"content": _LISTING, "metadata": {}}

    assert shown_to_model(result) == json.dumps(result)


def test_a_secret_is_masked_and_the_lines_around_it_reach_the_model() -> None:
    output = "\n".join(["build started", "export OPENAI_API_KEY=abcdef0123456789abcdef", "echo done", "build finished"])

    shown = json.loads(shown_to_model({"content": output, "metadata": {}}))["content"].split("\n")

    assert shown[0] == "build started"
    assert "abcdef0123456789abcdef" not in shown[1]
    assert shown[2:] == ["echo done", "build finished"]
