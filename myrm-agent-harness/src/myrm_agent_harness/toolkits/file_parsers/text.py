"""Text file parser

Supports plain text and Markdown files.

[INPUT]
- text_decoding::read_text_file (POS: file bytes to text in UTF-8, a Unicode BOM encoding or an identifiable legacy encoding)

[OUTPUT]
- TextParser: Plain text/Markdown parser; raises TextDecodingError for a file that is binary or whose encoding cannot be identified

[POS]
Text file parser
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from myrm_agent_harness.toolkits.file_parsers.base import FileParser
from myrm_agent_harness.toolkits.file_parsers.text_decoding import read_text_file

logger = logging.getLogger(__name__)


class TextParser(FileParser):
    """Plain text/Markdown parser"""

    async def parse(self, file_path: str) -> str:
        """Parse text file"""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = await asyncio.to_thread(read_text_file, path)

        logger.debug("Text file parsed: %s, length: %d chars", path.name, len(content))
        return content

    @property
    def supported_extensions(self) -> list[str]:
        return [".txt", ".md", ".markdown", ".rst", ".text"]
