"""
[POS] app/api/projects/dependency_expansion.py
[INPUT] fastapi, app.schemas.dependency_expansion, app.services.project.architecture_dependency_service
[OUTPUT] router

FastAPI router exposing Architectural Dependency Graph Expansion and Adaptive Complexity Dual-Track endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.dependency_expansion import (
    ArchitectureNodeDTO,
    ClassifyComplexityRequestDTO,
    DependencyEdgeDTO,
    DependencyGraphExpansionResponseDTO,
    ExpandDependenciesRequestDTO,
    RegisterArchitectureNodeRequestDTO,
    RegisterDependencyEdgeRequestDTO,
    TaskComplexityClassificationResponseDTO,
)
from app.services.project.architecture_dependency_service import (
    ArchitectureDependencyService,
    get_architecture_dependency_service,
)

router = APIRouter(prefix="/projects", tags=["Architecture Dependency Expansion"])


@router.post(
    "/{project_id}/dependencies/nodes",
    response_model=ArchitectureNodeDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register architectural entity node in dependency graph",
)
def register_node(
    project_id: str,
    req: RegisterArchitectureNodeRequestDTO,
    service: ArchitectureDependencyService = Depends(
        get_architecture_dependency_service
    ),
) -> ArchitectureNodeDTO:
    """注册跨栈架构实体节点 (组件、三方库、API契约、数据模型、架构决策)。"""
    return service.register_node(project_id, req)


@router.post(
    "/{project_id}/dependencies/edges",
    response_model=DependencyEdgeDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register dependency edge in architectural graph",
)
def register_edge(
    project_id: str,
    req: RegisterDependencyEdgeRequestDTO,
    service: ArchitectureDependencyService = Depends(
        get_architecture_dependency_service
    ),
) -> DependencyEdgeDTO:
    """建立架构拓扑实体间的关联依赖边。"""
    return service.register_edge(project_id, req)


@router.post(
    "/{project_id}/dependencies/expand",
    response_model=DependencyGraphExpansionResponseDTO,
    summary="Cascade expand dependencies and compute blast radius",
)
def expand_dependencies(
    project_id: str,
    req: ExpandDependenciesRequestDTO,
    service: ArchitectureDependencyService = Depends(
        get_architecture_dependency_service
    ),
) -> DependencyGraphExpansionResponseDTO:
    """从目标节点出发，级联展开跨栈依赖拓扑，计算变更影响面与前置约束。"""
    return service.expand_dependencies(project_id, req)


@router.post(
    "/complexity/classify",
    response_model=TaskComplexityClassificationResponseDTO,
    summary="Classify task complexity for adaptive dual-track scheduling",
)
def classify_task_complexity(
    req: ClassifyComplexityRequestDTO,
    service: ArchitectureDependencyService = Depends(
        get_architecture_dependency_service
    ),
) -> TaskComplexityClassificationResponseDTO:
    """任务复杂度动态自适应感知调度，分流至 Fast-Lean 或 Full-Workbench 轨道。"""
    return service.classify_complexity(req)
