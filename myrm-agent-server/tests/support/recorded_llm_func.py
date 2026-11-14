"""An extraction LLM function that remembers whether the model ever answered, for live tests.

[INPUT]
- collections.abc::Awaitable, Callable (POS: shape of the harness extraction LLM function ``(system, prompt) -> text``)

[OUTPUT]
- RecordedLlmFunc: wraps an extraction LLM function; ``answered`` says whether the model returned any text,
  ``require_answer`` fails the test naming the last error when it did not

[POS]
Server pytest-only helper for live extraction tests. The extractors log a failing model call and return an empty result,
so an empty result alone cannot tell "the model judged nothing worth keeping" from "the model never answered". Wrapping the
function the extractor calls makes that difference observable, so a test neither passes nor skips on a model that was silent.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

LlmFunc = Callable[[str, str], Awaitable[str]]


class RecordedLlmFunc:
    """Forwards every call to ``inner`` and keeps the replies and the last error."""

    def __init__(self, inner: LlmFunc) -> None:
        self._inner = inner
        self.replies: list[str] = []
        self.last_error: Exception | None = None

    async def __call__(self, system: str, prompt: str) -> str:
        try:
            reply = await self._inner(system, prompt)
        except Exception as exc:
            self.last_error = exc
            raise
        self.replies.append(reply)
        return reply

    @property
    def answered(self) -> bool:
        """Whether the model returned any text at all; whitespace is no answer."""
        return any(reply.strip() for reply in self.replies)

    def require_answer(self) -> None:
        """Fail the calling test when the model never answered, naming why."""
        assert self.answered, f"the model returned no reply, so nothing can be concluded (last error: {self.last_error!r})"
