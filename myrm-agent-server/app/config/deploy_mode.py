"""部署模式与运行方式

部署模式（DEPLOY_MODE）— 两种：
- LOCAL: 本地模式，本地存储，单用户，信任环境
- SANDBOX: 沙箱模式，控制平面管理的隔离实例，per-user 隔离

运行方式（DEPLOY_MODE=local 下的三种变体）：

    | 运行方式              | 启动入口                   | 触发条件                                     |
    |----------------------|---------------------------|----------------------------------------------|
    | Desktop Sidecar      | Tauri 桌面客户端           | WEBUI_MODE=false（默认），前端内嵌 WebView     |
    | WebUI Local          | run.py --webui             | WEBUI_MODE=true, WEBUI_REMOTE_MODE=false     |
    |                      | 或 Tauri 设置面板          |                                              |
    | WebUI Remote         | run.py --webui --remote    | WEBUI_MODE=true, WEBUI_REMOTE_MODE=true      |
    |                      | 或 Tauri 设置面板          |                                              |

    Desktop Sidecar: 绑定 127.0.0.1，Tauri WebView 直连
    WebUI Local:     绑定 127.0.0.1，Next.js 独立前端
    WebUI Remote:    绑定 0.0.0.0，使用 SANDBOX_API_KEY 进行单租户访问

两种部署模式的核心差异（14 维度）：

    | 维度             | 本地模式 (LOCAL)              | 沙箱模式 (SANDBOX)                  |
    |------------------|-------------------------------|--------------------------------------|
    | 访问控制         | 回环请求直接放行             | SANDBOX_API_KEY 单租户访问             |
    | 存储后端         | LocalStorageBackend           | LocalStorageBackend（指向持久化Volume）|
    | 文件服务         | LocalFileService              | LocalFileService（本地沙箱存储）        |
    | 产出物处理       | LocalArtifactProcessor        | LocalArtifactProcessor（本地记录）      |
    | 配置加密         | 明文存储                      | AES-256-GCM 加密                     |
    | 路由注册         | 全功能（通道管理/Events）     | 裁剪（由 CP 管理）                   |
    | 定时任务         | Shell Runner 启用             | Shell Runner 禁用                    |
    | 权限审批 (HITL)  | 人工审批                      | 自动放行（沙箱已隔离）               |
    | 安全策略引擎     | 启用                          | 不启用（cgroup 限制）                |
    | 浏览器池         | minimal 配置                  | defensive 配置                       |
    | MCP 验证         | 不验证                        | 响应大小验证                         |
    | 本地技能/文件    | 允许                          | 禁止（沙箱文件系统不可信）           |
    | 通道模式         | bidirectional                 | bidirectional                        |
    | 事件记录         | 启用                          | 不启用                               |
    | Prometheus metrics | 默认关闭（METRICS_ENABLED=true 可开） | 默认关闭（METRICS_ENABLED=true 可开） |

存储策略（统一）：
    所有模式统一使用 SQLite + 嵌入式 Qdrant。
    沙箱模式下数据存储在沙箱持久化卷上，控制平面通过 HTTP 反向代理路由。

云托管 vs 竞品平台（术语，非能力独占）：
    AgentScope Platform、QwenPaw「一键云端部署」等在后台同样会创建/调度托管实例。
    控制平面（CP）是基础设施层，**不面向最终用户**；用户只见 WebUI。
    Myrm 差异在于：local/Tauri/cloud 同一套 GUI 与 agent-server；CP 负责 per-user 容器+Volume、
    OAuth/计费/LLM Relay 等（见 myrm-control-plane/ARCHITECTURE.md），而非「独有 CP」本身。

使用方式：
    from app.config.deploy_mode import get_deploy_mode, DeployMode, is_local_mode, is_sandbox

    if is_sandbox():
        # 沙箱模式逻辑（受管环境，由 CP 创建）
        ...
    if is_local_mode():
        # 本地模式逻辑（信任环境）
        ...
    if is_webui_remote_mode():
        # WebUI 远程访问（由 middleware 使用 SANDBOX_API_KEY 认证）
        ...
"""

import os
from enum import Enum
from functools import lru_cache


