"""Unified recursive character splitter

Protects special blocks during recursive splitting in a single pass

[INPUT]
- utils.tiktoken_tables::encoding_for_model (POS: tiktoken encoding loaded from the bundled vocabularies)
- .markdown_link_handler::MarkdownLinkHandler (POS: Markdown link handling during split)
- .overlap_processor::OverlapProcessor (POS: Chunk overlap processing)
- .special_block_detector::SpecialBlockDetector (POS: Detects code/table/list blocks)
- .special_block_splitter::SpecialBlockSplitter (POS: Splits oversized special blocks)

[OUTPUT]
- RecursiveCharacterAndProtectSpecialChunkTextSplitterByTiktoken: Unified recursive character splitter

[POS]
Unified recursive character splitter
"""

import logging
import re

from myrm_agent_harness.utils.tiktoken_tables import encoding_for_model

from .markdown_link_handler import MarkdownLinkHandler
from .overlap_processor import OverlapProcessor
from .special_block_detector import SpecialBlockDetector
from .special_block_splitter import SpecialBlockSplitter

logger = logging.getLogger(__name__)


class RecursiveCharacterAndProtectSpecialChunkTextSplitterByTiktoken:
    """Unified recursive character splitter

    Features:
    1. Independent tiktoken token counting
    2. Protects special blocks during recursive splitting
    3. All processing completed in a single pass
    4. Unified overlap mechanism
    5. Better performance and maintainability

    Important notes:
    - Normal content stays within chunk_size; special blocks (code/tables) expand up to max_with_special
      (2x chunk_size; in the character-count fallback 1.3x of the character-scaled chunk_size)
    - Overlap is duplicate content (from previous chunk) and does not consume the current chunk quota
    - Therefore, total size after overlap is approximately: chunk_size + overlap_size
    - If downstream processing adds frontmatter or other extra content, callers should reserve space in chunk_size
    """

    def __init__(
        self,
        chunk_size: int,
        chunk_overlap: int,
        separators: list[str],
        model_name: str = "gpt-4",
    ):
        """Initialize the splitter

        Args:
            chunk_size: Target chunk size (tokens)
            chunk_overlap: Overlap size between chunks (tokens)
            separators: Split separator list (highest to lowest priority)
            model_name: tiktoken model name
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators
        self.model_name = model_name

        # Initialize tiktoken encoder
        self._init_tiktoken(model_name)

        # Special blocks (code/tables) can expand up to 2x
        self.max_with_special = int(chunk_size * 2)

        # Pre-compiled regex patterns
        self._markdown_header_pattern = re.compile(r"^#{1,6}\s+.+", re.MULTILINE)

        # Initialize sub-modules
        self._detector = SpecialBlockDetector()
        self._block_splitter = SpecialBlockSplitter(
            chunk_size=self.chunk_size,
            max_with_special=self.max_with_special,
            length_function=self._length_function,
            detector=self._detector,
        )
        self._overlap_processor = OverlapProcessor(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            max_with_special=self.max_with_special,
            length_function=self._length_function,
            detector=self._detector,
        )
        self._link_handler = MarkdownLinkHandler()

    def _init_tiktoken(self, model_name: str):
        """Initialize tiktoken encoder."""
        try:
            encoding = encoding_for_model(model_name)
            self._length_function = lambda text: len(encoding.encode(text, disallowed_special=()))
            self._use_tiktoken = True
        except Exception as e:
            logger.warning(f"tiktoken unavailable ({e!s}), using character count")
            self._length_function = len
            self._use_tiktoken = False
            self.chunk_size = self.chunk_size * 4
            self.chunk_overlap = self.chunk_overlap * 4
            self.max_with_special = int(self.chunk_size * 1.3)

    @classmethod
    def from_tiktoken_encoder(
        cls,
        chunk_size: int,
        chunk_overlap: int,
        separators: list[str],
        model_name: str = "gpt-4",
    ) -> "RecursiveCharacterAndProtectSpecialChunkTextSplitterByTiktoken":
        """Create tiktoken-based splitter (compatibility interface)."""
        return cls(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
            model_name=model_name,
        )

    def split_text(self, text: str) -> list[str]:
        """Split text and protect special blocks (unified processing)

        Args:
            text: Text to split

        Returns:
            List of split text chunks
        """
        if not text:
            return []

        # Step 1: Auto-detect split mode
        split_mode = self._detect_split_mode(text)

        # Step 2: Adjust separators based on mode
        effective_separators = self._get_effective_separators(split_mode)

        # Step 3: Protect Markdown links containing newlines
        protected_text, link_map = self._link_handler.protect_markdown_links(text)

        # Step 4: Unified recursive split (built-in special block protection and overlap)
        chunks = self._split_with_protection(protected_text, effective_separators)

        # Step 5: Restore Markdown links
        if link_map:
            chunks = self._link_handler.restore_and_check_links(
                chunks=chunks,
                link_map=link_map,
                max_with_special=self.max_with_special,
                length_function=self._length_function,
                resplit_callback=self._resplit_oversized_chunk,
            )

        return chunks

    def _detect_split_mode(self, text: str) -> str:
        """Auto-detect split mode

        Strategy:
        1. Count Markdown headings in text (excluding # inside code blocks)
        2. If 2+ headings found, use semantic splitting (preserves heading/content integrity)
        3. Otherwise use paragraph splitting (strict separator-based)

        Args:
            text: Text to split

        Returns:
            "semantic": Semantic split mode
            "paragraph": Paragraph split mode
        """
        if not text:
            return "paragraph"

        lines = text.split("\n")
        in_code_block = False
        header_count = 0

        for line in lines:
            stripped = line.strip()

            # Detect code block boundaries
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                continue

            # Skip content inside code blocks
            if in_code_block:
                continue

            # Detect Markdown headings
            if self._markdown_header_pattern.match(stripped):
                header_count += 1

        # If 2+ headings, use semantic splitting
        return "semantic" if header_count >= 2 else "paragraph"

    def _get_effective_separators(self, split_mode: str) -> list[str]:
        """Get effective separator list based on split mode

        Args:
            split_mode: Split mode ("semantic" or "paragraph")

        Returns:
            Separator list
        """
        if split_mode == "semantic":
            # Semantic split: skip heading separators, use only paragraph and sentence separators
            return [sep for sep in self.separators if not sep.startswith("\n#")]
        else:
            # Paragraph split: use all separators
            return self.separators

    def _split_with_protection(
        self, text: str, separators: list[str] | None = None, add_overlap: bool = True
    ) -> list[str]:
        """Unified recursive split (built-in special block protection)

        Core algorithm:
        1. Detect special blocks
        2. If special blocks exist, process segment by segment recursively
        3. If there are no special blocks, split normally and recursively
        4. Add overlap between all chunks

        Args:
            text: Text to split
            separators: Separator list
            add_overlap: Whether to add overlap (may be False in recursive calls)

        Returns:
            Chunk list
        """
        if not text or not text.strip():
            return []

        if separators is None:
            separators = self.separators

        # Return directly if the text is already small enough
        text_len = self._length_function(text)
        if text_len <= self.chunk_size:
            return [text]

        # Detect special blocks
        special_blocks = self._detector.extract_special_structures(text)

        if not special_blocks:
            # No special blocks: normal recursive split
            return self._recursive_split_text(text, separators, add_overlap)

        # Special blocks present: process segment by segment
        chunks = []
        pos = 0

        for block in special_blocks:
            # Process the text before the special block
            if block["start"] > pos:
                prefix_text = text[pos : block["start"]]
                if prefix_text.strip():
                    # Split the preceding text recursively (no overlap here; added once at the end)
                    prefix_chunks = self._recursive_split_text(prefix_text, separators, add_overlap=False)
                    chunks.extend(prefix_chunks)

            # Process the special block itself
            block_chunks = self._block_splitter.handle_special_block(block)
            chunks.extend(block_chunks)

            pos = block["end"]

        # Process the trailing text
        if pos < len(text):
            suffix_text = text[pos:]
            if suffix_text.strip():
                suffix_chunks = self._recursive_split_text(suffix_text, separators, add_overlap=False)
                chunks.extend(suffix_chunks)

        # Merge undersized chunks (less than 80% of chunk_size)
        if len(chunks) > 1:
            chunks = self._overlap_processor.merge_small_chunks(chunks)

        # Check for oversized chunks (a special block can be large by itself);
        # special blocks may stretch up to max_with_special, only chunks beyond that are force-split
        new_chunks = []
        for chunk in chunks:
            chunk_tokens = self._length_function(chunk)
            if chunk_tokens > self.max_with_special:
                # This chunk exceeds even the elastic limit and must be force-split
                logger.warning(
                    f"Oversized chunk detected ({chunk_tokens}T > {self.max_with_special}T), "
                    "force-splitting (likely an oversized code block or table)"
                )
                # Force-split by length
                sub_chunks = self._split_by_length(chunk)
                new_chunks.extend(sub_chunks)
            else:
                new_chunks.append(chunk)

        chunks = new_chunks

        # Add overlap uniformly
        if add_overlap and len(chunks) > 1:
            chunks = self._overlap_processor.add_overlap_to_chunks(chunks)

        return chunks

    def _recursive_split_text(self, text: str, separators: list[str], add_overlap: bool = True) -> list[str]:
        """Recursively split plain text (no special blocks)

        Args:
            text: Plain text
            separators: Separator list
            add_overlap: Whether to add overlap

        Returns:
            Chunk list
        """
        text_len = self._length_function(text)

        if text_len <= self.chunk_size:
            return [text] if text.strip() else []

        if not separators:
            # No separators left: force-truncate
            return self._split_by_length(text)

        # Try splitting with the current separator
        separator = separators[0]
        remaining_seps = separators[1:]

        if separator:
            splits = text.split(separator)
        else:
            splits = list(text)

        # Merge the splits into chunks
        chunks = []
        current_parts = []
        current_len = 0

        for i, split in enumerate(splits):
            if not split:
                continue

            # Restore the separator
            split_with_sep = split + separator if i < len(splits) - 1 and separator else split
            split_len = self._length_function(split_with_sep)

            # A single split exceeds the limit and needs recursive splitting
            if split_len > self.chunk_size:
                if current_parts:
                    chunks.append("".join(current_parts))
                    current_parts = []
                    current_len = 0

                if remaining_seps:
                    sub_chunks = self._recursive_split_text(split, remaining_seps, add_overlap=False)
                    chunks.extend(sub_chunks)
                else:
                    chunks.extend(self._split_by_length(split))
                continue

            # Check whether it fits into the current chunk
            if current_len + split_len <= self.chunk_size:
                current_parts.append(split_with_sep)
                current_len += split_len
            else:
                # The current chunk is full
                if current_parts:
                    chunks.append("".join(current_parts))
                current_parts = [split_with_sep]
                current_len = split_len

        if current_parts:
            chunks.append("".join(current_parts))

        # Add overlap
        if add_overlap and len(chunks) > 1:
            chunks = self._overlap_processor.add_overlap_to_chunks(chunks)

        return chunks

    def _split_by_length(self, text: str) -> list[str]:
        """Force-truncate text by length

        Args:
            text: Text to split

        Returns:
            List of split text chunks
        """
        chunks = []
        current_pos = 0
        text_len = len(text)

        while current_pos < text_len:
            end_pos = min(current_pos + self.chunk_size, text_len)

            if self._use_tiktoken:
                chunk_text = text[current_pos:end_pos]
                while self._length_function(chunk_text) > self.chunk_size and end_pos > current_pos + 1:
                    end_pos = int((end_pos + current_pos) / 2)
                    chunk_text = text[current_pos:end_pos]
            else:
                chunk_text = text[current_pos:end_pos]

            chunks.append(chunk_text)
            current_pos = end_pos

        return chunks

    def _resplit_oversized_chunk(self, oversized_content: str) -> list[str]:
        """Re-split an oversized chunk (used after link restoration)

        Args:
            oversized_content: Oversized chunk content

        Returns:
            Re-split chunk list
        """
        protected_content, chunk_link_map = self._link_handler.protect_markdown_links(oversized_content)
        resplit_protected = self._split_with_protection(protected_content, self.separators, add_overlap=False)
        resplit_chunks = [self._link_handler.restore_markdown_links(c, chunk_link_map) for c in resplit_protected]
        return resplit_chunks
