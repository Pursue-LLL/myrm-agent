# memory/strategies/extractor/

## 架构概述

自动记忆提取：信号与语言判定、提取模型、提示词、LLM 提取器、JSON 解析与批量入口分层放置；`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `MemoryExtractor` / 模型 / 检测函数 / 批量入口 | ✅ |
| `signals.py` | 逻辑 | 正负反馈与纠正信号检测 | ✅ |
| `models.py` | 契约 | `ExtractionConfig` / `ExtractedMemory` / `ExtractionResult` | ✅ |
| `prompt.py` | 逻辑 | 中文阈值、语言检测与系统提示构造 | ✅ |
| `runner.py` | 逻辑 | `MemoryExtractor`：调用 LLM、合并结果；提出的记忆与规则都带被提取的对话（`source_chat_id`），按对话级联删除靠它找到它们 | ✅ |
| `parse.py` | 逻辑 | LLM 输出的 JSON 清洗与解析 | ✅ |
| `pipeline.py` | 入口 | 会话与目标执行轨迹的批量提取 | ✅ |

## 依赖关系

- `parse.py` → `models.py`
- `pipeline.py` → `models.py`
- `pipeline.py` → `parse.py`
- `pipeline.py` → `prompt.py`
- `pipeline.py` → `runner.py`
- `prompt.py` → `models.py`
- `runner.py` → `models.py`
- `runner.py` → `parse.py`
- `runner.py` → `prompt.py`
