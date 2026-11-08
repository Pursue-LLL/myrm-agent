"""CSV file parser.

[INPUT]
- file path: CSV 文件
- myrm_agent_harness.toolkits.file_parsers.base::FileParser (POS: 解析器基类)
- myrm_agent_harness.toolkits.file_parsers.text_decoding::read_text_file (POS: 文件字节 → 文本，UTF-8 / Unicode BOM / 可识别的旧编码)

[OUTPUT]
- CsvParser.parse: CSV → Markdown 表格文本；二进制或编码无法识别的文件抛出 TextDecodingError
- CsvParser.supported_extensions: [".csv"]

[POS]
CSV parsing layer that converts tabular data into GFM markdown tables for
consistent downstream ingestion.
"""

from __future__ import annotations

import asyncio
import csv
import logging
from io import StringIO
from pathlib import Path

from myrm_agent_harness.toolkits.file_parsers.base import FileParser
from myrm_agent_harness.toolkits.file_parsers.text_decoding import read_text_file

logger = logging.getLogger(__name__)


class CsvParser(FileParser):
    """Parse CSV into markdown table text."""

    async def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        raw = await asyncio.to_thread(read_text_file, path)
        reader = csv.reader(StringIO(raw))
        rows = [row for row in reader if any(cell.strip() for cell in row)]
        if not rows:
            return ""

        def _cell(value: str) -> str:
            return value.replace("|", "\\|").strip()

        header = [_cell(cell) for cell in rows[0]]
        body = rows[1:] if len(rows) > 1 else []
        lines = [
            "| " + " | ".join(header) + " |",
            "| " + " | ".join(["---"] * len(header)) + " |",
        ]
        for row in body:
            padded = row + [""] * max(0, len(header) - len(row))
            lines.append("| " + " | ".join(_cell(cell) for cell in padded[: len(header)]) + " |")

        logger.info("CSV parsed: %s, rows=%d", path.name, len(rows))
        return "\n".join(lines)

    @property
    def supported_extensions(self) -> list[str]:
        return [".csv"]
