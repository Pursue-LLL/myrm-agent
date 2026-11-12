"""LangChain chat-model adapter sub-package.

Aggregates the aggregate root (``model``) with its generation mixins and
exception types.

[OUTPUT]
- model: TransportChatModel (LangChain-compatible chat model aggregate root), clean_model_kwargs
- async_mixin / async_stream_mixin / sync_mixin / message_mixin: generation and message assembly mixins
- exceptions: EmptyChoicesError, EmptyStreamError, StreamStallTimeoutError, adapter constants

[POS]
LangChain chat-model adapter layer.
"""

from .exceptions import (
    DEVELOPER_ROLE_PATTERN,
    EmptyChoicesError,
    EmptyStreamError,
    StreamStallTimeoutError,
)
from .model import TransportChatModel, clean_model_kwargs

__all__ = [
    "DEVELOPER_ROLE_PATTERN",
    "TransportChatModel",
    "EmptyChoicesError",
    "EmptyStreamError",
    "StreamStallTimeoutError",
    "clean_model_kwargs",
]
