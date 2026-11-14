from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

from app.ai_agents.agents import GeneralAgentParams
from app.core.types import ModelConfig
from app.services.kanban.task_runner import KanbanTaskRunner, _ResolvedProfile


@pytest.mark.asyncio
async def test_kanban_task_runner_uses_unattended_mode():
    """Test that KanbanTaskRunner sets unattended_mode=True when creating GeneralAgentParams."""

    task = KanbanTask(
        task_id="test-task-1",
        board_id="board-1",
        title="Test Kanban Task",
        description="This is a test task",
        agent_id="test-agent-1",
    )

    mock_store = AsyncMock()
    mock_store.get_board.return_value = None
    runner = KanbanTaskRunner(mock_store)

    mock_model_cfg = ModelConfig(model="test-model", api_key="test-key")

    mock_settings = MagicMock()
    mock_settings.database = MagicMock()
    mock_settings.database.event_log_dir = "/tmp/test-event-logs"
    mock_settings.event_log_max_jsonl_line_bytes = 1024

    with (
        patch("app.ai_agents.agents.AgentFactory.create_general_agent") as mock_create_agent,
        patch(
            "app.services.kanban.task_runner.runner.build_task_context",
            new_callable=AsyncMock,
        ) as mock_build_context,
        patch(
            "app.services.kanban.task_runner.runner.resolve_agent_profile",
            new_callable=AsyncMock,
        ) as mock_resolve_profile,
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
        ) as mock_load_user_configs,
        patch(
            "app.core.channel_bridge.model_resolver.resolve_model_config",
            return_value=mock_model_cfg,
        ),
        patch(
            "app.core.channel_bridge.model_resolver.enrich_model_context_window",
            return_value=mock_model_cfg,
        ),
        patch(
            "app.services.agent.swarm_fission_resume.stream_with_swarm_fission_resume",
            new_callable=AsyncMock,
        ) as mock_stream,
        patch(
            "app.config.settings.get_settings",
            return_value=mock_settings,
        ),
    ):
        mock_build_context.return_value = "test context"
        mock_resolve_profile.return_value = None

        mock_configs = MagicMock()
        mock_configs.retrieval_dict = {}
        mock_configs.providers_dict = {"providers": []}
        mock_configs.security_config_dict = {}
        mock_configs.search_cfg = {"searchService": "tavily"}
        mock_configs.search_is_user_configured = False
        mock_load_user_configs.return_value = mock_configs

        mock_agent = AsyncMock()
        mock_create_agent.return_value = mock_agent

        async def mock_stream_gen(*args, **kwargs):
            yield {"type": "message_end", "usage": {}}

        mock_stream.side_effect = mock_stream_gen

        await runner.run(task)

        mock_create_agent.assert_called_once()
        params = mock_create_agent.call_args[0][0]

        assert isinstance(params, GeneralAgentParams)
        assert params.unattended_mode is True, "Kanban tasks must run in unattended_mode to prevent blocking"
        assert params.event_log_dir == "/tmp/test-event-logs", "Kanban tasks must write event logs so runs trace is available"
        assert params.event_log_max_jsonl_line_bytes == 1024, "Kanban task event logs must cap JSONL line bytes"


