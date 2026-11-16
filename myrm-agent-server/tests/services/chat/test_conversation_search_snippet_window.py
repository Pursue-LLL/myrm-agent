"""``redacted_window`` reads a window out of the redacted text, so a credential at its edge never shows as a fragment."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable

import pytest

from app.services.chat.conversation_search_snippet import redacted_window
from tests.services.chat.search_support import shows_part_of

_VALUE = "Zk3Qm8Vt2Lp9Xw4R"
_TOKEN = "ghp_" + hashlib.sha256(b"snippet-window").hexdigest()[:36]
# A credential written the ways a transcript holds it: each form keeps its value between quotes or separators that an
# HTML-escaped copy would have turned into entities.
_FORMS: dict[str, Callable[[str], str]] = {
    "json": lambda value: '{"password": "' + value + '", "user": "demo"}',
    "env-double-quoted": lambda value: 'DB_PASSWORD="' + value + '"',
    "env-single-quoted": lambda value: "API_TOKEN='" + value + "'",
    "env-bare": lambda value: "DB_PASSWORD=" + value,
    "cli-flag": lambda value: "psql --password '" + value + "' -h db",
}


def _private_key_block() -> tuple[str, list[str]]:
    rows = [base64.b64encode(hashlib.sha256(str(i).encode()).digest() * 2).decode()[:64] for i in range(25)]
    begin, end = "-----BEGIN " + "RSA PRIVATE KEY-----", "-----END " + "RSA PRIVATE KEY-----"
    return "\n".join([begin, *rows, end]), rows


def test_text_that_redaction_leaves_alone_is_cut_as_it_is() -> None:
    text = "alpha beta gamma delta"

    assert redacted_window(text, 6, 16) == "beta gamma"


def test_a_window_after_a_masked_credential_keeps_its_own_text() -> None:
    text = f"DB_PASSWORD={_VALUE} then kestrelmark ends here"
    start = text.index("then")

    assert redacted_window(text, start, start + len("then kestrelmark ends")) == "then kestrelmark ends"


def test_a_window_before_a_masked_credential_keeps_its_own_text() -> None:
    text = f"the kestrelmark rollout ended. DB_PASSWORD={_VALUE} stays private"

    assert redacted_window(text, 0, len("the kestrelmark rollout")) == "the kestrelmark rollout"


def test_a_window_holding_a_whole_vendor_token_keeps_the_text_on_both_sides() -> None:
    text = f"alpha bravo charlie {_TOKEN} delta echo foxtrot"
    start = text.index("charlie")
    end = text.index("delta") + len("delta")

    window = redacted_window(text, start, end)

    # The mask is shorter than the token, so the window is lined up from both ends, not by its raw length.
    assert window is not None
    assert window.startswith("charlie ")
    assert window.endswith(" delta")
    assert not shows_part_of(_TOKEN, window)


@pytest.mark.parametrize("form", _FORMS.values(), ids=_FORMS.keys())
def test_a_window_holding_a_whole_labelled_credential_keeps_the_text_on_both_sides(form: Callable[[str], str]) -> None:
    text = f"alpha bravo charlie {form(_VALUE)} delta echo foxtrot"
    start = text.index("charlie")
    end = text.index("delta") + len("delta")

    window = redacted_window(text, start, end)

    assert window is not None
    assert window.startswith("charlie ")
    assert window.endswith(" delta")
    assert not shows_part_of(_VALUE, window)


@pytest.mark.parametrize("form", _FORMS.values(), ids=_FORMS.keys())
@pytest.mark.parametrize("width", [12, 30, 58])
def test_no_window_position_shows_part_of_a_credential(form: Callable[[str], str], width: int) -> None:
    prefix, suffix = "pad " * 30, " tail" * 30
    secret = form(_VALUE)
    text = f"{prefix}{secret}{suffix}"
    secret_start, secret_end = len(prefix), len(prefix) + len(secret)

    for start in range(secret_start - width - 5, secret_end + 5):
        window = redacted_window(text, start, start + width)
        if start + width <= secret_start or start >= secret_end:
            # A window clear of the credential is the raw text, whichever side of it the window falls on.
            assert window == text[start : start + width]
        else:
            assert window is None or not shows_part_of(_VALUE, window), (start, window)


@pytest.mark.parametrize("width", [12, 30, 58])
def test_no_window_position_shows_part_of_a_vendor_token(width: int) -> None:
    prefix, suffix = "pad " * 30, " tail" * 30
    text = f"{prefix}{_TOKEN}{suffix}"
    token_start, token_end = len(prefix), len(prefix) + len(_TOKEN)

    for start in range(token_start - width - 5, token_end + 5):
        window = redacted_window(text, start, start + width)
        assert window is None or not shows_part_of(_TOKEN, window), (start, window)


def test_a_window_that_starts_inside_a_vendor_token_keeps_the_text_after_it() -> None:
    text = f"use {_TOKEN} kestrelmark done"
    start = text.index(_TOKEN) + 10
    end = text.index("kestrelmark") + len("kestrelmark")

    window = redacted_window(text, start, end)

    assert window is not None
    assert window.endswith("kestrelmark")
    assert not shows_part_of(_TOKEN, window)


def test_a_window_inside_a_private_key_block_is_dropped() -> None:
    block, rows = _private_key_block()
    text = f"before {block} after"
    body_start = text.index(rows[3])

    assert redacted_window(text, body_start, body_start + 120) is None


def test_a_window_across_either_end_of_a_private_key_block_shows_no_row() -> None:
    block, rows = _private_key_block()
    text = f"before {block} after"
    block_start, block_end = text.index(block), text.index(block) + len(block)

    for start, end in [(block_start - 6, block_start + 150), (block_end - 150, block_end + 6)]:
        window = redacted_window(text, start, end)
        assert window is None or not any(row[:16] in window for row in rows)


def test_a_window_clear_of_a_private_key_block_is_the_raw_text() -> None:
    block, _ = _private_key_block()
    text = f"before {block} after"

    assert redacted_window(text, 0, 6) == "before"
    assert redacted_window(text, len(text) - 5, len(text)) == "after"


def test_characters_beyond_the_basic_plane_are_counted_as_one() -> None:
    text = f"密码 🔑 DB_PASSWORD={_VALUE} 结束 🔚 kestrelmark"
    start = text.index("结束")

    assert redacted_window(text, start, len(text)) == "结束 🔚 kestrelmark"
