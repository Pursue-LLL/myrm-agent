# bash/_tool/

## Overview
bash 工具横切能力域：LLM 描述提示词、输出格式化/截断、退出码语义、多模态、后台监听、后台进程工具的 action 处理器。

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | 域包入口，不导出符号；调用方按模块路径导入。 | — |
| `tool_description.py` | Internal | 静态缓存稳定的工具描述 `TOOL_DESCRIPTION_EN` / `TOOL_DESCRIPTION_ZH`，`resolve_bash_code_execute_tool_description` 按 locale 取其一（能力与交互式程序的出路/独立与未知返回的批量观察规则/每次调用留给下一次的状态/后台任务入口与进度标记、动作名并指向 `bash_process_tool` 的描述/eviction 读取提示）。 | ✅ |
| `formatting.py` | Core | 输出压缩编排、截断、脱敏、wrapping；消费压缩域 `BASH_OUTPUT_MAX_CHARS` 做硬截断。`read_exit_code()` 是 `format_result` 的读回端：只认工具自己追加在输出块末尾的 `[exit_code: N]`（其后至多跟一行 `[Auto-Hint]`），输出里同形的文字不算；没有该行的完成输出为 0，后台未结束、报错文本与非 bash 结果为 None。 | ✅ |
| `exit_semantics.py` | Core | Exit-code 语义解释（grep=1、git diff、信号）。 | ✅ |
| `terminal_hints.py` | Core | 输出模式故障自愈诊断与伪成功（Masked Success）防护。 | ✅ |
| `helpers.py` | Core | BashInput schema（reason 必填）、OS hint、上下文恢复/访问追踪。 | ✅ |
| `multimodal.py` | Core | Vision ContentBlock 内联返回（生成图片）。 | ✅ |
| `background_listeners.py` | Core | 后台 spawn ptc_notify 监听与退出分类。 | ✅ |
| `process_handlers.py` | Core | `bash_process_tool` 各 action（list/output/wait/kill/stdin）在会话后台任务上的处理器；`output` 与已结束任务的 `wait` 带同一组输出字段（两路输出、`dropped`，行被丢弃且任务有日志时再带 `log_file`，日志的工作区相对路径）；`list` 为每个有日志的任务带 `log_file`；`output` 与仍在运行的任务的 `wait` 带空闲标记及其说明，作业打印过未换行的文字时再带 `partial_line`（未结束的最后一行，通常是提示）；已结束的任务若留下仍在运行的进程，`list` / `output` / `wait` 的结果带 `leftover_processes`（大于 0 时才出现）；`kill_report` 如实说明停止的效果（任务进程组内是否发现还有进程在运行；平台无法列出进程组时只说发出了什么信号）。门面 `bash_process_tool` 负责 schema、能力校验与分发。 | ✅ |

## Key Dependencies

- `../_compression/output_compressor`（语义压缩，单向依赖）
- `../_compression/constants`（`BASH_OUTPUT_MAX_CHARS` 阈值消费方，单向依赖）
- `../_background`（后台监听；进程工具处理器读写后台任务注册表）
- `../_executor/error`（共享异常）
