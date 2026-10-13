"""Privacy masking for the auxiliary LLM calls that run outside the guarded agent run.

Chat title, channel title and offline compaction send user text to a lite model without passing through the security
guardrail, so they mask PII themselves when the persisted privacy switch is on.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from app.core.types import ModelConfig
from app.database.dto import _TitleModelConfig
from app.services.chat.chat_compaction import _ChatCompactionMixin, _mask_for_summary
from app.services.chat.chat_title import call_llm_for_title, generate_chat_title

_PHONE = "13812345678"
_ID_NUMBER = "110101199003074530"
_PASSWORD = "Sup3rSecret99"
_SENSITIVE_TEXT = f"帮我查社保，手机 {_PHONE}，身份证 {_ID_NUMBER}，password: {_PASSWORD}"
_ON = {"privacyEnabled": True}
_OFF = {"privacyEnabled": False}


class _CapturingLLM:
    """Fake chat model that records the prompt it is sent."""

    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        self.prompts.append("\n".join(str(m.content) for m in messages))
        return AIMessage(content="社保查询")


@pytest.fixture
def title_llm() -> Iterator[_CapturingLLM]:
    llm = _CapturingLLM()
    with patch(
        "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
        new=AsyncMock(return_value=llm),
    ):
        yield llm


def _title_model() -> _TitleModelConfig:
    return _TitleModelConfig.model_validate({"model": "lite", "apiKey": "k", "baseUrl": ""})


def _assert_masked(prompt: str) -> None:
    for secret in (_PHONE, _ID_NUMBER, _PASSWORD):
        assert secret not in prompt, f"{secret} reached the auxiliary LLM"


class TestTitleGeneration:
    async def test_privacy_on_masks_what_the_title_model_sees(self, title_llm: _CapturingLLM) -> None:
        await call_llm_for_title(_SENSITIVE_TEXT, _title_model(), mask_pii=True)

        _assert_masked(title_llm.prompts[0])
        assert "社保" in title_llm.prompts[0]

    async def test_privacy_off_sends_the_text_unchanged(self, title_llm: _CapturingLLM) -> None:
        await call_llm_for_title(_SENSITIVE_TEXT, _title_model())

        assert _PHONE in title_llm.prompts[0]

    async def test_a_span_straddling_the_prompt_window_never_leaks_half(self, title_llm: _CapturingLLM) -> None:
        # Six digits of the phone number fall inside the 200-character prompt window, the rest outside it.
        text = "x" * 194 + _PHONE

        await call_llm_for_title(text, _title_model(), mask_pii=True)

        assert _PHONE[:5] not in title_llm.prompts[0]

    async def test_the_conversation_title_path_forwards_the_switch(self, title_llm: _CapturingLLM) -> None:
        messages = [SimpleNamespace(role="user", content=_SENSITIVE_TEXT), SimpleNamespace(role="assistant", content="好的")]

        await generate_chat_title(messages, title_model=_title_model(), mask_pii=True)

        _assert_masked(title_llm.prompts[0])


class TestChannelTitle:
    @asynccontextmanager
    async def _no_session(self) -> AsyncIterator[None]:
        yield None

    @pytest.mark.parametrize(("mask_pii", "leaks"), [(True, False), (False, True)])
    async def test_channel_title_follows_the_switch(self, title_llm: _CapturingLLM, mask_pii: bool, leaks: bool) -> None:
        from app.core.channel_bridge.executor_helpers.history import generate_channel_title

        lite = ModelConfig(model="lite", api_key="k", base_url="")
        with (
            patch("app.database.connection.get_session", new=self._no_session),
            patch("app.services.chat.chat_service.ChatService.update_chat_title", new=AsyncMock()),
        ):
            await generate_channel_title("chat-1", _SENSITIVE_TEXT, lite, mask_pii=mask_pii)

        assert (_PHONE in title_llm.prompts[0]) is leaks


class TestOfflineCompaction:
    def _messages(self) -> list[BaseMessage]:
        return [HumanMessage(content=_SENSITIVE_TEXT), AIMessage(content="已记录")]

    def test_privacy_on_masks_a_copy_and_leaves_the_originals(self) -> None:
        originals = self._messages()

        masked = _mask_for_summary(originals, _ON)

        _assert_masked(str(masked[0].content))
        assert _PHONE in str(originals[0].content), "stored messages must keep their text"
        assert masked[1].content == "已记录"

    def test_privacy_off_hands_back_the_same_messages(self) -> None:
        originals = self._messages()

        assert _mask_for_summary(originals, _OFF) is originals
        assert _mask_for_summary(originals, None) is originals

    def test_non_text_content_is_left_alone(self) -> None:
        blocks = HumanMessage(content=[{"type": "text", "text": _PHONE}])

        assert _mask_for_summary([blocks], _ON)[0] is blocks

    @pytest.mark.parametrize(("settings", "leaks"), [(_ON, False), (_OFF, True)])
    async def test_flush_hands_the_summarizer_masked_messages_but_archives_the_originals(
        self, settings: dict[str, object], leaks: bool
    ) -> None:
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
        summarizer = AsyncMock(return_value=(None, SimpleNamespace(to_json=lambda: "{}")))
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
            patch("myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config", new=AsyncMock(return_value=object())),
            patch(
                "myrm_agent_harness.agent.context_management.strategies.summary.summarizer.generate_structured_summary",
                new=summarizer,
            ),
            patch(
                "app.services.chat.salient_tool_archive_service.SalientToolArchiveService.archive_salient_tools",
                new=archive,
            ),
        ):
            await _ChatCompactionMixin.flush_compaction_debt("chat-1")

        summarized = str(summarizer.call_args.args[0][0].content)
        assert (_PHONE in summarized) is leaks
        archived = str(archive.call_args.kwargs["messages"][0].content)
        assert _PHONE in archived, "the recall archive keeps the original text"
        repo.cas_update_compaction.assert_awaited_once()
