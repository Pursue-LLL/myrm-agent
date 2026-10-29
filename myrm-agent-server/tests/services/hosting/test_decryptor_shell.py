"""The unlock page of an encrypted publish: what a visitor can type, what they are told, and what the title may carry."""

from __future__ import annotations

import re
from html.parser import HTMLParser

import pytest

from app.services.hosting.crypto_packager import package_encrypted_publish_files
from app.services.hosting.packager import PublishFile


def _page(title: str = "Protected Artifact") -> str:
    files = {"index.html": PublishFile(path="index.html", content="<h1>Secret</h1>", encoding="utf-8")}
    return package_encrypted_publish_files(files, "any-password", title=title)["index.html"].content


class _Roles(HTMLParser):
    """The ``role`` of every element that has an id."""

    def __init__(self) -> None:
        super().__init__()
        self.by_id: dict[str, str | None] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if (element_id := attributes.get("id")) is not None:
            self.by_id[element_id] = attributes.get("role")


@pytest.mark.parametrize("element_id", ["error-msg", "env-error-msg"])
def test_a_message_that_appears_after_the_visitor_acts_is_announced(element_id: str) -> None:
    roles = _Roles()
    roles.feed(_page())
    assert roles.by_id[element_id] == "alert"


def test_the_typed_password_is_trimmed_like_the_one_the_publisher_encrypted_with() -> None:
    # The publisher strips the password before encrypting, so a pasted trailing space or newline can never be part of it.
    unlock = re.search(r"async function handleUnlock\(\) \{.*?\n    \}\n", _page(), re.DOTALL)
    assert unlock is not None
    assert "input.value.trim()" in unlock.group(0)


@pytest.mark.parametrize("jargon", ["Secure Context", "Web Cryptography", "Decrypting", "corrupted"])
def test_visitor_facing_copy_names_no_mechanism(jargon: str) -> None:
    page = _page()
    visible_copy = re.sub(r"<style>.*?</style>", "", page, flags=re.DOTALL)
    assert jargon not in visible_copy


def test_the_title_is_escaped_as_text() -> None:
    assert "<title>R&amp;D &lt;b&gt; &quot;Q3&quot;</title>" in _page('R&D <b> "Q3"')
