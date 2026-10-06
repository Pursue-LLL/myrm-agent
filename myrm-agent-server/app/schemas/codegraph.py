"""Pydantic schemas for CodeGraph memory assets and impact analysis.

[INPUT]
- Raw request payloads for CodeGraph indexing and impact analysis.

[OUTPUT]
- Pydantic schemas validating API requests and serializing responses.

[POS]
- app.schemas.codegraph
"""

from pydantic import BaseModel, Field


class CodeSymbolSchema(BaseModel):
    """Schema representing an individual code symbol."""

    symbol_id: str = Field(description="Unique symbol identifier (e.g. file::name)")
    name: str = Field(description="Symbol name")
    kind: str = Field(description="Symbol kind (FUNCTION, CLASS, METHOD, VARIABLE)")
    file_path: str = Field(description="Relative or normalized file path")
    line_start: int = Field(description="Starting line number")
    line_end: int = Field(description="Ending line number")
    parameters: list[str] = Field(default_factory=list, description="Parameter list")
    return_type: str = Field(default="", description="Return type annotation")
    docstring: str = Field(default="", description="Extracted docstring")


class ScanWorkspaceRequest(BaseModel):
    """Request payload to scan and index a workspace folder."""

    workspace_dir: str = Field(description="Path to workspace root to scan")
    incremental: bool = Field(
        default=True, description="Whether to only parse modified files"
    )
    max_files: int = Field(
        default=500, description="Maximum number of files to process"
    )


class ScanWorkspaceResponse(BaseModel):
    """Response returned after workspace scan and CodeGraph update."""

    scanned_files_count: int = Field(description="Number of files parsed in this run")
    indexed_symbols_count: int = Field(description="New or updated symbols indexed")
    total_symbols: int = Field(description="Total symbols currently in the CodeGraph")
    repo_id: str = Field(description="Target repository or workspace identifier")
    version_hash: str = Field(description="Snapshot version hash")


class AnalyzeImpactRequest(BaseModel):
    """Request to assess the blast radius before modifying a symbol."""

    symbol_name: str = Field(description="Target symbol name to modify")
    file_path: str = Field(
        default="", description="Optional file path to disambiguate symbol"
    )
    max_depth: int = Field(
        default=5, description="Max caller recursion depth to explore"
    )


class AnalyzeImpactResponse(BaseModel):
    """Structured impact analysis assessment with risk level."""

    target_symbol_id: str = Field(description="Normalized target symbol ID")
    target_symbol_name: str = Field(description="Target symbol name")
    file_path: str = Field(default="", description="Target file path")
    blast_radius: int = Field(description="Total affected caller and file score")
    risk_level: str = Field(description="Assessed risk level: LOW/MEDIUM/HIGH/CRITICAL")
    direct_callers: list[str] = Field(
        default_factory=list, description="Immediate 1-hop callers"
    )
    indirect_callers: list[str] = Field(
        default_factory=list, description="Transitive upstream callers"
    )
    affected_files: list[str] = Field(
        default_factory=list, description="List of affected source files"
    )
    safety_recommendations: list[str] = Field(
        default_factory=list, description="Safety precautions before modifying"
    )


class SymbolQueryRequest(BaseModel):
    """Request parameters to filter or search symbols."""

    query: str = Field(default="", description="Optional substring query for name")
    kind: str = Field(default="", description="Optional filter by SymbolKind")
    limit: int = Field(default=50, description="Maximum symbols to return")


class SymbolListResponse(BaseModel):
    """Paginated or listed response containing discovered symbols."""

    total: int = Field(description="Total matching symbols")
    symbols: list[CodeSymbolSchema] = Field(
        default_factory=list, description="Matched symbols"
    )


class CodeGraphAssetResponse(BaseModel):
    """Summary metadata of the current CodeGraph memory asset."""

    repo_id: str = Field(description="Repository or workspace ID")
    version_hash: str = Field(description="Snapshot hash")
    total_symbols: int = Field(description="Total registered symbols")
    total_edges: int = Field(description="Total dependency edges")
    updated_at: float = Field(description="Epoch timestamp of last update")
