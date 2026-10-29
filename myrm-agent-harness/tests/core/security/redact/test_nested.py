"""Nested values are redacted to a bounded depth, never loop, and are masked by the name of the field that holds them."""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest

from myrm_agent_harness.core.security.redact import redact_field_text, redact_for_display
from myrm_agent_harness.core.security.redact.nested import CIRCULAR, MAX_DEPTH, TOO_DEEP, redact_nested

_TOKEN = "sk-test-abcdefghijklmnopqrstuvwxyz1234567890abcdef"
_COOKIE_SECRET = "Zx81qPw0Lm3"
_COOKIE_VALUE = f"sessionid={_COOKIE_SECRET}"


def _chain(levels: int, leaf: object) -> dict[str, object]:
    """A payload that holds ``leaf`` under exactly ``levels`` nested dicts."""
    payload: dict[str, object] = {"a": leaf}
    for _ in range(levels - 1):
        payload = {"a": payload}
    return payload


class _Calls:
    """A leaf that records the (key, text) pairs it is asked to redact and masks nothing."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, str]] = []

    def __call__(self, key: str, text: str) -> str:
        self.seen.append((key, text))
        return text


def _loop_in_dict() -> dict[str, object]:
    payload: dict[str, object] = {"note": "text"}
    payload["left"] = payload
    payload["right"] = payload
    return payload


def _loop_in_list() -> dict[str, object]:
    items: list[object] = ["text"]
    items.append(items)
    items.append(items)
    return {"items": items}


class TestRedactNested:
    def test_the_leaf_is_given_the_name_of_the_field_that_holds_the_text(self) -> None:
        calls = _Calls()

        redact_nested({"a": "x", "inner": {"b": "y"}, "items": ["z", ("w",)], 7: "n"}, calls)

        assert calls.seen == [("a", "x"), ("b", "y"), ("items", "z"), ("items", "w"), ("", "n")]

    def test_containers_keep_their_type_and_other_values_pass_through(self) -> None:
        result = redact_nested({"t": ("a", 1), "l": ["b", None], "n": 3, "f": True}, _Calls())

        assert result == {"t": ("a", 1), "l": ["b", None], "n": 3, "f": True}
        assert isinstance(result, dict)
        assert isinstance(result["t"], tuple)

    def test_the_input_is_not_modified(self) -> None:
        payload: dict[str, object] = {"inner": {"a": "x"}}

        redact_nested(payload, lambda _key, _text: "masked")

        assert payload == {"inner": {"a": "x"}}

    def test_a_payload_at_the_depth_limit_is_walked_in_place(self) -> None:
        result = redact_nested(_chain(MAX_DEPTH, "x"), lambda _key, _text: "masked")

        assert "masked" in json.dumps(result)
        assert TOO_DEEP not in json.dumps(result)

    def test_a_container_below_the_depth_limit_is_replaced_by_a_marker(self) -> None:
        calls = _Calls()

        result = redact_nested(_chain(MAX_DEPTH + 1, "x"), calls)

        assert TOO_DEEP in json.dumps(result)
        assert calls.seen == []

    def test_a_payload_that_contains_itself_is_cut_where_the_loop_closes(self) -> None:
        payload: dict[str, object] = {"note": "text"}
        payload["loop"] = payload

        result = redact_nested(payload, _Calls())

        assert result == {"note": "text", "loop": CIRCULAR}

    @pytest.mark.parametrize("build", [_loop_in_dict, _loop_in_list])
    def test_a_container_that_holds_itself_twice_is_walked_once(self, build: Callable[[], dict[str, object]]) -> None:
        calls = _Calls()

        result = redact_nested(build(), calls)

        assert len(calls.seen) == 1
        assert json.dumps(result).count(CIRCULAR) == 2

    def test_a_container_shared_by_two_branches_is_redacted_in_both(self) -> None:
        shared = ["x"]
        calls = _Calls()

        result = redact_nested({"left": shared, "right": shared}, calls)

        assert len(calls.seen) == 2
        assert CIRCULAR not in json.dumps(result)


class TestRedactFieldText:
    def test_the_value_of_a_credential_field_is_masked_whatever_its_shape(self) -> None:
        assert _COOKIE_SECRET not in redact_field_text("Cookie", _COOKIE_VALUE)
        assert "dXNlcjpwYXNz" not in redact_field_text("Authorization", "Basic dXNlcjpwYXNz")
        assert redact_field_text("DB_PASSWORD", "Summer2024!") == "***"

    def test_a_long_credential_keeps_its_head_and_tail(self) -> None:
        masked = redact_field_text("api_key", _TOKEN)

        assert _TOKEN not in masked
        assert masked == f"{_TOKEN[:6]}...{_TOKEN[-4:]}"

    def test_a_variable_reference_and_an_empty_value_stay_readable(self) -> None:
        assert redact_field_text("api_key", "${API_KEY}") == "${API_KEY}"
        assert redact_field_text("password", "") == ""

    @pytest.mark.parametrize("key", ["tokens", "max_tokens", "cache_key", "author", "keyboard", "token_count", "note"])
    def test_an_ordinary_field_keeps_its_value(self, key: str) -> None:
        assert redact_field_text(key, "4096") == "4096"

    def test_the_text_of_an_ordinary_field_is_still_scanned_for_credentials(self) -> None:
        masked = redact_field_text("note", f"deploy with {_TOKEN}")

        assert _TOKEN not in masked
        assert masked.startswith("deploy with ")


class TestRedactForDisplay:
    def test_args_nested_past_the_recursion_limit_are_cut_not_raised(self) -> None:
        result = redact_for_display({"command": "ls", "extra": _chain(1200, _TOKEN)})

        assert result["command"] == "ls"
        assert _TOKEN not in json.dumps(result)
        assert TOO_DEEP in json.dumps(result)

    def test_a_credential_field_is_masked_even_when_its_text_has_no_known_shape(self) -> None:
        result = redact_for_display({"headers": {"Cookie": _COOKIE_VALUE, "Accept": "text/html"}})

        assert _COOKIE_SECRET not in json.dumps(result)
        assert isinstance(result["headers"], dict)
        assert result["headers"]["Accept"] == "text/html"

    def test_a_tuple_is_redacted_like_a_list(self) -> None:
        result = redact_for_display({"argv": ("curl", "-H", f"Authorization: Bearer {_TOKEN}")})

        assert _TOKEN not in json.dumps(result)
        assert isinstance(result["argv"], tuple)

    def test_args_that_contain_themselves_are_cut_where_the_loop_closes(self) -> None:
        args: dict[str, object] = {"command": "ls"}
        args["self"] = args

        assert redact_for_display(args) == {"command": "ls", "self": CIRCULAR}


class TestMaskKeys:
    def test_a_dict_key_is_left_alone_unless_the_caller_asks_for_it(self) -> None:
        assert redact_nested({_TOKEN: "x"}, lambda _key, _text: "masked") == {_TOKEN: "masked"}

    def test_a_key_that_is_a_credential_is_masked_on_request(self) -> None:
        result = redact_nested({"env": {_TOKEN: "prod"}}, redact_field_text, mask_keys=True)

        assert result == {"env": {f"{_TOKEN[:6]}...{_TOKEN[-4:]}": "prod"}}

    def test_the_value_under_a_masked_key_still_sees_the_original_field_name(self) -> None:
        calls = _Calls()

        redact_nested({"Cookie": "v", "inner": {"password": "w"}}, calls, mask_keys=True)

        assert ("Cookie", "v") in calls.seen
        assert ("password", "w") in calls.seen
        assert ("", "Cookie") in calls.seen

    def test_a_key_that_is_not_text_is_kept(self) -> None:
        assert redact_nested({7: "x"}, lambda _key, _text: "m", mask_keys=True) == {7: "m"}
