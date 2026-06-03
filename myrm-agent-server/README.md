# MyrmAgent - AI Agent 后端服务

> **许可**: MIT。本仓为 Server 单机业务编排与 Web/Desktop 客户端的开源实现。

MyrmAgent 是一个 Claw-class AI Agent 后端服务，提供持久化 Agent 能力、技能系统、多 Agent 协作、记忆与知识库等核心功能。基于 Myrm Agent Harness 框架构建，使用 FastAPI 和 LangGraph 实现。

## 功能特点

- **多模型接入**：使用 LiteLLM 支持 OpenAI、Anthropic、Qwen、Gemini 等多种 LLM 模型
- **在线搜索能力**：集成 Tavily、SearXNG 等搜索服务
- **文档解析能力**：支持从 PDF、Word、Excel、PowerPoint 等文件中提取内容
- **向量知识库**：支持文档嵌入和语义搜索（Qdrant）
- **AI 深度搜索**：使用 LangGraph 编排 AI 搜索工作流，实现复杂问题的解答能力
- **网页内容提取**：使用 magic-html 高效提取网页主体内容
- **记忆系统**：支持语义记忆、情景记忆、程序性记忆和用户画像
- **技能系统**：支持 MCP（Model Context Protocol）技能扩展
- **权限控制**：灵活的用户权限系统，支持 Local 和 Sandbox 模式
- **配置同步**：多设备配置同步，支持本地与云端配置合并
- **高性能运行**：uvicorn + uvloop 事件循环（IO 性能 ~2-3x）
- **安全仪表盘**：实时安全告警聚合（code scanning + Dependabot PRs）

## 技术栈

- **Python 3.13+**
- **Web 框架**：FastAPI + uvicorn (uvloop)
- **LLM 接入**：LiteLLM
- **AI 编排**：LangChain + LangGraph
- **向量数据库**：Qdrant（嵌入式/Server 模式）
- **关系数据库**：SQLite（默认嵌入式）/ PostgreSQL（可选，AGE 图查询后端）
- **图数据库**：PostgreSQL + Apache AGE / SQLite 递归 CTE（用于记忆因果链）
- **对象存储**：MinIO（Docker 模式）
- **网页提取**：magic-html
- **包管理**：UV（高性能 Python 包管理器）

## 快速开始

### 方式一：一键部署（推荐）

使用部署脚本自动完成环境配置和应用启动：

```bash
# Tauri 桌面客户端模式（本地嵌入式数据库，单用户）
uv run deploy.py tauri dev

# Sandbox 云端多租户模式（Docker 容器化服务）
uv run deploy.py sandbox

# Docker 全栈部署（后端 + 前端 + 数据库，一键启动）
uv run deploy.py docker
```

部署脚本会自动：

- 检查环境（Python、Docker 等）
- 安装依赖
- 配置环境变量
- 启动 Docker 服务（Sandbox 模式）
- 初始化数据库
- **自动启动应用**

### 方式二：手动部署

1. **克隆项目**

```bash
git clone <repository-url>
cd myrm-agent-server
```

2. **配置环境变量**

```bash
cp .env.example .env
# 按需修改 .env（本地模式仅需 4 行，大部分变量有默认值）
# LLM 配置通过前端页面设置，无需在 .env 中配置
```

3. **安装依赖（Harness 来自 PyPI）**

本仓库为开源产品仓，**Harness 仅通过 PyPI 安装**（见 `pyproject.toml` / `uv.lock`）。

```bash
# 在 myrm-agent 根目录（推荐）
myrm setup

# 或仅 server 目录
cd myrm-agent-server && uv sync --all-extras
```

4. **安装浏览器运行时（可选）**

```bash
cd myrm-agent-server
python -m patchright install chromium
```

5. **启动服务**

```bash
myrm dev      # 仅后端 :8080
myrm start    # 后端 + 前端 → http://localhost:3000

# 或在 myrm-agent-server 目录：
.venv/bin/python run.py
```

## API 文档

启动服务后，访问 <http://localhost:8080/docs> 查看完整的 API 文档。

### API 认证 / API Authentication

本地模式 / Local mode:
- 直接访问本机地址即可，无需额外认证。
- Requests to the local host are allowed without extra auth.

Sandbox 模式 / Sandbox mode:
- 在请求头中携带 `X-Sandbox-Api-Key: <SANDBOX_API_KEY>`。
- You can also send `Authorization: Bearer <SANDBOX_API_KEY>`.

