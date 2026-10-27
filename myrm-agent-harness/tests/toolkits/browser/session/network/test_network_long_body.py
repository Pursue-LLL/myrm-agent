"""A response body longer than the inline preview is kept in the vault, masked, and answered pointer-first.

The model reads the start of the body in the answer and the rest through `file_read` by line range. The copy is
masked before it is cut or stored, so a credential the cut would split leaves no fragment, and its lines are wrapped
at 200 characters, because a minified body is one line and a line range could not otherwise reach into it.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.runnables import RunnableConfig

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from myrm_agent_harness.agent.meta_tools.file_ops.utils.vault_read import read_vault_paths_to_parts
from myrm_agent_harness.toolkits.browser.session import ContentVault
from myrm_agent_harness.toolkits.browser.session.network import long_body
from myrm_agent_harness.toolkits.browser.session.network.intelligence import NetworkIntelligence
from myrm_agent_harness.toolkits.browser.session.network.long_body import (
    BODY_PREVIEW_MAX_CHARS,
    long_body_answer,
    wrap_long_lines,
)

_POINTER = re.compile(r"vault://[a-f0-9-]+")
_RESOLVE_ROOT = "myrm_agent_harness.agent.meta_tools.file_ops.utils.vault_read.resolve_workspace_root"
_DISPATCH = "myrm_agent_harness.utils.event_utils.dispatch_custom_event"
_PASSWORD = "mysecretvalue12345678"
_GOOGLE_KEY = "AIza" + "S" * 35  # a bare key is recognised only whole: a fragment of it passes the mask
_CAP = 20_000  # the copy cap the tests that cross it run with, so they need not build a million characters


class _RecordingVault:
    """A vault that notes every write and the thread it ran on, answers with a fixed pointer, or refuses."""

    def __init__(self, refuse_with: Exception | None = None) -> None:
        self.writes: list[tuple[str | bytes, str, str | None, str]] = []
        self.threads: list[int] = []
        self._refuse_with = refuse_with

    def put(self, content: str | bytes, filename: str, content_type: str | None = None, description: str = "") -> str:
        self.threads.append(threading.get_ident())
        if self._refuse_with is not None:
            raise self._refuse_with
        self.writes.append((content, filename, content_type, description))
        return "vault://stub"


def _rows(count: int) -> str:
    return json.dumps(
        [{"id": n, "name": f"item-{n:05d}", "url": f"https://cdn.example.com/p/{n:05d}.jpg"} for n in range(count)],
        separators=(",", ":"),
    )


def _pointer(answer: str) -> str:
    match = _POINTER.search(answer)
    assert match, f"the answer names no vault object: {answer[:300]!r}"
    return match.group(0)


def _stored(answer: str, workspace: Path) -> str:
    """What the vault holds behind the pointer the answer names."""
    return ArtifactVault(str(workspace)).get(_pointer(answer)).decode()


async def _file_read(target: str, workspace: Path) -> str:
    """file_read of a vault target, exactly as the tool reads it (the part after the `=== target ===` line)."""
    with patch(_RESOLVE_ROOT, return_value=str(workspace)), patch(_DISPATCH, new_callable=AsyncMock):
        (part,) = await read_vault_paths_to_parts([target], MagicMock(), "all", config=RunnableConfig())
    return part.split("\n", 1)[1]


async def _answer(body: str, workspace: Path, mime: str = "application/json") -> str:
    return await long_body_answer(
        body, mime, vault=ArtifactVault(str(workspace)), filename="network_response_1.txt", description="d"
    )


class TestWrapLongLines:
    def test_short_lines_and_their_endings_are_kept(self) -> None:
        text = "a\n\nbb\nccc\n"

        assert wrap_long_lines(text) == text

    def test_a_line_of_exactly_the_width_is_kept_and_one_character_more_is_cut(self) -> None:
        assert wrap_long_lines("x" * 200) == "x" * 200
        assert wrap_long_lines("x" * 201) == "x" * 200 + "\n" + "x"

    def test_nothing_is_lost_or_added_but_the_breaks(self) -> None:
        body = _rows(300)
        wrapped = wrap_long_lines(body)

        assert wrapped.replace("\n", "") == body
        assert all(len(line) <= 200 for line in wrapped.split("\n"))
        assert len(wrapped.split("\n")) == -(-len(body) // 200)

    def test_lines_are_counted_by_newline_only_like_file_read(self) -> None:
        text = "a\u2028b\rc\x0bd\x85e"

        assert wrap_long_lines(text) == text
        assert wrap_long_lines(text + "\nnext").count("\n") == 1

    def test_an_empty_text_stays_empty(self) -> None:
        assert wrap_long_lines("") == ""


class TestAnswerWithAVault:
    @pytest.mark.asyncio
    async def test_the_answer_names_the_whole_body_first_then_shows_its_start(self, tmp_path: Path) -> None:
        body = _rows(2000)

        answer = await _answer(body, tmp_path)

        assert answer == (
            f"[Response body: {len(body)} chars, saved in full to {_pointer(answer)} (read it with file_read; "
            f"lines wrapped at 200 chars). MIME: application/json. First 8000 chars:]\n{body[:8000]}"
        )

    @pytest.mark.asyncio
    async def test_file_read_pages_through_the_copy_to_the_last_row(self, tmp_path: Path) -> None:
        body = _rows(2000)
        answer = await _answer(body, tmp_path)
        pointer = _pointer(answer)
        total_lines = -(-len(body) // 200)

        first = await _file_read(f"{pointer}:1-2", tmp_path)
        last = await _file_read(f"{pointer}:{total_lines}-{total_lines}", tmp_path)

        assert first == body[:200] + "\n" + body[200:400] + "\n"
        assert last.strip() == body[(total_lines - 1) * 200 :]
        assert "item-01999" in last + await _file_read(f"{pointer}:{total_lines - 1}-{total_lines - 1}", tmp_path)
        assert "item-01999" not in answer

    @pytest.mark.asyncio
    async def test_lines_are_counted_in_characters_so_non_latin_text_wraps_and_reads_back_whole(
        self, tmp_path: Path
    ) -> None:
        body = ("商品名称：夏季新款连衣裙🙂，价格：199。" * 30 + "\n") * 40 + "结尾标记END"

        answer = await _answer(body, tmp_path)

        stored = _stored(answer, tmp_path)
        lines = stored.split("\n")
        assert max(len(line) for line in lines) == 200
        assert stored.replace("\n", "") == body.replace("\n", "")
        assert (await _file_read(f"{_pointer(answer)}:{len(lines)}-{len(lines)}", tmp_path)).strip() == "结尾标记END"

    @pytest.mark.asyncio
    async def test_a_credential_deep_in_the_body_is_masked_in_the_copy(self, tmp_path: Path) -> None:
        body = _rows(1000) + f'"password":"{_PASSWORD}"' + _rows(1000)

        answer = await _answer(body, tmp_path)

        stored = _stored(answer, tmp_path)
        assert _PASSWORD not in stored
        assert '"password"' in stored

    @pytest.mark.asyncio
    async def test_a_credential_the_preview_cut_would_split_is_masked(self, tmp_path: Path) -> None:
        body = "x" * (BODY_PREVIEW_MAX_CHARS - 10) + f'"password":"{_PASSWORD}"}}' + "y" * 500

        answer = await _answer(body, tmp_path)

        assert "mysecretval" not in answer
        assert "mysecretval" not in _stored(answer, tmp_path)

    @pytest.mark.asyncio
    async def test_a_credential_the_copy_cap_would_split_is_masked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(long_body, "VAULT_COPY_MAX_CHARS", _CAP)
        body = "x" * (_CAP - 25) + "&k=" + _GOOGLE_KEY + "&z=1" + "z" * 500
        assert body.index(_GOOGLE_KEY) < _CAP < body.index(_GOOGLE_KEY) + len(_GOOGLE_KEY)

        answer = await _answer(body, tmp_path)

        assert "AIzaSSS" not in _stored(answer, tmp_path)

    @pytest.mark.asyncio
    async def test_a_body_beyond_the_cap_says_how_much_of_it_the_copy_holds(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(long_body, "VAULT_COPY_MAX_CHARS", _CAP)
        body = "a" * _CAP + "b" * 5_000

        answer = await _answer(body, tmp_path)

        assert answer.startswith(f"[Response body: 25000 chars, the first {_CAP} saved to {_pointer(answer)} (")
        assert _stored(answer, tmp_path) == wrap_long_lines("a" * _CAP)

    @pytest.mark.asyncio
    async def test_a_body_that_masks_up_to_more_than_the_cap_does_not_claim_the_whole_copy(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(long_body, "VAULT_COPY_MAX_CHARS", _CAP)
        # 19,995 chars, each short secret masks to `***`: the masked text outgrows the cap
        body = '"password":"a",' * 1_333
        assert len(body) < _CAP

        answer = await _answer(body, tmp_path)

        assert answer.startswith(f"[Response body: {len(body)} chars, the first {_CAP} saved to {_pointer(answer)} (")

    @pytest.mark.asyncio
    async def test_a_body_just_over_the_cap_that_masks_down_under_it_is_saved_in_full(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(long_body, "VAULT_COPY_MAX_CHARS", _CAP)
        # 21,038 chars of long secrets, a few dozen chars once masked
        body = ('"password":"' + "q" * 300 + '",') * 67
        assert _CAP < len(body) < _CAP + long_body._CUT_MARGIN

        answer = await _answer(body, tmp_path)

        assert answer.startswith(f"[Response body: {len(body)} chars, saved in full to ")

    @pytest.mark.asyncio
    async def test_the_copy_is_made_off_the_event_loop_thread(self) -> None:
        vault = _RecordingVault()

        await long_body_answer("x" * 9000, "text/plain", vault=vault, filename="f.txt", description="d")

        assert vault.threads and vault.threads[0] != threading.get_ident()

    @pytest.mark.asyncio
    async def test_the_vault_gets_a_text_object_named_for_the_request(self) -> None:
        vault = _RecordingVault()

        await long_body_answer(
            "x" * 9000, "application/json", vault=vault, filename="network_response_7.txt", description="d"
        )

        assert vault.writes == [(wrap_long_lines("x" * 9000), "network_response_7.txt", "text/plain", "d")]


class TestAnswerWithoutAVaultCopy:
    @pytest.mark.asyncio
    async def test_no_vault_gives_the_masked_preview_and_the_length(self) -> None:
        body = "x" * (BODY_PREVIEW_MAX_CHARS - 10) + f'"password":"{_PASSWORD}"}}' + "y" * 500

        answer = await long_body_answer(body, None, vault=None, filename="f.txt", description="d")

        assert answer.endswith(f"\n\n... [truncated, total {len(body)} chars] MIME: unknown")
        assert answer.startswith("x" * 100)
        assert "mysecretval" not in answer
        assert len(answer) < BODY_PREVIEW_MAX_CHARS + 100

    @pytest.mark.asyncio
    async def test_a_vault_that_refuses_the_write_gives_the_same_answer_and_a_warning(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        vault = _RecordingVault(refuse_with=OSError("disk full"))

        with caplog.at_level(logging.WARNING, logger=long_body.logger.name):
            answer = await long_body_answer("x" * 9000, "text/plain", vault=vault, filename="f.txt", description="d")

        assert answer == "x" * 8000 + "\n\n... [truncated, total 9000 chars] MIME: text/plain"
        assert "disk full" in caplog.text


class TestNetworkIntelligenceUsesTheVault:
    @staticmethod
    def _tracked(vault: ContentVault) -> NetworkIntelligence:
        ni = NetworkIntelligence(content_vault=vault)
        ni._on_request_will_be_sent(
            {
                "requestId": "req-1",
                "type": "XHR",
                "request": {"url": "https://api.example.com/items?access_token=" + "t" * 40, "method": "GET"},
            }
        )
        ni._on_response_received({"requestId": "req-1", "response": {"status": 200, "mimeType": "application/json"}})
        ni._cdp_session = MagicMock(send=AsyncMock(return_value={"body": "x" * 9000, "base64Encoded": False}))
        return ni

    @pytest.mark.asyncio
    async def test_a_long_body_goes_to_the_vault_under_a_name_and_description_without_credentials(self) -> None:
        vault = _RecordingVault()

        answer = await self._tracked(vault).get_response_body(1)

        assert answer.startswith("[Response body: 9000 chars, saved in full to vault://stub (")
        ((_, filename, _, description),) = vault.writes
        assert filename == "network_response_1.txt"
        assert description == "Response body of GET https://api.example.com/items?access_token=***"

    @pytest.mark.asyncio
    async def test_a_body_that_fits_the_preview_never_touches_the_vault(self) -> None:
        vault = _RecordingVault()
        ni = self._tracked(vault)
        ni._cdp_session = MagicMock(send=AsyncMock(return_value={"body": "x" * 8000, "base64Encoded": False}))

        assert await ni.get_response_body(1) == "x" * 8000
        assert vault.writes == []
