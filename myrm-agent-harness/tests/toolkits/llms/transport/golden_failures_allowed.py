"""Registry of the failures the installed stack classifies or words differently from the previous one, each with its reason.

[INPUT]
- golden_compare::Allowed (POS: one entry: the facts that changed, with their new values, and why they are right)

[OUTPUT]
- HTTP_ALLOWED: the error replies (status, headers, body) whose verdict changed
- STREAM_ALLOWED: the 200 streams (an error event, an empty or garbage body) whose verdict changed

[POS]
A failure is classified once and the agent's recovery reads that verdict: repeat, switch key or provider, drop images,
compact, give up; the user reads the error card built from the same failure. An entry exists only where the new verdict
is the better input for that recovery or the better card for the user, or where the previous one came from reading a
field name or a number of the raw body as the provider's words; the reason says which. ``test_golden_failures`` fails
on a changed verdict with no entry, on an entry whose facts differ from what happens now, and on an entry whose case
no longer differs.
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
    "anthropic.kind_timeout_500": Allowed(
        {"card": "overloaded", "card_custom": "overloaded"},
        "A 500 is the provider failing, and the card says the service is overloaded. The previous stack showed the "
        "timeout card only because it read the word in the kind field of the raw body; a timeout kind comes with a 504, "
        "which keeps the timeout card (anthropic.kind_timeout_504).",
    ),
    "anthropic.kind_timeout_504": Allowed(
        {"reason": "overloaded", "kind": "overloaded"},
        "A 504 with a JSON body is filed with the provider being unavailable, as the previous stack already filed an "
        "HTML body and Gemini's: both reasons are transient and switch provider, only the probe schedule differs. The "
        "card still says the request timed out.",
    ),
    "anthropic.payload": Allowed(
        {"payload": True},
        "A 413 says the request is too large in bytes: the agent also drops historical images before it compacts text.",
    ),
    "anthropic.s404_kind_only": Allowed(
        {"card": "model", "card_custom": "custom_model_not_found"},
        "A 404 whose body holds no sentence leaves the status as all the provider said, and the card reads it as every "
        "wire does: a missing model.",
    ),
    "gemini.deadline": Allowed(
        {"card": "timeout", "card_custom": "timeout"},
        "A 504 is a gateway timeout, and the card says the request timed out and suggests streaming on every wire; the "
        "previous stack showed that card only for OpenAI-compatible endpoints and an overload card for Gemini.",
    ),
    "gemini.entity_not_found_404": Allowed(
        {"card": "unknown", "card_custom": "unknown"},
        "A 404 whose sentence names no model is not announced as a missing model: the previous stack read the numeric "
        "code field of the raw body as words, and the card now quotes the sentence the provider wrote.",
    ),
    "ollama.bad_request": Allowed(
        {"reason": "format", "kind": "format_error", "card": "format_error", "card_custom": "format_error"},
        "A 400 from Ollama is a refused request, not a lost connection: the agent stops repeating a request the server "
        "has already rejected, and the card quotes the refusal instead of announcing a timeout.",
    ),
    "ollama.not_found": Allowed(
        {"reason": "unknown", "kind": "unknown"},
        "A 404 naming a model that is not pulled is the server answering, not a connection failure: the recovery is the "
        "same transient retry, and the error card shows the server's own sentence instead of a timeout.",
    ),
    "ollama.server_500": Allowed(
        {"reason": "overloaded", "kind": "overloaded", "card": "overloaded", "card_custom": "overloaded"},
        "A 500 from a runner that died is the provider failing, so the agent retries or switches provider and the card "
        "says the service is overloaded; it is not a timeout of the connection.",
    ),
    "openai.code_unauthorized_400": Allowed(
        {"reason": "auth_permanent", "kind": "auth", "card": "api_key", "card_custom": "api_key"},
        "A body whose code says unauthorized is a rejected key even under a 400: the agent rotates the key instead of "
        "repeating the request and the card asks for a new one; the previous stack saw only the sentence and called "
        "the request malformed.",
    ),
    "openai.ctx_groq_tpm_413": Allowed(
        {"ctx": True, "payload": True},
        "Groq answers a request bigger than its per-minute token budget with a 413 and asks to reduce the message: "
        "shrinking the request is the recovery, since waiting cannot make that request fit.",
    ),
    "openai.policy_moonshot": Allowed(
        {"reason": "safety_block", "kind": "safety_block", "card": "safety_block", "card_custom": "safety_block"},
        "Moonshot's high-risk refusal is a content-policy block, so the agent hands the turn to its safety fallback "
        "model and the card says the safety filters blocked it, instead of treating it as a malformed request.",
    ),
    "openai.rl_503_capacity": Allowed(
        {"reason": "overloaded", "kind": "overloaded", "card": "overloaded", "card_custom": "overloaded"},
        "A 503 saying the tier is out of capacity is the provider being overloaded (the agent switches provider and "
        "the card says so), not this key's rate limit.",
    ),
    "openai.type_billing_400": Allowed(
        {"reason": "billing", "kind": "billing", "quota": True, "card": "billing", "card_custom": "billing"},
        "A body whose type says billing_error is an account problem even under a 400: the agent switches key or "
        "provider and the card points to billing; the previous stack saw only the sentence and called the request "
        "malformed.",
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
    "card": "unknown",
    "card_custom": "unknown",
}
_EMPTY_STREAM_WHY: Final = (
    "A 200 stream with no event (nothing, a bare [DONE], a gateway's HTML page) is no answer: the adapter retries it "
    "and then raises EmptyStreamError, whose card states the failure, instead of ending the turn with an empty reply."
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
            {"reason": "auth_permanent", "kind": "auth", "card": "api_key", "card_custom": "api_key"},
            "A rejected key reported inside the stream is an authentication failure (the key is rotated or disabled), "
            "not an overload the agent would retry with the same key; the card asks for a new key.",
        )
        for when in ("first", "after_text")
    },
    **{
        f"openai.err_{when}_server_error": Allowed(
            {"reason": "overloaded", "kind": "overloaded", "card": "overloaded", "card_custom": "overloaded"},
            "A server_error event is the provider failing, so the agent retries or switches provider and the card says "
            "the service is overloaded; it is not a timeout of the connection.",
        )
        for when in ("first", "after_text")
    },
}
