from app.channels.providers.telegram.html_converter import _utf16_len, split_message


def test_split_message_simple():
    text = "Hello " * 1000  # 6000 characters
    chunks = split_message(text, limit=4096)
    assert len(chunks) == 2
    assert _utf16_len(chunks[0]) <= 4096
    assert _utf16_len(chunks[1]) <= 4096
    assert "".join(chunks) == text


def test_split_message_with_tags():
    # A long message inside a <pre><code> block
    text = "<pre><code>" + "A" * 4090 + "B" * 100 + "</code></pre>"
    chunks = split_message(text, limit=4096)

    assert len(chunks) == 2

    # First chunk should close the tags
    assert chunks[0].startswith("<pre><code>")
    assert chunks[0].endswith("</code></pre>")
    assert _utf16_len(chunks[0]) <= 4096

    # Second chunk should reopen the tags
    assert chunks[1].startswith("<pre><code>")
    assert chunks[1].endswith("</code></pre>")
    assert _utf16_len(chunks[1]) <= 4096


def test_split_message_with_nested_tags():
    text = "<b>bold <i>italic " + "X" * 4090 + "</i></b>"
    chunks = split_message(text, limit=4096)

    assert len(chunks) == 2

    # First chunk should close <i> then <b>
    assert chunks[0].endswith("</i></b>")

    # Second chunk should reopen <b> then <i>
    assert chunks[1].startswith("<b><i>")
    assert chunks[1].endswith("</i></b>")


def test_split_message_utf16_emoji():
    # An emoji like  takes 2 UTF-16 code units
    emoji = "\U0001F600"
    assert _utf16_len(emoji) == 2

    # Create a string that is exactly 4095 code units long, then add an emoji
    # 4095 = 4095 'A's. Adding emoji makes it 4097, which exceeds 4096.
    text = "A" * 4095 + emoji
    chunks = split_message(text, limit=4096)

    assert len(chunks) == 2
    assert chunks[0] == "A" * 4095
    assert chunks[1] == emoji


def test_split_message_with_fake_tags():
    # Test that non-Telegram tags are treated as plain text and don't break the state machine
    text = "<b>bold</b> I love <3 you and <unknown> tags " * 200
    chunks = split_message(text, limit=4096)

    assert len(chunks) == 3
    # If <3 was treated as a tag, it would be closed at the end of chunk 1.
    # Since it's plain text, chunk 1 should just end with some text or a valid closing tag if it happened to split there.
    # We just ensure it doesn't crash and splits correctly.
    assert _utf16_len(chunks[0]) <= 4096
    assert _utf16_len(chunks[1]) <= 4096
    assert _utf16_len(chunks[2]) <= 4096


def test_split_message_smart_breakpoints():
    # Test that the algorithm prefers paragraph/sentence boundaries over hard splits

    # Create a text that is ~4100 chars long.
    # It has a paragraph break at 4000, a sentence break at 4050, and a space at 4080.

    part1 = "A" * 4000
    part2 = "B" * 48 + ". "
    part3 = "C" * 28 + " "
    part4 = "D" * 20

    text = part1 + "\n\n" + part2 + part3 + part4

    chunks = split_message(text, limit=4096)

    assert len(chunks) == 2

    # The split should happen at the paragraph boundary (\n\n) because it's the highest priority
    # Wait, the algorithm searches backwards from the limit (4096).
    # At 4096, the text is part1 + "\n\n" + part2 + part3 + "D"*14
    # It will search backwards for \n\n. The \n\n is at index 4000.
    # So the first chunk should end exactly after the \n\n.
    assert chunks[0] == part1 + "\n\n"
    assert chunks[1] == part2 + part3 + part4
