# app/server 模块架构

FastAPI 服务器配置层。管理应用 lifespan（启动三阶段 + 优雅关闭）、全局异常处理、中间件注册和路由组的按需加载。

**进程级启动**（`run.py` → `app/startup/*`）与 **运行时 lifespan** 分工见开源根 [ARCHITECTURE.md](../../ARCHITECTURE.md) 启动序图；`app/startup/_ARCH.md` 负责 env/锁/uvicorn，`app/lifecycle/_ARCH.md` 负责 Gateway/Cron/调度器。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `lifespan/` | 核心 | 应用 lifespan，按阶段分 5 个模块（state / startup / shutdown / app + 出口）：桌面 PATH 补全、Python 环境重置、配置迁移、checkpointer、隐私策略、自动续跑、并行启动任务（严格配对日志标签）、逆序关闭。见 [lifespan/_ARCH.md](lifespan/_ARCH.md) | ✅ |
| `lazy_routes.py` | 核心 | 路由组按需加载：`RouterMount` 声明一个路由的路由段与模块；`LazyRouteLoader` 把挂载按 `/api/v1` 之后的第一段分组，一个路由组在首次需要时整组导入并按声明位置并入聚合路由（终态与按声明顺序逐个 `include_router` 的急切聚合同构：路由顺序与 OpenAPI 一致），后台 `preload` 在 socket 绑定后把尚未加载的路由组逐组导入并在组间让出事件循环；`LazyRouteMiddleware` 是最外层纯 ASGI 中间件，HTTP 与 WebSocket 请求在路由匹配前先加载自己的路由组；导入失败记 ERROR 并保持待加载，下一个请求重试 | ✅ |
| `status.py` | 核心 | 系统状态透传模块。记录如数据库降级、恢复等全局状态。 | ✅ |
| `warmup.py` | 核心 | 后台预热引擎（Phase 3：调度器、浏览器池、向量缓存、导入回滚 journal 恢复、旧版插件技能记录清扫等非阻塞任务） | ✅ |
| `shutdown.py` | 核心 | 安全关闭辅助函数集（各组件的 safe_stop 封装；含 `safe_close_external_agent_pools`：关闭按 chat 复用的外部 CLI/ACP 运行时池，Gateway drain 之后调用；`safe_close_model_transport`：有界等待地关闭模型传输层的共享 HTTP 客户端，在所有可能还调用模型的组件停止之后调用） | ✅ |
| `exceptions.py` | 辅助 | 全局异常处理器（未捕获异常→HTTP 响应映射）：500 的错误信封与 `X-Trace-Id` 响应头用同一个请求 trace id（取自 `request.state`，该处理器运行在 `TracingMiddleware` 之外），日志同带该 id，用户拿到的 id 能直接在后端检索；404 处理器对结构化 `HTTPException.detail` 透传，避免丢失业务错误细节 | ✅ |
| `middlewares.py` | 核心 | FastAPI 中间件注册：TextSanitizer → Auth → Cache → MaxBodySize → CORS → PublicIngress | ✅ |
| `runtime_dev_info.py` | 辅助 | 运行时监听端口与 dev 模式标记；health 暴露 `backend_port` + `webui_dev_port`（split_dev 固定 3000） | ✅ |
| `stack_epoch.py` | 辅助 | 读取 `stack-epoch.json`（含 `source_fingerprint`）；`GET /api/v1/health` 暴露 `stack_epoch`（Verification Plane epoch 探测） | ✅ |
