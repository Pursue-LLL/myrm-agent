"""Text decoding: file bytes to ``str`` in UTF-8, a Unicode byte-order-mark encoding or an identifiable legacy encoding.

[INPUT]
- utils.content_sniff::PayloadKind, classify_payload (POS: Tells a binary file from text)
- charset_normalizer::from_bytes (POS: statistical encoding detector, imported on the first legacy-encoded input)

[OUTPUT]
- TextDecodingError: the bytes are binary, or text whose encoding cannot be identified reliably
- decode_text_bytes: bytes -> str; a few damaged bytes become U+FFFD, whatever else cannot be read as text is refused
- read_text_file: the text of a file on disk with LF line endings (blocking)

[POS]
The one place where file bytes become text for the file parsers, the Wiki source loader and the source-sync
converters. UTF-8 comes first, then UTF-16/32 with a byte-order mark, then UTF-8 with a few damaged bytes, then the
legacy encodings of the supported locales (GBK/GB18030, Big5, Shift-JIS, EUC-JP, EUC-KR, Windows-1252). A legacy guess
needs strong evidence and is otherwise refused, because a wrong decode is garbage that looks like text and would be
compiled into the knowledge base.
"""

from __future__ import annotations

import codecs
import logging
from pathlib import Path

from myrm_agent_harness.utils.content_sniff import PayloadKind, classify_payload

logger = logging.getLogger(__name__)


class TextDecodingError(ValueError):
    """The bytes are binary, or text in an encoding that cannot be identified reliably."""


# The detector chooses among the encodings of the supported locales only: offering it every codec makes it name a
# wrong one more often for the same text.
_LEGACY_ENCODINGS = ["gb18030", "cp950", "cp932", "euc_jp", "cp949", "cp1252"]
_SINGLE_BYTE_ENCODING = "cp1252"

# A larger file is judged by this many bytes from the line holding its first undecodable byte, so the cost stays
# bounded however large the file is.
_SAMPLE_BYTES = 64 * 1024
_ASCII_BYTES = bytes(range(0x80))
_HIGH_BYTES = bytes(range(0x80, 0x100))

# The detector rejects a text whose "mess" ratio is above this. Its default of 0.2 turns away a share of real
# Markdown and code-heavy documents in a legacy encoding.
_MAX_MESS_RATIO = 0.3
# Double-byte encodings often decode the same bytes into valid but different text. The winner must beat the runner-up
# by this much of mess ratio; a closer call is refused rather than guessed. A single-byte winner is exempt: next to
# it every double-byte decoding of a few accented letters looks clean, yet the detector still ranks it first.
_MIN_MESS_MARGIN = 0.05
# Non-ASCII bytes needed to trust a double-byte guess: fewer fit several encodings too well. A single-byte encoding
# needs no minimum, since accented letters stand alone between ASCII ones.
_MIN_DOUBLE_BYTE_EVIDENCE = 32

# Text is "mostly UTF-8" when its valid multi-byte characters outnumber the damaged bytes this many times over: legacy
# text read as UTF-8 is nearly all damage.
_UTF8_DOMINANCE = 2
# Text with no identifiable encoding is read as UTF-8 only when its undecodable bytes are this small a share: stray
# bytes in what is otherwise ASCII, not a file in another encoding.
_MAX_REPLACED_RATIO = 0.01
_REPLACEMENT = "\ufffd"

