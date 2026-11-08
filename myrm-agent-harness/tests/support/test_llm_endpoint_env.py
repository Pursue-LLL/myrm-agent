"""The endpoint-variable plugin keeps a developer's shell out of the model transport tests.

[INPUT]
- tests.support.llm_endpoint_env (POS: the plugin under test)
- llms.transport.profile::PROFILES, llms.transport.service_routes::SERVICE_PROFILES (POS: the tables that name the
  variables)

[OUTPUT]
- TestEndpointVariables: which variables the plugin scrubs, that credentials stay, that the plugin is registered

[POS]
Pins the plugin to the provider table (a new endpoint variable is scrubbed without touching the plugin) and to
the run (every test run registers it).
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.transport.profile import PROFILES
from myrm_agent_harness.toolkits.llms.transport.service_routes import SERVICE_PROFILES
from tests.support.llm_endpoint_env import endpoint_variables, scrub_endpoint_variables


class TestEndpointVariables:
    def test_every_endpoint_and_version_variable_of_the_table_is_named(self) -> None:
        profiles = (*PROFILES.values(), *SERVICE_PROFILES.values())
        declared = {name for p in profiles for name in (*p.api_base_env, *p.api_version_env)}
        assert endpoint_variables() == declared
        assert {"OPENAI_BASE_URL", "ANTHROPIC_API_BASE", "AZURE_API_BASE", "AZURE_API_VERSION"} <= declared
        assert {"JINA_AI_API_BASE", "VOYAGE_API_BASE"} <= declared  # providers that serve no chat

    def test_credentials_are_not_endpoint_variables(self) -> None:
        credentials = {name for p in PROFILES.values() for name in p.api_key_env}
        assert credentials
        assert not credentials & endpoint_variables()

    def test_the_scrub_removes_only_endpoint_variables_and_names_them(self) -> None:
        environ = {
            "OPENAI_BASE_URL": "https://a",
            "AZURE_API_VERSION": "2031-01-01",
            "OPENAI_API_KEY": "k",
            "PATH": "/bin",
        }
        assert scrub_endpoint_variables(environ) == ["AZURE_API_VERSION", "OPENAI_BASE_URL"]
        assert environ == {"OPENAI_API_KEY": "k", "PATH": "/bin"}

    def test_a_clean_environment_has_nothing_to_remove(self) -> None:
        environ = {"PATH": "/bin"}
        assert scrub_endpoint_variables(environ) == []
        assert environ == {"PATH": "/bin"}

    def test_every_test_run_registers_the_plugin(self, pytestconfig: pytest.Config) -> None:
        assert pytestconfig.pluginmanager.has_plugin("tests.support.llm_endpoint_env")
