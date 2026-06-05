
# app/api/skill_optimization/routes 模块架构

技能优化 API 子路由。按功能域拆分优化系统端点。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `optimization.py` | 核心 | 单技能优化触发与 batch-status 查询（批量入口仅 `/batch-optimization/tasks`） | ✅ |
| `ab_testing.py` | 核心 | Shadow A/B：`start_shadow_ab_test` 启动 + promote/stop | ✅ |
| `versions.py` | 核心 | 技能版本列表/对比/回滚（回滚同步磁盘） | ✅ |
| `dashboard.py` | 辅助 | 优化仪表盘数据端点 | ⚠️ 待补 |
| `system.py` | 辅助 | 系统状态端点 | ⚠️ 待补 |