### API 权限说明

| API 路径 | 认证要求 | 说明 |
|----------|----------|------|
| `/api/v1/agents/*` | 必需 | AI Agent 接口 |
| `/api/v1/chats/*` | 必需 | 聊天接口 |
| `/api/v1/config/*` | 必需 | 配置同步接口 |
| `/api/v1/memory/*` | 必需 | 记忆系统接口 |
| `/api/v1/knowledge/*` | 必需 | 知识库接口 |
| `/api/v1/skills/*` | 必需 | 技能管理接口 |
| `/health` | 公开 | 健康检查 |

**注意**：本项目不支持访客模式。本地模式自动使用 `local_user`，Sandbox 模式由控制平台处理认证。

## 部署模式

### 本地模式（Desktop/WebUI）

- 自动使用 `local_user` 用户
- 数据存储在本地 SQLite
- 配置明文存储（本地安全）
- 无需网络连接

### Sandbox 模式

- 认证由控制平台处理（Server 层信任代理请求）
- 每个用户独立沙箱运行
- 数据存储在持久化卷（SQLite + Qdrant 嵌入式）
- 敏感配置使用 E2EE 加密

### 测试登录功能

开发环境支持测试登录功能，方便开发和测试：

```bash
# 前端设置页面点击"本次测试"按钮
# 或在浏览器控制台执行：
localStorage.setItem('auth_token', 'test-user-token-' + Date.now());
window.location.reload();
```

测试登录会创建 `test-user-id` 测试用户，并支持完整的配置同步功能。

## 配置同步机制

### 多设备配置同步

- **新用户**：首次登录时，本地配置会同步到云端
- **现有用户**：登录时，云端配置会覆盖本地配置
- **实时同步**：配置变更后自动同步到云端

### 支持的配置类型

- 模型服务配置（API密钥等）
- 默认模型设置
- 聊天设置
- 个性化偏好
- 技能启用状态

## 项目结构

```text
myrm-agent-server/
├── assets/                   # 产品资产（prebuilt_skills 官方技能种子）
├── app/                      # 应用主目录
│   ├── schemas/              # 共享 Pydantic DTO（api + services 共用）
│   ├── api/                  # HTTP 接口层（FastAPI 路由与请求处理）
│   ├── services/             # 业务服务层（按域组织：agent/chat/wiki/...）
│   ├── ai_agents/            # AI Agent 定义层（配置、Prompt、工作流）
│   ├── core/                 # 核心基础设施（安全/Cron/检索/监控/工具）
│   ├── adapters/             # 适配器层（Harness Protocol 的业务实现）
│   ├── database/             # 数据层（ORM/DTO + Repository 仓储隔离）
│   ├── middleware/            # 中间件层（认证/安全/限流/文本清洗）
│   ├── platform_utils/       # 平台抽象层（本地/沙箱模式差异化）
│   ├── lifecycle/            # 应用生命周期管理
│   ├── server/               # 服务器配置（lifespan/异常/中间件注册）
│   ├── tasks/                # 后台任务执行器
│   ├── config/               # 配置层（环境变量、部署模式）
│   └── main.py               # FastAPI 应用入口
├── scripts/                  # 运维脚本（部署、CLI、门禁检查）
├── tests/                    # 测试套件（镜像 app/ 结构）
├── docker/                   # Sandbox 镜像构建
├── deployments/              # Prometheus 等运维配置
├── searxng/                  # SearXNG 搜索引擎配置
# i18n: frontend `myrm-agent-frontend/locales/` + harness channel i18n (not in server)
├── deploy.py                 # 部署入口（委托 scripts/deploy.py）
├── LICENSE                   # MIT
├── .env.example              # 环境变量模板
├── run.py                    # 应用启动脚本
├── docker-compose.yaml       # Docker Compose 配置
├── Dockerfile                # 多阶段构建
├── pyproject.toml            # 项目配置和依赖
└── ARCHITECTURE.md           # 架构文档
```

## 配置选项

进程级与运维级配置在 `.env` 中设置（完整列表见 `.env.example`）：

| 环境变量 | 说明 | 默认值 |
|---------|------|-------|
| `DEPLOY_MODE` | 部署模式（local/tauri/sandbox） | local |
| `HOST` | 主机地址 | 0.0.0.0 |
| `PORT` | 端口号 | 8080 |
| `MYRM_DATA_DIR` | 数据根目录（SQLite/Qdrant 等派生路径） | `~/.myrm` |

