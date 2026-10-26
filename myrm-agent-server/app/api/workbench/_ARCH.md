# Workbench API Architecture

## 1. 概述与定位
本模块位于 `myrm-agent-server/app/api/workbench/`，为前端辅助工作台的终端提供某个会话工作区上的后端服务。请求必须指明 `chat_id`，命令及其工作目录都限定在该会话的工作区内（`find_chat_workspace_root`：项目绑定目录 > 会话绑定目录 > 会话 JIT 沙箱目录），不存在“进程工作目录”兜底：
1. **终端执行通道 (`/terminal/exec`)**：在会话工作区内执行命令；先过 harness 静态命令闸（与 agent bash 同一套危险命令规则，容忍人手写的 shell 语法），子进程环境经 `build_isolated_child_env(CORE)` 剥离服务端凭据（与 agent 自身的 bash 会话同一套），stdin 绑定 `/dev/null`，等待因超时或处理协程被取消而结束时仍在运行的命令按进程组整树终止，stdout/stderr 各自限长（超出标记 `truncated`）。

## 2. 模块结构与文件表
| 文件 | 职责 |
|---|---|
| `models.py` | Pydantic 数据契约定义（`TerminalExecRequest`, `TerminalExecResponse`，零 Any） |
| `routes.py` | FastAPI 路由实现：命令执行 |
| `__init__.py` | 包门面导出 `workbench_router` |

## 3. 安全与设计红线
- **工作区边界**：命令的工作目录必须经 `_resolve_safe_path` 解析（`resolve()` 后做包含判断）并限定在会话工作区内；会话没有可用工作区时返回 404，不回退到服务进程目录；
- **危险命令防御**：复用 `gate_hook_command(strict=False)`，不在本模块另维护正则；
- **凭据隔离**：终端子进程不继承服务端进程的 API 密钥、令牌等环境变量，只保留工具链运行所需的核心变量；
- **读取上限**：命令的 stdout / stderr 各自受 `_MAX_RESPONSE_BYTES` 限制，超出部分读出后丢弃，不会把无限输出整份留在内存；
- **进程树回收**：子进程独立进程组；等待因超时或处理协程被取消而结束时，只要命令还在运行，就调用 `kill_process_group` 终止整树。客户端中断不会取消处理协程，命令运行到自然结束或 `timeout_seconds` 为止（界面固定 30 秒，接口上限 120 秒）；
- **类型安全**：严格使用 Python 3.13 强类型提示，禁止使用 `Any`。

文件浏览、预览与编辑不在本模块：前端工作台的文件页复用 `app/api/files/browse.py`（见 [`../files/_ARCH.md`](../files/_ARCH.md)），同一份文件树与预览供侧栏和工作台共用。
