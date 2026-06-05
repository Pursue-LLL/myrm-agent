
# app/api/skill_optimization/routes 模块架构

技能优化 API 子路由。按功能域拆分优化系统端点。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `optimization.py` | 核心 | 优化任务创建/查询端点 | ⚠️ 待补 |
| `ab_testing.py` | 核心 | A/B 测试（baseline 种子 + candidate 快照写入） | ✅ |
| `versions.py` | 核心 | 技能版本列表/对比/回滚（回滚同步磁盘） | ✅ |
| `dashboard.py` | 辅助 | 优化仪表盘数据端点 | ⚠️ 待补 |
| `system.py` | 辅助 | 系统状态端点 | ⚠️ 待补 |
