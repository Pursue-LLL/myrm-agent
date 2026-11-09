"""The share E2E proves the public page reproduces the real model reply.

Its probe is a fragment of the reply itself. A token the prompt asked the model to say
fails the test whenever the model words its answer differently, and a token the prompt
also contains is found on the page even when the reply is missing from it.
"""

from __future__ import annotations

import pytest
from test_chat_share_chrome_e2e import _norm_ws, _page_text, _reply_probe

PROMPT = "【E2E 分享真实对话】请用一句中文介绍你自己，回答必须以 OK 开头，不超过 80 字。"
# A real reply of the model that does not contain any token the prompt could have named.
REPLY = "OK，我是一个通用AI智能助手，能帮你查资料、写代码、做分析和生成可视化图表，随时说需求就行。"


def _page(*, user: str, assistant: str) -> str:
    return (
        "<html><head><title>Shared</title><style>.a{content:'x'}</style></head><body>"
        f'<div class="user"><p>{user}</p></div>'
        f'<div class="assistant">{assistant}</div>'
        "<script>window.__x = '分享';</script></body></html>"
    )


def test_norm_ws_collapses_every_kind_of_whitespace() -> None:
    assert _norm_ws("a b\nc\t d\r\n e") == "abcde"


def test_probe_is_a_fragment_of_the_reply_and_not_of_the_prompt() -> None:
    probe = _reply_probe(REPLY, PROMPT)
    assert probe in REPLY
    assert probe not in _norm_ws(PROMPT)
    assert 4 <= len(probe) <= 24


def test_probe_skips_text_the_reply_only_echoes_from_the_prompt() -> None:
    echoing = "请用一句中文介绍你自己，我是小助手Alice"
    assert _reply_probe(echoing, PROMPT) == "我是小助手Alice"


def test_reply_made_only_of_prompt_text_has_no_probe() -> None:
    with pytest.raises(AssertionError, match="no 4\\+ char text run"):
        _reply_probe("OK！回答必须以 OK 开头，不超过 80 字", PROMPT)


def test_probe_survives_markup_inside_the_reply() -> None:
    reply = "我是一个通用AI智能助手"
    page = _page(user=PROMPT, assistant="<p>我是一个通用AI<strong>智能</strong>助手</p>")
    assert _reply_probe(reply, PROMPT) in _page_text(page)


def test_probe_survives_rendering_between_paragraphs_and_entities() -> None:
    page = _page(user=PROMPT, assistant="<p>能帮你查资料</p>\n<p>做分析 &amp; 生成</p><!-- -->")
    assert _reply_probe("能帮你查资料\n做分析 & 生成", PROMPT) in _page_text(page)


def test_page_with_only_the_prompt_does_not_satisfy_the_probe() -> None:
    page = _page(user=PROMPT, assistant="")
    assert _reply_probe(REPLY, PROMPT) not in _page_text(page)


def test_page_text_ignores_script_and_style_content() -> None:
    assert "分享" not in _page_text(_page(user="hello", assistant=""))
