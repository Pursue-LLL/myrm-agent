"""A one-page PDF with a real text layer, small enough to build by hand.

[INPUT]
- (none)

[OUTPUT]
- minimal_pdf_bytes: the bytes of a valid PDF 1.4 whose only page shows the given text

[POS]
For tests that need a file the real PDF parser can read, so a text coming out of it proves the whole route works
without a binary fixture in the repository. The text goes into a PDF string literal as it is: it must not contain
parentheses or backslashes.
"""

from __future__ import annotations


def minimal_pdf_bytes(text: str) -> bytes:
    stream = f"BT /F1 18 Tf 72 720 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    body = b"%PDF-1.4\n"
    offsets: list[int] = []
    for number, obj in enumerate(objects, start=1):
        offsets.append(len(body))
        body += b"%d 0 obj\n%s\nendobj\n" % (number, obj)
    xref_offset = len(body)
    body += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    body += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    body += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objects) + 1, xref_offset)
    return body
