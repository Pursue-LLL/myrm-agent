# organize/ 模块架构

## 架构概述

Workspace 批量整理 HITL 执行层：校验 organize-plan.json、dry-run 预览、原子批量移动、job 持久化与回滚、Markdown wikilink 重写。由 `app/api/files/organize.py` 暴露 HTTP；Agent 侧通过 prebuilt skill 生成计划，不新增 Harness meta tool。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `types.py` | 核心 | OrganizePlan / OrganizeJob / 校验 issue 类型 | ✅ |
| `validation.py` | 核心 | 6 层路径安全 + scope/depth/collision/duplicate-src/mtime 校验 | ✅ |
| `apply.py` | 核心 | dry-run / apply / rollback；失败 mid-batch 自动逆移 | ✅ |
| `job_store.py` | 辅助 | JSON job 持久化（`state_dir/organize_jobs`）+ TTL 清理 | ✅ |
| `wikilink.py` | 辅助 | apply/rollback 后 workspace 内 `[[wikilink]]` 目标重写 | ✅ |

## 依赖关系

### 内部依赖
- `app/api/files/workspace_ops::_resolve_workspace` / `_validate_target` (POS: workspace 写操作安全栈)

### 被依赖方
- `app/api/files/organize.py` (POS: workspace organize HITL HTTP API)