# UTF-32 first: its little-endian byte-order mark (FF FE 00 00) begins with the UTF-16 one.
_BYTE_ORDER_MARKS: tuple[tuple[bytes, str], ...] = (
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


def decode_text_bytes(data: bytes) -> str:
    """The text in ``data``.

    UTF-8 (with or without a byte-order mark) and UTF-16/32 with a byte-order mark decode exactly. Mostly-UTF-8
    text keeps its damaged bytes as replacement characters, as does text with no identifiable encoding whose
    undecodable bytes are a tiny share, such as stray bytes in what is otherwise ASCII. Otherwise the encoding is
    identified from the bytes themselves among GBK/GB18030, Big5, Shift-JIS, EUC-JP, EUC-KR and Windows-1252, and
    the whole text must decode in it. Binary data, text in another encoding, text too short to identify and legacy
    text with a damaged byte are refused.

    Raises:
        TextDecodingError: the bytes cannot be read as text with confidence.
    """
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as failure:
        first_invalid = failure.start
    for byte_order_mark, codec in _BYTE_ORDER_MARKS:
        if data.startswith(byte_order_mark):
            return data.decode(codec, errors="replace")
    if classify_payload(None, data) is PayloadKind.BINARY:
        raise TextDecodingError("The data is binary, not text")
    sample = _sample_around(data, first_invalid)
    if _is_mostly_utf8(sample):
        return data.decode("utf-8-sig", errors="replace")
    encoding = _identify_legacy_encoding(sample)
    if encoding is not None:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError:
            logger.debug("%d bytes of text do not decode as the %s they look like", len(data), encoding)
        else:
            logger.debug("Decoded %d bytes of text as %s", len(data), encoding)
            return text
    text = data.decode("utf-8-sig", errors="replace")
    if text.count(_REPLACEMENT) > len(text) * _MAX_REPLACED_RATIO:
        raise TextDecodingError("The text is not UTF-8 and its encoding could not be identified reliably")
    return text


def read_text_file(path: Path) -> str:
    """The text of a file on disk (blocking), see :func:`decode_text_bytes`, with CRLF and CR line endings turned into LF
    the way reading in text mode does."""
    return decode_text_bytes(path.read_bytes()).replace("\r\n", "\n").replace("\r", "\n")


def _sample_around(data: bytes, first_invalid: int) -> bytes:
    """The bytes the encoding is judged from: the whole of a small file, else a window that always holds the first
    undecodable byte, so that the sample shows the damage the rest of the file has.

    A cut sample ends after its last ASCII byte, which also closes a character: a detector given half a character
    finds no encoding at all. The cut never falls before the first undecodable byte.
    """
    if len(data) <= _SAMPLE_BYTES:
        return data
    start = _character_boundary_before(data, first_invalid)
    sample = data[start : start + _SAMPLE_BYTES]
    if start + _SAMPLE_BYTES >= len(data):
        return sample
    complete = len(sample.rstrip(_HIGH_BYTES))
    return sample[:complete] if complete > first_invalid - start else sample


def _character_boundary_before(data: bytes, offset: int) -> int:
    """A position up to half a window before ``offset`` at which a character starts in every ASCII-compatible encoding.

    A line start is one, and so is the position after any ASCII byte; ``offset`` itself is the last resort for a stretch
    without a single ASCII byte.
    """
    farthest = max(0, offset - _SAMPLE_BYTES // 2)
    newline = data.rfind(b"\n", farthest, offset)
    if newline >= 0:
        return newline + 1
    if farthest == 0:
        return 0
    after_last_ascii = len(data[farthest:offset].rstrip(_HIGH_BYTES))
    return farthest + after_last_ascii if after_last_ascii else offset


def _is_mostly_utf8(sample: bytes) -> bool:
    text = sample.decode("utf-8", errors="replace")
    damaged = text.count(_REPLACEMENT)
    multi_byte_characters = len(text) - len(text.encode("ascii", errors="ignore")) - damaged
    return multi_byte_characters >= damaged * _UTF8_DOMINANCE


def _identify_legacy_encoding(sample: bytes) -> str | None:
    """The legacy encoding the sample is written in, or ``None`` when no single one is convincing."""
    # Imported here: the detector is needed only for text that is not UTF-8.
    from charset_normalizer import from_bytes

    matches = from_bytes(
        sample,
        cp_isolation=_LEGACY_ENCODINGS,
        threshold=_MAX_MESS_RATIO,
        enable_fallback=False,
    )
    best = matches.best()
    if best is None:
        return None
    if best.encoding == _SINGLE_BYTE_ENCODING:
        return best.encoding
    if len(sample.translate(None, _ASCII_BYTES)) < _MIN_DOUBLE_BYTE_EVIDENCE:
        return None
    best_text = str(best)
    for rival in matches:
        if rival is not best and str(rival) != best_text and rival.chaos - best.chaos < _MIN_MESS_MARGIN:
            return None
    return best.encoding
