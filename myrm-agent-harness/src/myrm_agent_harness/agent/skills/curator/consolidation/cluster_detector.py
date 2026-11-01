"""Skill cluster detection for consolidation.

Groups the skills that share a name prefix (``git-*``, ``deploy-*``) into candidate families for umbrella merging.
The grouping only proposes: the consolidation judge reads each family's descriptions and usage and decides whether
its members belong together.

[INPUT]
- backends.skills.types::SkillMetadata (POS: Skill system core data types.)
- .types::SkillCluster (POS: Data types for skill consolidation system.)

[OUTPUT]
- ClusterDetector: Detects candidate skill clusters for consolidation.

[POS]
Cluster detection layer for the skill consolidation system.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import TYPE_CHECKING

from .types import SkillCluster

if TYPE_CHECKING:
    from myrm_agent_harness.backends.skills.types import SkillMetadata

logger = logging.getLogger(__name__)

_MIN_CLUSTER_SIZE = 3
_PREFIX_MIN_LENGTH = 3


class ClusterDetector:
    """Detects candidate skill clusters for umbrella merging.

    Groups skills sharing a common name prefix (e.g. "git-*", "deploy-*"). Agents name the skills they create after
    the domain they work in, so a shared prefix is the cheap, deterministic signal that skills are one family.
    """

    def __init__(self, *, min_cluster_size: int = _MIN_CLUSTER_SIZE) -> None:
        self._min_cluster_size = min_cluster_size

    def detect(self, skills: list[SkillMetadata]) -> list[SkillCluster]:
        """Detect skill clusters from a list of active skills.

        Args:
            skills: Active, non-pinned skills to analyze.

        Returns:
            One SkillCluster per name prefix shared by at least ``min_cluster_size`` skills.
        """
        if len(skills) < self._min_cluster_size:
            return []

        prefix_groups: dict[str, list[SkillMetadata]] = defaultdict(list)
        for skill in skills:
            prefix = self._extract_prefix(skill.name.lower().removesuffix("_skill"))
            if len(prefix) >= _PREFIX_MIN_LENGTH:
                prefix_groups[prefix].append(skill)

        clusters = [
            SkillCluster(
                cluster_id=f"prefix-{prefix}",
                skill_names=tuple(skill.name for skill in group),
                shared_domain=prefix,
            )
            for prefix, group in prefix_groups.items()
            if len(group) >= self._min_cluster_size
        ]
        logger.info("ClusterDetector: %d prefix clusters", len(clusters))
        return clusters

    @staticmethod
    def _extract_prefix(name: str) -> str:
        """Extract a meaningful prefix from a skill name."""
        parts = re.split(r"[-_]", name)
        if len(parts) >= 2:
            return parts[0]
        return ""
