# wiki/retrieval/query/

## 架构概述

Wiki 查询引擎：检索、加载、答案三个阶段与编排入口分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 导出 `WikiQueryEngine` / `SemanticSearchFn` | ✅ |
| `base.py` | 基础 | 实例状态与跨阶段方法声明 | ✅ |
| `retrieval.py` | 核心 | 概念搜索、检索种子、索引命中与 sidecar 目录 | ✅ |
| `loading.py` | 核心 | 文章/目录 sidecar 加载、claim/asset 片段与截断 | ✅ |
| `answering.py` | 核心 | 拒答判定、答案组装、置信度与检索追踪 | ✅ |
| `engine.py` | 核心 | 组合三阶段并暴露 `query()` | ✅ |

## 依赖关系

- `answering.py` → `base.py`
- `engine.py` → `answering.py`
- `engine.py` → `base.py`
- `engine.py` → `loading.py`
- `engine.py` → `retrieval.py`
- `loading.py` → `base.py`
- `retrieval.py` → `base.py`
