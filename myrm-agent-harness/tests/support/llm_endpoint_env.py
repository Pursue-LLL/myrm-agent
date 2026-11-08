"""Keep a developer's model-endpoint variables out of the tests (a pytest plugin).

[INPUT]
- llms.transport.profile::PROFILES, llms.transport.service_routes::SERVICE_PROFILES (POS: each provider's
  ``api_base_env`` and ``api_version_env`` names)

[OUTPUT]
- endpoint_variables: every endpoint or API-version variable a provider profile reads
- scrub_endpoint_variables: remove those variables from an environment mapping and name what was removed
- pytest_configure: scrub the process environment, in the pytest master and in every xdist worker

[POS]
Registered from ``tests/conftest.py`` (``pytest_plugins``). The transport reads a provider's endpoint variables
(``OPENAI_BASE_URL``, ``ANTHROPIC_API_BASE``, ``AZURE_API_VERSION``, ...) when a call names no endpoint of its own, so
a shell that exports one would send the request tests to that host and change the URL they assert. Credential
variables stay: the suite loads its own keys from ``.env.test`` and a test that needs one sets it itself.
"""

from __future__ import annotations

import os
from collections.abc import MutableMapping


def endpoint_variables() -> frozenset[str]:
    from myrm_agent_harness.toolkits.llms.transport.profile import PROFILES
    from myrm_agent_harness.toolkits.llms.transport.service_routes import SERVICE_PROFILES

    profiles = (*PROFILES.values(), *SERVICE_PROFILES.values())
    return frozenset(name for profile in profiles for name in (*profile.api_base_env, *profile.api_version_env))


def scrub_endpoint_variables(environ: MutableMapping[str, str]) -> list[str]:
    """Remove every provider endpoint variable from ``environ``; the names that were set, sorted."""
    removed = sorted(name for name in endpoint_variables() if name in environ)
    for name in removed:
        del environ[name]
    return removed


def pytest_configure() -> None:
    scrub_endpoint_variables(os.environ)
