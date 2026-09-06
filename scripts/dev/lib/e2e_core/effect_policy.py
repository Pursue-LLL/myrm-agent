"""Shared HTTP effect policy for formal Chrome E2E.

The runtime guard and the PRIVATE redundancy scanner must classify the same
routes. Keeping the policy in one module prevents a newly added global write
from being protected by one entry point and missed by the other.
"""

from __future__ import annotations

from typing import Final

GLOBAL_MUTATION_PREFIXES: Final[tuple[str, ...]] = (
    "/api/v1/config/",
    "/api/v1/features/",
    "/api/v1/admin/",
    "/api/v1/security/",
    "/api/v1/org/",
    "/api/v1/voice/",
    "/api/v1/web_push/",
    "/api/v1/workspace/",
    "/api/v1/statistics/",
)

TEST_FIXTURE_PREFIXES: Final[tuple[str, ...]] = (
    "/api/v1/approvals/test/",
    "/api/v1/background-tasks/test/",
    "/api/v1/chats/test/",
    "/api/v1/integrations/provider-oauth/test/",
    "/api/v1/memory/test/",
    "/api/v1/projects/test/",
    "/api/v1/security/allowlist/test/",
    "/api/v1/skills/drafts/test/",
    "/api/v1/skills/evolution/test/",
    "/api/v1/skills/test/",
    "/api/v1/tasks/test/",
)

TEST_FIXTURE_EXACT_PATHS: Final[frozenset[str]] = frozenset(
    {"/api/v1/webui/desktop/approval/test-seed"}
)

NAMESPACE_WRITE_BOOTSTRAP_PATHS: Final[frozenset[str]] = frozenset(
    {
        "/api/v1/config/onboarding/complete",
        "/api/v1/agents/test-media-config",
    }
)

# These endpoints use POST for transport semantics but do not persist shared
# application state. They remain valid in SHARED+READ tests; all stateful POST,
# PUT, PATCH and DELETE routes still require an explicit write scope.
NON_PERSISTENT_OPERATION_PREFIXES: Final[tuple[str, ...]] = (
    "/api/v1/tts/synthesize",
    "/api/v1/tts/synthesize-stream",
)
