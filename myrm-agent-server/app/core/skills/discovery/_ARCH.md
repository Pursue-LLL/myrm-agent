# app/core/skills/discovery 子包架构


---

## 架构概述

技能发现、采纳、挂载与上游更新子域。覆盖三个生命周期事件：显式 allowlist 场景下安装后自动采纳（adopt）、安装/更新后 catalog enable（mount）、上游版本检测（autoupdate）。属于 Server 业务层，适配 Harness 技能存储与版本能力。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 子域聚合出口：导出 adopt/mount/autoupdate 公共 API。 |
| `adopt.py` | 显式 allowlist 场景安装后自动采纳：`complete_discovery_adoption`（append skill_id）、`remove_skill_from_all_agents`（卸载孤儿清理）、`sync_skill_to_agents`（跨 Agent 白名单批量同步）。 |
| `mount.py` | 安装/更新后 catalog enable 入口：`maybe_mount_after_install`/`resolve_mount_skill_id`/`DEFAULT_MOUNT_AGENT_ID`，触发 `SKILL_POOL_UPDATED` 广播，返回 `SkillMountResult`。 |
| `autoupdate.py` | 上游版本检测与更新检查：`get_update_checker`。 |

---

## 依赖关系

**被依赖**：
- `app/core/skills/store/` — 技能存储层
- `app/api/skills/` — 技能 API
