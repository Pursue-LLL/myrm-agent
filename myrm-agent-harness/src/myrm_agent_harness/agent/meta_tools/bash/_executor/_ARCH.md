# bash/_executor/

## Overview
BashExecutor 聚合根与执行编排域：同步/后台执行、上下文构建、技能 staging、会话生命周期。

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | 域聚合出口：导出 `BashExecutor`、`BashExecutionError`。 | — |
| `executor.py` | Core | BashExecutor 聚合根（DI 编排，MRO: Execute → Background → Prepare → Context，由架构测试锁定）。 | ✅ |
| `execute_mixin.py` | Core | 同步 ``execute()`` 编排；stdout/stderr 对称 eviction；失败路径双流落盘 + ``BashExecutionError`` 携带 eviction 引用；一次技能执行起一个只属于它的 MCP IPC 服务端（`AsyncExitStack`，脚本无论怎样结束都随之停止）；失败路径先剥掉 MCP 调用标记（模型不读标记和 nonce），并附上失败前已完成的 MCP 调用摘要。技能的保存设置只交给该技能脚本的纯调用（`plain_skill_call`）：命令按纯调用走 `ensure_skills_in_workspace(pristine=True)` 先把工作区里的技能目录还原成随包文件（还原失败则不交设置），其余命令照常执行但不带设置，失败消息末尾附 `settings_withheld_note`。会话有工作区根目录时才执行 Office 写入审计（`OfficeBashAudit`）。 | ✅ |
| `background_mixin.py` | Core | ``spawn_background()`` 后台进程注册（后台作业默认受当前 agent 能力句柄约束）；剥离裸尾 ``&`` 防孤儿进程。 | ✅ |
| `prepare_mixin.py` | Core | 代码类型检测、`CallerScope`（服务端替哪次运行调用，由宿主决定）、技能命令按需起这次执行的 MCP IPC 服务端（`PreparedExecution` 带回该服务端的标记 nonce）；内联 Python 之外，裸 `[cd <工作区根> &&] python[3] <file>.py` 形态的保存脚本若导入宿主能服务的 MCP 技能，也由宿主读入并走同一套技能运行时，但其服务端范围带 `script_file`，只放行只读 MCP 工具；其余启动形态（带参数/管道/环境变量前缀等）仍交给 shell；技能 staging；MCP 技能的超时下限取该技能各 server 最长 `execute_timeout` + `MCP_HOST_MARGIN_SECONDS`（不低于 `MCP_MIN_TIMEOUT`），使带名字的错误先于宿主的终止到达脚本。 | ✅ |
| `context_mixin.py` | Core | ExecutionContext 构建（带当前请求的取消令牌，使停止能到达在跑的命令；技能命令带 `enter_work_dir`，从技能目录起跑）、`_execution_workspace_root`（`/workspace` 对 shell 与解释器的含义：执行器绑定的根，未绑定才用会话自己的工作区目录；保存脚本的解析与执行上下文共用它）、OAuth issuer 作用域、事件日志。 | ✅ |
| `constants.py` | Internal | 共享常量（MCP 超时下限、宿主相对 server 调用上限的余量）。 | — |
| `workspace_manager.py` | Core | 工作区薄委托（懒加载绑定存储根）。 | ✅ |
| `skill_workspace_manager.py` | Core | 技能文件 staging 路径解析；`pristine=True` 时先移除工作区里该技能的旧副本（技能目录是符号链接时只解除链接；`.claude` 或 `.claude/skills` 是符号链接则拒绝）再按存储里的原文件重新 staging。 | ✅ |
| `mcp_citation_handler.py` | Core | MCP Metadata Extractor：只信任带这次执行的 IPC 服务端 nonce 的标记（调用方显式传入；没有 nonce 即不信任任何标记）；从标记解出的内容以及自己不认证的形似标记片段会再脱敏（输出脱敏器放行了它们）；`extract_completed_calls` 供失败路径取出去标记的 stdout 和「失败前已完成的 MCP 调用」一行摘要。 | ✅ |
| `event_logging.py` | Internal | 命令执行事件日志（命令经 `redact_command_line` 脱敏，输出经共享脱敏器，再分类）。 | ✅ |
| `error.py` | Core | 结构化 ``BashExecutionError``，携带 stdout/stderr eviction 引用与异常消息脱敏。 | ✅ |
| `auto_yield.py` | Core | 前台白名单命令超时自动后台化。 | ✅ |
| `command_classifier.py` | Core | 命令分类器（READ/WRITE/DANGEROUS/NETWORK/GIT/SEARCH/PYTHON/SKILL）。 | ✅ |

## Key Dependencies

- `../_compression/output_eviction`（大输出落盘）
- `../_background`（后台任务注册表）
- `toolkits.code_execution`（执行器）
