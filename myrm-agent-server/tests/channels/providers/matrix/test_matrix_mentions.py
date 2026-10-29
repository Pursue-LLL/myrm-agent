"""Tests for Matrix mention conversion."""

from __future__ import annotations

import pytest

from app.channels.providers.matrix.html import (
    convert_matrix_mentions,
    mentioned_user_ids,
    strip_matrix_mention,
)


class TestConvertMatrixMentions:
    """Test Matrix @user → @user:server.com conversion."""

    def test_basic_single_mention_conversion(self) -> None:
        """Basic @user → @user:server.com conversion."""
        members = {"alice": "@alice:matrix.org"}
        text = "Hi @alice, how are you?"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice:matrix.org, how are you?"

    def test_multiple_mentions_conversion(self) -> None:
        """Multiple mentions should all be converted."""
        members = {
            "alice": "@alice:matrix.org",
            "bob": "@bob:server.com",
        }
        text = "Hi @alice and @bob"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice:matrix.org and @bob:server.com"

    def test_unknown_user_preserved(self) -> None:
        """Unknown @user should remain unchanged."""
        members = {"alice": "@alice:matrix.org"}
        text = "Hi @alice and @unknown"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice:matrix.org and @unknown"

    def test_fenced_code_block_protection(self) -> None:
        """@mentions in fenced code blocks should NOT be converted."""
        members = {"alice": "@alice:matrix.org", "bob": "@bob:server.com"}
        text = "Hi @alice, check:\n```python\n@bob in code\n```"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice:matrix.org, check:\n```python\n@bob in code\n```"

    def test_inline_code_protection(self) -> None:
        """@mentions in inline code should NOT be converted."""
        members = {"alice": "@alice:matrix.org", "bob": "@bob:server.com"}
        text = "Hi @alice, see `@bob` in code"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice:matrix.org, see `@bob` in code"

    def test_mixed_code_and_normal_mentions(self) -> None:
        """Mix of code-protected and normal mentions."""
        members = {
            "alice": "@alice:matrix.org",
            "bob": "@bob:server.com",
            "charlie": "@charlie:example.org",
        }
        text = "Hi @alice, `@bob`, and:\n```\n@charlie\n```\nTalk to @alice"
        result = convert_matrix_mentions(text, members)
        expected = "Hi @alice:matrix.org, `@bob`, and:\n```\n@charlie\n```\nTalk to @alice:matrix.org"
        assert result == expected

    def test_empty_members_dict(self) -> None:
        """Empty members dict should leave mentions unchanged."""
        members: dict[str, str] = {}
        text = "Hi @alice and @bob"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice and @bob"

    def test_empty_text(self) -> None:
        """Empty text should remain empty."""
        members = {"alice": "@alice:matrix.org"}
        text = ""
        result = convert_matrix_mentions(text, members)
        assert result == ""

    def test_complex_markdown_with_mentions(self) -> None:
        """Complex markdown formatting with mentions."""
        members = {
            "alice": "@alice:matrix.org",
            "bob": "@bob:server.com",
            "charlie": "@charlie:example.org",
        }
        text = """
# Title @alice
**@bob**, check this:
- Item with `@charlie`
- Item with @alice

```python
# @bob comment
pass
```
"""
        result = convert_matrix_mentions(text, members)
        assert "@alice:matrix.org" in result
        assert "@bob:server.com" in result
        assert "`@charlie`" in result
        assert "# @bob comment" in result

    def test_mention_at_text_boundaries(self) -> None:
        """Mentions at start and end of text."""
        members = {
            "alice": "@alice:matrix.org",
            "bob": "@bob:server.com",
        }
        text = "@alice middle content @bob"
        result = convert_matrix_mentions(text, members)
        assert result == "@alice:matrix.org middle content @bob:server.com"

    def test_repeated_same_mention(self) -> None:
        """Same mention repeated multiple times."""
        members = {"alice": "@alice:matrix.org"}
        text = "@alice @alice @alice"
        result = convert_matrix_mentions(text, members)
        assert result == "@alice:matrix.org @alice:matrix.org @alice:matrix.org"

    def test_mention_with_special_chars_in_displayname(self) -> None:
        """Displaynames with numbers/underscores (valid \\w pattern)."""
        members = {
            "alice123": "@alice:matrix.org",
            "bob_test": "@bob:server.com",
        }
        text = "Hi @alice123 and @bob_test"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice:matrix.org and @bob:server.com"

    def test_unicode_in_text(self) -> None:
        """Unicode characters in surrounding text."""
        members = {"alice": "@alice:matrix.org"}
        text = "你好 @alice，很高兴见到你"
        result = convert_matrix_mentions(text, members)
        assert result == "你好 @alice:matrix.org，很高兴见到你"

    def test_no_mentions_in_text(self) -> None:
        """Text without any @mentions."""
        members = {"alice": "@alice:matrix.org"}
        text = "Hello world, no mentions here"
        result = convert_matrix_mentions(text, members)
        assert result == "Hello world, no mentions here"

    def test_mention_in_link(self) -> None:
        """Mention in markdown link should be converted."""
        members = {"alice": "@alice:matrix.org"}
        text = "Check [@alice](https://example.com)"
        result = convert_matrix_mentions(text, members)
        assert result == "Check [@alice:matrix.org](https://example.com)"

    def test_partial_mention_not_converted(self) -> None:
        """Partial word that looks like mention (e.g., email) not converted."""
        members = {"alice": "@alice:matrix.org"}
        text = "Email: alice@example.com, mention @alice"
        result = convert_matrix_mentions(text, members)
        assert result == "Email: alice@example.com, mention @alice:matrix.org"

    def test_multiline_fenced_code_protection(self) -> None:
        """Multiline fenced code block protection."""
        members = {"alice": "@alice:matrix.org", "bob": "@bob:server.com"}
        text = """Hi @alice:
```
def func():
    # @bob
    pass
```
End @alice"""
        result = convert_matrix_mentions(text, members)
        assert result.count("@alice:matrix.org") == 2
        assert "@bob" in result and "@bob:server.com" not in result

    def test_consecutive_inline_code_blocks(self) -> None:
        """Multiple consecutive inline code blocks."""
        members = {"alice": "@alice:matrix.org", "bob": "@bob:server.com", "charlie": "@charlie:example.org"}
        text = "Hi @alice `@bob` `@charlie` normal"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice:matrix.org `@bob` `@charlie` normal"

    def test_case_sensitive_displayname_matching(self) -> None:
        """Displayname matching should be case-sensitive."""
        members = {"Alice": "@alice:matrix.org"}
        text = "Hi @alice and @Alice"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice and @alice:matrix.org"

    def test_qualified_id_with_port(self) -> None:
        """Qualified Matrix ID with port number."""
        members = {"alice": "@alice:server.com:8448"}
        text = "Hi @alice"
        result = convert_matrix_mentions(text, members)
        assert result == "Hi @alice:server.com:8448"


