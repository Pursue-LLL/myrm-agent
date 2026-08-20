"""Coverage tests for the AgentRepository public CRUD surface.

Complements the allow_discovery-focused tests by exercising the remaining
public entry points (get/list/count/delete, core field updates, command
binding and gateway-config rehydration, conflict handling) so the
repository module stays fully covered.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.backends.profiles.types import AgentProfile
from sqlalchemy.orm.exc import StaleDataError

from app.core.security.master_key import MasterKeyProvider
from app.database.models import Agent
from app.database.repositories.agent_repo import AgentRepository


class TestGetProfile:
    @pytest.mark.asyncio
    async def test_returns_profile(self) -> None:
        db = AsyncMock()
        agent = Agent(id="a1", name="Agent1")
        result = MagicMock()
        result.scalar_one_or_none.return_value = agent
        db.execute.return_value = result

        profile = await AgentRepository.get_profile(db, "a1")

        assert profile is not None
        assert profile.id == "a1"
        assert profile.display_name == "Agent1"

    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        assert await AgentRepository.get_profile(db, "missing") is None


class TestListProfiles:
    @pytest.mark.asyncio
    async def test_lists_all(self) -> None:
        db = AsyncMock()
        agents = [Agent(id="a1", name="A"), Agent(id="a2", name="B")]
        result = MagicMock()
        result.scalars.return_value.all.return_value = agents
        db.execute.return_value = result

        profiles = await AgentRepository.list_profiles(db)

        assert [p.id for p in profiles] == ["a1", "a2"]

    @pytest.mark.asyncio
    async def test_lists_with_exclude_ids(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        db.execute.return_value = result

        await AgentRepository.list_profiles(db, exclude_ids=["a1"])

        assert result.scalars.return_value.all.called


class TestCountProfiles:
    @pytest.mark.asyncio
    async def test_counts(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one.return_value = 3
        db.execute.return_value = result

        assert await AgentRepository.count_profiles(db) == 3

    @pytest.mark.asyncio
    async def test_counts_with_exclude_ids(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one.return_value = 1
        db.execute.return_value = result

        assert await AgentRepository.count_profiles(db, exclude_ids=["a1"]) == 1


class TestCreateProfile:
    @staticmethod
    def _added_agent(db: AsyncMock) -> Agent:
        for call in db.add.call_args_list:
            obj = call.args[0]
            if isinstance(obj, Agent):
                return obj
        raise AssertionError("Agent was never added to the session")

    @pytest.mark.asyncio
    async def test_raises_when_id_exists(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = Agent(id="a1", name="Existing")
        db.execute.return_value = result

        with pytest.raises(ValueError):
            await AgentRepository.create_profile(db, AgentProfile(id="a1", display_name="Agent1"))

    @pytest.mark.asyncio
    async def test_sets_model_selection_from_profile_model(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        profile = AgentProfile(id="a1", display_name="Agent1", model="gpt-4o")
        await AgentRepository.create_profile(db, profile)

        agent = self._added_agent(db)
        assert agent.model_config == {"model": "gpt-4o"}
        assert agent.model_selection == {"providerId": "auto", "model": "gpt-4o"}

    @pytest.mark.asyncio
    async def test_encrypts_gateway_token_on_create(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        profile = AgentProfile(
            id="a1",
            display_name="Agent1",
            metadata={"tool_gateway_config": {"auth_token": "raw-token"}},
        )
        with (
            patch.object(MasterKeyProvider, "get_master_key", return_value="mk"),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.derive_key",
                return_value="derived",
            ),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.encrypt_value",
                return_value={"value": "encrypted"},
            ),
        ):
            await AgentRepository.create_profile(db, profile)

        agent = self._added_agent(db)
        assert agent.tool_gateway_config == {"auth_token": {"value": "encrypted"}}


class TestUpdateProfileCoreFields:
    @pytest.mark.asyncio
    async def test_returns_none_when_missing(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        assert await AgentRepository.update_profile(db, "missing", {}) is None

    @pytest.mark.asyncio
    async def test_updates_core_fields(self) -> None:
        db = AsyncMock()
        agent = Agent(id="a1", name="Old", description="")
        result = MagicMock()
        result.scalar_one_or_none.return_value = agent
        db.execute.return_value = result

        with patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "display_name": "New",
                    "description": "Desc",
                    "model": "gpt-4o",
                    "system_prompt": "SP",
                    "skills": ["s1"],
                    "max_iterations": 10,
                    "tools_allowed": [],
                    "memory_policy": None,
                    "workspace_policy": "ISOLATED_COPY",
                    "built_in": True,
                },
            )

        assert agent.name == "New"
        assert agent.description == "Desc"
        assert agent.model_config == {"model": "gpt-4o"}
        assert agent.system_prompt == "SP"
        assert agent.skill_ids == ["s1"]
        assert agent.max_iterations == 10
        assert agent.workspace_policy == "ISOLATED_COPY"
        assert agent.is_public is True
        assert agent.is_built_in is True

    @pytest.mark.asyncio
    async def test_updates_metadata_fields(self) -> None:
        db = AsyncMock()
        agent = Agent(id="a1", name="Agent1", subagent_ids=[])
        result = MagicMock()
        result.scalar_one_or_none.return_value = agent
        db.execute.return_value = result

        with patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "metadata": {
                        "mcp_ids": ["mcp1"],
                        "home_directory": "/home/agent",
                        "prompt_mode": "lean",
                        "personality_style": "friendly",
                        "subagent_ids": ["s1"],
                        "auto_restore_domains": ["example.com"],
                        "suggestion_prompts": ["prompt"],
                        "agent_type": "team",
                        "mounted_skill_ids": ["skill1"],
                    }
                },
            )

        assert agent.mcp_servers == ["mcp1"]
        assert agent.home_directory == "/home/agent"
        assert agent.prompt_mode == "lean"
        assert agent.personality_style == "friendly"
        assert agent.subagent_ids == ["s1"]
        assert agent.auto_restore_domains == ["example.com"]
        assert agent.suggestion_prompts == ["prompt"]
        assert agent.agent_type == "team"
        assert agent.mounted_skill_ids == ["skill1"]

    @pytest.mark.asyncio
    async def test_conflict_on_history_flush_raises_409(self) -> None:
        from fastapi import HTTPException

        db = AsyncMock()
        agent = Agent(id="a1", name="Agent1")
        result = MagicMock()
        result.scalar_one_or_none.return_value = agent
        db.execute.return_value = result
        db.flush.side_effect = StaleDataError("stale")

        with (
            pytest.raises(HTTPException) as exc_info,
            patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()),
        ):
            await AgentRepository.update_profile(db, "a1", {"display_name": "New"})

        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_conflict_on_final_flush_raises_409(self) -> None:
        from fastapi import HTTPException

        db = AsyncMock()
        agent = Agent(id="a1", name="Agent1")
        result = MagicMock()
        result.scalar_one_or_none.return_value = agent
        db.execute.return_value = result
        db.flush.side_effect = StaleDataError("stale")

        with (
            pytest.raises(HTTPException) as exc_info,
            patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()),
        ):
            await AgentRepository.update_profile(db, "a1", {"metadata": {"allow_discovery": False}})

        assert exc_info.value.status_code == 409


class TestDeleteProfile:
    @pytest.mark.asyncio
    async def test_deletes_existing(self) -> None:
        db = AsyncMock()
        agent = Agent(id="a1", name="Agent1")
        result = MagicMock()
        result.scalar_one_or_none.return_value = agent
        db.execute.return_value = result

        assert await AgentRepository.delete_profile(db, "a1") is True
        db.delete.assert_called_once_with(agent)

    @pytest.mark.asyncio
    async def test_returns_false_when_missing(self) -> None:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        assert await AgentRepository.delete_profile(db, "missing") is False


class TestRehydrationCoverage:
    def test_parses_command_bindings(self) -> None:
        agent = Agent(
            id="a1",
            name="Agent1",
            command_bindings=[
                {
                    "command_name": "cmd",
                    "skill_ids": ["s1"],
                    "description": "desc",
                    "aliases": ["c"],
                    "instruction": "instr",
                }
            ],
        )

        profile = AgentRepository._agent_to_profile(agent)

        assert profile.command_bindings is not None
        assert profile.command_bindings[0].command_name == "cmd"
        assert profile.command_bindings[0].skill_ids == ("s1",)

    def test_skips_invalid_command_bindings(self) -> None:
        agent = Agent(
            id="a1",
            name="Agent1",
            command_bindings=[{"no_command": True}],
        )

        profile = AgentRepository._agent_to_profile(agent)

        assert profile.command_bindings is None

    def test_decrypts_gateway_token(self) -> None:
        agent = Agent(
            id="a1",
            name="Agent1",
            tool_gateway_config={"auth_token": "enc:abc"},
        )

        with (
            patch.object(MasterKeyProvider, "get_master_key", return_value="mk"),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.derive_key",
                return_value="derived",
            ),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.decrypt_value",
                return_value={"value": "plain"},
            ),
        ):
            profile = AgentRepository._agent_to_profile(agent)

        assert profile.metadata is not None
        assert profile.metadata["tool_gateway_config"]["auth_token"] == "plain"

    def test_plaintext_gateway_token_falls_back(self) -> None:
        agent = Agent(
            id="a1",
            name="Agent1",
            tool_gateway_config={"auth_token": "already-plain"},
        )

        with (
            patch.object(MasterKeyProvider, "get_master_key", return_value="mk"),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.derive_key",
                return_value="derived",
            ),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.decrypt_value",
                side_effect=Exception("decrypt failed"),
            ),
        ):
            profile = AgentRepository._agent_to_profile(agent)

        assert profile.metadata is not None
        assert profile.metadata["tool_gateway_config"]["auth_token"] == "already-plain"

    def test_crypto_init_failure_keeps_plaintext(self) -> None:
        """Crypto bootstrap failure must not crash profile rehydration."""
        agent = Agent(
            id="a1",
            name="Agent1",
            tool_gateway_config={"auth_token": "raw"},
        )

        with (
            patch.object(
                MasterKeyProvider,
                "get_master_key",
                side_effect=Exception("no master key"),
            ),
        ):
            profile = AgentRepository._agent_to_profile(agent)

        assert profile.metadata is not None
        assert profile.metadata["tool_gateway_config"]["auth_token"] == "raw"


class TestUpdateProfileMetadataBranches:
    """Remaining update_profile metadata branches not covered elsewhere."""

    @staticmethod
    def _make_db(agent: Agent) -> AsyncMock:
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = agent
        db.execute.return_value = result
        return db

    @pytest.mark.asyncio
    async def test_updates_misc_metadata_fields(self) -> None:
        db = self._make_db(Agent(id="a1", name="Agent1"))
        agent = db.execute.return_value.scalar_one_or_none.return_value

        with patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "metadata": {
                        "mcp_tool_selections": {"mcp1": ["tool-a"]},
                        "security_overrides": {"danger": ["rm"]},
                        "default_security_preset": "strict",
                        "workspace_policy": "ISOLATED_COPY",
                        "engine_params": {"marketplace_entry_id": "entry-1"},
                        "openapi_services": ["svc"],
                        "session_policy": {"max_turns": 5},
                        "notify_targets": ["webhook"],
                    }
                },
            )

        assert agent.mcp_tool_selections == {"mcp1": ["tool-a"]}
        assert agent.security_overrides == {"danger": ["rm"]}
        assert agent.default_security_preset == "strict"
        assert agent.workspace_policy == "ISOLATED_COPY"
        assert agent.engine_params == {"marketplace_entry_id": "entry-1"}
        assert agent.openapi_services == ["svc"]
        assert agent.session_policy == {"max_turns": 5}
        assert agent.notify_targets == ["webhook"]

    @pytest.mark.asyncio
    async def test_metadata_none_values_are_cleared(self) -> None:
        db = self._make_db(Agent(id="a1", name="Agent1"))
        agent = db.execute.return_value.scalar_one_or_none.return_value

        with patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "metadata": {
                        "mcp_tool_selections": None,
                        "engine_params": None,
                        "auto_restore_domains": None,
                        "suggestion_prompts": None,
                        "openapi_services": None,
                        "session_policy": None,
                        "notify_targets": None,
                        "tool_gateway_config": None,
                    }
                },
            )

        assert agent.mcp_tool_selections is None
        assert agent.engine_params is None
        assert agent.auto_restore_domains is None
        assert agent.suggestion_prompts is None
        assert agent.openapi_services is None
        assert agent.session_policy is None
        assert agent.notify_targets is None
        assert agent.tool_gateway_config is None

    @pytest.mark.asyncio
    async def test_updates_avatar_skill_configs_and_cron(self) -> None:
        db = self._make_db(Agent(id="a1", name="Agent1"))
        agent = db.execute.return_value.scalar_one_or_none.return_value

        with patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "avatar": "https://example.com/a.png",
                    "skill_configs": {"s1": {"enabled": True}},
                    "cron_post_run_verify": True,
                    "command_bindings": None,
                },
            )

        assert agent.avatar == "https://example.com/a.png"
        assert agent.skill_configs == {"s1": {"enabled": True}}
        assert agent.cron_post_run_verify is True
        assert agent.command_bindings is None

    @pytest.mark.asyncio
    async def test_updates_model_selection_from_dict(self) -> None:
        db = self._make_db(Agent(id="a1", name="Agent1"))
        agent = db.execute.return_value.scalar_one_or_none.return_value

        with patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "model": "gpt-4.1",
                    "model_selection": {"providerId": "openai", "model": "gpt-4.1"},
                },
            )

        assert agent.model_config == {"model": "gpt-4.1"}
        assert agent.model_selection == {
            "providerId": "openai",
            "model": "gpt-4.1",
        }

    @pytest.mark.asyncio
    async def test_updates_command_binding_objects(self) -> None:
        from myrm_agent_harness.backends.profiles.types import CommandBinding

        db = self._make_db(Agent(id="a1", name="Agent1"))
        agent = db.execute.return_value.scalar_one_or_none.return_value

        with patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "command_bindings": [
                        CommandBinding(
                            command_name="cmd",
                            skill_ids=("s1",),
                            description="desc",
                            aliases=("c",),
                            instruction="instr",
                        )
                    ],
                },
            )

        assert agent.command_bindings == [
            {
                "command_name": "cmd",
                "skill_ids": ["s1"],
                "description": "desc",
                "aliases": ["c"],
                "instruction": "instr",
            }
        ]

    @pytest.mark.asyncio
    async def test_updates_enabled_builtin_tools_via_metadata(self) -> None:
        db = self._make_db(Agent(id="a1", name="Agent1"))
        agent = db.execute.return_value.scalar_one_or_none.return_value

        with patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()):
            await AgentRepository.update_profile(
                db,
                "a1",
                {"metadata": {"enabled_builtin_tools": ["web_search"]}},
            )

        assert agent.enabled_builtin_tools == ["web_search"]

    @pytest.mark.asyncio
    async def test_updates_browser_source_dialog_policy_session_recording(self) -> None:
        db = self._make_db(Agent(id="a1", name="Agent1"))
        agent = db.execute.return_value.scalar_one_or_none.return_value

        with patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "metadata": {
                        "browser_source": "chromium",
                        "dialog_policy": "auto",
                        "session_recording": "enabled",
                    }
                },
            )

        assert agent.browser_source == "chromium"
        assert agent.dialog_policy == "auto"
        assert agent.session_recording == "enabled"

    @pytest.mark.asyncio
    async def test_encrypts_gateway_token_on_update(self) -> None:
        db = self._make_db(Agent(id="a1", name="Agent1"))
        agent = db.execute.return_value.scalar_one_or_none.return_value

        with (
            patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()),
            patch.object(MasterKeyProvider, "get_master_key", return_value="mk"),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.derive_key",
                return_value="derived",
            ),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.encrypt_value",
                return_value={"value": "encrypted"},
            ),
        ):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "metadata": {
                        "tool_gateway_config": {"auth_token": "raw-token"},
                    }
                },
            )

        assert agent.tool_gateway_config == {"auth_token": {"value": "encrypted"}}

    @pytest.mark.asyncio
    async def test_update_encrypt_failure_removes_token(self) -> None:
        """Encryption failure must never persist a plaintext gateway token."""
        db = self._make_db(Agent(id="a1", name="Agent1"))
        agent = db.execute.return_value.scalar_one_or_none.return_value

        with (
            patch.object(AgentRepository, "_agent_to_profile", return_value=MagicMock()),
            patch.object(MasterKeyProvider, "get_master_key", return_value="mk"),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.derive_key",
                return_value="derived",
            ),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.encrypt_value",
                side_effect=Exception("encrypt failed"),
            ),
        ):
            await AgentRepository.update_profile(
                db,
                "a1",
                {
                    "metadata": {
                        "tool_gateway_config": {"auth_token": "raw-token"},
                    }
                },
            )

        assert agent.tool_gateway_config == {}

    @pytest.mark.asyncio
    async def test_create_encrypt_failure_removes_token(self) -> None:
        """create_profile must drop the token (never store plaintext) on failure."""
        db = AsyncMock()
        result = MagicMock()
        result.scalar_one_or_none.return_value = None
        db.execute.return_value = result

        profile = AgentProfile(
            id="a1",
            display_name="Agent1",
            metadata={"tool_gateway_config": {"auth_token": "raw-token"}},
        )
        with (
            patch.object(MasterKeyProvider, "get_master_key", return_value="mk"),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.derive_key",
                return_value="derived",
            ),
            patch(
                "myrm_agent_harness.utils.crypto.config_crypto.ConfigCrypto.encrypt_value",
                side_effect=Exception("encrypt failed"),
            ),
        ):
            await AgentRepository.create_profile(db, profile)

        for call in db.add.call_args_list:
            obj = call.args[0]
            if isinstance(obj, Agent):
                assert obj.tool_gateway_config == {}
                return
        raise AssertionError("Agent was never added to the session")
