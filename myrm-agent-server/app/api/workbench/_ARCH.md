# Workbench API Architecture

## 1. 概述与定位
本模块位于 `myrm-agent-server/app/api/workbench/`，为前端辅助工作台提供某个会话工作区上的后端服务。每个请求必须指明 `chat_id`，所有路径与命令都限定在该会话的工作区内（`find_chat_workspace_root`：项目绑定目录 > 会话绑定目录 > 会话 JIT 沙箱目录），不存在“进程工作目录”兜底：
1. **工作区文件树遍历 (`/files`)**：递归文件树、防目录穿越（含符号链接逃逸）与常用敏感目录忽略；
2. **文件内容读取 (`/file/content`)**：编码容错、语言类型推断；
3. **终端执行通道 (`/terminal/exec`)**：在会话工作区内执行命令；先过 harness 静态命令闸（与 agent bash 同一套危险命令规则，容忍人手写的 shell 语法），stdin 绑定 `/dev/null`，超时后按进程组整树终止，stdout/stderr 各自限长（超出标记 `truncated`）。

## 2. 模块结构与文件表
| 文件 | 职责 |
|---|---|
| `models.py` | Pydantic 数据契约定义（`WorkbenchFileNode`, `FileTreeResponse`, `FileContentResponse`, `TerminalExecRequest`, `TerminalExecResponse`，零 Any） |
| `routes.py` | FastAPI 路由实现：文件树遍历、内容读取、命令执行 |
| `__init__.py` | 包门面导出 `workbench_router` |

## 3. 安全与设计红线
- **工作区边界**：所有访问路径必须经 `_resolve_safe_path` 解析（`resolve()` 后做包含判断）并限定在会话工作区内；会话没有可用工作区时返回 404，不回退到服务进程目录；
- **危险命令防御**：复用 `gate_hook_command(strict=False)`，不在本模块另维护正则；
- **进程树回收**：子进程独立进程组，超时调用 `kill_process_group` 终止整树；
- **类型安全**：严格使用 Python 3.13 强类型提示，禁止使用 `Any`。
