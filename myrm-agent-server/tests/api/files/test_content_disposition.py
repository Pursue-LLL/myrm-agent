"""Content-Disposition values must survive any file name a client or filesystem supplies."""

from app.api.files.content_disposition import build_content_disposition


def test_ascii_name_is_quoted_and_repeated_in_filename_star():
    value = build_content_disposition("inline", "report.pdf")

    assert value == "inline; filename=\"report.pdf\"; filename*=UTF-8''report.pdf"


def test_non_ascii_name_gets_an_ascii_fallback_and_a_percent_encoded_original():
    value = build_content_disposition("attachment", "报告 v1.pdf")

    assert value == "attachment; filename=\"__ v1.pdf\"; filename*=UTF-8''%E6%8A%A5%E5%91%8A%20v1.pdf"


def test_quote_and_backslash_are_escaped_in_the_fallback_and_encoded_in_the_original():
    value = build_content_disposition("inline", 'a"b\\c.txt')

    assert value == 'inline; filename="a\\"b\\\\c.txt"; filename*=UTF-8\'\'a%22b%5Cc.txt'


def test_control_characters_cannot_inject_headers():
    value = build_content_disposition("inline", "x\r\nSet-Cookie: a=b\x00.txt")

    assert "\r" not in value
    assert "\n" not in value
    assert "\x00" not in value
    assert "%0D" not in value
    assert "%0A" not in value
    assert "%00" not in value


def test_a_lone_surrogate_does_not_break_the_header():
    """Undecodable file-system bytes surface as lone surrogates, which a UTF-8 encoder rejects."""
    value = build_content_disposition("inline", "bad\ud800name.txt")

    value.encode("latin-1")
    assert "bad" in value
    assert "name.txt" in value


def test_a_name_made_only_of_control_characters_falls_back_to_a_plain_name():
    value = build_content_disposition("attachment", "\r\n")

    assert value == "attachment; filename=\"file\"; filename*=UTF-8''file"


def test_every_result_is_latin_1_encodable():
    for name in ("中文.pdf", "emoji 🙂.png", 'a"b.txt', "tab\tname.txt", "\u202eevil.txt"):
        build_content_disposition("inline", name).encode("latin-1")
