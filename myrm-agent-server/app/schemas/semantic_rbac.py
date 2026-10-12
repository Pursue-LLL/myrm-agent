"""Pydantic schemas for Semantic Layer RBAC & Private Fact Masking.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for semantic views, column access modifiers,
  identity-aware row-level query plans, and governed query execution.

[POS]
- Server schemas. Exposes typed contracts for semantic queries and data security.
"""

from __future__ import annotations

from typing import Union

from pydantic import BaseModel, ConfigDict, Field

JsonScalar = Union[str, int, float, bool, None]


class SemanticColumnDefinitionDto(BaseModel):
    """Specification of a column in a governed semantic view."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Column name")
    data_type: str = Field(..., description="Data type string, e.g. string, float, integer")
    access_modifier: str = Field(
        default="PUBLIC", description="PUBLIC, PRIVATE_ACCESS, or RESTRICTED"
    )
    allowed_roles: list[str] = Field(
        default_factory=list, description="Roles permitted for RESTRICTED columns"
    )
    description: str = Field(default="", description="Column description")


class SemanticViewSchemaDto(BaseModel):
    """Governed schema of a semantic entity view."""

    model_config = ConfigDict(extra="forbid")

    view_name: str = Field(..., description="Unique view identifier")
    columns: list[SemanticColumnDefinitionDto] = Field(..., description="Column definitions")
    tenant_column: str = Field(default="tenant_id", description="Column for tenant isolation")
    dept_column: str = Field(default="dept_id", description="Column for department isolation")


class RegisterViewRequest(BaseModel):
    """Request to register a governed semantic view."""

    model_config = ConfigDict(extra="forbid")

    view_name: str = Field(..., description="Unique view name")
    columns: list[SemanticColumnDefinitionDto] = Field(..., description="Column definitions")
    tenant_column: str = Field(default="tenant_id", description="Tenant column name")
    dept_column: str = Field(default="dept_id", description="Department column name")


class UserIdentityDto(BaseModel):
    """Caller identity context for semantic RBAC."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., description="User identifier")
    tenant_id: str = Field(..., description="Tenant identifier")
    dept_id: str = Field(..., description="Department identifier")
    role: str = Field(..., description="User role name")
    is_admin: bool = Field(default=False, description="Whether user possesses admin privilege")


class PlanSemanticQueryRequest(BaseModel):
    """Request to generate a safe governed semantic query plan."""

    model_config = ConfigDict(extra="forbid")

    view_name: str = Field(..., description="Target semantic view name")
    requested_columns: list[str] = Field(default_factory=list, description="Requested projected columns")
    aggregated_metrics: list[str] = Field(default_factory=list, description="Requested aggregate formulas")
    identity: UserIdentityDto = Field(..., description="Caller identity credentials")


class SemanticQueryPlanDto(BaseModel):
    """Governed query plan representation."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(..., description="Unique query execution plan ID")
    target_view: str = Field(..., description="Target view name")
    projected_columns: list[str] = Field(..., description="Authorized projected columns")
    aggregated_metrics: list[str] = Field(..., description="Authorized aggregated metrics")
    injected_predicates: list[str] = Field(..., description="Injected row-level security predicates")
    raw_sql: str = Field(..., description="Governed SQL string")


class ExecuteSemanticQueryRequest(BaseModel):
    """Request to execute a semantic query against dataset with row/col RBAC."""

    model_config = ConfigDict(extra="forbid")

    view_name: str = Field(..., description="Target semantic view name")
    requested_columns: list[str] = Field(default_factory=list, description="Requested projected columns")
    aggregated_metrics: list[str] = Field(default_factory=list, description="Requested aggregate formulas")
    identity: UserIdentityDto = Field(..., description="Caller identity credentials")
    raw_data: list[dict[str, JsonScalar]] = Field(
        default_factory=list, description="Source raw rows to evaluate"
    )


class ExecuteSemanticQueryResponse(BaseModel):
    """Result of executing a governed semantic query."""

    model_config = ConfigDict(extra="forbid")

    query_id: str = Field(..., description="Query execution plan ID")
    rows: list[dict[str, JsonScalar]] = Field(..., description="Projected and filtered result rows")
    total_rows: int = Field(..., description="Number of returned rows")
    injected_predicates: list[str] = Field(..., description="Row-level predicates that were applied")
