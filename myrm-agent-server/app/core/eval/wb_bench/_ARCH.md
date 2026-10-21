# app/core/eval/wb_bench 子包架构


---

## 架构概述

WorkBuddy Bench 数据源适配子包。将 WBBench 生态（GitHub 源、归档下载、任务工作区构建、判定逻辑）从单文件模块拆分到单职责模块，经包级 Facade 保持既有 `from app.core.eval.wb_bench import ...` 调用点不变。本子包属于 Server 业务层，负责数据获取与任务构建；判定评分逻辑对接 Harness 的确定性/LLM judge 能力。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合出口：re-export `download`/`workspace` 的公共 API（常量、`WbBenchSubset`、`ensure_wb_bench_source`/`list_wb_bench_sources`/`build_wb_bench_cases`）。 |
| `download.py` | WBBench 数据源层：源发现/下载/缓存（`ARCHIVES_DIR`/`SOURCES_DIR`/`WORKSPACES_DIR`），`DownloadAbortedError` 支持可取消下载。 |
| `workspace.py` | 任务/工作区构建：`build_wb_bench_cases` 生成可执行基准用例与预置工作区。 |
| `verifier.py` | 判定接线：WBBench native/composite 确定性判分与 LLM judge 装配。 |

---

## 依赖关系

**被依赖**：
- `app/core/eval/service.py` — 泛化基准编排经 `run_wb_bench_background` 委托到本子包
- `app/api/eval/` — 评测 API 层
