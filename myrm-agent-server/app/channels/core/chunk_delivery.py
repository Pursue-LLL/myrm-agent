"""Ordered delivery of the chunks of one reply, for providers that post each chunk as its own request.

[INPUT]
- channels.core.exceptions::ChannelSendError (POS: delivery failure with partial-delivery markers)
- channels.reliability.retry::send_with_retry, RetryConfig (POS: retry with backoff, jitter and retry-after)

[OUTPUT]
- ChunkChannel: the name and retry policy chunk delivery reads from a channel
- deliver_chunks(): send the chunks in order; a chunk after the first is retried alone, and one that still fails is a partial delivery

[POS]
A provider's ``send()`` splits the reply with ``render()`` and calls ``deliver_chunks`` instead of looping
over the chunks itself. The message bus retries a failed ``send()`` as a whole, which is right while nothing
has arrived and wrong afterwards: the chunks the recipient already holds would be sent again. So only the
first chunk is left to the bus; every later chunk is retried by itself with the channel's own retry policy,
and one that still fails raises ``ChannelSendError(accepted=True)``, the partial delivery the bus never replays.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Protocol, TypeVar

from app.channels.core.exceptions import ChannelSendError
from app.channels.reliability.retry import RetryConfig, send_with_retry

_C = TypeVar("_C")


class ChunkChannel(Protocol):
    """What chunk delivery needs of a channel: its name and the retry policy it already declares."""

    @property
    def name(self) -> str: ...

    @property
    def retry_config(self) -> RetryConfig: ...

    def should_retry(self, exc: BaseException) -> bool: ...

    def extract_retry_after(self, exc: BaseException) -> float | None: ...


async def deliver_chunks(
    channel: ChunkChannel,
    chunks: Sequence[_C],
    send_chunk: Callable[[_C, int], Awaitable[str | None]],
) -> str | None:
    """Send ``chunks`` in order with ``send_chunk(chunk, index)``; return the last id the platform reported.

    ``send_chunk`` raises ``ChannelSendError`` (or an error the channel's ``should_retry`` classifies) when the
    platform does not take a chunk. A failure of the first chunk propagates as it is: nothing has arrived, so
    the bus retries the whole message. A later chunk is retried alone; when it still fails the error is a
    partial delivery that names how many chunks arrived.
    """
    last_id: str | None = None
    total = len(chunks)
    for index, chunk in enumerate(chunks):
        if index == 0:
            sent = await send_chunk(chunk, index)
        else:
            try:
                sent = await send_with_retry(
                    send_chunk,
                    chunk,
                    index,
                    config=channel.retry_config,
                    should_retry=channel.should_retry,
                    extract_retry_after=channel.extract_retry_after,
                    label=f"{channel.name}:chunk {index + 1}/{total}",
                )
            except Exception as exc:
                raise ChannelSendError.for_text_chunks(channel.name, delivered=index, total=total, cause=exc) from exc
        last_id = sent or last_id
    return last_id
