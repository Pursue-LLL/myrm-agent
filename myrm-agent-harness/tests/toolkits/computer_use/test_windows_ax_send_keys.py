"""Tests for the text a Windows text entry hands to uiautomation's SendKeys.

SendKeys reads `{` and `}` as the delimiters of key names (`{Win}r` presses the Windows key), so a value is sent as the
key script that types it literally: `{` as `{{}` and `}` as `{}}`, in one pass over the value.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from importlib import reload
from unittest.mock import MagicMock, patch

import pytest

import myrm_agent_harness.toolkits.computer_use.perception.windows_ax as windows_ax


def _edit_control() -> MagicMock:
    control = MagicMock(spec=["ControlTypeName", "GetChildren", "BoundingRectangle", "SendKeys", "Click"])
    control.ControlTypeName = "EditControl"
    control.GetChildren.return_value = []
    control.BoundingRectangle.width.return_value = 40
    control.BoundingRectangle.height.return_value = 20
    return control


@contextmanager
def _windows_with(control: MagicMock) -> Iterator[None]:
    """`windows_ax` bound to a uiautomation stub whose foreground window holds only `control`."""
    foreground = MagicMock()
    foreground.ControlTypeName = "PaneControl"
    foreground.GetChildren.return_value = [control]
    auto = MagicMock()
    auto.GetForegroundControl.return_value = foreground
    with patch.dict("sys.modules", {"uiautomation": auto}):
        reload(windows_ax)
        yield


def _keys_sent_for(action: str, text: str) -> str:
    control = _edit_control()
    with _windows_with(control):
        result = windows_ax.invoke_ax_element("0", action, text=text)
    assert result.success is True
    control.SendKeys.assert_called_once()
    return str(control.SendKeys.call_args.args[0])


class TestATextEntryIsSentAsTheKeyScriptThatTypesItLiterally:
    @pytest.mark.parametrize(
        ("value", "key_script"),
        [
            ("ab{c}d", "ab{{}c{}}d"),
            ("p{ass", "p{{}ass"),
            ("{Win}r", "{{}Win{}}r"),
            ("notepad{Enter}", "notepad{{}Enter{}}"),
            ("}{", "{}}{{}"),
            ("{}", "{{}{}}"),
            ('{"a": 1}', '{{}"a": 1{}}'),
        ],
    )
    def test_braces_are_escaped_in_a_single_pass(self, value: str, key_script: str) -> None:
        assert _keys_sent_for("fill", value) == key_script

    @pytest.mark.parametrize("value", ["hello world", "a+b(c)=%d^e~", "p\u00e4ss-\u5bc6\u7801"])
    def test_a_value_without_braces_is_sent_unchanged(self, value: str) -> None:
        assert _keys_sent_for("fill", value) == value

    @pytest.mark.parametrize("action", ["fill", "type", "set_value"])
    def test_every_text_verb_escapes(self, action: str) -> None:
        assert _keys_sent_for(action, "ab{c}d") == "ab{{}c{}}d"
