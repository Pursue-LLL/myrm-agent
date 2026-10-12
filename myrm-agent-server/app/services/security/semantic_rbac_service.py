"""Semantic Layer RBAC & Private Fact Masking Service.

[INPUT]
- RegisterViewRequest, PlanSemanticQueryRequest, ExecuteSemanticQueryRequest.

[OUTPUT]
- SemanticViewSchemaDto, SemanticQueryPlanDto, ExecuteSemanticQueryResponse.

[POS]
- Server security service. Wraps harness SemanticRbacEngine to enforce column
  access modifiers and identity-aware row-level predicates.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.semantic_rbac import (
    AccessModifier,
    SemanticColumnDefinition,
    SemanticQueryPlan,
    SemanticRbacEngine,
    SemanticViewSchema,
    UserIdentityContext,
)

from app.schemas.semantic_rbac import (
    ExecuteSemanticQueryRequest,
    ExecuteSemanticQueryResponse,
    PlanSemanticQueryRequest,
    RegisterViewRequest,
    SemanticColumnDefinitionDto,
    SemanticQueryPlanDto,
    SemanticViewSchemaDto,
    UserIdentityDto,
)

logger = logging.getLogger(__name__)


def _column_dto_to_domain(dto: SemanticColumnDefinitionDto) -> SemanticColumnDefinition:
    """Convert column DTO to harness domain model."""
    return SemanticColumnDefinition(
        name=dto.name,
        data_type=dto.data_type,
        access_modifier=AccessModifier(dto.access_modifier),
        allowed_roles=tuple(dto.allowed_roles),
        description=dto.description,
    )


def _column_domain_to_dto(col: SemanticColumnDefinition) -> SemanticColumnDefinitionDto:
    """Convert harness domain column to DTO."""
    return SemanticColumnDefinitionDto(
        name=col.name,
        data_type=col.data_type,
        access_modifier=col.access_modifier.value,
        allowed_roles=list(col.allowed_roles),
        description=col.description,
    )


def _view_domain_to_dto(view: SemanticViewSchema) -> SemanticViewSchemaDto:
    """Convert harness domain view schema to DTO."""
    return SemanticViewSchemaDto(
        view_name=view.view_name,
        columns=[_column_domain_to_dto(c) for c in view.columns],
        tenant_column=view.tenant_column,
        dept_column=view.dept_column,
    )


def _identity_dto_to_domain(dto: UserIdentityDto) -> UserIdentityContext:
    """Convert user identity DTO to harness context."""
    return UserIdentityContext(
        user_id=dto.user_id,
        tenant_id=dto.tenant_id,
        dept_id=dto.dept_id,
        role=dto.role,
        is_admin=dto.is_admin,
    )


def _plan_domain_to_dto(plan: SemanticQueryPlan) -> SemanticQueryPlanDto:
    """Convert harness query plan to DTO."""
    return SemanticQueryPlanDto(
        query_id=plan.query_id,
        target_view=plan.target_view,
        projected_columns=list(plan.projected_columns),
        aggregated_metrics=list(plan.aggregated_metrics),
        injected_predicates=list(plan.injected_predicates),
        raw_sql=plan.raw_sql,
    )


class SemanticRbacService:
    """Service administering semantic views and executing governed queries."""

    def __init__(self) -> None:
        self._engine = SemanticRbacEngine()
        # Seed default enterprise sales schema
        default_schema = SemanticViewSchema(
            view_name="enterprise_sales",
            columns=(
                SemanticColumnDefinition("order_id", "string", AccessModifier.PUBLIC),
                SemanticColumnDefinition("tenant_id", "string", AccessModifier.PUBLIC),
                SemanticColumnDefinition("dept_id", "string", AccessModifier.PUBLIC),
                SemanticColumnDefinition("customer", "string", AccessModifier.PUBLIC),
                SemanticColumnDefinition("gross_sales", "float", AccessModifier.PUBLIC),
                SemanticColumnDefinition("base_cost", "float", AccessModifier.PRIVATE_ACCESS),
                SemanticColumnDefinition("discount_pct", "float", AccessModifier.PRIVATE_ACCESS),
                SemanticColumnDefinition(
                    "executive_margin",
                    "float",
                    AccessModifier.RESTRICTED,
                    allowed_roles=("cfo", "executive"),
                ),
            ),
        )
        self._engine.register_view(default_schema)

    @property
    def engine(self) -> SemanticRbacEngine:
        """Underlying harness engine instance."""
        return self._engine

    def register_view(self, req: RegisterViewRequest) -> SemanticViewSchemaDto:
        """Register or replace a semantic view schema."""
        domain_columns = tuple(_column_dto_to_domain(c) for c in req.columns)
        schema = SemanticViewSchema(
            view_name=req.view_name,
            columns=domain_columns,
            tenant_column=req.tenant_column,
            dept_column=req.dept_column,
        )
        self._engine.register_view(schema)
        return _view_domain_to_dto(schema)

    def get_view(self, view_name: str) -> SemanticViewSchemaDto | None:
        """Fetch schema for a semantic view by name."""
        schema = self._engine.get_view(view_name)
        return _view_domain_to_dto(schema) if schema is not None else None

    def plan_query(self, req: PlanSemanticQueryRequest) -> SemanticQueryPlanDto:
        """Plan a governed query with row filtering and column security."""
        identity = _identity_dto_to_domain(req.identity)
        plan = self._engine.plan_query(
            view_name=req.view_name,
            requested_columns=req.requested_columns,
            aggregated_metrics=req.aggregated_metrics,
            identity=identity,
        )
        return _plan_domain_to_dto(plan)

    def execute_query(self, req: ExecuteSemanticQueryRequest) -> ExecuteSemanticQueryResponse:
        """Plan and execute a governed query against data."""
        identity = _identity_dto_to_domain(req.identity)
        plan = self._engine.plan_query(
            view_name=req.view_name,
            requested_columns=req.requested_columns,
            aggregated_metrics=req.aggregated_metrics,
            identity=identity,
        )
        results = self._engine.execute_query(
            plan=plan,
            raw_rows=req.raw_data,
            identity=identity,
        )
        return ExecuteSemanticQueryResponse(
            query_id=plan.query_id,
            rows=results,
            total_rows=len(results),
            injected_predicates=list(plan.injected_predicates),
        )


_service_instance: SemanticRbacService | None = None


def get_semantic_rbac_service() -> SemanticRbacService:
    """Obtain or initialize the singleton SemanticRbacService instance."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SemanticRbacService()
    return _service_instance
