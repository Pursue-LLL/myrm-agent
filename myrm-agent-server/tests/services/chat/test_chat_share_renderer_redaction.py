"""A shared conversation page is public: credentials pasted into the chat must not be readable on it."""

from __future__ import annotations

import threading
from unittest.mock import MagicMock, patch

import pytest

from app.services.chat import share_renderer
from tests.services.chat.share_support import agentless_db, make_chat, make_message, render_page

_OPENAI_KEY = "sk-proj-A1b2C3d4E5f6G7h8I9j0K1l2M3n4"
_AWS_KEY = "AKIAQWERTYUIOPASDFGH"
_GITLAB_TOKEN = "glpat-Xy9Wv8Ut7Sr6Qp5On4Ml"
_GITHUB_TOKEN = "ghp_Qa1Ws2Ed3Rf4Tg5Yh6Uj7Ik8Ol9Pz0Xc1Vb2"

# The part of each credential that a masked copy must no longer carry.
_HIDDEN_PARTS = ("A1b2C3d4E5f6G7h8I9j0", "WERTYUIOPASDF", "Wv8Ut7Sr6Qp5", "Ws2Ed3Rf4Tg5Yh6Uj7Ik8")


@pytest.fixture
def mock_db() -> MagicMock:
    return agentless_db()


def _assert_no_credential(html: str) -> None:
    for part in _HIDDEN_PARTS:
        assert part not in html


async def test_credentials_a_user_pasted_are_not_readable_on_the_page(mock_db: MagicMock) -> None:
    pasted = f"please deploy with {_OPENAI_KEY} and {_AWS_KEY}, the runner token is {_GITLAB_TOKEN} / {_GITHUB_TOKEN}"

    html = await render_page(mock_db, "en", messages=[make_message("m1", "user", pasted)])

    _assert_no_credential(html)
    assert "please deploy with" in html


async def test_credentials_in_an_assistant_reply_are_masked_inside_its_markdown(mock_db: MagicMock) -> None:
    reply = f"Use this:\n\n```bash\nexport OPENAI_API_KEY={_OPENAI_KEY}\n```\n\nor inline `{_GITLAB_TOKEN}`, see **the docs**."

    html = await render_page(mock_db, "en", messages=[make_message("m1", "assistant", reply)])

    _assert_no_credential(html)
    assert "<pre>" in html
    assert "<strong>the docs</strong>" in html


async def test_the_title_and_the_link_preview_do_not_carry_a_credential(mock_db: MagicMock) -> None:
    chat = make_chat().model_copy(update={"title": f"fix {_OPENAI_KEY}", "first_message": f"token {_GITHUB_TOKEN} is rejected"})

    html = await render_page(mock_db, "en", chat=chat, messages=[make_message("m1", "user", "hi")])

    _assert_no_credential(html)
    assert "<title>fix " in html
    assert 'property="og:description" content="token ' in html


async def test_a_credential_at_the_edge_of_the_link_preview_is_masked_before_the_preview_is_cut(mock_db: MagicMock) -> None:
    chat = make_chat().model_copy(update={"first_message": "a" * 187 + f" {_OPENAI_KEY} and more text after it"})

    html = await render_page(mock_db, "en", chat=chat, messages=[make_message("m1", "user", "hi")])

    # Cut first, the preview would end with the first 11 characters of the key, too short for the masker to recognise.
    assert "sk-proj-A1b" not in html


async def test_text_without_credentials_reads_exactly_as_written(mock_db: MagicMock) -> None:
    text = "See https://example.com/docs?page=2 for the steps; the build takes 3 minutes."

    html = await render_page(mock_db, "en", messages=[make_message("m1", "user", text)])

    assert text in html


async def test_the_page_is_built_off_the_event_loop_thread(mock_db: MagicMock) -> None:
    seen: list[int] = []
    real_build = share_renderer._build_html

    def spy(*args: object, **kwargs: object) -> str:
        seen.append(threading.get_ident())
        return real_build(*args, **kwargs)  # type: ignore[arg-type]

    with patch("app.services.chat.share_renderer._build_html", side_effect=spy):
        await render_page(mock_db, "en")

    assert seen
    assert seen[0] != threading.get_ident()
