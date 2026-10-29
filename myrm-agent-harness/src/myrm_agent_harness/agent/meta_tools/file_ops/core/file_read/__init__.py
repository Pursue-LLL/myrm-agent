"""How file_read_tool reads and shows a file: multimodal blocks, text pages, truncation, outlines and read-scope guards.

[INPUT]
- file_read.multimodal::build_multimodal_result, append_media_text_parts (POS: multimodal read execution)
- file_read.text_paths::process_text_paths, read_structure_outline (POS: text read execution)
- file_read.truncation::truncate_file_output (POS: complete-line truncation with a precomputed continuation offset)
- file_read.view_redaction::redact_read_view (POS: per-file redaction of the text a read shows)
- file_read.outline::extract_file_outline, extract_truncated_outline (POS: symbol and heading outline extraction)
- file_read.scope::partition_urls, assert_paths_allowed_for_read, assert_evicted_uploaded_read_scope (POS: read-scope guards)

[OUTPUT]
- build_multimodal_result / append_media_text_parts: multimodal and media text-mode read handlers
- process_text_paths / read_structure_outline: text path read handlers
- truncate_file_output: file_read output truncation
- extract_file_outline / extract_truncated_outline: structural outlines
- partition_urls / assert_paths_allowed_for_read / assert_evicted_uploaded_read_scope: read-scope guards the tool runs before reading
- redact_read_view: per-file redaction of the text a read shows

[POS]
file_read_tool execution subpackage; file_read_tool.py is the tool facade, core/__init__ re-exports the handlers and only the tool uses the scope guards and the view redaction.
"""

from .multimodal import append_media_text_parts, build_multimodal_result
from .outline import extract_file_outline, extract_truncated_outline
from .scope import assert_evicted_uploaded_read_scope, assert_paths_allowed_for_read, partition_urls
from .text_paths import process_text_paths, read_structure_outline
from .truncation import truncate_file_output
from .view_redaction import redact_read_view

__all__ = [
    "append_media_text_parts",
    "assert_evicted_uploaded_read_scope",
    "assert_paths_allowed_for_read",
    "build_multimodal_result",
    "extract_file_outline",
    "extract_truncated_outline",
    "partition_urls",
    "process_text_paths",
    "read_structure_outline",
    "redact_read_view",
    "truncate_file_output",
]
