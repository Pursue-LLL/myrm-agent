"""An always-allow pattern is stored, listed in the settings and logged, so it never carries a credential.

The pattern is the first two words of the command followed by ``*``. A credential typed into those two words
(``psql --password=Secret99``, ``mysql -pSecret99``) would be written into the allowlist verbatim, and the rule would
match only that one password. The pattern is checked without its trailing ``*``: a ``*`` that follows a credential-named
option (``kubectl --token *``) names no value, so it is no credential.
"""

from __future__ import annotations

import pytest

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent.middlewares.approval import add_to_allowlist_if_needed

_USER = "user-pattern-credentials"
_PERMISSION = "code_interpreter"
_TOOL = "bash_code_execute_tool"


@pytest.fixture(autouse=True)
def _fresh_allowlist() -> None:
    approval_flow._allowlist = approval_flow.Allowlist()


async def _allow_always_pattern(command: str) -> None:
    await add_to_allowlist_if_needed(
        allow_always={"tool": True, "pattern": True},
        user_id=_USER,
        permission_type=_PERMISSION,
        tool_name=_TOOL,
        tool_command=command,
    )


def _is_allowed(command: str) -> bool:
    return approval_flow.get_allowlist().check(_USER, _PERMISSION, _TOOL, None, command=command)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approved", "same_credential"),
    [
        ("psql --password=Secret99 db", "psql --password=Secret99 other_db"),
        ("mysql -pSecret99 -u root db", "mysql -pSecret99 -u admin"),
        ("curl -uadmin:Secret99 https://x.io", "curl -uadmin:Secret99 https://y.io"),
        ("tool --key=abc123xyz run", "tool --key=abc123xyz stop"),
        ("export TOKEN=abc123xyz", "export TOKEN=abc123xyz extra"),
    ],
)  # fmt: skip
async def test_a_pattern_that_embeds_a_credential_is_not_stored(approved: str, same_credential: str) -> None:
    await _allow_always_pattern(approved)
    assert not _is_allowed(same_credential)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("approved", "later"),
    [
        ("docker run -e API_KEY=abc123 image", "docker run alpine"),
        ("npm run build --token abc123xyz", "npm run test"),
        ("kubectl --token abc get pods", "kubectl --token other get nodes"),
        ("psql --password Secret99 db", "psql --password Other db"),
        ("git status", "git status -sb"),
    ],
)  # fmt: skip
async def test_a_pattern_without_a_credential_is_stored(approved: str, later: str) -> None:
    await _allow_always_pattern(approved)
    assert _is_allowed(later)
