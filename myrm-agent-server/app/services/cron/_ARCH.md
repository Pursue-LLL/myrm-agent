# cron 模块架构

Cron 业务服务层。提供定时任务创建前的手动成功验证门禁、连接器健康度聚合与先验执行统计服务。

---

## 架构职责

- `prerequisite_service.py`: 统计指纹工作流在历史 Chat 与 Kanban 中的手动执行成功次数，提供先验验证门禁。
- `connector_health_service.py`: 聚合与分析外发连接器的健康度与降级状态，提供错误分类与排障建议。

---

## 文件清单

| 路径 | 地位 | 职责 |
|------|------|------|
| `__init__.py` | 模块入口 | 暴露 Cron 业务服务公共符号 |
| `connector_health_service.py` | 核心服务 | 连接器健康追踪与异常降级分析服务 |
| `prerequisite_service.py` | 核心服务 | Cron 任务前置验证门禁服务与统计聚合 |
