
# app/api/goals 模块架构

Goal HTTP API endpoints. 提供对目标状态的管理接口，包括生命周期控制、预算管理、子目标管理、队列管理和 DAG 可视化。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| __init__.py | 辅助 | 模块导出 | ✅ |
| router.py | 核心 | 提供 pause/resume/cancel/approve/reject, budget, subgoals, constraints (PUT/GET), queue (list/cancel/reorder), DAG 等 HTTP 接口 | ✅ |
