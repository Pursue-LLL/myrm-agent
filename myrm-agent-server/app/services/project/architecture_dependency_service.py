"""
[POS] app/services/project/architecture_dependency_service.py
[INPUT] myrm_agent_harness.agent.context_management.dependency_expansion, app.schemas.dependency_expansion
[OUTPUT] ArchitectureDependencyService, get_architecture_dependency_service

Service layer bridging Server runtime to Harness ArchitecturalDependencyGraphExpander and AdaptiveComplexityGovernor.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading

from myrm_agent_harness.agent.context_management.dependency_expansion import (
    AdaptiveComplexityGovernor,
    ArchitecturalDependencyGraphExpander,
    ArchitectureNode,
    ArchitectureNodeType,
    DependencyEdge,
    DependencyEdgeType,
)

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


class ArchitectureDependencyService:
    """跨栈全链路架构依赖展开与任务复杂度自适应双轨调度服务。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # project_id -> ArchitecturalDependencyGraphExpander
        self._expanders: dict[str, ArchitecturalDependencyGraphExpander] = {}
        self._governor = AdaptiveComplexityGovernor(multi_component_threshold=2)

    def _get_or_create_expander(
        self, project_id: str
    ) -> ArchitecturalDependencyGraphExpander:
        with self._lock:
            if project_id not in self._expanders:
                self._expanders[project_id] = (
                    ArchitecturalDependencyGraphExpander()
                )
            return self._expanders[project_id]

    @staticmethod
    def _node_to_dto(node: ArchitectureNode) -> ArchitectureNodeDTO:
        return ArchitectureNodeDTO(
            node_id=node.node_id,
            node_type=node.node_type.value,
            name=node.name,
            file_path=node.file_path,
            description=node.description,
            metadata=dict(node.metadata),
        )

    def register_node(
        self, project_id: str, req: RegisterArchitectureNodeRequestDTO
    ) -> ArchitectureNodeDTO:
        """注册或更新项目下的架构实体节点。"""
        matched_type = ArchitectureNodeType.COMPONENT
        type_str = req.node_type.lower()
        for nt in ArchitectureNodeType:
            if nt.value == type_str:
                matched_type = nt
                break

        node = ArchitectureNode(
            node_id=req.node_id,
            node_type=matched_type,
            name=req.name,
            file_path=req.file_path,
            description=req.description,
            metadata=req.metadata,
        )
        expander = self._get_or_create_expander(project_id)
        expander.add_node(node)
        return self._node_to_dto(node)

    def register_edge(
        self, project_id: str, req: RegisterDependencyEdgeRequestDTO
    ) -> DependencyEdgeDTO:
        """注册跨栈依赖边。"""
        matched_edge = DependencyEdgeType.CALLS
        edge_str = req.edge_type.lower()
        for et in DependencyEdgeType:
            if et.value == edge_str:
                matched_edge = et
                break

        edge = DependencyEdge(
            source_id=req.source_id,
            target_id=req.target_id,
            edge_type=matched_edge,
            description=req.description,
        )
        expander = self._get_or_create_expander(project_id)
        expander.add_edge(edge)
        return DependencyEdgeDTO(
            source_id=edge.source_id,
            target_id=edge.target_id,
            edge_type=edge.edge_type.value,
            description=edge.description,
        )

    def expand_dependencies(
        self, project_id: str, req: ExpandDependenciesRequestDTO
    ) -> DependencyGraphExpansionResponseDTO:
        """级联展开目标节点的跨栈依赖拓扑并评估影响面。"""
        expander = self._get_or_create_expander(project_id)
        res = expander.expand_dependencies(
            node_id=req.target_node_id, max_depth=req.max_depth
        )
        dtos = [self._node_to_dto(n) for n in res.visited_nodes]

        return DependencyGraphExpansionResponseDTO(
            target_node_id=res.target_node_id,
            visited_nodes=dtos,
            blast_radius_score=res.blast_radius_score,
            critical_constraints=list(res.critical_constraints),
            rejected_alternatives=list(res.rejected_alternatives),
            formatted_expansion_block=res.formatted_expansion_block,
        )

    def classify_complexity(
        self, req: ClassifyComplexityRequestDTO
    ) -> TaskComplexityClassificationResponseDTO:
        """评估任务复杂度并动态判定调度轨道 (Fast-Lean vs Full-Workbench)。"""
        res = self._governor.classify_task_complexity(
            task_prompt=req.task_prompt,
            target_components_or_files=req.target_components_or_files,
            is_multi_turn_project_session=req.is_multi_turn_project_session,
        )
        return TaskComplexityClassificationResponseDTO(
            track=res.track.value,
            reason=res.reason,
            estimated_token_overhead=res.estimated_token_overhead,
            bypass_state_sync=res.bypass_state_sync,
        )


_service_singleton: ArchitectureDependencyService | None = None


def get_architecture_dependency_service() -> ArchitectureDependencyService:
    """获取 ArchitectureDependencyService 单例。"""
    global _service_singleton
    if _service_singleton is None:
        _service_singleton = ArchitectureDependencyService()
    return _service_singleton
