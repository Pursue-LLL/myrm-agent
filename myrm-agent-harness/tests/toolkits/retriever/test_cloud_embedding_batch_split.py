"""Tests for CloudEmbedding batch splitting logic."""

from __future__ import annotations

from collections.abc import Sequence
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding import (
    _MAX_CHARS_PER_BATCH,
    _MAX_TEXTS_PER_BATCH,
    CloudEmbedding,
)
from myrm_agent_harness.toolkits.retriever.embedding.window_policy import SAFETY_MARGIN

_AEMBED = "myrm_agent_harness.toolkits.retriever.embedding.cloud_embedding.aembed"

# Cloudflare Workers AI answers HTTP 400 (code 8007) above this many tokens in one bge-m3 request.
_CLOUDFLARE_REQUEST_TOKEN_CAP = 60_000
# The chunk size bge-m3 gets from the embed budget (0.9 of its 8192 window).
_BGE_M3_CHUNK_CHARS = 7_372
_CLOUDFLARE_ENDPOINT = "https://api.cloudflare.com/client/v4/accounts/account-id/ai/v1"


def _vectors(count: int, dim: int = 1536) -> list[list[float]]:
    return [[0.1] * dim for _ in range(count)]


@pytest.fixture()
def service() -> CloudEmbedding:
    return CloudEmbedding(model="text-embedding-3-small", api_key="test-key")


class TestSplitIntoBatches:
    """Unit tests for _split_into_batches static method."""

    def test_small_batch_no_split(self) -> None:
        texts = ["hello"] * 10
        batches = CloudEmbedding._split_into_batches(texts)
        assert batches == [texts]

    def test_split_by_count(self) -> None:
        texts = ["short"] * 100
        batches = CloudEmbedding._split_into_batches(texts)
        assert len(batches) == 4  # 32 + 32 + 32 + 4
        assert sum(len(b) for b in batches) == 100
        assert all(len(b) <= _MAX_TEXTS_PER_BATCH for b in batches)

    def test_split_by_chars(self) -> None:
        texts = ["x" * 40_000] * 10  # 400K total, exceeds 100K limit
        batches = CloudEmbedding._split_into_batches(texts)
        assert len(batches) > 1
        assert sum(len(b) for b in batches) == 10
        for batch in batches:
            total_chars = sum(len(t) for t in batch)
            assert total_chars <= _MAX_CHARS_PER_BATCH + 40_000  # single text can exceed

    def test_single_oversized_text(self) -> None:
        texts = ["x" * 200_000]  # Single text exceeds char limit
        batches = CloudEmbedding._split_into_batches(texts)
        assert len(batches) == 1
        assert batches[0] == texts

    def test_empty_input(self) -> None:
        batches = CloudEmbedding._split_into_batches([])
        assert batches == [[]]  # greedy packing returns one empty batch

    def test_exactly_at_count_limit(self) -> None:
        texts = ["hi"] * _MAX_TEXTS_PER_BATCH
        batches = CloudEmbedding._split_into_batches(texts)
        assert len(batches) == 1

    def test_one_over_count_limit(self) -> None:
        texts = ["hi"] * (_MAX_TEXTS_PER_BATCH + 1)
        batches = CloudEmbedding._split_into_batches(texts)
        assert len(batches) == 2
        assert len(batches[0]) == _MAX_TEXTS_PER_BATCH
        assert len(batches[1]) == 1

    def test_mixed_lengths_split_by_chars(self) -> None:
        texts = ["short"] * 20 + ["x" * 80_000] * 2
        batches = CloudEmbedding._split_into_batches(texts)
        assert sum(len(b) for b in batches) == 22
        assert len(batches) >= 2

    def test_a_smaller_character_cap_packs_fewer_texts_per_batch(self) -> None:
        texts = ["x" * 7_000] * 10
        batches = CloudEmbedding._split_into_batches(texts, max_chars=20_000)
        assert [len(b) for b in batches] == [2] * 5  # a third text would make 21,000 characters


