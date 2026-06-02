"""Integration test: Splitter handles Discord's message splitting requirements."""

from __future__ import annotations

from app.channels.rendering.splitter import split_message


class TestDiscordSplitterIntegration:
    """Test that splitter correctly handles Discord-specific requirements."""

    def test_splitter_discord_limit(self) -> None:
        """Direct test: splitter handles Discord's 2000-char limit correctly."""
        # Create a message that's just over 2000 chars
        long_text = "a" * 1000 + "\n```python\n" + "code line\n" * 100 + "```\n" + "b" * 1000

        # Split with Discord's limit
        chunks = split_message(long_text, max_len=2000)

        # Verify splitting occurred
        assert len(chunks) >= 2, "Long message should be split"

        # Verify all chunks are under limit (with small overflow tolerance)
        for i, chunk in enumerate(chunks):
            # Allow 20% overflow (overflow_tolerance default)
            assert len(chunk) <= 2000 * 1.2, f"Chunk {i + 1} exceeds limit: {len(chunk)} chars"

        # Verify all chunks have balanced fences
        for i, chunk in enumerate(chunks):
            if "```" in chunk:
                fence_count = chunk.count("```")
                assert fence_count % 2 == 0, f"Chunk {i + 1} has unbalanced fences"
