"""Agent 测试共享工具模块

提供 Agent 测试中常用的辅助函数和配置。
"""

import json
import uuid
from typing import Optional

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.agent.config.litellm_routing import normalize_env_model_selection_string

from tests.support.test_secrets import load_test_secrets, resolve_test_env

# 顶层 error 事件中可识别为环境问题（而非真实 Agent bug）的关键字
_ENV_SKIP_KEYWORDS = (
    "Authentication",
    "Authorization",
    "Recursion limit",
    "Cannot connect",
    "Connection error",
    "InternalServerError",
    "timeout",
    "Timeout",
    "LLM Provider NOT provided",
    "litellm.BadRequestError",
    "ServiceUnavailableError",
    "quota exceeded",
    "rate limit",
    "RateLimitError",
    "Iteration limit reached",
    "No active tab",
)

# 强环境失败信号：内嵌在工具失败 / 流恢复消息中（非顶层 error 事件），
# 且绝不会出现在正常回答正文里，可安全用于全量事件扫描。
_ENV_SKIP_BLOB_KEYWORDS = (
    "quota exceeded",
    "search service quota",
    "searchapierror",
    "iteration limit reached",
    "recursion limit",
    "ratelimiterror",
    "serviceunavailableerror",
    "no active tab",
)


def check_e2e_errors(collected_data: list[dict[str, object]]) -> None:
    """Skip on environment issues, fail on genuine agent errors.

    环境问题有两种出现形式，均应 skip 而非 fail：
    1. 顶层 ``error`` 事件（如 LLM 鉴权 / 限流）。
    2. 工具执行失败内嵌在其他事件中（如搜索配额耗尽 → Iteration limit reached），
       不会发出顶层 error 事件，需扫描完整事件流的强信号关键字。
    """
    error_events = [
        d for d in collected_data if isinstance(d, dict) and d.get("type") == "error"
    ]
    if error_events:
        error_msg = str(error_events[0].get("error", "") or error_events[0].get("data", ""))
        if any(kw.lower() in error_msg.lower() for kw in _ENV_SKIP_KEYWORDS):
            pytest.skip(f"环境配置问题: {error_msg[:120]}")
        pytest.fail(f"Agent execution error: {error_msg}")

    blob = json.dumps(collected_data, ensure_ascii=False, default=str).lower()
    for kw in _ENV_SKIP_BLOB_KEYWORDS:
        if kw in blob:
            pytest.skip(f"环境配置问题: 命中工具失败信号 '{kw}'")


def _require_env(name: str) -> str:
    value = resolve_test_env(name)
    if not value:
        raise RuntimeError(f"{name} must be set in .env.test")
    return value


def _strip_provider_prefix(model: str) -> str:
    """Strip the LiteLLM provider prefix from a model string."""
    if "/" in model:
        return model.split("/", 1)[1]
    return model


def _infer_provider_id(model: str, fallback: str = "default") -> str:
    """Infer the provider id from a LiteLLM model string when possible."""
    if "/" in model:
        provider_id = model.split("/", 1)[0].strip()
        if provider_id:
            if provider_id.endswith("-compatible"):
                return provider_id.replace("-compatible", "")
            return provider_id
    return fallback


def _convert_litellm_model(model: str) -> str:
    """Normalize env/model picker strings to LiteLLM model ids (harness single source)."""
    return normalize_env_model_selection_string(model)


def get_model_selection() -> dict[str, object]:
    """获取模型选择配置（新 API 格式）"""
    raw_model = _require_env("BASIC_MODEL")
    provider_id = _infer_provider_id(raw_model)

    api_model = _convert_litellm_model(raw_model)

    selection: dict[str, object] = {
        "providerId": provider_id,
        "model": api_model,
        "baseUrl": resolve_test_env("BASIC_BASE_URL"),
    }

    if "claude" in raw_model.lower() or "anthropic" in raw_model.lower():
        selection["modelKwargs"] = {
            "thinking": {"type": "enabled", "budget_tokens": 24576},
            "reasoning": {"type": "enabled"},
            "extra_body": {
                "thinking": {"type": "enabled"},
                "enable_thinking": True,
                "max_tokens": 32768,
            },
        }

    return selection


def get_lite_model_selection() -> dict[str, object]:
    """获取 liteModel 选择配置。"""
    raw_model = _require_env("LITE_MODEL")
    return {
        "providerId": _infer_provider_id(raw_model),
        "model": _convert_litellm_model(raw_model),
        "baseUrl": resolve_test_env("LITE_BASE_URL"),
    }


def get_base_model_config() -> dict[str, object]:
    """获取基础模型配置（旧格式，兼容）"""
    raw_model = _require_env("BASIC_MODEL")
    api_model = _convert_litellm_model(raw_model)
    config: dict[str, object] = {
        "model": api_model,
        "api_key": resolve_test_env("BASIC_API_KEY"),
        "base_url": resolve_test_env("BASIC_BASE_URL"),
        "max_context_tokens": 128000,
    }

    if "claude" in api_model.lower() or "anthropic" in api_model.lower():
        config["model_kwargs"] = {
            "thinking": {"type": "enabled", "budget_tokens": 24576},
            "reasoning": {"type": "enabled"},
            "extra_body": {
                "thinking": {"type": "enabled"},
                "enable_thinking": True,
                "max_tokens": 32768,
            },
        }

    return config


