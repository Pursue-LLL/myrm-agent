# app/services/onboarding/second_brain_preset 子包架构

Second Brain 预设：读路径（状态 + checklist）与写路径（幂等 apply + 回滚）分离，cron 供给与 agent/vault 变更各自独立；`app.services.onboarding.second_brain_preset` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `apply_second_brain_preset`、`get_second_brain_preset_status`、`SecondBrainPresetError`、`reconcile_second_brain_cron_ids`、`repair_wiki_delta_job_security` | — |
| `common.py` | 辅助 | 常量（config key / cron 名 / template id / user & device）、`SecondBrainPresetError`、`_ApplyMutation`、preset state 读写、模板加载与 locale 归一；**唯一的 `get_cron_manager` 打桩点** | ✅ |
| `checks.py` | 核心 | provider / wiki / agent tool 就绪检查、`_build_checklist`、`_resolve_agent`（创建或复用 user agent，含技能启用与 vault seed） | ✅ |
| `cron_setup.py` | 核心 | cron job 查找、blueprint 供给（read-it-later + wiki delta + maintenance）、id reconcile、security repair、read-it-later hygiene | ✅ |
| `mutations.py` | 核心 | wiki gmail source 开启、成功消息、apply 回滚（删除 agent / cron） | ✅ |
| `status.py` | 核心 | 读路径：`get_second_brain_preset_status` | ✅ |
| `apply.py` | 核心 | 写路径：`apply_second_brain_preset`（幂等 apply，失败回滚） | ✅ |

## 依赖关系

- 上游：`app.core.cron.adapters.setup`、`app.services.agent.agent_service`、`app.services.agent.template_utils`、`app.services.config.service`、`app.services.wiki.vault` / `wiki.source_sync`
- 下游：`app/api/config/routes/onboarding.py`（status / apply）、`app/lifecycle/schedulers/cron.py`（启动时 reconcile / repair）
