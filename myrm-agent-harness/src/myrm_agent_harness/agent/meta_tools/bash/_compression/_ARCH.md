# bash/_compression/

## Overview
bash 输出压缩域：命令感知语义压缩（双引擎）、大输出即时 eviction 落盘、声明式 YAML 过滤器。

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | 域聚合出口：导出 `compress_output`、`maybe_evict_large_output`、`BASH_OUTPUT_MAX_CHARS`。 | — |
| `constants.py` | Internal | 压缩域常量：`BASH_OUTPUT_MAX_CHARS`（字符截断阈值单一事实源）。 | ✅ |
| `output_compressor.py` | Internal | 语义压缩入口：硬编码 14 条压缩器匹配规则 + DeclarativeFilterEngine；eviction banner 幂等跳过。 | ✅ |
| `compressors.py` | Internal | 10 个具体压缩器（git status/diff/log/operation、ls、test、package install、docker build、build tool、compiler error）。 | ✅ |
| `log_compressor.py` | Internal | 日志流去重兜底：只处理日志形状的输出（时间戳或级别开头的行占 80% 以上），重复消息折叠成计数、各条不同的消息都保留；文件清单、grep 结果、JSON 转储等数据输出原样通过。 | ✅ |
| `output_eviction.py` | Internal | 大输出（token>20k 或 chars>8k）即时落盘 `.context/{chat_id}/evicted/` + 智能预览 + file_read_tool footer。json/xml/yaml/log 给结构概要，其余给首尾真实行；rg/grep 的 `path:line:内容` 搜索列表会被内容嗅探器误认成代码或 CSV，因此不走概要。 | ✅ |
| `builtin_filters.yaml` | Config | 内置声明式过滤器（terraform-plan/make/rsync/docker-pull）。 | — |

## Key Dependencies

- `.constants`（`BASH_OUTPUT_MAX_CHARS` 字符截断阈值单一事实源）
- `agent.context_management.strategies.filter`（token 阈值）
- `agent.context_management.infra.evicted`（落盘 + footer）
