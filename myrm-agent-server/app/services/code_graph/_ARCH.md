# code_graph 模块架构

## 职责定位
提供本地轻量级、零外部中间件依赖的代码 AST 符号图谱与调用链分析能力。支持 Python 3.13 与 TypeScript/JavaScript 多语言，配合 SQLite WAL 模式实现高并发读写与毫秒级单文件增量重析（reingest）。

## 核心文件清单
- `models.py`: 核心数据模型（`SymbolNode`, `CallEdge`, `CallSite`, `IndexStats`）。
- `ast_extractor.py`: 基于 Python 原生 `ast` 模块与正则规则的高性能符号与调用抽取器。
- `graph_store.py`: 基于 SQLite WAL 模式的符号表与关系存储，支持 8 大确定性图遍历操作。
- `service.py`: 对外业务服务门面，集成全量目录扫描与单文件增量更新。
- `cli.py`: 面向 Agent 沙箱或本地终端的命令行操作入口。

## 架构边界
严格遵守 `myrm-agent-harness/src/myrm_agent_harness/toolkits/_ARCH.md` 规则 4，属于 Server 业务层提供的预置代码智能技能，不侵入 Harness 核心执行框架。
