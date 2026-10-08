# services/memory/pitfall_alert 模块架构

## 架构概述

主动踩坑预警与决策辅助：`PitfallAlertServiceProvider` 持有 Harness `ProactivePitfallAlertEngine`，对用户输入做决策意图识别并检索历史复盘三元组，产出预警卡片；支持会话级静音/取消静音、登记复盘三元组与状态查询；首次实例化时写入种子复盘（`_bootstrap_seeded_postmortems`）。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 辅助 | 导出 provider 公共入口 | ✅ |
| `provider.py` | 核心 | `PitfallAlertServiceProvider`：evaluate_query / register_triad / mute_subject / unmute_subject / get_status；`get_pitfall_alert_service` 单例入口 | ✅ |