class TestResolvedProfile:
    def test_agent_type_field_exists(self):
        """Verify _ResolvedProfile includes agent_type to prevent AttributeError."""
        profile = _ResolvedProfile(
            agent_type="team",
            system_prompt=None,
            model=None,
            skill_ids=(),
            subagent_ids=("sub1", "sub2"),
            security_overrides=None,
            max_iterations=None,
            memory_policy=None,
            memory_decay_profile=None,
            memory_extraction_preset=None,
            engine_params=None,
            auto_restore_domains=(),
            enabled_builtin_tools=("web_search",),
        )
        assert profile.agent_type == "team"

    def test_agent_type_default_individual(self):
        """Verify from_resolved defaults agent_type to 'individual'."""
        mock_resolved = MagicMock(spec=[])
        profile = _ResolvedProfile.from_resolved(mock_resolved)
        assert profile.agent_type == "individual"

    def test_from_resolved_extracts_agent_type(self):
        """Verify from_resolved correctly extracts agent_type from source."""
        mock_resolved = MagicMock()
        mock_resolved.agent_type = "team"
        mock_resolved.system_prompt = "test prompt"
        mock_resolved.model = "gpt-4"
        mock_resolved.skill_ids = ("skill1",)
        mock_resolved.subagent_ids = ("sub1",)
        mock_resolved.security_overrides = None
        mock_resolved.max_iterations = 50
        mock_resolved.memory_policy = None
        mock_resolved.memory_decay_profile = "normal"
        mock_resolved.engine_params = None
        mock_resolved.auto_restore_domains = ()
        mock_resolved.enabled_builtin_tools = ("web_search",)

        profile = _ResolvedProfile.from_resolved(mock_resolved)
        assert profile.agent_type == "team"
        assert profile.system_prompt == "test prompt"
        assert profile.model == "gpt-4"


class TestTaskModelOverride:
    """Per-task model_override must win over the agent profile model."""

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("task_model", "profile_model", "expected"),
        [
            ("anthropic/claude-sonnet-4", "openai/gpt-4o", "anthropic/claude-sonnet-4"),
            (None, "openai/gpt-4o", "openai/gpt-4o"),
            (None, None, None),
        ],
    )
    async def test_model_resolution_priority(self, task_model, profile_model, expected):
        task = KanbanTask(
            task_id="model-task-1",
            board_id="board-1",
            title="Model Override Task",
            agent_id="agent-1",
            model_override=task_model,
        )

        mock_store = AsyncMock()
        mock_store.get_board.return_value = None
        runner = KanbanTaskRunner(mock_store)

        mock_model_cfg = ModelConfig(model="resolved-model", api_key="test-key")

        mock_settings = MagicMock()
        mock_settings.database = MagicMock()
        mock_settings.database.event_log_dir = "/tmp/test-event-logs"
        mock_settings.event_log_max_jsonl_line_bytes = 1024

        resolved_args: list[str | None] = []

        def _capture_resolve(providers, **kwargs):
            resolved_args.append(kwargs.get("model_override"))
            return mock_model_cfg

        with (
            patch("app.ai_agents.agents.AgentFactory.create_general_agent") as mock_create_agent,
            patch(
                "app.services.kanban.task_runner.runner.build_task_context",
                new_callable=AsyncMock,
            ) as mock_build_context,
            patch(
                "app.services.kanban.task_runner.runner.resolve_agent_profile",
                new_callable=AsyncMock,
            ) as mock_resolve_profile,
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
            ) as mock_load_user_configs,
            patch(
                "app.core.channel_bridge.model_resolver.resolve_model_config",
                side_effect=_capture_resolve,
            ),
            patch(
                "app.core.channel_bridge.model_resolver.enrich_model_capabilities",
                return_value=mock_model_cfg,
            ),
            patch(
                "app.core.channel_bridge.model_resolver.enrich_model_context_window",
                return_value=mock_model_cfg,
            ),
            patch(
                "app.services.agent.swarm_fission_resume.stream_with_swarm_fission_resume",
                new_callable=AsyncMock,
            ) as mock_stream,
            patch(
                "app.config.settings.get_settings",
                return_value=mock_settings,
            ),
        ):
            mock_build_context.return_value = "test context"
            mock_resolve_profile.return_value = (
                _ResolvedProfile(
                    agent_type="team",
                    system_prompt=None,
                    model=profile_model,
                    skill_ids=(),
                    subagent_ids=(),
                    security_overrides=None,
                    max_iterations=None,
                    memory_policy=None,
                    memory_decay_profile=None,
                    memory_extraction_preset=None,
                    engine_params=None,
                    auto_restore_domains=(),
                    enabled_builtin_tools=("web_search",),
                )
                if profile_model
                else None
            )

            mock_configs = MagicMock()
            mock_configs.retrieval_dict = {}
            mock_configs.providers_dict = {"providers": []}
            mock_configs.security_config_dict = {}
            mock_configs.search_cfg = {"searchService": "tavily"}
            mock_configs.search_is_user_configured = False
            mock_load_user_configs.return_value = mock_configs

            mock_agent = AsyncMock()
            mock_create_agent.return_value = mock_agent

            async def _stream_events(*args, **kwargs):
                yield {"type": "message_end", "usage": {}}

            mock_agent.process_stream = _stream_events

            async def mock_stream_gen(*args, **kwargs):
                yield {"type": "message_end", "usage": {}}

            mock_stream.side_effect = mock_stream_gen

            await runner.run(task)

            assert resolved_args == [expected], (
                f"resolve_model_config must receive {expected!r} as model_override "
                f"(task={task_model!r}, profile={profile_model!r})"
            )


