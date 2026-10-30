"""A failed cron run is repeated only when a repeat can clear its cause."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.api.config import ConfigIncompleteError
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    DeliveryConfig,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)
from myrm_agent_harness.toolkits.llms.errors import FailoverReason, MyrmLLMError

from app.core.cron.adapters import agent_runner
from app.core.cron.adapters.agent_runner import AgentJobRunner, _failure_result, _StreamAccumulator
from app.core.cron.adapters.failure_recoverability import is_transient_failure
from app.core.types import ModelConfig

_BUDGET_GATE = "app.services.budget.enforcer.should_block_execution"
_INJECTION_SCAN = "app.core.cron.adapters.agent_runner.scan_cron_prompt"
_LOAD_USER_CONFIGS = "app.core.channel_bridge.config_loader.load_user_configs"
_RESOLVE_MODEL = "app.core.channel_bridge.model_resolver.resolve_model_config"
_TEMPLATE_GUARD = "app.services.workflow_templates.validation.validate_cron_template_at_execution"
_CREATE_AGENT = "app.ai_agents.agents.AgentFactory.create_general_agent"
_RUNTIME_CONTEXT = "app.services.agent.runtime_context.build_agent_runtime_context"
_SESSION_CREDENTIALS = "app.services.agent.session_credential_assembler.assemble_session_credentials"


def _job(**overrides: object) -> CronJob:
    fields: dict[str, object] = {
        "id": "cron-1",
        "user_id": "user-1",
        "name": "Daily report",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"),
        "status": JobStatus.ACTIVE,
        "prompt": "Generate the report.",
        "delivery": DeliveryConfig(channel="chat"),
        "max_retries": 2,
    }
    fields.update(overrides)
    return CronJob(**fields)  # type: ignore[arg-type]


class _ProviderError(Exception):
    """A provider SDK error: the HTTP status and the body the classifier reads next to the message."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(f"Error code: {status_code} - {message}")
        self.status_code = status_code
        self.body: dict[str, object] = {"error": {"message": message}}


_CONFIG_INCOMPLETE = ConfigIncompleteError(
    user_friendly_message={"en": "No default model configured."},
    technical_details="No defaultModelConfig found",
    resolution_steps=[],
)
_TRANSIENT_RAW: list[Exception] = [
    _ProviderError(429, "Rate limit reached for requests"),
    _ProviderError(504, "Gateway Time-out"),
    _ProviderError(500, "Internal server error"),
    asyncio.TimeoutError(),
    RuntimeError("boom"),
]
_PERMANENT_RAW: list[Exception] = [
    _ProviderError(401, "Incorrect API key provided: sk-...1429"),
    _ProviderError(
        400, "This model's maximum context length is 128000 tokens. However, your messages resulted in 150000 tokens."
    ),
    _ProviderError(402, "You exceeded your current quota, please check your plan and billing details"),
    _CONFIG_INCOMPLETE,
]


class TestIsTransientFailure:
    @pytest.mark.parametrize("exc", _TRANSIENT_RAW, ids=lambda e: type(e).__name__)
    def test_a_cause_that_passes_is_repeatable(self, exc: Exception) -> None:
        assert is_transient_failure(exc) is True

    @pytest.mark.parametrize("exc", _PERMANENT_RAW, ids=lambda e: type(e).__name__)
    def test_a_cause_that_stays_is_not_repeatable(self, exc: Exception) -> None:
        assert is_transient_failure(exc) is False

    @pytest.mark.parametrize(
        ("reason", "repeatable"),
        [
            (FailoverReason.RATE_LIMIT, True),
            (FailoverReason.OVERLOADED, True),
            (FailoverReason.UNKNOWN, True),
            (FailoverReason.AUTH_PERMANENT, False),
            (FailoverReason.CONTEXT_OVERFLOW, False),
            (FailoverReason.BILLING, False),
            (FailoverReason.FORMAT_ERROR, False),
        ],
    )
    def test_an_agent_stream_failure_is_judged_by_its_recorded_reason(self, reason: FailoverReason, repeatable: bool) -> None:
        assert is_transient_failure(MyrmLLMError(error_code=reason, default_msg="provider failed")) is repeatable

    def test_the_recorded_reason_wins_over_what_the_text_alone_classifies_as(self) -> None:
        """The stream gives up on an empty answer with a message the text classifier knows nothing about."""
        empty_answer = MyrmLLMError(
            error_code=FailoverReason.FORMAT_ERROR, default_msg="LLM returned an empty response repeatedly."
        )
        key_text = MyrmLLMError(error_code=FailoverReason.RATE_LIMIT, default_msg="Incorrect API key provided")

        assert is_transient_failure(empty_answer) is False
        assert is_transient_failure(key_text) is True


