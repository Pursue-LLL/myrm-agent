# cron 模块架构

Cron 业务服务层。提供定时任务创建前的手动成功验证门禁、外发投递目的地的健康度聚合与先验执行统计服务。

---

## 架构职责

- `prerequisite_service.py`: 统计指纹工作流在历史 Chat 与 Kanban 中的手动执行成功次数，提供先验验证门禁。
- `connector_health_service.py`: 按投递目的地聚合外发连接器的投递健康度。目的地由 `delivery_key`（执行器写进运行记录的目标指纹，来自 harness 的 `delivery_target_key`）认定，不是脱敏后的地址，所以只差一个密钥的两个机器人不会并成一个；一次运行只算进它的 `delivery_key` 对应的目的地，没有该字段的运行不计入。只统计发生过投递尝试（delivered 或 failed）的运行，取窗口内最近 50 次，跳过投递的运行不计入；连续失败数、最近一次错误分类与三态状态（HEALTHY / DEGRADED / DOWN）都只来自投递记录，任务自身的失败不算连接器故障；最近投递时间是发生投递尝试的运行的结束时刻（取于投递之前）。

---

## 文件清单

| 路径 | 地位 | 职责 |
|------|------|------|
| `__init__.py` | 模块入口 | 暴露 Cron 业务服务公共符号 |
| `connector_health_service.py` | 核心服务 | 按投递目的地（`delivery_key`）聚合外发连接器健康度的服务 |
| `prerequisite_service.py` | 核心服务 | Cron 任务前置验证门禁服务与统计聚合 |
