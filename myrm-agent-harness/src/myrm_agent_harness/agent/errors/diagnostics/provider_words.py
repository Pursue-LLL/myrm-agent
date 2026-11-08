"""The provider's words in an LLM exception, as the diagnostic engine reads and shows them.

[INPUT]
- core.security.redact::redact_sensitive_text (POS: Secret redaction of text shown to users and logs)
- toolkits.llms.errors.error_payload::is_json_shaped, provider_error_message (POS: The one reader of the provider's answer in an LLM exception)
- toolkits.llms.transport::LLMCallError (POS: the failures of a model call, whose text is a provider's answer behind the transport's framing)

[OUTPUT]
- keyword_text: the lowercased text the engine's keyword families read
- provider_message: the provider's own words as one clean line, ``None`` when the provider said nothing
- error_text: the text of an unclassified failure as one clean line

[POS]
Text half of the diagnostic engine. The engine decides which card an error gets; this module decides which words the
error is read by and which of the provider's words a card quotes: from the payload the exception carries, else from the
exception text with its library framing removed, then presented to a user (page markup removed, secrets masked, cut
to a line).
"""

import html
import json
import re

from myrm_agent_harness.core.security.redact import redact_sensitive_text
from myrm_agent_harness.toolkits.llms.errors.error_payload import is_json_shaped, provider_error_message
from myrm_agent_harness.toolkits.llms.transport import LLMCallError

# Framing in front of the provider's words: the model transport's own ("openai API error 400: ", "anthropic stream
# error: ", "openai answer error: "), a LiteLLM proxy's relayed exception class ("litellm.BadRequestError: ") and provider tag
# ("OpenAIException - ", "AzureException BadRequestError - "), the OpenAI SDK's status line ("Error code: 400 - ", or
# "Error code: 400" alone when the SDK leaves the body out of the text). The `provider` group is non-empty only when
# the provider's framing is present.
_LLM_LIBRARY_PREFIX = re.compile(
    r"^(?:litellm\.[A-Za-z]+Error:\s*)*"
    r"(?P<provider>[\w.-]+\s+(?:API error\s+\d{3}|(?:stream|answer) error):\s*"
    r"|(?:[A-Za-z]+Exception(?:\s+[A-Za-z]+Error)?\s+-\s+)?(?:Error code:\s*\d{3}(?:\s+-\s+|\s*$))?)"
)
# The human sentence inside a JSON or Python-dict error body: `{"error": {"message": "..."}}`. Each quote style
# has its own branch and an escape pair never overlaps a plain character, so a body cut off mid-string fails in
# linear time instead of retrying every way to split a run of backslashes.
_MESSAGE_FIELD = re.compile(
    r"""["']message["']\s*:\s*(?:"(?P<double>(?:\\.|[^"\\])*)"|'(?P<single>(?:\\.|[^'\\])*)')""", re.DOTALL
)
# The escapes of a Python dict repr: \xNN, \uNNNN, \UNNNNNNNN, or a backslash before any one character.
_ESCAPE = re.compile(r"\\(?:x([0-9a-fA-F]{2})|u([0-9a-fA-F]{4})|U([0-9a-fA-F]{8})|(.))", re.DOTALL)
_HTML_DOCUMENT = re.compile(r"<\s*(?:!doctype|html|head|body)\b", re.IGNORECASE)
_HTML_NON_TEXT = re.compile(r"<(script|style)\b.*?(?:</\1\s*>|$)", re.IGNORECASE | re.DOTALL)
_HTML_TAG = re.compile(r"<[^>]*>")
# Bounds the work done on a provider page; the shown text is cut to _MAX_ERROR_MESSAGE_CHARS afterwards.
_MAX_ERROR_SOURCE_CHARS = 2000
_MAX_ERROR_MESSAGE_CHARS = 200


