# memory/operations/crud/import_flows 模块架构

记忆导入/导出/回滚的相态实现。父目录的 `import_archive.py` 是唯一对外门面，re-export 本包全部 handler 与 token 基线常量（见 `crud/_ARCH.md`），路由与测试只经门面引用。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `export_flow.py` | 核心 | 导出（JSON + Markdown ZIP）、归档、规则安全导出与预览 | ✅ |
| `dry_run.py` | 核心 | 导入 dry-run 编排：模型车道 → 竞品来源归一化 → 审查会话哈希绑定 → 响应装配 | ✅ |
| `dry_run_source.py` | 辅助 | 竞品来源只读一次：载荷加载、技能截断（上限 500）、指令计划、MCP/模型/cron/会话旁路，以及 confirm 重放所需的 session metadata | ✅ |
| `dry_run_preview.py` | 辅助 | 预览行组装：instruction/memory/skill/credential/cron/session 车道（含 `detail_parts` 本地化片段）、会话样例、指令预览（persona 截断 1200）、token 经济估算、cron 跳过原因 | ✅ |
| `paste_lane.py` | 辅助 | 粘贴文本的模型车道：40k 字符预算内单次抽取，未配置模型/超预算/抽取失败一律回退确定性解析；不写库也不跳过审查 | ✅ |
| `confirm_flow.py` | 核心 | 导入 confirm 编排：写入记忆 → 按审阅顺序重放车道 → 诊断 → readiness → 响应（`workspace_bind_candidates` 与账本条目供回滚重放） | ✅ |
| `instruction_lane.py` | 核心 | confirm 写入车道：指令计划（persona/全局/规则）+ MCP 配置 + 模型迁移（Hermes `moa`→Agent `moa_overlay`，经 `hermes_moa_migrator`）+ `instruction_rollback` 账本；MCP 写入失败不推翻已生效的指令车道 | ✅ |
| `confirm_followups.py` | 辅助 | confirm 后续车道：cron 暂停导入、会话落库、导入后诊断（失败降级）、readiness 聚合与持久化（含 recheck facts） | ✅ |
| `side_effects.py` | 辅助 | confirm 之后的副作用：MCP 配置迁移、模型迁移搬运、`POST /import/readiness-recheck` 用当前 provider 状态重算 readiness | ✅ |
| `rollback_flow.py` | 核心 | 导入回滚预演与执行（读 confirm 写入的账本条目） | ✅ |

## 依赖关系

- `app/schemas/memory/archive.py` — 导入/回滚请求与响应 Schema
- `app/services/memory/imports/` — 审查会话、账本、readiness 合同、回滚与来源解析服务
- `app/services/migration/source/` — 竞品载荷加载与归一化
- 路由入口：`app/api/memory/operations/crud.py` 经父目录门面绑定 handler。
