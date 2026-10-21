"""Privacy for the auxiliary LLM calls that run outside the guarded agent run.

Chat title, channel title and offline compaction send user text to a lite model without passing through the security
guardrail. They carry no privacy code: the persisted privacy settings are published process-wide and the outbound
guard masks what any model call would put on the wire. These tests drive the real call sites against a real
ChatLiteLLM and read what its provider client received.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.security.outbound_privacy_guard import set_process_privacy_policy
from myrm_agent_harness.toolkits.llms.adapters.chat_model.outbound_guard import set_outbound_message_guard

from app.core.security.privacy_policy_sync import sync_privacy_policy
from app.core.types import ModelConfig
from app.database.dto import _TitleModelConfig
from app.services.chat.chat_compaction import _ChatCompactionMixin
from app.services.chat.chat_title import call_llm_for_title, generate_chat_title
from tests.support.privacy_wire import wire_llm

_PHONE = "13812345678"
_ID_NUMBER = "110101199003074530"
_PASSWORD = "Sup3rSecret99"
_SENSITIVE_TEXT = f"帮我查社保，手机 {_PHONE}，身份证 {_ID_NUMBER}，password: {_PASSWORD}"
_ON = {"privacyEnabled": True}
_ON_REDACT_S2 = {"privacyEnabled": True, "privacyS2Action": "redact"}
_OFF = {"privacyEnabled": False}


@pytest.fixture(autouse=True)
def _clean_process_policy() -> Iterator[None]:
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)
    yield
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)


@pytest.fixture
def title_wire() -> Iterator[list[str]]:
    llm, sent = wire_llm("社保查询")
    with patch("myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config", new=AsyncMock(return_value=llm)):
        yield sent


def _title_model() -> _TitleModelConfig:
    return _TitleModelConfig.model_validate({"model": "lite", "apiKey": "k", "baseUrl": ""})


def _assert_masked(sent: list[str]) -> None:
    """The default policy redacts S3 content (identity number, password); a bare phone number is S2 and only warned."""
    joined = "\n".join(sent)
    for secret in (_ID_NUMBER, _PASSWORD):
        assert secret not in joined, f"{secret} reached the auxiliary LLM"


class TestTitleGeneration:
    async def test_privacy_on_masks_what_the_title_model_receives(self, title_wire: list[str]) -> None:
        sync_privacy_policy(_ON)

        await call_llm_for_title(_SENSITIVE_TEXT, _title_model())

        _assert_masked(title_wire)
        assert "社保" in title_wire[0]

    async def test_privacy_off_sends_the_text_unchanged(self, title_wire: list[str]) -> None:
        sync_privacy_policy(_OFF)

        await call_llm_for_title(_SENSITIVE_TEXT, _title_model())

        assert _PHONE in title_wire[0]
        assert _ID_NUMBER in title_wire[0]

    async def test_a_span_straddling_the_prompt_window_never_leaks_half(self, title_wire: list[str]) -> None:
        # Six digits of the phone number fall inside the 200-character prompt window, the rest outside it.
        straddling = "x" * 193 + " " + _PHONE

        sync_privacy_policy(_OFF)
        await call_llm_for_title(straddling, _title_model())
        assert _PHONE[:5] in title_wire[0], "the window must really cut the number, or this test proves nothing"

        sync_privacy_policy(_ON_REDACT_S2)
        await call_llm_for_title(straddling, _title_model())
        assert _PHONE[:5] not in title_wire[1]

    async def test_a_warn_action_leaves_a_bare_phone_number_as_the_main_chat_would(self, title_wire: list[str]) -> None:
        sync_privacy_policy(_ON)

        await call_llm_for_title(f"手机 {_PHONE}", _title_model())

        assert _PHONE in title_wire[0]

    async def test_the_conversation_title_path_is_covered_too(self, title_wire: list[str]) -> None:
        sync_privacy_policy(_ON)
        messages = [SimpleNamespace(role="user", content=_SENSITIVE_TEXT), SimpleNamespace(role="assistant", content="好的")]

        await generate_chat_title(messages, title_model=_title_model())

        _assert_masked(title_wire)


class TestChannelTitle:
    @asynccontextmanager
    async def _no_session(self) -> AsyncIterator[None]:
        yield None

    @pytest.mark.parametrize(("settings", "leaks"), [(_ON, False), (_OFF, True)])
    async def test_channel_title_follows_the_published_settings(
        self, title_wire: list[str], settings: dict[str, object], leaks: bool
    ) -> None:
        from app.core.channel_bridge.executor_helpers.history import generate_channel_title

        sync_privacy_policy(settings)
        lite = ModelConfig(model="lite", api_key="k", base_url="")
        with (
            patch("app.database.connection.get_session", new=self._no_session),
            patch("app.services.chat.chat_service.ChatService.update_chat_title", new=AsyncMock()),
        ):
            await generate_channel_title("chat-1", _SENSITIVE_TEXT, lite)

        assert (_ID_NUMBER in title_wire[0]) is leaks


class TestOfflineCompaction:
    @pytest.mark.parametrize(("settings", "leaks"), [(_ON, False), (_OFF, True)])
    async def test_flush_sends_the_summarizer_masked_text_but_archives_the_originals(
        self, settings: dict[str, object], leaks: bool
    ) -> None:
        sync_privacy_policy(settings)
        llm, sent = wire_llm('{"goal": "社保"}')
        stored = [
            SimpleNamespace(id="m1", role="user", content=_SENSITIVE_TEXT, extra_data=None),
            SimpleNamespace(id="m2", role="assistant", content="已记录", extra_data=None),
        ]
        repo = SimpleNamespace(
            get_latest_message=AsyncMock(
                return_value=SimpleNamespace(id="m2", created_at=datetime.now(UTC) - timedelta(hours=1))
            ),
            get_chat_by_id=AsyncMock(return_value=SimpleNamespace(compacted_before_id=None)),
            get_all_messages=AsyncMock(return_value=stored),
            cas_update_compaction=AsyncMock(return_value=True),
        )
        archive = AsyncMock()
        model_cfg = SimpleNamespace(max_context_tokens=8000, api_keys=None)

        class _Uow:
            session = object()

            async def __aenter__(self) -> _Uow:
                return self

            async def __aexit__(self, *exc: object) -> None:
                return None

        with (
            patch("asyncio.sleep", new=AsyncMock()),
            patch("app.services.chat.chat_compaction.UnitOfWork", new=_Uow),
            patch("app.services.chat.chat_compaction._ChatServiceBase._cr", new=staticmethod(lambda _uow: repo)),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new=AsyncMock(return_value=SimpleNamespace(providers_dict=None, personal_settings_dict=settings)),
            ),
            patch("app.core.channel_bridge.model_resolver.resolve_model_config", new=lambda _providers: model_cfg),
            patch("app.core.channel_bridge.model_resolver.enrich_model_context_window", new=lambda cfg, _providers: cfg),
            patch("myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config", new=AsyncMock(return_value=llm)),
            patch(
                "app.services.chat.salient_tool_archive_service.SalientToolArchiveService.archive_salient_tools",
                new=archive,
            ),
        ):
            await _ChatCompactionMixin.flush_compaction_debt("chat-1")

        assert sent, "the summarizer never called the model"
        assert (_ID_NUMBER in "\n".join(sent)) is leaks
        archived = str(archive.call_args.kwargs["messages"][0].content)
        assert _PHONE in archived, "the recall archive keeps the original text"
        repo.cas_update_compaction.assert_awaited_once()
