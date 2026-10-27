"""How file_read_tool reads and shows a file: multimodal blocks, text pages, truncation and outlines.

[INPUT]
- file_read.multimodal: image/PDF/document/video blocks and their text-mode fallbacks
- file_read.text_paths: preview/stream/all text reads and the structure outline
- file_read.truncation: complete-line truncation with a precomputed continuation offset
- file_read.outline: symbol and heading outline extraction

[OUTPUT]
- build_multimodal_result / append_media_text_parts: multimodal and media text-mode read handlers
- process_text_paths / read_structure_outline: text path read handlers
- truncate_file_output: file_read output truncation
- extract_file_outline / extract_truncated_outline: structural outlines

[POS]
file_read_tool execution subpackage; file_read_tool.py is the tool facade and core/__init__ re-exports the handlers.
"""

from .multimodal import append_media_text_parts, build_multimodal_result
from .outline import extract_file_outline, extract_truncated_outline
from .text_paths import process_text_paths, read_structure_outline
from .truncation import truncate_file_output

__all__ = [
    "append_media_text_parts",
    "build_multimodal_result",
    "extract_file_outline",
    "extract_truncated_outline",
    "process_text_paths",
    "read_structure_outline",
    "truncate_file_output",
]