LLM、Embedding、Search 等业务配置通过前端 Settings 页面管理（存储在数据库），**不要**在 `.env` 中配置 API Key。
本地/tauri 首次启动若未配置模型，preflight 会输出 warning（不阻塞启动）。


## 贡献指南

1. Fork 本仓库
2. 创建功能分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'Add some amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 许可证

本项目采用 MIT 许可证 - 详情请查看 [LICENSE](LICENSE) 文件

## MCP服务器配置

### 基本配置

```json
{
  "name": "example-server",
  "type": "sse",
  "url": "https://example.com/sse",
  "description": "示例MCP服务器"
}
```

### 带额外参数的配置

支持通过 `extraParams` 字段传递任意额外参数给MCP客户端：

```json
{
  "name": "advanced-server",
  "type": "sse", 
  "url": "https://api.example.com/mcp",
  "description": "高级MCP服务器配置",
  "extraParams": {
    "timeout": 30,
    "retries": 3,
    "headers": {
      "Authorization": "Bearer your-token",
      "User-Agent": "MyApp/1.0"
    },
    "maxConnections": 10
  }
}
```

这些额外参数会直接传递给底层的MCP客户端，支持各种自定义配置需求。

## 部署模式

### 部署模式对比

| 特性 | 本地桌面模式 | Sandbox 云端模式 |
|------|---------------|--------------|
| **适用场景** | 本地桌面应用，单用户 | 云端多租户，订阅制 |
| **数据库** | SQLite（嵌入式） | PostgreSQL（Docker 容器） |
| **向量库** | Qdrant 嵌入式 | Qdrant Server（Docker 容器） |
| **图查询** | SQLite 递归 CTE | PostgreSQL + Apache AGE |
| **存储** | 本地文件系统 | MinIO / S3（云对象存储） |
| **沙箱** | 本地执行 | Docker 隔离执行 |
| **搜索服务** | Tavily（云 API） | 外部 API（Tavily/Serper） |
| **启动方式** | uvicorn（单进程） | uvicorn（单进程，沙箱内） |
| **依赖** | Python | Python, Docker |

### 本地桌面模式

#### 前置条件

- Python 3.11+

#### 部署步骤

```bash
# 通过 deploy.py 部署并启动
uv run deploy.py tauri dev

# 或直接启动
DEPLOY_MODE=local uv run run.py
```

**特点**：

- 无需 Docker，所有数据库嵌入式运行
- 数据存储在 `~/.myrm-agent/`
- 单进程运行，避免嵌入式数据库文件锁冲突

#### 服务端口

| 服务 | 端口 |
|------|------|
| MyrmAgent API | 8080 |

### Sandbox 云端模式

#### 前置条件

- Python 3.11+
- Docker Desktop 或 Docker Engine

#### 部署步骤

```bash
# 通过 deploy.py 一键部署（自动启动 Docker 服务 + 应用）
uv run deploy.py sandbox

# 或手动管理 Docker 服务
docker compose --profile storage up -d
DEPLOY_MODE=sandbox uv run run.py
```

**特点**：

- 所有基础设施容器化（PostgreSQL + AGE、Qdrant、MinIO）
- 不包含 SearXNG（使用外部搜索 API）
- 高性能部署（uvicorn + uvloop）

#### 手动管理 Docker 服务

```bash
# 启动核心服务 + MinIO
docker compose --profile storage up -d

# 查看服务状态
docker compose ps

# 查看日志
docker compose logs -f

# 停止服务
docker compose down

# 停止并删除数据
docker compose down -v
```

#### 服务端口

| 服务 | 端口 | 说明 |
|------|------|------|
| MyrmAgent API | 8080 | 主服务 |
| PostgreSQL | 5432 | 关系数据 + 图查询 |
| Qdrant REST | 6333 | 向量存储 |
| Qdrant gRPC | 6334 | 向量存储 |
| MinIO API | 9000 | 对象存储 |
| MinIO Console | 9001 | 对象存储 |

## 详细配置

### 环境变量配置

部署脚本会自动生成 `.env` 文件。进程级与运维级配置见 `.env.example`：

#### 必须配置

```env
# 部署模式
DEPLOY_MODE=local
```

> LLM / Embedding / Search 等业务配置通过前端 Settings 管理（存储在数据库），无需在 `.env` 中配置 API Key。

