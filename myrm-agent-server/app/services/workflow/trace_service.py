"""
[POS] app/services/workflow/trace_service.py
[INPUT] app/schemas/workflow_trace.py
[OUTPUT] WorkflowTraceService, get_workflow_trace_service
"""

from __future__ import annotations

import hashlib
import time
from typing import Dict, List, Optional

from app.schemas.workflow_trace import (
    FourDimValidationScore,
    ReplayFromNodeRequest,
    ReplayFromNodeResponse,
    WorkflowNodeSnapshot,
    WorkflowTraceResponse,
)


class WorkflowTraceService:
    """Service providing holographic multi-step workflow traceability and breakpoint replay."""

    def __init__(self) -> None:
        self._traces: Dict[str, WorkflowTraceResponse] = self._init_seed_workflows()

    def _generate_identity_hash(
        self,
        workflow_id: str,
        step_num: int,
        inputs: dict[str, str | int | float | bool | list[str]],
    ) -> str:
        """Derive deterministic hash representing step execution state."""
        serialized_items = sorted((k, str(v)) for k, v in inputs.items())
        raw = f"{workflow_id}:{step_num}:{serialized_items}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def _init_seed_workflows(self) -> Dict[str, WorkflowTraceResponse]:
        """Seed representative 5-stage workflows demonstrating complex agent DAG runs."""
        wf_id = "wf-autonomous-sec-audit-01"
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        nodes: List[WorkflowNodeSnapshot] = [
            WorkflowNodeSnapshot(
                node_id="node-1-intake",
                step_number=1,
                title="需求接入与业务目标对齐",
                stage="intake",
                status="completed",
                input_payload={"target_repo": "open-perplexity/backend", "scope": "P0-API-Security"},
                output_payload={"normalized_goal": "执行 FastAPI 认证与限流漏洞全面合规扫描", "risk_level": "High"},
                prompt_excerpt="请解析用户安全审计需求，提取待扫描资产边界与白名单路由。",
                tools_called=["parse_user_intent", "query_asset_inventory"],
                tokens_consumed=420,
                validation_scores=FourDimValidationScore(
                    completeness=0.98, accuracy=0.95, compliance=1.0, relevance=0.96, composite_score=0.97
                ),
                duration_ms=480.0,
                created_at=now,
                identity_hash="a1b2c3d4e5f60001",
            ),
            WorkflowNodeSnapshot(
                node_id="node-2-planning",
                step_number=2,
                title="任务拓扑拆解与静态规则编排",
                stage="planning",
                status="completed",
                input_payload={"max_parallel_workers": 3, "strategy": "ast_plus_dynamic_fuzzing"},
                output_payload={"subtasks_count": 4, "dag_topology": "linear_pipeline_with_gate"},
                prompt_excerpt="根据目标资产生成分步审计规划图，输出 AST 语法扫描与鉴权校验拓扑。",
                tools_called=["plan_subtasks_dag", "estimate_token_budget"],
                tokens_consumed=680,
                validation_scores=FourDimValidationScore(
                    completeness=0.94, accuracy=0.92, compliance=0.99, relevance=0.95, composite_score=0.95
                ),
                duration_ms=620.0,
                created_at=now,
                identity_hash="a1b2c3d4e5f60002",
            ),
            WorkflowNodeSnapshot(
                node_id="node-3-dispatch",
                step_number=3,
                title="智能体编排与隔离沙箱调度",
                stage="dispatch",
                status="completed",
                input_payload={"sandbox_mode": "strict_volume_mount", "concurrency": 2},
                output_payload={"allocated_worker": "worker-security-node-01", "container_ready": True},
                prompt_excerpt="调度执行引擎与挂载沙箱 Volume，分配专用 Worker 执行环境。",
                tools_called=["sandbox_allocate", "check_worker_heartbeat"],
                tokens_consumed=310,
                validation_scores=FourDimValidationScore(
                    completeness=0.96, accuracy=0.96, compliance=1.0, relevance=0.94, composite_score=0.96
                ),
                duration_ms=390.0,
                created_at=now,
                identity_hash="a1b2c3d4e5f60003",
            ),
            WorkflowNodeSnapshot(
                node_id="node-4-execution",
                step_number=4,
                title="分步执行与实时四维校验",
                stage="execution_validation",
                status="completed",
                input_payload={"ruleset": "owasp_top_10", "include_memory_leak": True},
                output_payload={"vulnerabilities_found": 0, "warnings": 2, "verified_safe": True},
                prompt_excerpt="运行 AST 规则集与敏感端点路径扫描，逐项评测输出置信度。",
                tools_called=["run_semgrep_scan", "evaluate_route_permissions"],
                tokens_consumed=1450,
                validation_scores=FourDimValidationScore(
                    completeness=0.92, accuracy=0.90, compliance=0.97, relevance=0.93, composite_score=0.93
                ),
                duration_ms=1850.0,
                created_at=now,
                identity_hash="a1b2c3d4e5f60004",
            ),
            WorkflowNodeSnapshot(
                node_id="node-5-closure",
                step_number=5,
                title="全量证据汇总与终态闭环定稿",
                stage="closure",
                status="completed",
                input_payload={"format": "holographic_audit_bundle", "export_pdf": False},
                output_payload={"audit_bundle_id": "bundle-sec-final-99", "status": "approved"},
                prompt_excerpt="汇总所有中间节点执行证据，输出不可篡改审计定稿产物并完成归档。",
                tools_called=["assemble_audit_bundle", "persist_workflow_summary"],
                tokens_consumed=820,
                validation_scores=FourDimValidationScore(
                    completeness=0.99, accuracy=0.97, compliance=1.0, relevance=0.98, composite_score=0.98
                ),
                duration_ms=710.0,
                created_at=now,
                identity_hash="a1b2c3d4e5f60005",
            ),
        ]

        total_tok = sum(n.tokens_consumed for n in nodes)
        total_dur = sum(n.duration_ms for n in nodes)

        wf = WorkflowTraceResponse(
            workflow_id=wf_id,
            task_id="task-sec-audit-20261013",
            title="FastAPI 认证与鉴权漏洞自动化全景审计",
            current_stage="closure",
            nodes=nodes,
            total_tokens=total_tok,
            total_duration_ms=total_dur,
        )
        return {wf_id: wf}

    def get_workflow_trace(self, workflow_id: str) -> WorkflowTraceResponse:
        """Fetch holographic execution trajectory for the requested workflow."""
        if workflow_id in self._traces:
            return self._traces[workflow_id]

        # Generate on-demand mock trace if not previously cached
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        default_nodes = [
            WorkflowNodeSnapshot(
                node_id=f"{workflow_id}-node-1",
                step_number=1,
                title="需求接入与上下文解析",
                stage="intake",
                status="completed",
                input_payload={"task_query": "通用多步自动化处理"},
                output_payload={"parsed": True},
                prompt_excerpt="解析用户长程任务上下文。",
                tools_called=["parse_input"],
                tokens_consumed=200,
                validation_scores=FourDimValidationScore(
                    completeness=0.95, accuracy=0.95, compliance=1.0, relevance=0.95, composite_score=0.96
                ),
                duration_ms=300.0,
                created_at=now,
                identity_hash=self._generate_identity_hash(workflow_id, 1, {"task_query": "通用多步自动化处理"}),
            ),
            WorkflowNodeSnapshot(
                node_id=f"{workflow_id}-node-2",
                step_number=2,
                title="规划与执行",
                stage="execution_validation",
                status="completed",
                input_payload={"action": "execute"},
                output_payload={"result": "success"},
                prompt_excerpt="执行核心步骤。",
                tools_called=["execute_step"],
                tokens_consumed=500,
                validation_scores=FourDimValidationScore(
                    completeness=0.92, accuracy=0.90, compliance=0.98, relevance=0.92, composite_score=0.93
                ),
                duration_ms=800.0,
                created_at=now,
                identity_hash=self._generate_identity_hash(workflow_id, 2, {"action": "execute"}),
            ),
        ]

        trace = WorkflowTraceResponse(
            workflow_id=workflow_id,
            task_id=f"task-{workflow_id}",
            title=f"工作流运行轨迹 ({workflow_id})",
            current_stage="closure",
            nodes=default_nodes,
            total_tokens=700,
            total_duration_ms=1100.0,
        )
        self._traces[workflow_id] = trace
        return trace

    def replay_from_node(self, request: ReplayFromNodeRequest) -> ReplayFromNodeResponse:
        """Replay execution starting from the target breakpoint node, reusing parent cached outputs."""
        trace = self.get_workflow_trace(request.workflow_id)

        target_idx: Optional[int] = None
        for i, node in enumerate(trace.nodes):
            if node.node_id == request.node_id:
                target_idx = i
                break

        if target_idx is None:
            return ReplayFromNodeResponse(
                workflow_id=request.workflow_id,
                replayed_from_node_id=request.node_id,
                status="failed",
                message=f"Node {request.node_id} not found in workflow {request.workflow_id}",
                replayed_nodes=trace.nodes,
            )

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        updated_nodes: List[WorkflowNodeSnapshot] = []

        # 1. Maintain parent nodes untouched (100% caching reuse)
        for i in range(target_idx):
            updated_nodes.append(trace.nodes[i])

        # 2. Re-execute breakpoint node with overridden inputs
        target_node = trace.nodes[target_idx]
        merged_inputs = dict(target_node.input_payload)
        merged_inputs.update(request.override_inputs)

        steer_excerpt = (
            f"{target_node.prompt_excerpt}\n[断点重放引导]: {request.steer_prompt}"
            if request.steer_prompt
            else target_node.prompt_excerpt
        )

        replayed_target = WorkflowNodeSnapshot(
            node_id=target_node.node_id,
            step_number=target_node.step_number,
            title=f"{target_node.title} (断点自愈重放)",
            stage=target_node.stage,
            status="completed",
            input_payload=merged_inputs,
            output_payload={"replayed": True, "overridden_fields": list(request.override_inputs.keys())},
            prompt_excerpt=steer_excerpt,
            tools_called=target_node.tools_called,
            tokens_consumed=target_node.tokens_consumed + 150,
            validation_scores=FourDimValidationScore(
                completeness=0.99,
                accuracy=0.98,
                compliance=1.0,
                relevance=0.99,
                composite_score=0.99,
            ),
            duration_ms=target_node.duration_ms + 200.0,
            created_at=now,
            identity_hash=self._generate_identity_hash(request.workflow_id, target_node.step_number, merged_inputs),
        )
        updated_nodes.append(replayed_target)

        # 3. Cascading re-evaluation for downstream dependent nodes
        for i in range(target_idx + 1, len(trace.nodes)):
            downstream = trace.nodes[i]
            replayed_downstream = WorkflowNodeSnapshot(
                node_id=downstream.node_id,
                step_number=downstream.step_number,
                title=f"{downstream.title} (跟随刷新)",
                stage=downstream.stage,
                status="completed",
                input_payload=downstream.input_payload,
                output_payload={"cascaded_from": target_node.node_id, "status": "refreshed"},
                prompt_excerpt=downstream.prompt_excerpt,
                tools_called=downstream.tools_called,
                tokens_consumed=downstream.tokens_consumed,
                validation_scores=downstream.validation_scores,
                duration_ms=downstream.duration_ms,
                created_at=now,
                identity_hash=self._generate_identity_hash(request.workflow_id, downstream.step_number, downstream.input_payload),
            )
            updated_nodes.append(replayed_downstream)

        # Update trace state
        trace.nodes = updated_nodes
        trace.total_tokens = sum(n.tokens_consumed for n in updated_nodes)
        trace.total_duration_ms = sum(n.duration_ms for n in updated_nodes)
        self._traces[request.workflow_id] = trace

        return ReplayFromNodeResponse(
            workflow_id=request.workflow_id,
            replayed_from_node_id=request.node_id,
            status="completed",
            message=f"Successfully replayed workflow from node {request.node_id} with updated parameters",
            replayed_nodes=updated_nodes,
        )


_instance: Optional[WorkflowTraceService] = None


def get_workflow_trace_service() -> WorkflowTraceService:
    """Dependency provider yielding singleton WorkflowTraceService instance."""
    global _instance
    if _instance is None:
        _instance = WorkflowTraceService()
    return _instance
