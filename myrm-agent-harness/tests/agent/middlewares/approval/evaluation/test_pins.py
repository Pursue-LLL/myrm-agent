"""The pin of a file call: the files it opened when it was judged, and the check that it still opens only those."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.middlewares.approval.evaluation import path_moved, pin_of
from myrm_agent_harness.agent.middlewares.approval.evaluation.pins import build_path_pins
from myrm_agent_harness.agent.middlewares.approval.evaluation.record import PATH_PINS_KEY, PathPin
from myrm_agent_harness.runtime.checkpointing.factory import PickleSerde

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="links are POSIX behaviour")


@pytest.fixture
def workspace(tmp_path: Path) -> str:
    root = tmp_path / "ws"
    root.mkdir()
    (root / ".env").write_text("A=1")
    (root / "plan.md").write_text("plan")
    return str(root.resolve())


def _read(call_id: str | None, *paths: str) -> ToolCall:
    return ToolCall(type="tool_call", name="file_read_tool", args={"paths": list(paths)}, id=call_id)


def _pin(workspace: str, *paths: str) -> PathPin:
    pins = build_path_pins([_read("c1", *paths)], workspace)
    return pins["c1"]


class TestBuildPathPins:
    def test_a_file_call_is_pinned_to_the_files_its_paths_open(self, workspace: str) -> None:
        pin = _pin(workspace, "plan.md", "./plan.md")

        assert pin["typed"] == ["plan.md", "./plan.md"]
        assert pin["opened"] == [f"{workspace}/plan.md"]

    def test_only_file_calls_are_pinned_and_only_when_they_have_an_id(self, workspace: str) -> None:
        shell = ToolCall(type="tool_call", name="bash_code_execute_tool", args={"command": "ls"}, id="s1")
        fetch = ToolCall(type="tool_call", name="web_fetch", args={"url": "https://example.com"}, id="f1")

        pins = build_path_pins([shell, fetch, _read(None, "plan.md"), _read("r1", "plan.md")], workspace)

        assert list(pins) == ["r1"]

    def test_a_write_is_pinned_like_a_read(self, workspace: str) -> None:
        write = ToolCall(type="tool_call", name="file_write_tool", args={"path": "new.md", "content": "x"}, id="w1")

        pins = build_path_pins([write], workspace)

        assert pins["w1"]["opened"] == [f"{workspace}/new.md"]

    def test_a_text_no_file_can_be_named_by_is_marked(self, workspace: str) -> None:
        assert _pin(workspace, "bad\x00name")["opened"] == [""]

    def test_the_pins_survive_the_checkpoint_serializer_the_product_uses(self, workspace: str) -> None:
        serde = PickleSerde()
        pins = build_path_pins([_read("c1", "plan.md")], workspace)

        assert serde.loads_typed(serde.dumps_typed(pins)) == pins


class TestPinOf:
    def test_it_reads_the_pin_of_a_call_from_the_graph_state(self, workspace: str) -> None:
        pins = build_path_pins([_read("c1", "plan.md")], workspace)

        assert pin_of({PATH_PINS_KEY: pins}, "c1") == pins["c1"]

    @pytest.mark.parametrize(
        "state",
        [
            {},
            {PATH_PINS_KEY: None},
            {PATH_PINS_KEY: {}},
            {PATH_PINS_KEY: {"c1": "garbage"}},
            {PATH_PINS_KEY: {"c1": {}}},
        ],
        ids=["no-key", "cleared", "no-such-call", "not-a-pin", "empty-pin"],
    )
    def test_it_is_none_when_the_state_holds_no_pin_for_the_call(self, state: dict[str, object]) -> None:
        assert pin_of(state, "c1") is None


class TestPathMoved:
    def test_a_call_that_opens_what_it_was_judged_on_has_not_moved(self, workspace: str) -> None:
        pin = _pin(workspace, "plan.md")

        assert not path_moved(pin, "file_read_tool", {"paths": ["plan.md"]}, workspace)

    @POSIX_ONLY
    def test_a_path_that_a_link_has_since_redirected_has_moved(self, workspace: str) -> None:
        pin = _pin(workspace, "notes.txt")
        (Path(workspace) / "notes.txt").symlink_to(".env")

        assert path_moved(pin, "file_read_tool", {"paths": ["notes.txt"]}, workspace)

    @POSIX_ONLY
    def test_a_directory_that_a_link_has_since_replaced_moves_every_path_below_it(self, workspace: str) -> None:
        pin = _pin(workspace, "out/report.md")
        (Path(workspace) / "out").symlink_to("/tmp")

        assert path_moved(pin, "file_read_tool", {"paths": ["out/report.md"]}, workspace)

    def test_a_file_created_since_opens_the_place_its_name_always_pointed_at(self, workspace: str) -> None:
        pin = _pin(workspace, "fresh.md")
        (Path(workspace) / "fresh.md").write_text("new")

        assert not path_moved(pin, "file_read_tool", {"paths": ["fresh.md"]}, workspace)

    @POSIX_ONLY
    def test_a_call_whose_paths_the_person_edited_is_not_held_to_the_judged_files(self, workspace: str) -> None:
        pin = _pin(workspace, "notes.txt")
        (Path(workspace) / "notes.txt").symlink_to(".env")

        assert not path_moved(pin, "file_read_tool", {"paths": [".env"]}, workspace)
