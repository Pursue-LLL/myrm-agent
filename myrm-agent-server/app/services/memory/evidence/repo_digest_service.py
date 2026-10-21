"""Repository History Evidence Digest Service.

Extracts structured commit history and recent change digests for workspace repositories,
providing zero-model-cost evidence anchoring for code and repository memories.

[INPUT]
- workspace_path: str | Path | None

[OUTPUT]
- MemoryRepoEvidenceResponse: Strong-typed repo evidence response

[POS]
Server memory service layer. Bridges Harness git_digest with Memory Command Center API.
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.api import (
    RepoHistoryEvidenceDigest,
    extract_repo_history_digest,
    get_workspace_root,
)

from app.schemas.memory.command_center import (
    MemoryRepoCommitDigestItem,
    MemoryRepoEvidenceResponse,
)

logger = logging.getLogger(__name__)


class RepoHistoryDigestService:
    """Service providing repository history digest extraction and memory integration."""

    def __init__(self, default_workspace: str | Path | None = None) -> None:
        self._default_workspace = Path(default_workspace).resolve() if default_workspace else None

    def get_effective_workspace_path(self, target_path: str | None = None) -> Path:
        """Resolve target workspace path using explicit input, default workspace, or harness root."""
        if target_path and target_path.strip():
            return Path(target_path).resolve()
        if self._default_workspace and self._default_workspace.is_dir():
            return self._default_workspace

        try:
            harness_root = get_workspace_root()
            if harness_root and Path(harness_root).is_dir():
                return Path(harness_root).resolve()
        except Exception:
            pass

        return Path.cwd().resolve()

    def get_repo_evidence_digest(
        self,
        workspace_path: str | None = None,
        max_commits: int = 5,
    ) -> MemoryRepoEvidenceResponse:
        """Extract recent repository commit digest without LLM cost."""
        path = self.get_effective_workspace_path(workspace_path)
        digest: RepoHistoryEvidenceDigest = extract_repo_history_digest(path, max_commits=max_commits)

        commits = [
            MemoryRepoCommitDigestItem(
                commit_hash=c.commit_hash,
                short_hash=c.short_hash,
                author=c.author,
                committed_at=c.committed_at,
                subject=c.subject,
                files_changed=list(c.files_changed),
            )
            for c in digest.recent_commits
        ]

        is_git_available = digest.current_branch not in ("none", "unknown")

        return MemoryRepoEvidenceResponse(
            repo_name=digest.repo_name,
            repo_path=digest.repo_path,
            current_branch=digest.current_branch,
            is_dirty=digest.is_dirty,
            recent_commits=commits,
            total_commits_examined=digest.total_commits_examined,
            extracted_at=digest.extracted_at,
            is_git_available=is_git_available,
        )
