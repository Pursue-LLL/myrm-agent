"""Archiving of a pruned tool result: the full text goes to the offload store once, a restorable reference replaces it.

[INPUT]
- infra.schemas::ContextCompressOffloadCallback, ContextOffloadResult, normalize_context_offload_result (POS: the offload store contract)
- pipeline.base::ProcessorContext (POS: the run a pass belongs to)
- processors.cache_ttl_prune_helpers::ArchiveAttempt, build_archived_placeholder (POS: attempt outcome and the reference text)

[OUTPUT]
- ToolResultArchiver: offload a tool result through the host's callback, at most once per chat, tool call and content

[POS]
Archive half of the TTL prune. The host supplies the store; this class owns the idempotency cache that keeps a retried
pass from writing the same payload again, and tells the host whenever the store answered so it can queue a summary.
"""

from collections import OrderedDict
from collections.abc import Callable
from hashlib import sha256

from langchain_core.messages import ToolMessage

from myrm_agent_harness.utils.logger_utils import get_agent_logger

from ...infra.schemas import (
    ContextCompressOffloadCallback,
    ContextOffloadResult,
    normalize_context_offload_result,
)
from ..base import ProcessorContext
from .cache_ttl_prune_helpers import ArchiveAttempt, build_archived_placeholder

logger = get_agent_logger(__name__)

_OFFLOAD_IDEMPOTENCY_CACHE_LIMIT = 512


class ToolResultArchiver:
    """Offloads tool results through the host's callback; the same tool call's content in the same chat is stored once.

    ``on_stored`` is called with the message, its text, the archive path and the run's context whenever the offload
    callback has just answered with a path; a payload this archiver stored before is answered from its cache instead.
    """

    def __init__(
        self,
        offload: ContextCompressOffloadCallback | None,
        *,
        estimate_tokens: Callable[[str], int],
        on_stored: Callable[[ToolMessage, str, str, ProcessorContext], None],
    ) -> None:
        self._offload = offload
        self._estimate_tokens = estimate_tokens
        self._on_stored = on_stored
        self._offload_result_cache: OrderedDict[str, ContextOffloadResult] = OrderedDict()

    async def try_archive(
        self,
        *,
        msg: ToolMessage,
        content: str,
        context: ProcessorContext,
    ) -> ArchiveAttempt:
        """Archive full content and replace the message with a restorable reference."""
        if self._offload is None:
            return ArchiveAttempt(archived=False, failure_kind="unsupported")

        tool_name = msg.name or "unknown"
        cache_key = None
        scope_id = context.chat_id
        if scope_id:
            cache_key = self._offload_cache_key(
                msg=msg,
                tool_name=tool_name,
                content=content,
                context=context,
            )
            cached_result = self._get_cached_offload_result(cache_key)
            if cached_result is not None:
                return self._build_archive_attempt(
                    tool_name=tool_name,
                    archive_path=cached_result.path,
                    content=content,
                    offload_reused=True,
                    original_bytes=cached_result.original_bytes,
                    stored_bytes=cached_result.stored_bytes,
                )

        try:
            offload_result = normalize_context_offload_result(
                await self._offload(
                    content=content,
                    tool_name=tool_name,
                    scope_id=scope_id,
                )
            )
        except Exception as exc:
            logger.warning(
                "[CacheTtlPrune] offload failed for tool=%s: %s",
                tool_name,
                exc,
            )
            return ArchiveAttempt(archived=False, failure_kind="temporary_failure")

        if not offload_result.succeeded:
            if offload_result.message:
                logger.warning(
                    "[CacheTtlPrune] offload denied for tool=%s kind=%s: %s",
                    tool_name,
                    offload_result.failure_kind,
                    offload_result.message,
                )
            return ArchiveAttempt(
                archived=False,
                failure_kind=offload_result.failure_kind or "temporary_failure",
            )

        self._on_stored(msg, content, offload_result.path, context)

        if cache_key is not None:
            self._remember_successful_offload(cache_key, offload_result)
        return self._build_archive_attempt(
            tool_name=tool_name,
            archive_path=offload_result.path,
            content=content,
            offload_reused=offload_result.reused,
            original_bytes=offload_result.original_bytes,
            stored_bytes=offload_result.stored_bytes,
        )

    def _offload_cache_key(
        self,
        *,
        msg: ToolMessage,
        tool_name: str,
        content: str,
        context: ProcessorContext,
    ) -> str:
        """Build a scoped idempotency key for retry-safe archive offload."""
        content_sha = sha256(content.encode("utf-8")).hexdigest()
        parts = [
            context.chat_id or "",
            tool_name,
            msg.tool_call_id or "",
            str(len(content)),
            content_sha,
        ]
        return "\0".join(parts)

    def _get_cached_offload_result(self, cache_key: str) -> ContextOffloadResult | None:
        result = self._offload_result_cache.get(cache_key)
        if result is None:
            return None
        self._offload_result_cache.move_to_end(cache_key)
        return result

    def _remember_successful_offload(
        self,
        cache_key: str,
        offload_result: ContextOffloadResult,
    ) -> None:
        self._offload_result_cache[cache_key] = offload_result
        self._offload_result_cache.move_to_end(cache_key)
        while len(self._offload_result_cache) > _OFFLOAD_IDEMPOTENCY_CACHE_LIMIT:
            self._offload_result_cache.popitem(last=False)

    def _build_archive_attempt(
        self,
        *,
        tool_name: str,
        archive_path: str,
        content: str,
        offload_reused: bool,
        original_bytes: int = 0,
        stored_bytes: int = 0,
    ) -> ArchiveAttempt:
        placeholder = build_archived_placeholder(
            tool_name=tool_name,
            archive_path=archive_path,
            content=content,
            original_tokens=self._estimate_tokens(content),
            original_chars=len(content),
        )
        return ArchiveAttempt(
            archived=True,
            replacement_content=placeholder,
            offload_reused=offload_reused,
            original_bytes=original_bytes,
            stored_bytes=stored_bytes,
        )
