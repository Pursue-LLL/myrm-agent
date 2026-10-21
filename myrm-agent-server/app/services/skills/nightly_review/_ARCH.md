# skills/nightly_review/ 模块架构

每夜一体检：协作评分、回归验收盯梢与早晨 digest。只读诊断与账本，只写 findings/watches/digest 三类记录；修复走 curator 现成 API。

## 文件清单

| 文件         | 地位 | 职责                                                             | I/O/P |
| ------------ | ---- | ---------------------------------------------------------------- | ----- |
| `scorer.py`  | 核心 | 纯函数 360° 信号：账本负事件按实体聚类，阈值出 findings（零 LLM） | ✅    |
| `acceptance.py` | 核心 | 不再犯盯梢：开 watch（账本）与到期验收（零复发即 verified）     | ✅    |
| `service.py` | 核心 | 夜间编排：读昨日→评分→开盯梢→验旧梢→digest 落库+广播；后台环启停 | ✅    |
| `__init__.py` | —   | 包标记（禁聚合导出，外部穿透导入子模块）                         | —     |

## 模块依赖

- `..experience_ledger` — 事件读写（账本 SSOT）
- `app.core.skills.curator.service` — 诊断读取与修复调用（只读调 API，不拥有）
- `app.database.models.notification::SystemNotification` — digest 落库
- `app.services.event.app_event_bus` — digest 广播（复用 SYSTEM_NOTIFICATION）
- `app.server.warmup` — 后台环启动；`app.server.lifespan` — 关闭

## 设计原则

- 诊断只读、修复调用现成 API，本包不自建状态表（账本即事实源）。
- LLM 禁打分禁开方；digest 文案模板生成，零新增提示词面。