#### 可选配置

```env
# 数据根目录（默认 ~/.myrm；SQLite 等路径由此派生）
# MYRM_DATA_DIR=~/.myrm

# 图查询：默认使用 SQLite 递归 CTE（零配置）
# 可选：设置 DATABASE_URL 启用 PostgreSQL + Apache AGE 后端
# DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/myrmagent

# MCP 服务配置
MCP_ALLOW_STDIO=true  # Sandbox 部署时设为 false 以禁用本地进程执行
```

#### MCP 服务配置

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `MCP_ALLOW_STDIO` | 是否允许 stdio 模式（本地进程通信） | `true` |

> **安全提示**：Sandbox 部署时应将 `MCP_ALLOW_STDIO` 设为 `false`，以防止用户在服务器上执行任意本地命令。

### 配置文件

| 文件 | 用途 |
|------|------|
| `.env.local` | 本地模式预设 |
| `.env.docker` | Docker 模式预设 |
| `.env.sandbox` | Sandbox 模式预设 |
| `.env` | 实际使用的配置（被 .gitignore 忽略） |

## 常用命令

### 服务管理

```bash
# 查看服务状态
uv run deploy.py status

# 停止所有服务
uv run deploy.py stop
```

### 数据库操作

```bash
# 初始化数据库表
source .venv/bin/activate
python -c "import asyncio; from app.database.connection import init_database; asyncio.run(init_database())"
```

### 构建沙箱镜像

```bash
cd docker/sandbox
./build.sh
```

## 故障排除

### SQLite 数据库问题

```bash
# 检查数据库文件
ls -la ~/.myrm-agent/data.db

# 检查 WAL 模式
sqlite3 ~/.myrm-agent/data.db "PRAGMA journal_mode;"
```

### Qdrant 向量库问题

```bash
# 检查嵌入式模式数据目录
ls -la ~/.myrm-agent/qdrant/
docker compose logs qdrant
```

### 图功能异常

图功能用于记忆系统的因果链查询：
- **本地模式**：使用 SQLite 递归 CTE，无额外依赖，若失败会自动降级到向量检索
- **Sandbox 模式**：使用 PostgreSQL + Apache AGE 扩展，需确保 AGE 扩展已安装

### Docker 服务无法启动

```bash
# 检查端口是否被占用
lsof -i :8080  # Backend
lsof -i :3000  # Frontend

# 清理后重试
docker compose down -v
docker compose up -d
```

## 生产环境建议

### 安全配置

```env
# 启用 HTTPS
# 配置反向代理（Nginx/Caddy）

# Sandbox 模式：设置 API Key / Sandbox mode: configure API key
SANDBOX_API_KEY=your-generated-api-key

# Sandbox 模式：配置加密密钥
CONFIG_ENCRYPTION_KEY=your-encryption-key
```

### 性能优化

```bash
# Sandbox 模式（默认 uvicorn 单进程，沙箱内嵌入式 DB 需单进程）
uv run deploy.py sandbox

# Docker 资源限制
# 修改 docker-compose.yaml 中的 deploy.resources
```

### 启动方式说明

| 方式 | 命令 | 说明 |
|------|------|------|
| **推荐** | `uv run deploy.py tauri dev` / `uv run deploy.py sandbox` / `uv run deploy.py docker` | 部署并自动启动应用 |
| **手动启动** | `uv run run.py` | 单独启动应用（自动选择启动方式） |
| **调试模式** | `python -m app.main` | 直接使用 uvicorn（不推荐，仅用于调试） |

**启动方式选择**：

- `run.py` 所有模式默认使用 `uvicorn` 单进程（嵌入式 SQLite + Qdrant 需单进程避免文件锁冲突）
  - 如需手动切换为 granian 多进程，设置 `SERVER_MODE=granian`（仅适用于无嵌入式 DB 的场景）

### 备份

```bash
# PostgreSQL 备份
docker exec postgres pg_dump -U myrmagent myrmagent > backup.sql

# Qdrant 备份
# 数据在 Docker volume: qdrant-data

# 完整备份
docker compose down
tar -czvf backup.tar.gz \
    data/ \
    ~/.myrm/ \
    $(docker volume inspect --format '{{ .Mountpoint }}' qdrant-data)
```

## 测试

```bash
# 运行所有测试
python -m pytest

# 运行MCP相关测试
python -m pytest tests/api/test_mcp_verify.py
```