class TestMentionBoundaries:
    """A mention is a bare ``@name`` or the full ``@name:server`` ID of a room member, never part of a longer word."""

    MEMBERS = {"alice": "@alice:matrix.org"}

    @pytest.mark.parametrize(
        "text",
        ["mail support@alice.org", "see @alice.org", "a/@alice", "@carol:matrix.org is not here"],
        ids=["email", "dotted-host", "after-slash", "full-id-of-a-non-member"],
    )
    def test_text_that_is_no_mention_stays_untouched_and_mentions_nobody(self, text: str) -> None:
        assert convert_matrix_mentions(text, self.MEMBERS) == text
        assert mentioned_user_ids(text, self.MEMBERS) == []

    @pytest.mark.parametrize(
        "text",
        ["@alice:matrix.org hi", "thanks @alice:matrix.org.", "(@alice:matrix.org)"],
        ids=["leading", "trailing-period", "parenthesised"],
    )
    def test_the_full_id_of_a_member_stays_as_written_and_is_listed(self, text: str) -> None:
        assert convert_matrix_mentions(text, self.MEMBERS) == text
        assert mentioned_user_ids(text, self.MEMBERS) == ["@alice:matrix.org"]

    @pytest.mark.parametrize("text", ["@alice:other.org says hi", "see @alice.org"], ids=["foreign-id", "dotted-host"])
    def test_a_member_name_that_only_starts_a_longer_word_is_no_mention(self, text: str) -> None:
        members = {"alic": "@alic:matrix.org"}
        assert convert_matrix_mentions(text, members) == text
        assert mentioned_user_ids(text, members) == []

    def test_a_name_followed_by_a_colon_and_a_space_is_still_a_mention(self) -> None:
        assert convert_matrix_mentions("@alice: hello", self.MEMBERS) == "@alice:matrix.org: hello"
        assert mentioned_user_ids("@alice: hello", self.MEMBERS) == ["@alice:matrix.org"]

    def test_names_and_full_ids_are_listed_in_order_of_appearance(self) -> None:
        members = {"alice": "@alice:matrix.org", "bob": "@bob:server.com"}
        assert mentioned_user_ids("@bob:server.com then @alice", members) == ["@bob:server.com", "@alice:matrix.org"]


