# [POS]: app/services/memory/git_okf_service.py
# [INPUT]: OKF bundle path, query parameters, validation requests
# [OUTPUT]: GitOKFService facade coordinating bundle loading, BM25 search, rot validation, and progressive disclosure

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.toolkits.memory import (
    OKFBundleLoader,
    OKFConcept,
    OKFDisclosureSummary,
    OKFSearchResult,
    OKFValidationReport,
)

logger = logging.getLogger(__name__)


class GitOKFService:
    """Server facade managing Git-native OKF v0.2 knowledge bundles,

    sub-millisecond BM25 lexical search, memory rot audits, and two-phase progressive disclosure.
    """

    def __init__(self, default_bundle_dir: str | None = None) -> None:
        self._bundle_dir: Path | None = Path(default_bundle_dir).resolve() if default_bundle_dir else None
        self._loader: OKFBundleLoader | None = None
        if self._bundle_dir and self._bundle_dir.exists():
            self._loader = OKFBundleLoader(self._bundle_dir)
            self._loader.load_bundle()

    def load_bundle(self, bundle_path: str) -> tuple[int, str]:
        """Load and index a knowledge bundle from the filesystem."""
        path = Path(bundle_path).resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"Knowledge bundle directory not found: {bundle_path}")

        loader = OKFBundleLoader(path)
        count = loader.load_bundle()
        self._bundle_dir = path
        self._loader = loader
        logger.info("Loaded OKF knowledge bundle at %s (%d concepts)", path, count)
        return count, str(path)

    def search_concepts(
        self,
        query: str,
        limit: int = 10,
        filter_governance: str | None = None,
        filter_status: str | None = None,
    ) -> list[OKFSearchResult]:
        """Execute sub-millisecond in-memory BM25 lexical search over loaded concepts."""
        if not self._loader:
            return []
        return self._loader.search(
            query=query,
            limit=limit,
            filter_governance=filter_governance,
            filter_status=filter_status,
        )

    def validate_bundle(self) -> OKFValidationReport:
        """Run OKF v0.2 conformance, memory rot, and anti-tamper audit."""
        if not self._loader:
            return OKFValidationReport(
                bundle_path=str(self._bundle_dir) if self._bundle_dir else "",
                declared_version="0.2",
                concept_count=0,
                is_conformant=True,
                gate_passed=True,
            )
        return self._loader.validate()

    def get_disclosure_summary(self) -> OKFDisclosureSummary:
        """Produce first-phase lightweight progressive disclosure card (<300 tokens footprint)."""
        if not self._loader:
            return OKFDisclosureSummary(
                bundle_path=str(self._bundle_dir) if self._bundle_dir else "",
                total_concepts=0,
                stale_count=0,
                concepts=[],
            )
        return self._loader.get_disclosure_summary()

    def get_concept_detail(self, concept_id: str) -> OKFConcept | None:
        """Fetch full concept markdown content and metadata for phase-two deep inspection."""
        if not self._loader:
            return None
        return self._loader.get_concept(concept_id)


_git_okf_service_instance: GitOKFService | None = None


def get_git_okf_service() -> GitOKFService:
    """Dependency provider returning singleton GitOKFService instance."""
    global _git_okf_service_instance
    if _git_okf_service_instance is None:
        _git_okf_service_instance = GitOKFService()
    return _git_okf_service_instance
