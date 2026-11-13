"""文件流式读取 - 大文件分块读取与行预览

[INPUT]
- none (imports no other project module)

[OUTPUT]
- read_file_chunked(): 分块读取文件，返回完整内容（不一次性加载全文件到内存）；可设字符上限，读到超出一个字符即停
- read_file_preview(): 读取前N行（快速预览）

[POS]
File streaming reader. Chunked reads keep large files from exhausting memory; the preview returns the first lines with a hint to read on.
"""

from __future__ import annotations

from pathlib import Path

import aiofiles

# 单次 read() 的字符数上限：大文件按块读，不一次性读进内存。
_CHUNK_CHARS = 10 * 1024 * 1024
_PREVIEW_LINES = 1000


async def read_file_chunked(file_path: Path, max_chars: int | None = None) -> str:
    """分块读取文件（防止OOM）

    Args:
        file_path: 文件路径
        max_chars: 读到超过该字符数就停止（None 表示读完整个文件）

    Returns:
        完整文件内容；设置 max_chars 时，最多返回前 max_chars + 1 个字符
        （多出的一个字符让调用方知道文件还有后续）

    Note:
        内部分块读取。相比一次性read()，避免大文件OOM。
        使用aiofiles异步IO，避免阻塞事件循环。
    """
    chunks: list[str] = []
    gathered = 0

    async with aiofiles.open(file_path, encoding="utf-8", errors="replace") as f:
        while True:
            # 最后一块只取到 max_chars + 1，不会多读。
            size = _CHUNK_CHARS if max_chars is None else min(_CHUNK_CHARS, max_chars + 1 - gathered)
            chunk = await f.read(size)
            if not chunk:
                break
            chunks.append(chunk)
            gathered += len(chunk)
            if max_chars is not None and gathered > max_chars:
                break

    return "".join(chunks)


async def read_file_preview(file_path: Path, max_lines: int = _PREVIEW_LINES) -> str:
    """读取文件预览（前N行）

    Args:
        file_path: 文件路径
        max_lines: 最大行数

    Returns:
        前N行内容

    Note:
        使用aiofiles异步IO，快速读取前N行后立即返回。
        不估算总行数（避免额外采样开销）。
    """
    lines: list[str] = []

    async with aiofiles.open(file_path, encoding="utf-8", errors="replace") as f:
        # 只读取前max_lines行
        i = 0
        async for line in f:
            lines.append(line.rstrip("\n"))
            i += 1
            if i >= max_lines:
                break

    content = "\n".join(lines)

    # 如果读取了max_lines行，说明文件可能更大
    if len(lines) >= max_lines:
        content += f"\n\n... (file continues, showing first {max_lines:,} lines)"
        content += "\n\n Tip: File is large. Use line range syntax to read specific sections: 'file.py:1001-2000'"

    return content
