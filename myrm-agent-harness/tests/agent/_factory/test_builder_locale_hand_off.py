"""Language hand-off of the SkillAgent factory: the spec's languages become the runtime config's.

``locale`` is the session language; ``prompt_locale`` is the language of the prompt and of the model-facing tool texts
the agent builds itself, and it falls back to ``locale`` when the spec names none. A host that sets only ``locale``
still gets a runtime that writes everything in that language.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from myrm_agent_harness.agent.types import AgentRuntimeSpec


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("locale", "prompt_locale", "expected"),
    [
        pytest.param("zh-CN", None, ("zh-CN", "zh-CN"), id="prompt-locale-falls-back-to-locale"),
        pytest.param("zh-CN", "en", ("zh-CN", "en"), id="explicit-prompt-locale-wins"),
        pytest.param(None, None, (None, None), id="no-language-at-all"),
    ],
)
async def test_create_skill_agent_hands_the_runtime_config_the_spec_languages(
    locale: str | None, prompt_locale: str | None, expected: tuple[str | None, str | None]
) -> None:
    from myrm_agent_harness.agent._factory.builder import create_skill_agent

    spec = AgentRuntimeSpec(
        agent_id="agent-locale-hand-off",
        name="locale-hand-off",
        system_prompt="test",
        locale=locale,
        prompt_locale=prompt_locale,
    )

    with patch(
        "myrm_agent_harness.agent.skill_agent.SkillAgent",
    ) as mock_skill_agent_cls:
        mock_skill_agent_cls.return_value = MagicMock()
        await create_skill_agent(spec=spec, llm=MagicMock(), executor=MagicMock())

    config = mock_skill_agent_cls.call_args.kwargs["config"]
    assert (config.locale, config.prompt_locale) == expected