class TestFailureResult:
    @pytest.mark.parametrize(
        ("exc", "effectful", "retry_safe"),
        [
            (_TRANSIENT_RAW[0], False, True),
            (_TRANSIENT_RAW[0], True, False),
            (_PERMANENT_RAW[0], False, False),
            (_PERMANENT_RAW[0], True, False),
        ],
        ids=["transient", "transient-after-a-send", "permanent", "permanent-after-a-send"],
    )
    def test_a_run_is_repeatable_only_when_nothing_took_effect_and_the_cause_passes(
        self, exc: Exception, effectful: bool, retry_safe: bool
    ) -> None:
        acc = _StreamAccumulator(progress_steps=[{"tool_name": "send_message"}] if effectful else [])

        result = _failure_result(_job(), exc, acc)

        assert result.success is False
        assert result.error == str(exc)
        assert result.retry_safe is retry_safe


class TestInProcessRetries:
    @staticmethod
    async def _run_with(monkeypatch: pytest.MonkeyPatch, exc: Exception) -> AsyncMock:
        """Run the retry loop over runs that fail with ``exc`` and report how often a run started."""
        monkeypatch.setattr(agent_runner, "_memory_overload_reason", lambda: None)
        monkeypatch.setattr(agent_runner.asyncio, "sleep", AsyncMock())
        runner = AgentJobRunner()
        run_once = AsyncMock(side_effect=lambda job, context="": _failure_result(job, exc, _StreamAccumulator()))
        monkeypatch.setattr(runner, "_run_once", run_once)
        await runner._run_with_retries(_job(max_retries=2), context="")
        return run_once

    @pytest.mark.asyncio
    async def test_a_permanent_failure_runs_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert (await self._run_with(monkeypatch, _PERMANENT_RAW[0])).await_count == 1

    @pytest.mark.asyncio
    async def test_a_transient_failure_uses_every_attempt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert (await self._run_with(monkeypatch, _TRANSIENT_RAW[0])).await_count == 3


@contextmanager
def _run_up_to_the_agent(*, model_error: Exception | None = None, template_error: str | None = None) -> Iterator[None]:
    """Stand-ins for everything ``_run_once`` consults before the agent starts, with the budget gate open."""
    user_configs = MagicMock(personal_settings_dict={}, search_cfg=None, security_config_dict={})
    agent = MagicMock()
    agent.model_cfg = MagicMock(model="test-model")
    agent.release_pooled_session = AsyncMock()
    model = (
        {"side_effect": model_error} if model_error else {"return_value": ModelConfig(model="openai/test-model", api_key="key")}
    )
    with ExitStack() as stack:
        stack.enter_context(patch(_BUDGET_GATE, new_callable=AsyncMock, return_value=False))
        stack.enter_context(patch(_LOAD_USER_CONFIGS, new_callable=AsyncMock, return_value=user_configs))
        stack.enter_context(patch(_RESOLVE_MODEL, **model))
        stack.enter_context(patch(_TEMPLATE_GUARD, return_value=template_error))
        stack.enter_context(patch(_CREATE_AGENT, return_value=agent))
        stack.enter_context(patch.object(agent_runner, "grant_run_lease", return_value="lease"))
        stack.enter_context(patch(_RUNTIME_CONTEXT, new_callable=AsyncMock))
        stack.enter_context(patch(_SESSION_CREDENTIALS, new_callable=AsyncMock, return_value=MagicMock()))
        yield


class TestGatesThatTurnTheJobAway:
    """The same job meets the same gate on every repeat, so a run the gate stops is never repeated."""

    @pytest.mark.asyncio
    async def test_job_without_a_prompt(self) -> None:
        result = await AgentJobRunner()._run_once(_job(prompt=""))

        assert (result.success, result.error, result.retry_safe) == (False, "agent job requires a prompt", False)

    @pytest.mark.asyncio
    async def test_prompt_the_injection_scan_rejects(self) -> None:
        with (
            patch(_BUDGET_GATE, new_callable=AsyncMock, return_value=False),
            patch(_INJECTION_SCAN, return_value=["instruction override"]),
        ):
            result = await AgentJobRunner()._run_once(_job())

        assert (result.success, result.error, result.retry_safe) == (
            False,
            "prompt injection detected: instruction override",
            False,
        )

    @pytest.mark.asyncio
    async def test_workflow_template_the_execution_guard_rejects(self) -> None:
        with _run_up_to_the_agent(template_error="template is not trusted"):
            result = await AgentJobRunner()._run_once(_job(workflow_template_id="wf-1"))

        assert (result.success, result.error, result.retry_safe) == (False, "template is not trusted", False)

    @pytest.mark.asyncio
    async def test_run_without_a_usable_model_setting(self) -> None:
        with _run_up_to_the_agent(model_error=_CONFIG_INCOMPLETE):
            result = await AgentJobRunner()._run_once(_job())

        assert result.success is False
        assert result.retry_safe is False
