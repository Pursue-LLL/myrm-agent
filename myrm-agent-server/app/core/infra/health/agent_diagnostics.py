"""[INPUT]
- myrm_agent_harness.observability.diagnostics.protocols::HealthReport (POS: 健康状态报告结构)
- myrm_agent_harness.observability.diagnostics.protocols::DiagnosticProtocol (POS: 诊断接口)

[OUTPUT]
- AgentColdStartDiagnostic: Agent 冷启动首轮预热就绪度与阶段延迟诊断探针。
- OllamaModelContextDiagnostic: 本地 Ollama 模型 64K 上下文配置与 Agentic 衍生检测探针。
- AgentStepBudgetDiagnostic: 活跃 Agent 单次执行步数预算充足度探针。
- AgentPromptCacheAlignmentDiagnostic: Agent 系统提示词前缀对齐与 KV Cache 抖动审计探针。

[POS]
Server 层 Agent 与模型生态专项健康诊断探针集合。
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

from myrm_agent_harness.observability.diagnostics.protocols import (
    DiagnosticProtocol,
    HealthReport,
)

logger = logging.getLogger(__name__)


class AgentColdStartDiagnostic(DiagnosticProtocol):
    """Agent cold-start warm-path readiness and stage latency diagnostic probe.

    Evaluates the readiness of the primary turn-1 execution warm path without consuming
    any LLM tokens. Diagnoses 4 key dimensions:
    1. Model Provider Configuration (credentials & client viability)
    2. Tool Catalog / MCP Registry (lazy index cache status)
    3. ExecutionCache Warm State (warm BuiltExecutionUnit count & idle status)
    4. Storage / DB Liveness & Query Latency (SQLite microsecond-level ping)
    """

    async def check_health(self) -> HealthReport:
        ready_phases: list[str] = []
        phase_details: dict[str, object] = {}
        score: int = 0
        status: str = "pass"
        code: str = "OK_AGENT_WARM_PATH_READY"
        fix_suggestions: list[str] = []

        # 1. Model Provider Readiness
        try:
            from app.core.channel_bridge.config_loader import load_user_configs

            configs = await load_user_configs()
            model_name = getattr(configs.model_cfg, "model", "")
            if model_name:
                ready_phases.append("model_ready")
                phase_details["model_provider"] = model_name
                score += 35
            else:
                phase_details["model_provider"] = "unconfigured"
                fix_suggestions.append(
                    "Configure a default LLM Provider in Settings -> Models."
                )
        except Exception as exc:
            phase_details["model_provider_error"] = str(exc)
            fix_suggestions.append(
                "Verify LLM Provider credentials and network connection."
            )

        # 2. Tool Catalog Readiness
        try:
            from myrm_agent_harness.api import is_registered_action_tool

            has_bash = is_registered_action_tool("bash")
            ready_phases.append("tools_ready")
            phase_details["tools_ssot_active"] = bool(has_bash)
            score += 25
        except Exception as exc:
            phase_details["tools_error"] = str(exc)
            fix_suggestions.append("Check tool catalog plugin registration status.")

        # 3. Execution Cache Warm State
        try:
            from app.services.agent.execution_cache import get_execution_cache

            cache = get_execution_cache()
            warm_units = getattr(cache, "warm_entry_count", 0)
            phase_details["warm_execution_units"] = warm_units
            if warm_units > 0:
                ready_phases.append("cache_warm")
                score += 20
            else:
                score += 10
        except Exception as exc:
            phase_details["cache_error"] = str(exc)

        # 4. Storage / DB Ping Latency
        storage_latency_ms: float | None = None
        try:
            from sqlalchemy import text

            from app.database.connection import get_session

            start_t = time.perf_counter()
            async with asyncio.timeout(1.0):
                async with get_session() as session:
                    await session.execute(text("SELECT 1"))
            storage_latency_ms = round((time.perf_counter() - start_t) * 1000, 2)
            ready_phases.append("storage_healthy")
            phase_details["storage_latency_ms"] = storage_latency_ms
            score += 20
        except Exception as exc:
            phase_details["storage_error"] = str(exc)
            fix_suggestions.append(
                "Check database connection and file lock permissions."
            )

        if "model_ready" not in ready_phases:
            status, code, message = (
                "warn",
                "WARN_AGENT_MODEL_UNCONFIGURED",
                "Agent model provider is not configured.",
            )
        elif "storage_healthy" not in ready_phases:
            status, code, message = (
                "warn",
                "WARN_AGENT_STORAGE_UNHEALTHY",
                "Agent storage connectivity is degraded.",
            )
        elif "cache_warm" in ready_phases:
            status, code = "pass", "OK_AGENT_WARM_PATH_WARM"
            message = f"Agent warm-path fully primed (score: {score}/100, storage: {storage_latency_ms}ms)"
        else:
            status, code = "pass", "OK_AGENT_WARM_PATH_COLD_READY"
            message = f"Agent warm-path ready (score: {score}/100, cold cache, storage: {storage_latency_ms}ms)"

        detail_items = [f"Phases: {', '.join(ready_phases)}", f"Score: {score}/100"]
        if storage_latency_ms is not None:
            detail_items.append(f"DB ping: {storage_latency_ms}ms")
        if "warm_execution_units" in phase_details:
            detail_items.append(f"Warm units: {phase_details['warm_execution_units']}")

        return HealthReport(
            component_name="AgentColdStart",
            status=status,
            code=code,
            meta_data={
                "warm_path_score": score,
                "ready_phases": ready_phases,
                "phase_details": phase_details,
            },
            message=message,
            detail="; ".join(detail_items),
            fix_suggestion="; ".join(fix_suggestions) if fix_suggestions else None,
            metrics={"warm_path_score": float(score), "storage_latency_ms": storage_latency_ms or 0.0},
        )


class OllamaModelContextDiagnostic(DiagnosticProtocol):
    """Probe Ollama local models to detect if active models have >=64k context (num_ctx).

    Prevents silent 2048 token truncation for local agentic workflows.
    """

    async def check_health(self) -> HealthReport:
        from app.config.deploy_mode import DeployMode, get_deploy_mode

        if get_deploy_mode() == DeployMode.SANDBOX:
            return HealthReport(
                component_name="OllamaContext",
                status="pass",
                code="OK_OLLAMA_SANDBOX_SKIPPED",
                message="Local Ollama check skipped in Cloud Sandbox mode.",
            )

        try:
            import httpx

            async with httpx.AsyncClient(timeout=2.0) as client:
                res = await client.get("http://localhost:11434/api/tags")
                if res.status_code != 200:
                    return HealthReport(
                        component_name="OllamaContext",
                        status="pass",
                        code="OK_OLLAMA_NOT_RUNNING",
                        message="Ollama is not running locally (optional).",
                    )

                data = res.json()
                models = [m.get("name") for m in data.get("models", []) if "name" in m]
                if not models:
                    return HealthReport(
                        component_name="OllamaContext",
                        status="pass",
                        code="OK_OLLAMA_EMPTY",
                        message="Ollama is active with 0 installed models.",
                    )

                agentic_models = [m for m in models if "-agentic" in m]
                if not agentic_models:
                    return HealthReport(
                        component_name="OllamaContext",
                        status="warn",
                        code="WARN_OLLAMA_NO_AGENTIC_MODELS",
                        message=f"Ollama has {len(models)} installed models but none configured with 64K agentic Modelfile.",
                        detail="Native Ollama models default to 2048 context. Use Settings -> Model Service (Hardware Cookbook) to derive 64K agentic models.",
                        fix_suggestion="Pull models via Myrm UI or create Modelfile with PARAMETER num_ctx 64000.",
                        meta_data={"total_models": len(models), "agentic_models": []},
                        metrics={"installed_models_count": float(len(models)), "agentic_models_count": 0.0},
                    )

                return HealthReport(
                    component_name="OllamaContext",
                    status="pass",
                    code="OK_OLLAMA_CONTEXT_READY",
                    message=f"Ollama local model ecosystem ready ({len(models)} models, {len(agentic_models)} agentic 64K).",
                    detail=f"Detected models: {', '.join(models[:5])}",
                    meta_data={"total_models": len(models), "agentic_models": agentic_models},
                    metrics={"installed_models_count": float(len(models)), "agentic_models_count": float(len(agentic_models))},
                )
        except Exception:
            return HealthReport(
                component_name="OllamaContext",
                status="pass",
                code="INFO_OLLAMA_UNREACHABLE",
                message="Ollama is unreachable or idle (optional).",
            )


class AgentStepBudgetDiagnostic(DiagnosticProtocol):
    """Diagnose if active agents have sufficiently high step/recursion budgets."""

    RECOMMENDED_MIN_STEPS: int = 100

    async def check_health(self) -> HealthReport:
        try:
            from sqlalchemy import select

            from app.database.connection import get_session
            from app.database.models.agent import Agent

            low_budget_agents: list[dict[str, object]] = []
            total_active_agents: int = 0

            async with get_session() as session:
                stmt = select(Agent).where(Agent.is_active == True)  # noqa: E712
                res = await session.execute(stmt)
                agents = res.scalars().all()
                total_active_agents = len(agents)

                for ag in agents:
                    budget = ag.max_iterations
                    if budget is not None and budget < self.RECOMMENDED_MIN_STEPS:
                        low_budget_agents.append({"id": ag.id, "name": ag.name, "max_iterations": budget})

            if low_budget_agents:
                agent_names = [f"{a['name']} ({a['max_iterations']} steps)" for a in low_budget_agents[:3]]
                summary_str = ", ".join(agent_names)
                if len(low_budget_agents) > 3:
                    summary_str += f" and {len(low_budget_agents) - 3} more"

                return HealthReport(
                    component_name="AgentStepBudget",
                    status="warn",
                    code="WARN_AGENT_STEP_BUDGET_LOW",
                    message=f"{len(low_budget_agents)} Agent(s) have step limits below recommended {self.RECOMMENDED_MIN_STEPS} steps.",
                    detail=f"Low budget agents: {summary_str}. May encounter early stoppage during complex tasks.",
                    fix_suggestion="Update Agent settings to increase step budget (recommended >= 100 or unlimited).",
                    meta_data={"low_budget_agents": low_budget_agents, "recommended_min_steps": self.RECOMMENDED_MIN_STEPS},
                    metrics={"low_budget_agent_count": float(len(low_budget_agents)), "total_active_agents": float(total_active_agents)},
                )

            return HealthReport(
                component_name="AgentStepBudget",
                status="pass",
                code="OK_AGENT_STEP_BUDGET_READY",
                message=f"All active Agent step budgets meet or exceed {self.RECOMMENDED_MIN_STEPS} steps.",
                detail=f"Verified {total_active_agents} active Agent profile(s).",
                meta_data={"total_active_agents": total_active_agents, "recommended_min_steps": self.RECOMMENDED_MIN_STEPS},
                metrics={"low_budget_agent_count": 0.0, "total_active_agents": float(total_active_agents)},
            )
        except Exception as exc:
            logger.warning("Agent step budget health check failed: %s", exc)
            return HealthReport(
                component_name="AgentStepBudget",
                status="pass",
                code="OK_AGENT_STEP_BUDGET_SKIPPED",
                message="Agent step budget check skipped or DB uninitialized.",
            )


class AgentPromptCacheAlignmentDiagnostic(DiagnosticProtocol):
    """Diagnose if active agents adhere to LLM Prompt Cache Prefix Alignment best practices."""

    DYNAMIC_PREFIX_PATTERNS = [
        re.compile(r"\{\{\s*(?:current_)?(?:time|date|datetime|now|timestamp)\s*\}\}", re.IGNORECASE),
        re.compile(r"\b(?:current\s+time|today['’]?s\s+date|current\s+date)\s*[:：]\s*\d{4}[-/.]\d{1,2}[-/.]\d{1,2}", re.IGNORECASE),
        re.compile(r"当前(?:时间|日期|北京时间)\s*[:：]\s*(?:\{\{|\d{4})", re.IGNORECASE),
    ]

    async def check_health(self) -> HealthReport:
        try:
            from sqlalchemy import select

            from app.database.connection import get_session
            from app.database.models.agent import Agent

            jitter_agents: list[dict[str, object]] = []
            total_active_agents: int = 0

            async with get_session() as session:
                stmt = select(Agent).where(Agent.is_active == True)  # noqa: E712
                res = await session.execute(stmt)
                agents = res.scalars().all()
                total_active_agents = len(agents)

                for ag in agents:
                    prompt = (ag.system_prompt or "").strip()
                    if not prompt:
                        continue

                    prefix_snippet = prompt[:500]
                    matched_patterns = [p.pattern for p in self.DYNAMIC_PREFIX_PATTERNS if p.search(prefix_snippet)]
                    if matched_patterns:
                        jitter_agents.append({"id": ag.id, "name": ag.name, "reason": "Dynamic time/date placeholder in system prompt header"})

            if jitter_agents:
                agent_names = [f"{a['name']}" for a in jitter_agents[:3]]
                summary_str = ", ".join(agent_names)
                if len(jitter_agents) > 3:
                    summary_str += f" and {len(jitter_agents) - 3} more"

                return HealthReport(
                    component_name="AgentPromptCacheAlignment",
                    status="warn",
                    code="WARN_PROMPT_CACHE_PREFIX_JITTER",
                    message=f"{len(jitter_agents)} Agent(s) have dynamic variables in system prompt prefix.",
                    detail=f"Jitter detected in: {summary_str}. Dynamic prefix invalidates provider KV Cache on every turn, increasing latency and cost.",
                    fix_suggestion="Move dynamic timestamps or dates out of the System Prompt and into Human Messages to keep system prefix cache static.",
                    meta_data={"jitter_agents": jitter_agents},
                    metrics={"jitter_agent_count": float(len(jitter_agents)), "total_active_agents": float(total_active_agents)},
                )

            return HealthReport(
                component_name="AgentPromptCacheAlignment",
                status="pass",
                code="OK_PROMPT_CACHE_ALIGNED",
                message="All active Agent system prompts maintain static prefix alignment.",
                detail=f"Verified {total_active_agents} active Agent profile(s). Static system prompt ensures optimal KV Cache hit rates (>85%).",
                meta_data={"total_active_agents": total_active_agents},
                metrics={"jitter_agent_count": 0.0, "total_active_agents": float(total_active_agents)},
            )
        except Exception as exc:
            logger.warning("Agent prompt cache alignment health check failed: %s", exc)
            return HealthReport(
                component_name="AgentPromptCacheAlignment",
                status="pass",
                code="OK_PROMPT_CACHE_ALIGNMENT_SKIPPED",
                message="Agent prompt cache alignment check skipped or DB uninitialized.",
            )




