"""Host spellings every real client is asked about when it is handed a canonical URL.

[OUTPUT]
- DIAL_SPELLINGS: the host text (between ``http://`` and ``:port``) of spellings a document or an attacker can write
  for one host. The canonicalizer admits each of them, and a client that is handed the canonical URL must dial the
  canonical host.

[POS]
Shared by the tests that run Chromium and libcurl against ``utils.url_syntax``, so both clients are asked about the same
names. Names use the reserved ``.test`` top-level domain (and ``localhost``), so a client that derives another name
fails to resolve instead of reaching a real host. Spellings the canonicalizer refuses are pinned in
``tests/utils/test_url_syntax.py`` and are not dialed.
"""

from __future__ import annotations

DIAL_SPELLINGS: tuple[str, ...] = (
    # case and the trailing dot
    "example.test",
    "EXAMPLE.TEST",
    "example.test.",
    "Example.Test.",
    "localhost",
    "LOCALHOST",
    "localhost.",
    # labels with underscores, hyphens, digits
    "a_b.test",
    "a-b.test",
    "-a.test",
    "a.b.c.d.test",
    "0b1.test",
    # legacy IPv4 spellings of loopback
    "127.1",
    "2130706433",
    "0x7f.1",
    "0177.0.0.1",
    "0x7f000001",
    "127.0.0.1.",
    "0x7f.0.0.1",
    "127.0x0.0.1",
    "127.0.1",
    # non-ASCII names: IDNA 2008 versus 2003, case folding, compatibility mappings
    "straße.test",
    "strasse.test",
    "faß.test",
    "σας.test",
    "ΣΑΣ.test",
    "aΣ",
    "München.test",
    "例え.localhost",
    "ǅ.test",
    "ﬁ.test",
    "İ.test",
    "ı.test",
    "㎒.test",
    "ⓔⓧⓐⓜⓟⓛⓔ.test",
    "xn--strae-oqa.test",
    "XN--STRAE-OQA.TEST",
    # full-width characters and the dots a browser reads as a full stop
    "ＥＸＡＭＰＬＥ。ｔｅｓｔ",
    "ｅｘａｍｐｌｅ．ｔｅｓｔ",
    "①②⑦.0.0.1",
    "１２７。０。０。１",
    "127。0。0。1",
    "127｡0｡0｡1",
    # characters a mapping drops or keeps
    "exa\u00admple.test",
    "exa\u200bmple.test",
    "exa\u2060mple.test",
    "\u200d.test",
    "a\u200db.test",
    "a\u200cb.test",
    # Arabic-Indic digits
    "٣.test",
    "a.٣",
    # IPv6 literals and brackets around something that is not one
    "[::1]",
    "[0:0:0:0:0:0:0:1]",
    "[::ffff:127.0.0.1]",
    "[::FFFF:7f00:1]",
    "[example.test]",
    "[v1.x]",
    # what precedes the last '@' is credentials, never the host
    "user@example.test",
    "a:b@example.test",
    "example.test@evil.test",
    "example.test:80@evil.test",
    "evil.test@example.test",
)
