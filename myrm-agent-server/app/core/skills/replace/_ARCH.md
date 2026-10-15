# Skill replace (`app/core/skills/replace/`)

| 文件 | 职责 |
|------|------|
| `manifest_snapshot.py` | 替换前收集 SKILL.md + 有界文本资源；返回 snapshot_truncated |
| `snapshot_honesty.py` | 替换后检测未纳入快照的文件；合并 truncated 并写回 batch metadata |
| `finalize.py` | 替换成功后统一：undo 指针 + honesty 合并 + metadata 持久化 |
| `service.py` | 创建 mutation batch 快照、记录成功替换 |
| `state.py` | `last_replace_batch_id`（local 侧车 / prebuilt metadata） |

前端：Discover 安装/更新与 URL 导入共用 `skillInstallRollbackToastAction.ts` 展示撤销 Toast（`pre_replace_batch_id`）。