class TestEmbedBatchWithSplit:
    """Integration tests for embed_batch with batch splitting."""

    @pytest.mark.asyncio()
    async def test_large_batch_splits_api_calls(self, service: CloudEmbedding) -> None:
        call_sizes: list[int] = []

        async def mock_aembed(model: str, texts: Sequence[str], **kwargs: object) -> list[list[float]]:
            call_sizes.append(len(texts))
            return _vectors(len(texts))

        with patch(_AEMBED, side_effect=mock_aembed):
            result = await service.embed_batch(["text"] * 100)

        assert len(result) == 100
        assert len(call_sizes) == 4  # 32+32+32+4
        assert all(size <= _MAX_TEXTS_PER_BATCH for size in call_sizes)

    @pytest.mark.asyncio()
    async def test_small_batch_single_call(self, service: CloudEmbedding) -> None:
        call_count = 0

        async def mock_aembed(model: str, texts: Sequence[str], **kwargs: object) -> list[list[float]]:
            nonlocal call_count
            call_count += 1
            return _vectors(len(texts))

        with patch(_AEMBED, side_effect=mock_aembed):
            result = await service.embed_batch(["hello"] * 5)

        assert len(result) == 5
        assert call_count == 1

    @pytest.mark.asyncio()
    async def test_long_texts_split_by_chars(self, service: CloudEmbedding) -> None:
        call_sizes: list[int] = []

        async def mock_aembed(model: str, texts: Sequence[str], **kwargs: object) -> list[list[float]]:
            call_sizes.append(len(texts))
            return _vectors(len(texts))

        # Each text stays under the embed token window; combined chars exceed batch limit.
        long_texts = ["word " * 1_600 for _ in range(20)]
        with patch(_AEMBED, side_effect=mock_aembed):
            result = await service.embed_batch(long_texts)

        assert len(result) == 20
        assert len(call_sizes) > 1  # Must split due to chars
        assert sum(call_sizes) == 20

    @pytest.mark.asyncio()
    async def test_empty_batch(self, service: CloudEmbedding) -> None:
        result = await service.embed_batch([])
        assert result == []

    @pytest.mark.asyncio()
    @pytest.mark.parametrize("model_id", ["@cf/baai/bge-m3", "openai/@cf/baai/bge-m3"])
    async def test_a_provider_token_cap_limits_the_characters_of_every_request(self, model_id: str) -> None:
        """bge-m3 spends up to one token per character (emoji 1.0, base64 0.76, JSON 0.66, prose 0.26-0.60)."""
        request_chars: list[int] = []

        async def mock_aembed(model: str, texts: Sequence[str], **kwargs: object) -> list[list[float]]:
            request_chars.append(sum(len(text) for text in texts))
            return _vectors(len(texts), dim=1024)

        service = CloudEmbedding(model=model_id, api_key="test-key", api_base=_CLOUDFLARE_ENDPOINT)
        with patch(_AEMBED, side_effect=mock_aembed):
            result = await service.embed_batch(["x" * _BGE_M3_CHUNK_CHARS] * 20)

        assert len(result) == 20
        assert max(request_chars) <= _CLOUDFLARE_REQUEST_TOKEN_CAP * SAFETY_MARGIN
        assert request_chars == [7 * _BGE_M3_CHUNK_CHARS, 7 * _BGE_M3_CHUNK_CHARS, 6 * _BGE_M3_CHUNK_CHARS]

    @pytest.mark.asyncio()
    async def test_a_model_without_a_known_cap_keeps_the_default_request_size(self, service: CloudEmbedding) -> None:
        request_chars: list[int] = []

        async def mock_aembed(model: str, texts: Sequence[str], **kwargs: object) -> list[list[float]]:
            request_chars.append(sum(len(text) for text in texts))
            return _vectors(len(texts))

        with patch(_AEMBED, side_effect=mock_aembed):
            await service.embed_batch(["x" * _BGE_M3_CHUNK_CHARS] * 14)

        assert request_chars == [13 * _BGE_M3_CHUNK_CHARS, _BGE_M3_CHUNK_CHARS]
        assert request_chars[0] <= _MAX_CHARS_PER_BATCH

    @pytest.mark.asyncio()
    async def test_preserves_order(self, service: CloudEmbedding) -> None:
        """Verify vectors match input text order across splits."""
        counter = 0

        async def mock_aembed(model: str, texts: Sequence[str], **kwargs: object) -> list[list[float]]:
            nonlocal counter
            vectors = []
            for _ in texts:
                vectors.append([float(counter)] * 1536)
                counter += 1
            return vectors

        with patch(_AEMBED, side_effect=mock_aembed):
            result = await service.embed_batch(["t"] * 70)

        assert len(result) == 70
        for i, vec in enumerate(result):
            assert vec[0] == float(i), f"Order mismatch at index {i}"
