"""Bounded gzip decompression for the executors' text reads.

A few kilobytes of gzip expand to gigabytes, so decompressing a ``.gz`` file in one call lets a single read
exhaust the host's memory. The output of one read is capped instead.

[INPUT]
- (none — stdlib only: gzip, io)

[OUTPUT]
- MAX_GUNZIP_BYTES: ceiling on the decompressed size of one gzip file read as text
- gunzip_bounded: gzip data decompressed, refused when the output would exceed the ceiling

[POS]
Shared by ``CodeExecutor.read_file`` and ``LocalFileOpsMixin.read_file``, the two places that decompress
``.gz`` files transparently. Decompresses at most ``limit + 1`` bytes, so memory stays bounded whatever the
compression ratio.
"""

import gzip
import io

MAX_GUNZIP_BYTES = 64 * 1024 * 1024


def gunzip_bounded(data: bytes, limit: int = MAX_GUNZIP_BYTES) -> bytes:
    """Decompress gzip *data* (concatenated members included), refusing output larger than *limit* bytes.

    Raises ValueError when the output would exceed *limit*, and gzip's own BadGzipFile / EOFError for data
    that is not a complete gzip stream.
    """
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as stream:
        out = stream.read(limit + 1)
    if len(out) > limit:
        raise ValueError(f"Decompressed content exceeds the {limit}-byte limit")
    return out
