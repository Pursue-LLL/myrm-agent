"""CodeGraph memory asset and impact analysis service.

[INPUT]
- Workspace path, symbol queries, and modification pre-check requests.

[OUTPUT]
- Service orchestrating AST scanning, CodeGraph indexing, and impact analysis.

[POS]
- app.services.memory.codegraph_service
"""

import logging
import os
from pathlib import Path

from myrm_agent_harness.toolkits.memory.codegraph import (
    AstTopologyExtractor,
    CodeGraphMemoryStore,
    CodeImpactAnalyzer,
)

from app.schemas.codegraph import (
    AnalyzeImpactResponse,
    CodeGraphAssetResponse,
    CodeSymbolSchema,
    ScanWorkspaceResponse,
    SymbolListResponse,
)

logger = logging.getLogger(__name__)

IGNORED_DIRS: set[str] = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    ".ruff_cache",
}


class CodeGraphService:
    """Service orchestrating workspace parsing, topology indexing, and blast radius evaluation."""

    def __init__(self, repo_id: str = "default_workspace") -> None:
        self.repo_id = repo_id
        self.store = CodeGraphMemoryStore(repo_id=repo_id)
        self.extractor = AstTopologyExtractor()
        self.analyzer = CodeImpactAnalyzer(store=self.store)

    def scan_workspace(
        self,
        workspace_dir: str,
        incremental: bool = True,
        max_files: int = 500,
    ) -> ScanWorkspaceResponse:
        """Scan workspace directory for Python files and sync CodeGraph store."""
        workspace_path = Path(workspace_dir)
        if not workspace_path.exists() or not workspace_path.is_dir():
            logger.warning("Workspace directory does not exist: %s", workspace_dir)
            snapshot = self.store.get_asset_snapshot()
            return ScanWorkspaceResponse(
                scanned_files_count=0,
                indexed_symbols_count=0,
                total_symbols=snapshot.total_symbols,
                repo_id=self.repo_id,
                version_hash=snapshot.version_hash,
            )

        files_data: list[tuple[str, str, float]] = []
        for root, dirs, files in os.walk(workspace_path):
            # Prune ignored directory trees in-place
            dirs[:] = [d for d in dirs if d not in IGNORED_DIRS and not d.startswith(".")]

            for file in files:
                if file.endswith(".py"):
                    full_file_path = Path(root) / file
                    try:
                        rel_path = str(full_file_path.relative_to(workspace_path))
                    except ValueError:
                        rel_path = str(full_file_path)

                    try:
                        stat = full_file_path.stat()
                        content = full_file_path.read_text(encoding="utf-8")
                        files_data.append((rel_path, content, stat.st_mtime))
                    except (OSError, UnicodeDecodeError):
                        continue

                    if len(files_data) >= max_files:
                        break
            if len(files_data) >= max_files:
                break

        if not incremental:
            # Wipe store clean for full re-scan
            self.store = CodeGraphMemoryStore(repo_id=self.repo_id)
            self.analyzer = CodeImpactAnalyzer(store=self.store)

        scanned_count, total_symbols = self.store.incremental_sync_files(
            files_data=files_data,
            extractor=self.extractor,
        )

        snapshot = self.store.get_asset_snapshot()
        logger.info(
            "Scanned %d files (%d updated), total symbols: %d",
            len(files_data),
            scanned_count,
            total_symbols,
        )

        return ScanWorkspaceResponse(
            scanned_files_count=scanned_count,
            indexed_symbols_count=total_symbols,
            total_symbols=snapshot.total_symbols,
            repo_id=self.repo_id,
            version_hash=snapshot.version_hash,
        )

    def analyze_impact(
        self,
        symbol_name: str,
        file_path: str = "",
        max_depth: int = 5,
    ) -> AnalyzeImpactResponse:
        """Assess caller ripple effect and blast radius before modifying a symbol."""
        report = self.analyzer.analyze_symbol_impact(
            symbol_name=symbol_name,
            file_path=file_path,
            max_depth=max_depth,
        )

        return AnalyzeImpactResponse(
            target_symbol_id=report.target_symbol_id,
            target_symbol_name=report.target_symbol_name,
            file_path=report.file_path,
            blast_radius=report.blast_radius,
            risk_level=report.risk_level.value,
            direct_callers=report.direct_callers,
            indirect_callers=report.indirect_callers,
            affected_files=report.affected_files,
            safety_recommendations=report.safety_recommendations,
        )

    def query_symbols(
        self,
        query: str = "",
        kind: str = "",
        limit: int = 50,
    ) -> SymbolListResponse:
        """Search registered symbols by substring name and kind."""
        all_symbols = self.store.list_all_symbols()
        filtered: list[CodeSymbolSchema] = []

        query_lower = query.lower()
        kind_upper = kind.upper()

        for sym in all_symbols:
            if query_lower and query_lower not in sym.name.lower():
                continue
            if kind_upper and sym.kind.value != kind_upper:
                continue

            filtered.append(
                CodeSymbolSchema(
                    symbol_id=sym.symbol_id,
                    name=sym.name,
                    kind=sym.kind.value,
                    file_path=sym.file_path,
                    line_start=sym.line_start,
                    line_end=sym.line_end,
                    parameters=sym.parameters,
                    return_type=sym.return_type,
                    docstring=sym.docstring,
                )
            )
            if len(filtered) >= limit:
                break

        return SymbolListResponse(total=len(filtered), symbols=filtered)

    def get_asset_metadata(self) -> CodeGraphAssetResponse:
        """Retrieve high-level metadata about the CodeGraph memory asset."""
        snapshot = self.store.get_asset_snapshot()
        return CodeGraphAssetResponse(
            repo_id=snapshot.repo_id,
            version_hash=snapshot.version_hash,
            total_symbols=snapshot.total_symbols,
            total_edges=snapshot.total_edges,
            updated_at=snapshot.updated_at,
        )


# Global default service singleton
codegraph_service = CodeGraphService()