class TestKanbanEnableMemory:
    """Kanban tasks must honor the user-level memory master switch.

    Kanban runs unattended (``unattended_mode=True``); mounting the memory
    group / enabling auto-extraction when the user disabled memory globally
    would write task outputs into a memory store the user turned off.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("personal_settings", "expected"),
        [
            ({"enableMemory": True}, True),
            ({"enableMemory": False}, False),
            (None, False),
            ({}, False),
        ],
    )
    async def test_enable_memory_follows_global_switch(self, personal_settings, expected):
        task = KanbanTask(
            task_id="memory-task-1",
            board_id="board-1",
            title="Memory Switch Task",
            agent_id="agent-1",
        )

        mock_store = AsyncMock()
        mock_store.get_board.return_value = None
        runner = KanbanTaskRunner(mock_store)

        mock_model_cfg = ModelConfig(model="test-model", api_key="test-key")

        mock_settings = MagicMock()
        mock_settings.database = MagicMock()
        mock_settings.database.event_log_dir = "/tmp/test-event-logs"
        mock_settings.event_log_max_jsonl_line_bytes = 1024

        with (
            patch("app.ai_agents.agents.AgentFactory.create_general_agent") as mock_create_agent,
            patch(
                "app.services.kanban.task_runner.runner.build_task_context",
                new_callable=AsyncMock,
            ) as mock_build_context,
            patch(
                "app.services.kanban.task_runner.runner.resolve_agent_profile",
                new_callable=AsyncMock,
            ) as mock_resolve_profile,
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
            ) as mock_load_user_configs,
            patch(
                "app.core.channel_bridge.model_resolver.resolve_model_config",
                return_value=mock_model_cfg,
            ),
            patch(
                "app.core.channel_bridge.model_resolver.enrich_model_context_window",
                return_value=mock_model_cfg,
            ),
            patch(
                "app.services.agent.swarm_fission_resume.stream_with_swarm_fission_resume",
                new_callable=AsyncMock,
            ) as mock_stream,
            patch(
                "app.config.settings.get_settings",
                return_value=mock_settings,
            ),
        ):
            mock_build_context.return_value = "test context"
            mock_resolve_profile.return_value = None

            mock_configs = MagicMock()
            mock_configs.retrieval_dict = {}
            mock_configs.providers_dict = {"providers": []}
            mock_configs.security_config_dict = {}
            mock_configs.search_cfg = {"searchService": "tavily"}
            mock_configs.search_is_user_configured = False
            mock_configs.personal_settings_dict = personal_settings
            mock_load_user_configs.return_value = mock_configs

            mock_agent = AsyncMock()
            mock_create_agent.return_value = mock_agent

            async def mock_stream_gen(*args, **kwargs):
                yield {"type": "message_end", "usage": {}}

            mock_stream.side_effect = mock_stream_gen

            await runner.run(task)

            mock_create_agent.assert_called_once()
            params = mock_create_agent.call_args[0][0]
            assert params.enable_memory is expected