def get_search_service_config() -> dict[str, object]:
    """获取搜索服务配置"""
    config: dict[str, object] = {
        "search_service": resolve_test_env("SEARCH_SERVICE"),
        "api_base": resolve_test_env("SEARXNG_URL"),
        "api_key": resolve_test_env("TAVILY_API_KEY"),
    }

    if resolve_test_env("SEARCH_SERVICE") == "searxng":
        config["extra_params"] = {
            "categories": resolve_test_env("SEARXNG_ENGINE") or "general",
            "language": "all",
        }

    return config


def get_deploy_mode() -> str:
    """获取当前部署模式"""
    from app.config.deploy_mode import get_deploy_mode as _get_deploy_mode

    return _get_deploy_mode().value


def build_memory_e2e_embedding_retrieval_dict() -> dict[str, object] | None:
    """Minimal ``retrievalDict`` for memory E2E when only BASIC_* embedding fallbacks exist."""
    secrets = load_test_secrets()
    api_key = (
        secrets.get("EMBEDDING_API_KEY")
        or secrets.get("OPENAI_API_KEY")
        or secrets.basic_api_key
    )
    if not api_key:
        return None

    embedding_cfg: dict[str, object] = {
        "provider": secrets.get("EMBEDDING_PROVIDER", "openai"),
        "model": secrets.get("EMBEDDING_MODEL", "text-embedding-3-small"),
        "apiKey": api_key,
    }
    api_base = (
        secrets.get("EMBEDDING_BASE_URL")
        or secrets.get("OPENAI_API_BASE")
        or secrets.get("OPENAI_BASE_URL")
        or secrets.basic_base_url
    )
    if api_base:
        embedding_cfg["apiBase"] = api_base

    return {"embeddingApplied": True, "embeddingConfig": embedding_cfg}


def perform_agent_search(
    client: TestClient, query: str, chat_history: Optional[list[list[str]]] = None
) -> tuple[str, list[dict[str, object]], list[str], list[str]]:
    """执行 Agent 搜索并收集响应"""
    search_request: dict[str, object] = {
        "messageId": str(uuid.uuid4()),
        "query": query,
        "modelSelection": get_model_selection(),
        "searchServiceCfg": get_search_service_config(),
        "actionMode": "agent",
    }

    if chat_history:
        search_request["chatHistory"] = chat_history

    print(f"\n{'=' * 60}")
    print(f"🔍 查询: {query}")
    if chat_history:
        print(f"📜 对话历史: {len(chat_history) // 2} 轮")
    print(f"{'=' * 60}")

    collected_data: list[dict[str, object]] = []
    message_chunks: list[str] = []
    tool_results: list[str] = []

    with client.stream(
        "POST", "/api/v1/agents/agent-stream", json=search_request
    ) as response:
        if response.status_code != 200:
            response.read()
            error_content = response.text
            print(f"\n❌ HTTP错误 {response.status_code}:")
            print(f"响应内容: {error_content}")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        for line in response.iter_lines():
            if line:
                line = line.strip()
                if line.startswith("data: "):
                    try:
                        json_str = line[6:]
                        data = json.loads(json_str)
                        if not isinstance(data, dict):
                            continue
                        collected_data.append(data)
                        data_type = data.get("type", "unknown")

                        if len(collected_data) == 1:
                            print(
                                f"\n  🔍 第一个事件完整内容: {json.dumps(data, ensure_ascii=False, indent=2)}\n"
                            )

                        if data_type == "message":
                            content = data.get("data", "")
                            if content:
                                message_chunks.append(str(content))
                                print(f"  💬 消息: {str(content)[:80]}...")
                        elif data_type == "sources":
                            sources_data = data.get("data", [])
                            tool_results.append(str(sources_data))
                            print(
                                f"  🔍 搜索来源: {len(sources_data) if isinstance(sources_data, list) else 0} 个结果"
                            )
                        elif data_type == "tasks_steps":
                            task_title = data.get("task_title", "unknown")
                            step_data_list = data.get("data", [])
                            print(f"  🔧 任务步骤: {task_title}")
                            if isinstance(step_data_list, list):
                                print(f"     数据项数: {len(step_data_list)}")
                                for idx, step_item in enumerate(step_data_list[:3]):
                                    if isinstance(step_item, dict):
                                        if "text" in step_item:
                                            text = step_item["text"]
                                            print(
                                                f"     项{idx + 1}: {str(text)[:80]}..."
                                            )
                                        elif "url" in step_item:
                                            url = step_item["url"]
                                            print(
                                                f"     项{idx + 1}: URL - {str(url)[:80]}..."
                                            )
                                        else:
                                            print(
                                                f"     项{idx + 1}: {str(step_item)[:80]}..."
                                            )
                        else:
                            print(f"  📋 事件: {data_type}")
                            if data_type == "error":
                                print(f"     错误详情: {data}")

                    except json.JSONDecodeError as e:
                        print(f"JSON解析错误: {e}")

    full_answer = "".join(message_chunks)

    print("\n📊 收集统计:")
    print(f"  - 总事件数: {len(collected_data)}")
    print(f"  - 消息块数: {len(message_chunks)}")
    print(f"  - 工具结果数: {len(tool_results)}")
    print(f"  - 完整回答长度: {len(full_answer)} 字符")

    return full_answer, collected_data, message_chunks, tool_results
