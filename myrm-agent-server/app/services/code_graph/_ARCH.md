# code_graph 模块架构

## 职责定位
提供本地轻量级、零外部中间件依赖的代码 AST 符号图谱与调用链分析能力。支持 Python 3.13 与 TypeScript/JavaScript 多语言，配合 SQLite WAL 模式实现高并发读写与毫秒级单文件增量重析（reingest）。

## 核心文件清单
- `models.py`: 核心数据模型（`SymbolNode`, `CallEdge`, `CallSite`, `IndexStats`）。
- `ast_extractor.py`: 基于 Python 原生 `ast` 模块与正则规则的高性能符号与调用抽取器。JS/TS 抽取器按行匹配行首无缩进的 `class`、`function` / `async function` 与 `const f = (...) =>` 声明，各产出一个符号（函数的 `line_end` 与类同口径，等于声明行）；类方法、嵌套函数、`export default function` 与带泛型的函数不产出符号。
- `graph_store.py`: 基于 SQLite WAL 模式的符号表与关系存储，支持 8 大确定性图遍历操作。
- `service.py`: 对外业务服务门面，集成全量目录扫描与单文件增量更新；全量扫描只按相对扫描根的路径片段排除 `EXCLUDE_DIRS`（`.git`、`node_modules`、`dist`、`build` 等），根目录自身的祖先目录名不参与判断。
- `cli.py`: 面向 Agent 沙箱或本地终端的命令行操作入口。

## 架构边界
严格遵守 `myrm-agent-harness/src/myrm_agent_harness/toolkits/_ARCH.md` 规则 4，属于 Server 业务层提供的预置代码智能技能，不侵入 Harness 核心执行框架。
