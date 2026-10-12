"""Unit tests for SemanticRbacService."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.semantic_rbac import (
    PrivateFactExposureError,
    SemanticRbacError,
)

from app.schemas.semantic_rbac import (
    ExecuteSemanticQueryRequest,
    PlanSemanticQueryRequest,
    RegisterViewRequest,
    SemanticColumnDefinitionDto,
    UserIdentityDto,
)
from app.services.security.semantic_rbac_service import SemanticRbacService


def test_default_enterprise_view_and_private_fact_blocking() -> None:
    service = SemanticRbacService()

    # 1. Fetch default seeded view
    view = service.get_view("enterprise_sales")
    assert view is not None
    assert any(c.name == "base_cost" and c.access_modifier == "PRIVATE_ACCESS" for c in view.columns)

    # 2. Plan query with direct projection of private_access column -> fails
    identity = UserIdentityDto(
        user_id="analyst-1",
        tenant_id="tenant-alpha",
        dept_id="sales",
        role="analyst",
        is_admin=False,
    )

    with pytest.raises(PrivateFactExposureError, match="marked as private_access"):
        service.plan_query(
            PlanSemanticQueryRequest(
                view_name="enterprise_sales",
                requested_columns=["order_id", "base_cost"],
                aggregated_metrics=[],
                identity=identity,
            )
        )


def test_role_restricted_column_enforcement() -> None:
    service = SemanticRbacService()

    rep_identity = UserIdentityDto(
        user_id="rep-1",
        tenant_id="tenant-alpha",
        dept_id="sales",
        role="sales_rep",
        is_admin=False,
    )
    cfo_identity = UserIdentityDto(
        user_id="cfo-1",
        tenant_id="tenant-alpha",
        dept_id="finance",
        role="cfo",
        is_admin=False,
    )

    # Blocked for sales_rep
    with pytest.raises(SemanticRbacError, match="not authorized to project column"):
        service.plan_query(
            PlanSemanticQueryRequest(
                view_name="enterprise_sales",
                requested_columns=["order_id", "executive_margin"],
                aggregated_metrics=[],
                identity=rep_identity,
            )
        )

    # Allowed for CFO
    cfo_plan = service.plan_query(
        PlanSemanticQueryRequest(
            view_name="enterprise_sales",
            requested_columns=["order_id", "executive_margin"],
            aggregated_metrics=[],
            identity=cfo_identity,
        )
    )
    assert "executive_margin" in cfo_plan.projected_columns


def test_execute_query_with_aggregation_and_row_filtering() -> None:
    service = SemanticRbacService()

    identity = UserIdentityDto(
        user_id="user-ops",
        tenant_id="tenant-alpha",
        dept_id="dept-west",
        role="analyst",
        is_admin=False,
    )

    raw_data = [
        {"order_id": "1", "tenant_id": "tenant-alpha", "dept_id": "dept-west", "base_cost": 50.0, "discount_pct": 0.1},
        {"order_id": "2", "tenant_id": "tenant-alpha", "dept_id": "dept-west", "base_cost": 70.0, "discount_pct": 0.3},
        {"order_id": "3", "tenant_id": "tenant-alpha", "dept_id": "dept-east", "base_cost": 200.0, "discount_pct": 0.2},
        {"order_id": "4", "tenant_id": "tenant-beta", "dept_id": "dept-west", "base_cost": 1000.0, "discount_pct": 0.5},
    ]

    exec_resp = service.execute_query(
        ExecuteSemanticQueryRequest(
            view_name="enterprise_sales",
            requested_columns=[],
            aggregated_metrics=["SUM(base_cost)", "AVG(discount_pct)"],
            identity=identity,
            raw_data=raw_data,
        )
    )

    assert exec_resp.total_rows == 1
    # Only items 1 and 2 matching tenant-alpha and dept-west: 50 + 70 = 120
    assert exec_resp.rows[0]["SUM(base_cost)"] == 120.0
    assert exec_resp.rows[0]["AVG(discount_pct)"] == 0.20


def test_register_custom_view() -> None:
    service = SemanticRbacService()

    req = RegisterViewRequest(
        view_name="hr_payroll",
        columns=[
            SemanticColumnDefinitionDto(name="emp_id", data_type="string", access_modifier="PUBLIC"),
            SemanticColumnDefinitionDto(name="tenant_id", data_type="string", access_modifier="PUBLIC"),
            SemanticColumnDefinitionDto(name="dept_id", data_type="string", access_modifier="PUBLIC"),
            SemanticColumnDefinitionDto(name="salary", data_type="float", access_modifier="PRIVATE_ACCESS"),
        ],
        tenant_column="tenant_id",
        dept_column="dept_id",
    )

    reg_resp = service.register_view(req)
    assert reg_resp.view_name == "hr_payroll"
    assert len(reg_resp.columns) == 4
