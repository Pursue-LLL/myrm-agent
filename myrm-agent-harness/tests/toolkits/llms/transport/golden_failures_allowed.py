"""Registry of the failures the installed stack classifies differently from the previous one, each with its reason.

[INPUT]
- golden_compare::Allowed (POS: one entry: the facts that changed, with their new values, and why they are right)

[OUTPUT]
- HTTP_ALLOWED: the error replies (status, headers, body) whose verdict changed
- STREAM_ALLOWED: the 200 streams (an error event, an empty or garbage body) whose verdict changed

[POS]
A failure is classified once and the agent's recovery reads that verdict: repeat, switch key or provider, drop images,
compact, give up. An entry exists only where the new verdict is the better input for that recovery; the reason says
why. ``test_golden_failures`` fails on a changed verdict with no entry, on an entry whose facts differ from what
happens now, and on an entry whose case no longer differs.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from .golden_compare import Allowed

HTTP_ALLOWED: Final[Mapping[str, Allowed]] = {
    "anthropic.ctx_anthropic_bedrock_style": Allowed(
        {"reason": "context_overflow", "kind": "context_overflow", "ctx": True},
        "Bedrock's wording for an over-long prompt, sent through the Anthropic wire, is a context overflow: the agent "
        "compacts instead of treating the request as malformed.",
    ),
    "anthropic.payload": Allowed(
        {"payload": True},
        "A 413 says the request is too large in bytes: the agent also drops historical images before it compacts text.",
    ),
    "ollama.bad_request": Allowed(
        {"reason": "format", "kind": "format_error"},
        "A 400 from Ollama is a refused request, not a lost connection: the agent stops repeating a request the server "
        "has already rejected.",
    ),
    "ollama.not_found": Allowed(
        {"reason": "unknown", "kind": "unknown"},
        "A 404 naming a model that is not pulled is the server answering, not a connection failure: the recovery is the "
        "same transient retry, and the error card shows the server's own sentence instead of a timeout.",
    ),
    "ollama.server_500": Allowed(
        {"reason": "overloaded", "kind": "overloaded"},
        "A 500 from a runner that died is the provider failing, so the agent retries or switches provider; it is not a "
        "timeout of the connection.",
    ),
    "openai.ctx_groq_tpm_413": Allowed(
        {"ctx": True, "payload": True},
        "Groq answers a request bigger than its per-minute token budget with a 413 and asks to reduce the message: "
        "shrinking the request is the recovery, since waiting cannot make that request fit.",
    ),
    "openai.policy_moonshot": Allowed(
        {"reason": "safety_block", "kind": "safety_block"},
        "Moonshot's high-risk refusal is a content-policy block, so the agent hands the turn to its safety fallback "
        "model instead of treating the refusal as a malformed request.",
    ),
    "openai.rl_503_capacity": Allowed(
        {"reason": "overloaded", "kind": "overloaded"},
        "A 503 saying the tier is out of capacity is the provider being overloaded (the agent switches provider), "
        "not this key's rate limit.",
    ),
}

# What a stream that completed empty before reports now: the adapter's EmptyStreamError, which blames no provider fault.
_RAISES_EMPTY_STREAM: Final[Mapping[str, object]] = {
    "outcome": "RAISED",
    "text": None,
    "partial": "",
    "reason": "unknown",
    "kind": "unknown",
    "ctx": False,
    "payload": False,
    "quota": False,
}
_EMPTY_STREAM_WHY: Final = (
    "A 200 stream with no event (nothing, a bare [DONE], a gateway's HTML page) is no answer: the adapter retries it "
    "and then raises EmptyStreamError, instead of ending the turn with an empty reply."
)

STREAM_ALLOWED: Final[Mapping[str, Allowed]] = {
    **{
        case: Allowed(_RAISES_EMPTY_STREAM, _EMPTY_STREAM_WHY)
        for case in (
            "anthropic.empty_stream",
            "anthropic.garbage_html",
            "gemini.empty_stream",
            "openai.empty_stream",
            "openai.garbage_html",
            "openai.only_done",
        )
    },
    **{
        f"anthropic.err_{when}_authentication_error": Allowed(
            {"reason": "auth_permanent", "kind": "auth"},
            "A rejected key reported inside the stream is an authentication failure (the key is rotated or disabled), "
            "not an overload the agent would retry with the same key.",
        )
        for when in ("first", "after_text")
    },
    **{
        f"openai.err_{when}_server_error": Allowed(
            {"reason": "overloaded", "kind": "overloaded"},
            "A server_error event is the provider failing, so the agent retries or switches provider; it is not a "
            "timeout of the connection.",
        )
        for when in ("first", "after_text")
    },
}
