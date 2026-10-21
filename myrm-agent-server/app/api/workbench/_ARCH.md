# Workbench API Architecture

## 1. 概述与定位
本模块位于 `myrm-agent-server/app/api/workbench/`，对标 Roadmap Item 25 (`IndependentMultiTabAuxiliaryWorkbenchWithBuiltinDiffAndPty` · P0)。
为前端辅助工作台提供后端核心数据服务支持：
1. **工作区文件树遍历 (`/files`)**：提供递归文件树、防目录穿越（Directory Traversal）安全根检查与常用敏感目录忽略；
2. **文件内容安全读取 (`/file/content`)**：支持编码自动检测、语言语法类型推断与大小限制；
3. **文本/代码 Diff 对比引擎 (`/diff`)**：支持基于 `difflib` 的标准 unified diff 差异生成、增删行统计与行级 DiffHunk 分块；
4. **终端执行通道 (`/terminal/exec`)**：支持受控异步子进程命令执行、危险高危指令拦截（如 `rm -rf /`）与超时保护；
5. **插件生命周期与健康探针 (`/plugins`, `/plugins/{id}/probe`)**：提供插件列表与毫秒级健康探活。

## 2. 模块结构与文件表
| 文件 | 职责 |
|---|---|
| `models.py` | Pydantic 数据契约定义（`WorkbenchFileNode`, `FileTreeResponse`, `FileDiffResponse`, `TerminalExecResponse`, `PluginItemModel` 等，零 Any） |
| `routes.py` | FastAPI 路由实现，包含文件树遍历、内容读取、Diff 计算、命令执行与插件探活 |
| `__init__.py` | 包门面导出 `workbench_router` |

## 3. 安全与设计红线
- **防止路径遍历**：所有访问路径必须通过 `_resolve_safe_path` 严格解析并约束在工作区白名单根目录内部；
- **高危命令防御**：拦截包含递归删除根目录、格式化磁盘等破坏性指令；
- **类型安全**：严格使用 Python 3.13 强类型提示，禁止使用 `Any`。