class TestMentionedUserIds:
    """The IDs to ping are exactly the ones ``convert_matrix_mentions`` writes into the text."""

    MEMBERS = {"alice": "@alice:matrix.org", "bob": "@bob:server.com"}

    def test_lists_each_member_once_in_order_of_appearance(self) -> None:
        assert mentioned_user_ids("@bob, @alice, @bob", self.MEMBERS) == ["@bob:server.com", "@alice:matrix.org"]

    def test_skips_unknown_names_and_code_blocks(self) -> None:
        assert mentioned_user_ids("@carol\n```\n@alice\n```\n`@bob`", self.MEMBERS) == []

    def test_agrees_with_what_the_conversion_replaced(self) -> None:
        text = "@alice and @carol and ```@bob```"
        converted = convert_matrix_mentions(text, self.MEMBERS)
        assert [uid for uid in self.MEMBERS.values() if uid in converted] == mentioned_user_ids(text, self.MEMBERS)


class TestStripMatrixMention:
    """Test Matrix bot mention stripping for inbound messages."""

    def test_basic_strip_bot_mention(self) -> None:
        """Strip bot mention from start of message."""
        text = "@bot:matrix.org hello world"
        result = strip_matrix_mention(text, "@bot:matrix.org")
        assert result == "hello world"

    def test_strip_bot_mention_with_extra_spaces(self) -> None:
        """Strip bot mention with multiple trailing spaces."""
        text = "@bot:matrix.org    hello"
        result = strip_matrix_mention(text, "@bot:matrix.org")
        assert result == "hello"

    def test_no_bot_mention(self) -> None:
        """Text without bot mention remains unchanged."""
        text = "hello world"
        result = strip_matrix_mention(text, "@bot:matrix.org")
        assert result == "hello world"

    def test_bot_mention_in_middle_not_stripped(self) -> None:
        """Bot mention in middle of text is not stripped (only first occurrence)."""
        text = "hello @bot:matrix.org world"
        result = strip_matrix_mention(text, "@bot:matrix.org")
        assert result == "hello @bot:matrix.org world"

    def test_empty_text(self) -> None:
        """Empty text returns empty string."""
        text = ""
        result = strip_matrix_mention(text, "@bot:matrix.org")
        assert result == ""

    def test_empty_bot_user_id(self) -> None:
        """Empty bot_user_id returns original text."""
        text = "@bot:matrix.org hello"
        result = strip_matrix_mention(text, "")
        assert result == "@bot:matrix.org hello"

    def test_bot_mention_with_port(self) -> None:
        """Strip bot mention with port number."""
        text = "@bot:server.com:8448 hello"
        result = strip_matrix_mention(text, "@bot:server.com:8448")
        assert result == "hello"

    def test_strip_only_first_occurrence(self) -> None:
        """Only strip first occurrence of bot mention."""
        text = "@bot:matrix.org @bot:matrix.org hello"
        result = strip_matrix_mention(text, "@bot:matrix.org")
        assert result == "@bot:matrix.org hello"