class DeployMode(str, Enum):
    """部署模式"""

    LOCAL = "local"  # 本地模式（桌面客户端 / CLI WebUI）
    TAURI = "tauri"  # Tauri 桌面 Sidecar（单用户，浏览器池 minimal）
    SANDBOX = "sandbox"  # 控制平面管理的沙箱实例


class DatabaseMode(str, Enum):
    """数据库模式 - 所有部署模式统一使用 SQLite"""

    SQLITE = "sqlite"


class QdrantMode(str, Enum):
    """Qdrant 向量数据库模式 - 所有部署模式统一使用嵌入式"""

    EMBEDDED = "embedded"


class StorageMode(str, Enum):
    """文件存储模式"""

    LOCAL = "local"  # 所有模式均使用本地文件系统


class ModelSource(str, Enum):
    """模型来源 - 统一使用自定义提供商"""

    CUSTOM = "custom"  # 用户自定义 API (支持 OpenAI 兼容接口，包括本地 Ollama 等)


@lru_cache(maxsize=1)
def get_deploy_mode() -> DeployMode:
    """获取当前部署模式"""
    raw = os.getenv("DEPLOY_MODE", "local").lower()
    if raw == "webui":
        raw = "local"
    try:
        return DeployMode(raw)
    except ValueError:
        return DeployMode.LOCAL


def get_database_mode() -> DatabaseMode:
    """获取数据库模式 - 所有部署模式统一使用 SQLite"""
    return DatabaseMode.SQLITE


def get_qdrant_mode() -> QdrantMode:
    """获取 Qdrant 模式 - 所有部署模式统一使用嵌入式"""
    return QdrantMode.EMBEDDED


def get_storage_mode() -> StorageMode:
    """获取文件存储模式

    优先使用 STORAGE_MODE 环境变量，否则根据部署模式推断。
    """
    mode = os.getenv("STORAGE_MODE")
    if mode:
        try:
            return StorageMode(mode.lower())
        except ValueError:
            pass
    return StorageMode.LOCAL


def get_embedding_mode() -> ModelSource:
    """获取 Embedding 模型来源

    统一使用 CUSTOM 模式（自定义提供商）
    支持 OpenAI 兼容接口，包括本地 Ollama 等
    """
    # 总是返回 CUSTOM，环境变量仅用于配置具体的服务地址
    return ModelSource.CUSTOM


def get_reranker_mode() -> ModelSource:
    """获取 Reranker 模型来源

    统一使用 CUSTOM 模式（自定义提供商）
    支持 OpenAI 兼容接口，包括本地部署的重排模型服务
    """
    # 总是返回 CUSTOM，环境变量仅用于配置具体的服务地址
    return ModelSource.CUSTOM


def is_local_mode() -> bool:
    """是否为本地模式

    本地模式共享相同的基础设施：SQLite、嵌入式 Qdrant、本地存储、宽松安全策略。
    """
    return get_deploy_mode() in (DeployMode.LOCAL, DeployMode.TAURI)


def is_sandbox() -> bool:
    """是否为沙箱模式（运行在控制平面管理的隔离沙箱中）"""
    return get_deploy_mode() == DeployMode.SANDBOX


def is_webui_mode() -> bool:
    """是否为 WebUI 浏览器访问模式（通过 run.py --webui 启动）"""
    return os.getenv("WEBUI_MODE", "false").lower() == "true"


def is_webui_remote_mode() -> bool:
    """是否为 WebUI 远程访问模式

    触发方式：run.py --webui --remote 或 Tauri 设置面板开启远程访问。
    远程模式绑定 0.0.0.0，使用 SANDBOX_API_KEY 进行单租户访问。
    """
    return is_webui_mode() and os.getenv("WEBUI_REMOTE_MODE", "false").lower() == "true"


__all__ = [
    "DeployMode",
    "DatabaseMode",
    "QdrantMode",
    "StorageMode",
    "ModelSource",
    "get_deploy_mode",
    "get_database_mode",
    "get_qdrant_mode",
    "get_storage_mode",
    "get_embedding_mode",
    "get_reranker_mode",
    "is_local_mode",
    "is_sandbox",
    "is_webui_mode",
    "is_webui_remote_mode",
]
