"""Tests for retry memory extraction privacy context wiring.

Covers the server-layer bridge that re-establishes the harness privacy
context (policy + PseudonymStore + regex PII pseudonymizer) so retried
memories are protected exactly like the agent-run path, and LLM-based deep
PII scan applies when the user enabled it.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.memory.retry_chat_memory_extract import (
    _privacy_deep_scan_context,
    _run_retry_extract,
)


class TestPrivacyDeepScanContext:
    """Test the _privacy_deep_scan_context helper."""

    def test_disabled_when_no_personal_settings(self):
        """Privacy context must stay inactive when settings are missing."""
        with (
            patch("myrm_agent_harness.api.hooks.set_privacy_policy") as mock_set_policy,
            patch("myrm_agent_harness.api.hooks.set_pseudonym_store") as mock_set_store,
        ):
            with _privacy_deep_scan_context(None, "/tmp/ws") as deep_scan:
                assert deep_scan is False
            mock_set_policy.assert_not_called()
            mock_set_store.assert_not_called()

    def test_disabled_when_privacy_disabled(self):
        """Privacy context must stay inactive when privacyEnabled is off."""
        settings = {"privacyDeepScan": True, "privacyEnabled": False}
        with (
            patch("myrm_agent_harness.api.hooks.set_privacy_policy") as mock_set_policy,
            patch("myrm_agent_harness.api.hooks.set_pseudonym_store") as mock_set_store,
        ):
            with _privacy_deep_scan_context(settings, "/tmp/ws") as deep_scan:
                assert deep_scan is False
            mock_set_policy.assert_not_called()
            mock_set_store.assert_not_called()

    def test_enabled_installs_policy_and_store(self):
        """Deep scan on with PSEUDONYMIZE must install policy + store + closure."""
        settings = {
            "privacyDeepScan": True,
            "privacyEnabled": True,
            "privacyS2Action": "pseudonymize",
            "privacyS3Action": "redact",
        }
        mock_store = MagicMock()
        with (
            patch("myrm_agent_harness.api.hooks.set_privacy_policy") as mock_set_policy,
            patch("myrm_agent_harness.api.hooks.set_pseudonym_store") as mock_set_store,
            patch(
                "myrm_agent_harness.api.hooks.get_pseudonym_store",
                return_value=None,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_privacy_policy",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.api.hooks.build_pseudonym_store",
                return_value=mock_store,
            ) as mock_build_store,
            patch(
                "myrm_agent_harness.api.hooks.install_memory_pseudonymizer",
                return_value=None,
            ) as mock_install,
            patch("myrm_agent_harness.api.hooks.restore_memory_pseudonymizer"),
        ):
            with _privacy_deep_scan_context(settings, "/tmp/ws") as deep_scan:
                assert deep_scan is True
        installed_policy = mock_set_policy.call_args_list[0].args[0]
        assert installed_policy.deep_scan is True
        assert installed_policy.s2_action.value == "pseudonymize"
        mock_build_store.assert_called_once_with("/tmp/pseudonym_store.db")
        assert mock_set_store.call_args_list[0].args[0] is mock_store
        mock_install.assert_called_once_with(installed_policy, mock_store)

    def test_regex_closure_installed_without_deep_scan(self):
        """PSEUDONYMIZE alone must still install the regex pseudonymizer.

        Privacy promise must not depend on the LLM deep-scan toggle: even with
        deep_scan off, retried memory writes get regex-level pseudonymization.
        """
        settings = {
            "privacyDeepScan": False,
            "privacyEnabled": True,
            "privacyS2Action": "pseudonymize",
            "privacyS3Action": "redact",
        }
        mock_store = MagicMock()
        with (
            patch("myrm_agent_harness.api.hooks.set_privacy_policy"),
            patch("myrm_agent_harness.api.hooks.set_pseudonym_store"),
            patch(
                "myrm_agent_harness.api.hooks.get_pseudonym_store",
                return_value=None,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_privacy_policy",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.api.hooks.build_pseudonym_store",
                return_value=mock_store,
            ) as mock_build_store,
            patch(
                "myrm_agent_harness.api.hooks.install_memory_pseudonymizer",
                return_value=None,
            ) as mock_install,
            patch("myrm_agent_harness.api.hooks.restore_memory_pseudonymizer"),
        ):
            with _privacy_deep_scan_context(settings, "/tmp/ws") as deep_scan:
                assert deep_scan is False
        mock_build_store.assert_called_once_with("/tmp/pseudonym_store.db")
        mock_install.assert_called_once()

    def test_missing_workspace_logs_warning_and_skips_store(self):
        """Missing workspace must log a warning and skip store + closure."""
        settings = {
            "privacyDeepScan": True,
            "privacyEnabled": True,
            "privacyS2Action": "pseudonymize",
            "privacyS3Action": "redact",
        }
        with (
            patch("myrm_agent_harness.api.hooks.set_privacy_policy"),
            patch("myrm_agent_harness.api.hooks.set_pseudonym_store") as mock_set_store,
            patch(
                "myrm_agent_harness.api.hooks.get_pseudonym_store",
                return_value=None,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_privacy_policy",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.api.hooks.build_pseudonym_store",
            ) as mock_build_store,
            patch(
                "myrm_agent_harness.api.hooks.install_memory_pseudonymizer",
            ) as mock_install,
            patch("app.services.memory.retry_chat_memory_extract.logger") as mock_logger,
        ):
            with _privacy_deep_scan_context(settings, None) as deep_scan:
                assert deep_scan is True
        mock_build_store.assert_not_called()
        mock_install.assert_not_called()
        mock_set_store.assert_not_called()
        mock_logger.warning.assert_called_once()

    def test_enabled_without_store_when_no_pseudonymize(self):
        """Deep scan on without PSEUDONYMIZE must not build a store."""
        settings = {
            "privacyDeepScan": True,
            "privacyEnabled": True,
            "privacyS2Action": "redact",
            "privacyS3Action": "block",
        }
        with (
            patch("myrm_agent_harness.api.hooks.set_privacy_policy") as mock_set_policy,
            patch(
                "myrm_agent_harness.api.hooks.get_pseudonym_store",
                return_value=None,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_privacy_policy",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.api.hooks.build_pseudonym_store",
            ) as mock_build_store,
        ):
            with _privacy_deep_scan_context(settings, "/tmp/ws") as deep_scan:
                assert deep_scan is True
        mock_build_store.assert_not_called()
        installed_policy = mock_set_policy.call_args_list[0].args[0]
        assert installed_policy.deep_scan is True

    def test_restores_previous_context_on_exit(self):
        """Exit must restore the previous policy, store, and pseudonymizer."""
        settings = {
            "privacyDeepScan": True,
            "privacyEnabled": True,
            "privacyS2Action": "pseudonymize",
            "privacyS3Action": "redact",
        }
        prev_policy = MagicMock()
        prev_store = MagicMock()
        prev_pseudonymizer = MagicMock()
        with (
            patch("myrm_agent_harness.api.hooks.set_privacy_policy") as mock_set_policy,
            patch("myrm_agent_harness.api.hooks.set_pseudonym_store") as mock_set_store,
            patch(
                "myrm_agent_harness.api.hooks.get_privacy_policy",
                return_value=prev_policy,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_pseudonym_store",
                return_value=prev_store,
            ),
            patch(
                "myrm_agent_harness.api.hooks.build_pseudonym_store",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.api.hooks.install_memory_pseudonymizer",
                return_value=prev_pseudonymizer,
            ),
            patch(
                "myrm_agent_harness.api.hooks.restore_memory_pseudonymizer"
            ) as mock_restore,
        ):
            with _privacy_deep_scan_context(settings, "/tmp/ws") as deep_scan:
                assert deep_scan is True
        # First call installs the new policy; last call restores the previous one.
        calls = [call.args[0] for call in mock_set_policy.call_args_list]
        assert calls[0] is not prev_policy
        assert calls[-1] is prev_policy
        assert mock_set_store.call_args_list[-1].args[0] is prev_store
        mock_restore.assert_called_once_with(prev_pseudonymizer)

    def test_invalid_action_falls_back_to_default(self):
        """Invalid persisted PII actions must fall back without crashing."""
        settings = {
            "privacyDeepScan": True,
            "privacyEnabled": True,
            "privacyS2Action": "alert",
            "privacyS3Action": "alert",
        }
        with (
            patch("myrm_agent_harness.api.hooks.set_privacy_policy") as mock_set_policy,
            patch("myrm_agent_harness.api.hooks.get_pseudonym_store"),
            patch(
                "myrm_agent_harness.api.hooks.get_privacy_policy",
                return_value=MagicMock(),
            ),
            patch("myrm_agent_harness.api.hooks.set_pseudonym_store"),
        ):
            with _privacy_deep_scan_context(settings, "/tmp/ws") as deep_scan:
                assert deep_scan is True
        installed_policy = mock_set_policy.call_args_list[0].args[0]
        assert installed_policy.s2_action.value == "warn"
        assert installed_policy.s3_action.value == "redact"


class TestRunRetryExtractDeepScan:
    """Test that _run_retry_extract wires deep_scan into auto_extract_memories."""

    @pytest.mark.asyncio
    async def test_passes_deep_scan_when_enabled(self):
        """deep_scan=True must reach auto_extract_memories when user enables it."""
        from myrm_agent_harness.agent.security.types import PrivacyPolicy

        chat_id = "chat-deep-1"
        binding_context = MagicMock()
        binding_context.binding = MagicMock()
        binding_context.agent_id = "agent-1"
        binding_context.memory_decay_profile = "default"

        configs = MagicMock()
        configs.personal_settings_dict = {
            "privacyDeepScan": True,
            "privacyEnabled": True,
            "privacyS2Action": "pseudonymize",
            "privacyS3Action": "redact",
        }

        with (
            patch(
                "app.services.context.context_assembly.ContextAssemblyService.resolve_binding_for_chat",
                new_callable=AsyncMock,
                return_value=binding_context,
            ),
            patch(
                "app.services.memory.resolve_chat_extraction_llm.resolve_chat_extraction_llm",
                new_callable=AsyncMock,
                return_value=(MagicMock(), MagicMock()),
            ),
            patch(
                "app.services.agent.platform_config.require_platform_embedding_config",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch(
                "app.core.memory.adapters.setup.create_memory_manager",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=configs,
            ),
            patch(
                "app.ai_agents.extensions.extraction_lifecycle.make_extraction_lifecycle_observer",
                return_value=None,
            ),
            patch(
                "myrm_agent_harness.api.hooks.auto_extract_memories",
                new_callable=AsyncMock,
            ) as mock_auto_extract,
            patch(
                "myrm_agent_harness.api.hooks.get_pseudonym_store",
                return_value=None,
            ),
            patch(
                "myrm_agent_harness.api.hooks.get_privacy_policy",
                return_value=PrivacyPolicy(),
            ),
            patch(
                "myrm_agent_harness.api.hooks.build_pseudonym_store",
                return_value=MagicMock(),
            ),
            patch("myrm_agent_harness.api.hooks.set_privacy_policy"),
            patch("myrm_agent_harness.api.hooks.set_pseudonym_store"),
            patch("myrm_agent_harness.api.hooks.install_memory_pseudonymizer"),
            patch("myrm_agent_harness.api.hooks.restore_memory_pseudonymizer"),
        ):
            await _run_retry_extract(
                chat_id,
                "query",
                [["human", "hi"]],
                "reply",
                source="manual_retry_extract",
                workspace_path="/tmp/ws",
            )

        mock_auto_extract.assert_called_once()
        assert mock_auto_extract.call_args.kwargs["deep_scan"] is True
        assert mock_auto_extract.call_args.kwargs["source_chat_id"] == chat_id
        assert mock_auto_extract.call_args.kwargs["enable_verbatim"] is False

    @pytest.mark.asyncio
    async def test_passes_no_deep_scan_when_disabled(self):
        """deep_scan must be False when the user has not enabled it."""
        chat_id = "chat-plain-1"
        binding_context = MagicMock()
        binding_context.binding = MagicMock()
        binding_context.agent_id = "agent-1"
        binding_context.memory_decay_profile = "default"

        configs = MagicMock()
        configs.personal_settings_dict = {
            "privacyDeepScan": False,
            "privacyEnabled": False,
        }

        with (
            patch(
                "app.services.context.context_assembly.ContextAssemblyService.resolve_binding_for_chat",
                new_callable=AsyncMock,
                return_value=binding_context,
            ),
            patch(
                "app.services.memory.resolve_chat_extraction_llm.resolve_chat_extraction_llm",
                new_callable=AsyncMock,
                return_value=(MagicMock(), MagicMock()),
            ),
            patch(
                "app.services.agent.platform_config.require_platform_embedding_config",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch(
                "app.core.memory.adapters.setup.create_memory_manager",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
            patch(
                "app.core.channel_bridge.config_loader.load_user_configs",
                new_callable=AsyncMock,
                return_value=configs,
            ),
            patch(
                "app.ai_agents.extensions.extraction_lifecycle.make_extraction_lifecycle_observer",
                return_value=None,
            ),
            patch(
                "myrm_agent_harness.api.hooks.auto_extract_memories",
                new_callable=AsyncMock,
            ) as mock_auto_extract,
        ):
            await _run_retry_extract(
                chat_id,
                "query",
                [["human", "hi"]],
                "reply",
                source="manual_retry_extract",
                workspace_path="/tmp/ws",
            )

        mock_auto_extract.assert_called_once()
        assert mock_auto_extract.call_args.kwargs["deep_scan"] is False
