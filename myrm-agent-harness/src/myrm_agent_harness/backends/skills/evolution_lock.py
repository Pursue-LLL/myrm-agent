"""Rewrites the evolution lock flag in a SKILL.md frontmatter block.

[INPUT]
- re::re (POS: Regular expression library)

[OUTPUT]
- update_frontmatter_evolution_lock(): set ``evolution_locked`` in the SKILL.md frontmatter, appending it when absent

[POS]
Text-level edit of one frontmatter key: the rest of the file stays byte-identical, so comments and key order survive.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def update_frontmatter_evolution_lock(skill_path: str | Path, locked: bool) -> None:
    """Update the evolution_locked flag in the SKILL.md YAML frontmatter.

    If the field exists, it updates it. If it doesn't exist, it appends it to the end
    of the frontmatter block.

    Args:
        skill_path: Path to the SKILL.md file.
        locked: True to lock, False to unlock.
    """
    path = Path(skill_path)
    if not path.exists():
        return

    content = path.read_text(encoding="utf-8")
    # Match the frontmatter block safely.
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n", content, re.DOTALL)
    if not match:
        logger.warning(f"Failed to find valid YAML frontmatter in {path} to update evolution_locked.")
        return

    frontmatter = match.group(1)

    # Check if evolution_locked or evolution-locked already exists
    pattern = r"^(evolution[-_]locked\s*:\s*)(.*)$"
    if re.search(pattern, frontmatter, re.IGNORECASE | re.MULTILINE):
        # Replace the existing value
        new_frontmatter = re.sub(
            pattern,
            f"\\g<1>{str(locked).lower()}",
            frontmatter,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    else:
        # Append to the end of frontmatter
        # Ensure there's exactly one newline before appending
        stripped_fm = frontmatter.rstrip()
        new_frontmatter = stripped_fm + f"\nevolution_locked: {str(locked).lower()}\n"

    # Reconstruct the file content
    new_content = content[: match.start(1)] + new_frontmatter + content[match.end(1) :]
    path.write_text(new_content, encoding="utf-8")
    logger.debug(f"Updated evolution_locked to {locked} in {path}")
