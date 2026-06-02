
# app/server 模块架构

FastAPI 服务器配置层。管理应用 lifespan（启动三阶段 + 优雅关闭）、全局异常处理和中间件注册。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `lifespan.py` | 核心 | 应用 lifespan 上下文管理器（Phase 1/2/3 启动编排，Phase 2 含 Channel Gateway + Cron + Kanban Dispatchers 并行启动 + 关闭协调，含记忆管理器缓存释放与数据库容灾降级） | ✅ |
| `status.py` | 核心 | 系统状态透传模块。记录如数据库降级、恢复等全局状态。 | ✅ |
| `warmup.py` | 核心 | 后台预热引擎（Phase 3：调度器、浏览器池、向量缓存、stale turn 恢复、导入回滚 journal 恢复等非阻塞任务） | ✅ |
| `shutdown.py` | 核心 | 安全关闭辅助函数集（各组件的 safe_stop 封装） | ✅ |
| `exceptions.py` | 辅助 | 全局异常处理器（未捕获异常→HTTP 响应映射） | ⚠️ 待补 |
| `middlewares.py` | 核心 | FastAPI 中间件注册：TextSanitizer → Auth → Cache → MaxBodySize → CORS → PublicIngress | ✅ |
