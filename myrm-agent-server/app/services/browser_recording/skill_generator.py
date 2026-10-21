"""Generate Browser Skills from recorded action steps.

Takes a completed CaptureSession and produces a SKILL.md file with structured
browser instructions. Detects credential fields and emits `fill_credential`
directives so the agent pulls the real secret from CredentialVault instead of
typing a masked placeholder.


[INPUT]
- types::CaptureSession (POS: completed recording session)
- serializer::steps_to_natural_language (POS: human-readable step descriptions)

[OUTPUT]
- generate_skill_from_session: (skill_id, content, credential_labels) tuple
- generate_skill_description: async LLM description generation from recorded steps (None on failure)
- default_skill_description: template fallback description shared by generator and API layer

[POS]
Skill generation service for browser recordings. Produces SKILL.md content
with allowed-tools (real harness tool names), semantic credential labels,
and step descriptions.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import TYPE_CHECKING
from urllib.parse import urlparse

from myrm_agent_harness.toolkits.browser.action_capture import (
    ActionType,
    steps_to_natural_language,
)

from app.core.utils.chat_utils import extract_answer_text

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from myrm_agent_harness.toolkits.browser.action_capture import CaptureSession

logger = logging.getLogger(__name__)

_DESCRIPTION_MAX_CHARS = 200

# Real harness-registered browser tool names (see toolkits/browser/tools/*.py).
_ALLOWED_BROWSER_TOOLS = (
    "browser_navigate_tool browser_interact_tool browser_snapshot_tool browser_extract_tool browser_manage_tool"
)


async def generate_skill_description(llm: BaseChatModel | None, session: CaptureSession) -> str | None:
    """Generate a semantic skill description from recorded steps via LLM.

    The skill description tells the agent when a skill applies, so a plain
    URL-based template description leaves recorded skills unreachable. Returns
    None when no model is configured or generation fails, so callers fall back
    to the template description.

    Args:
        llm: The chat model to use; None skips generation.
        session: The completed recording session.

    Returns:
        A concise one-sentence description, or None when generation fails.
    """
    if not session.steps or llm is None:
        return None
    credential_labels = _build_credential_labels(session)
    step_lines = steps_to_natural_language(session.steps, credential_labels=credential_labels)
    prompt = (
        "Write a concise one-sentence description of the browser automation "
        "skill these steps describe. Focus on what the skill does and when an "
        "agent should use it:\n\n"
        f"{step_lines}\n"
    )
    try:
        response = await llm.ainvoke(prompt)
        text = extract_answer_text(response).strip()
    except Exception as exc:
        logger.warning("LLM description generation failed: %s", exc)
        return None
    if not text:
        return None
    return text[:_DESCRIPTION_MAX_CHARS]


def _slugify(text: str, fallback: str) -> str:
    """Normalize free-form element text into a stable lowercase label slug."""
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return slug or fallback


def _site_prefix(session: CaptureSession) -> str:
    """Derive a stable per-site label prefix from the session start URL.

    CredentialVault labels are globally unique, so namespacing them by site
    host prevents two recorded skills for different sites from resolving the
    same vault entry (and silently reusing the wrong password).
    """
    host = urlparse(session.start_url or "").netloc
    return host or "site"


def _build_credential_labels(session: CaptureSession) -> dict[int, str]:
    """Map credential step seq -> semantic CredentialVault label.

    Only fill/type steps on sensitive fields are treated as credential steps —
    a click landing on a password input is a locator action, not a value input.
    Labels derive from the captured element text/role namespaced by the site
    host (e.g. `example.com-password`), and collisions are de-duplicated.
    """
    prefix = _site_prefix(session)
    labels: dict[int, str] = {}
    used: set[str] = set()
    for step in session.steps:
        if not step.is_password:
            continue
        if step.action not in (ActionType.FILL, ActionType.TYPE):
            continue
        base = _slugify(step.element_text or step.element_role, f"field-{step.seq}")
        label = f"{prefix}-{base}"
        n = 2
        while label in used:
            label = f"{prefix}-{base}-{n}"
            n += 1
        used.add(label)
        labels[step.seq] = label
    return labels


def _yaml_single_line(value: str) -> str:
    """Escape a free-form string as a single-line YAML double-quoted scalar.

    Recording descriptions may contain newlines or quotes that would otherwise
    break the frontmatter YAML block.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", " ").replace("\n", " ")
    return f'"{escaped}"'


def _build_skill_content(
    session: CaptureSession,
    skill_name: str,
    description: str,
    credential_labels: dict[int, str],
) -> str:
    """Build agentskills.io-compliant SKILL.md content from recorded steps.

    The YAML frontmatter (name/description/allowed-tools) is what the skill
    system validates on save — it must be present or `save_skill` rejects the
    file. Body sections are free-form instructions for the agent.
    """
    nl_steps = steps_to_natural_language(session.steps, credential_labels=credential_labels)

    credential_section = ""
    if credential_labels:
        cred_lines = [f'- Step {seq}: `fill_credential "{label}"`' for seq, label in credential_labels.items()]
        credential_section = f"""
## Credentials

Some steps above target password fields. The `fill_credential` action on those
steps provides the real value automatically:

{"\n".join(cred_lines)}
"""

    frontmatter = (
        f"---\nname: {skill_name}\ndescription: {_yaml_single_line(description)}\nallowed-tools: {_ALLOWED_BROWSER_TOOLS}\n---\n"
    )

    return f"""{frontmatter}
# {skill_name}

{description}

## Source

Start URL: {session.start_url}

## Steps

{nl_steps}
{credential_section}"""


def default_skill_description(session: CaptureSession) -> str:
    """Return the template fallback description for a recording session.

    Shared by the generator and the API layer so the SKILL.md frontmatter
    description, the saved skill metadata, and the API response always agree
    when neither a user description nor an LLM-generated one is available.
    """
    if session.steps:
        first_url = session.start_url or session.steps[0].url
        return f"Browser automation skill recorded from {first_url}"
    return "Browser automation skill"


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
        description = default_skill_description(session)

    credential_labels = _build_credential_labels(session)
    content = _build_skill_content(session, skill_name, description, credential_labels)

    skill_id = f"recorded-{skill_name}-{uuid.uuid4().hex[:8]}"

    logger.info(
        "Generated skill '%s' (id=%s) from session %s: %d steps, %d credential fields",
        skill_name,
        skill_id,
        session.session_id,
        len(session.steps),
        len(credential_labels),
    )

    return skill_id, content, list(credential_labels.values())
