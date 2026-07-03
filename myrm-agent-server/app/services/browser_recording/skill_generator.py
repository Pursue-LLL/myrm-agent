"""Generate Browser Skills from recorded action steps.

Takes a completed CaptureSession and produces a SKILL.md file with structured
browser instructions. Detects credential fields and replaces values with
`{{credential:label}}` placeholders for secure replay via CredentialVault.


[INPUT]
- types::CaptureSession (POS: completed recording session)
- serializer::steps_to_natural_language (POS: human-readable step descriptions)

[OUTPUT]
- generate_skill_from_session: (skill_id, content, credential_labels) tuple

[POS]
Skill generation service for browser recordings. Produces SKILL.md content
with allowed-tools, credential placeholders, and step descriptions.
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.browser.action_capture import (
    steps_to_natural_language,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.browser.action_capture import CaptureSession

logger = logging.getLogger(__name__)


def _detect_credential_steps(session: CaptureSession) -> list[int]:
    """Return seq numbers of steps that involve password/sensitive fields."""
    return [step.seq for step in session.steps if step.is_password]


def _build_skill_content(
    session: CaptureSession,
    skill_name: str,
    description: str,
    credential_seqs: list[int],
) -> str:
    """Build SKILL.md content from recorded steps."""
    nl_steps = steps_to_natural_language(session.steps)

    credential_section = ""
    if credential_seqs:
        cred_lines = [
            f"- Step {seq}: Uses credential — value will be injected from CredentialVault at runtime"
            for seq in credential_seqs
        ]
        credential_section = f"""
## Credentials

This skill requires credentials stored in CredentialVault. Sensitive values
detected during recording are replaced with `{{{{credential:label}}}}` placeholders.

{chr(10).join(cred_lines)}
"""

    return f"""# {skill_name}

{description}

## Source

Generated from browser recording session `{session.session_id}`.
Start URL: {session.start_url}

## Steps

{nl_steps}
{credential_section}
## Configuration

- `allowed-tools`: browser_navigate, browser_click, browser_type, browser_snapshot, browser_select
- `primary-env`: browser
"""


def generate_skill_from_session(
    session: CaptureSession,
    skill_name: str,
    description: str = "",
) -> tuple[str, str, list[str]]:
    """Generate a Browser Skill from a recording session.

    Args:
        session: Completed capture session with recorded steps.
        skill_name: Name for the skill (validated upstream).
        description: Optional description (auto-generated if empty).

    Returns:
        Tuple of (skill_id, skill_content, credential_placeholders).
    """
    if not description:
        if session.steps:
            first_url = session.start_url or session.steps[0].url
            description = f"Browser automation skill recorded from {first_url}"
        else:
            description = "Browser automation skill"

    credential_seqs = _detect_credential_steps(session)
    credential_labels = [f"credential_step_{seq}" for seq in credential_seqs]

    content = _build_skill_content(session, skill_name, description, credential_seqs)

    skill_id = f"recorded-{skill_name}-{uuid.uuid4().hex[:8]}"

    logger.info(
        f"Generated skill '{skill_name}' (id={skill_id}) from session "
        f"{session.session_id}: {len(session.steps)} steps, "
        f"{len(credential_seqs)} credential fields"
    )

    return skill_id, content, credential_labels
