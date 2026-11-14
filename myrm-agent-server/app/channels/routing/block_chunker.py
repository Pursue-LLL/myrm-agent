"""Block chunking for streamed text: when a preview is worth sending and where to cut it without splitting a code block.

[INPUT]
- (none)

[OUTPUT]
- ChunkConfig: Chunking configuration
- BlockChunker: Text chunker with code fence protection (fence lines are recognised whatever their info string says)

[POS]
Chunking decisions for streamed replies, used by StreamCoordinator and the Router.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class ChunkConfig:
    """Configuration for block chunking."""

    block_size: int = 500
    enable_code_fence_protection: bool = True
    prefer_newline_breaks: bool = True


class BlockChunker:
    """Intelligent text chunker with code fence protection.

    Features:
    1. Code fence protection: never split inside ```
    2. Newline-preferred breaks: prefer breaking at newlines
    3. Fixed block size: simple and predictable

    Design philosophy: Simple and effective, not over-engineered.
    Avoids complex paragraph/sentence detection (NLP overhead).
    """

    def __init__(self, config: ChunkConfig | None = None) -> None:
        self.config = config or ChunkConfig()
        # A fence line is "```" and a word before the newline wherever it stands (a closing fence glued to the end of a
        # code line counts), or a line that begins with backticks and carries any info string: "c++", "python title=demo".
        self._code_fence_pattern = re.compile(r"```\w*\n|^[ \t]*(?P<info_fence>`{3,})[^`\n]*\n", re.MULTILINE)

    def _fence_starts(self, text: str) -> list[int]:
        """Where the backticks of each fence line in ``text`` begin."""
        return [max(match.start(), match.start("info_fence")) for match in self._code_fence_pattern.finditer(text)]

    def should_emit_block(self, accumulated: str, is_final: bool) -> bool:
        """Determine if accumulated text should be emitted as a block.

        Args:
            accumulated: Current accumulated text
            is_final: Whether this is the final chunk

        Returns:
            True if should emit now
        """
        if is_final:
            return True

        if len(accumulated) < self.config.block_size:
            return False

        if not self.config.enable_code_fence_protection:
            return True

        return not self._is_inside_code_fence(accumulated)

    def find_break_point(self, text: str, max_length: int) -> int:
        """Find optimal break point in text.

        Priority:
        1. Code fence boundary (never break inside)
        2. Newline (prefer breaking at line boundaries)
        3. Fixed max_length

        Args:
            text: Text to break
            max_length: Maximum length before forced break

        Returns:
            Break point index (0 means no break needed)
        """
        if len(text) <= max_length:
            return 0

        if self.config.enable_code_fence_protection:
            if self._is_inside_code_fence(text):
                return 0

            fence_starts = self._fence_starts(text)
            best_fence_end = 0
            for start in fence_starts:
                closing = text.find("```", start + 3)
                if closing > 0:
                    fence_end = closing + 3
                    if start < max_length <= fence_end:
                        if fence_end <= max_length * 1.2:
                            return fence_end
                        return 0
                    if fence_end <= max_length:
                        best_fence_end = max(best_fence_end, fence_end)

            if best_fence_end > 0:
                return best_fence_end

        if self.config.prefer_newline_breaks:
            last_newline = text.rfind("\n", 0, max_length)
            if last_newline > max_length * 0.7:
                return last_newline + 1

        return max_length

    def _is_inside_code_fence(self, text: str) -> bool:
        """Check if text ends inside a code fence."""
        fence_starts = self._fence_starts(text)
        if not fence_starts:
            return False

        fence_count = len(fence_starts)
        closing_fences = text.count("```", fence_starts[-1] + 3)

        return (fence_count - closing_fences) % 2 == 1

    def _find_code_fence_end(self, text: str) -> int:
        """Find the end position of the current code fence.

        Returns:
            - Position after closing ``` if fence is closed
            - 0 if no fence or fence is not closed
        """
        fence_starts = self._fence_starts(text)
        if not fence_starts:
            return 0

        last_start = fence_starts[-1]
        closing_pos = text.find("```", last_start + 3)

        if closing_pos > 0:
            return closing_pos + 3

        return 0