def _unescape(text: str) -> str:
    """Decode the escapes of a Python-repr string; a code point that is not a character stays as written."""

    def decode(match: re.Match[str]) -> str:
        digits = match.group(1) or match.group(2) or match.group(3)
        if digits is None:
            return " " if match.group(4) in "nrt" else match.group(4)
        code = int(digits, 16)
        return chr(code) if code <= 0x10FFFF and not 0xD800 <= code <= 0xDFFF else match.group(0)

    return _ESCAPE.sub(decode, text)


def _unescape_json(text: str) -> str:
    """Decode the escapes of the inside of a JSON string, surrogate pairs included."""
    try:
        decoded = json.loads(f'"{text}"')
    except ValueError:
        return _unescape(text)
    return decoded if isinstance(decoded, str) else text


def _embedded_message(raw: str) -> str | None:
    """The provider's words inside exception text: a body's `message` field, the text after provider framing, or a page.

    Framing followed by a bare JSON payload yields nothing: data with no sentence in it is not for a user.
    """
    field = _MESSAGE_FIELD.search(raw)
    if field:
        double = field.group("double")
        return _unescape_json(double) if double is not None else _unescape(field.group("single"))
    prefix = _LLM_LIBRARY_PREFIX.match(raw)
    if prefix and prefix.group("provider"):
        words = raw[prefix.end() :]
        return None if is_json_shaped(words) else words
    return raw if _HTML_DOCUMENT.search(raw) else None


def _provider_words(exc: Exception, raw: str) -> str | None:
    """What the provider said, from its payload when the exception carries one, else from the exception text."""
    return provider_error_message(exc) or _embedded_message(raw)


def _present(text: str) -> str:
    """One line a user can read: page markup removed, secrets masked, whitespace collapsed, cut with an ellipsis.

    Redaction runs before the cut so a credential is never left half-shown at the boundary.
    """
    if _HTML_DOCUMENT.search(text):
        text = html.unescape(_HTML_TAG.sub(" ", _HTML_NON_TEXT.sub(" ", text)))
    text = " ".join(redact_sensitive_text(text).split())
    if len(text) <= _MAX_ERROR_MESSAGE_CHARS:
        return text
    return text[:_MAX_ERROR_MESSAGE_CHARS].rstrip() + "…"


def provider_message(exc: Exception) -> str | None:
    """The provider's own words as one clean line, or ``None`` when the provider said nothing."""
    words = _provider_words(exc, str(exc)[:_MAX_ERROR_SOURCE_CHARS])
    return _present(words[:_MAX_ERROR_SOURCE_CHARS]) or None if words else None


def error_text(exc: Exception) -> str:
    """The text of an unclassified failure as one clean line: the provider's words, else the exception's own text.

    Text that is only a rendering of data names the exception instead.
    """
    raw = str(exc)[:_MAX_ERROR_SOURCE_CHARS]
    words = _provider_words(exc, raw)
    if not words:
        words = _LLM_LIBRARY_PREFIX.sub("", raw)
        if is_json_shaped(words):
            words = ""
    return _present(words[:_MAX_ERROR_SOURCE_CHARS]) or type(exc).__name__


def keyword_text(exc: Exception) -> str:
    """The lowercased text the keyword families read.

    A transport failure the provider put into words is read by that sentence alone (a plain-text page when it sent
    one), never by the transport's framing ("openai API error 429: ") or the fields of a JSON body. The status digits
    and the numeric ``code`` of a body are data the shared classifier weighs against the payload; read as words they
    would turn a billing refusal sent with a 429 into a rate limit, a 403 that says "rate limiting" into a rejected key
    and any 404 into a missing model. A transport failure the provider put no words to is read by its text, whose
    framing then carries the status, all the provider said. Any other exception is read by its text and class.
    """
    said = provider_error_message(exc) if isinstance(exc, LLMCallError) else None
    if said is not None:
        return said[:_MAX_ERROR_SOURCE_CHARS].lower()
    return f"{exc} {exc!r}".lower()
