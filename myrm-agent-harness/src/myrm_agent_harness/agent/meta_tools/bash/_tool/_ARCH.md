# bash/_tool/

## Overview
bash 工具横切能力域：LLM 描述提示词、输出格式化/截断、退出码语义、多模态、后台监听、被存下的输出流的 UI 告知、失败转 `ToolError`、后台进程工具的 action 处理器。

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | 域包入口，不导出符号；调用方按模块路径导入。 | — |
| `tool_description.py` | Internal | 静态缓存稳定的工具描述 `TOOL_DESCRIPTION_EN` / `TOOL_DESCRIPTION_ZH`，`resolve_bash_code_execute_tool_description` 按 locale 取其一（能力与交互式程序的出路/独立与未知返回的合并与观察规则/专用工具路由/每次调用都当作全新开始的状态/输出与错误约定/后台任务进度标记）；参数限制归 `helpers.py` 的 `BashInput` 字段，后台作业管理归 `bash_process_tool`，落盘输出的读回路径归 eviction 页脚，描述不重复这三处。 | ✅ |
| `formatting.py` | Core | 输出压缩编排、截断、脱敏、wrapping；消费压缩域 `BASH_OUTPUT_MAX_CHARS` 做硬截断。`read_exit_code()` 是 `format_result` 的读回端：只认工具自己追加在输出块末尾的 `[exit_code: N]`（其后至多跟一行 `[Auto-Hint]`），输出里同形的文字不算；没有该行的完成输出为 0，后台未结束、报错文本与非 bash 结果为 None。 | ✅ |
| `exit_semantics.py` | Core | Exit-code 语义解释（grep=1、git diff、信号）。 | ✅ |
| `terminal_hints.py` | Core | 输出模式故障自愈诊断与伪成功（Masked Success）防护。 | ✅ |
| `helpers.py` | Core | BashInput schema（`reason` 必填、不少于 10 个字符；`command` 不得为空或纯空白，在入口拒绝并说明原因，免得空命令带着 shell 注入头走到执行器、被安全扫描按头里的文字拦下；两处校验只在报错时起作用，不改变交给模型的工具定义）、OS hint、上下文恢复/访问追踪。 | ✅ |
| `multimodal.py` | Core | Vision ContentBlock 内联返回（生成图片）。 | ✅ |
| `background_listeners.py` | Core | 后台 spawn ptc_notify 监听与退出分类。 | ✅ |
| `evicted_emit.py` | Core | 把一次 bash 调用里被整份存下的输出流告知 UI（引用、字符数、行数），好让 UI 提供「查看完整输出」：成功路径带给模型看的预览（只对 stdout），失败路径不带预览（步骤的 stdout 留着执行中累积的部分输出）；失败路径上某条告知出错只记警告，不盖住原错误。 | ✅ |
| `failure.py` | Core | `build_failure_error`：一次 bash 调用抛出的异常变成交给模型的 `ToolError`；`BashExecutionError` 另带它的修复提示、错误类别和被存下的输出流，并追加输出模式诊断。 | ✅ |
| `process_handlers.py` | Core | `bash_process_tool` 各 action（list/output/wait/kill/stdin）在会话后台任务上的处理器；`output` 与已结束任务的 `wait` 带同一组输出字段（两路输出、`dropped`，这次读取没有给出的行数 `omitted_lines`（大于 0 时才出现），其时任务有日志再带 `log_file`，日志的工作区相对路径）；`list` 为每个有日志的任务带 `log_file`；`output` 与仍在运行的任务的 `wait` 带空闲标记及其说明，作业打印过未换行的文字时再带 `partial_line`（未结束的最后一行，通常是提示）；已结束的任务若留下仍在运行的进程，`list` / `output` / `wait` 的结果带 `leftover_processes`（大于 0 时才出现）；`output` 或 `wait` 返回了任务自己的退出结果时，向唤醒处理器报告「已读」（`list`、仍在运行的任务的 `output`、超时的 `wait` 不报告；被终止的任务不会被结算，也不报告），该任务结束所排的唤醒回合据此让位；`kill_report` 如实说明停止的效果（任务进程组内是否发现还有进程在运行；平台无法列出进程组时只说发出了什么信号）。门面 `bash_process_tool` 负责 schema、能力校验与分发。 | ✅ |

## Key Dependencies

- `../_compression/output_compressor`（语义压缩，单向依赖）
- `../_compression/constants`（`BASH_OUTPUT_MAX_CHARS` 阈值消费方，单向依赖）
- `../_background`（后台监听；进程工具处理器读写后台任务注册表）
- `../_executor/error`（共享异常）
