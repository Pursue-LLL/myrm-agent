# app/server/lifespan 子包架构

FastAPI 应用 lifespan。启动按“串行关键阶段 → 并行阶段”执行，关闭时逆序收尾；`optimized_lifespan` 只做编排，阶段实现分模块。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `optimized_lifespan`、阶段函数与 logger（测试用 `inspect` 检查阶段实现） | — |
| `state.py` | 辅助 | logger、`_checkpointer_cleanup` 与 `_context_cleanup_scheduler_instance` 两个进程级句柄 | ✅ |
| `startup.py` | 核心 | `_phase_1a_sequential`（本地开发持久根配置、挂起的实例切换、数据库初始化与救援、特性开关、配置加密迁移、Provider 凭据整理、订阅令牌刷新器、TLS 与隐私策略、控制面 SSRF 登记等）、`_phase_1b_parallel`（并行启动任务，含 checkpointer、状态管理器、白名单与工作区信任存储、预置技能（`prebuilt_skills.py`）与内置 Agent、Vault 凭据、Wiki Vault 等，带严格配对的日志标签）及启动小工具（pool metrics、@startup 事件、工具层预热、trunk 模板、code execution 配置） | ✅ |
| `prebuilt_skills.py` | 核心 | 预置技能同步在 lifespan 里的两个步骤：`init_prebuilt_skills`（阶段 1b 的并行任务）在本地模式请求沿用上次的完整同步（种子没变且留存副本齐全时不在监听前对账），沙箱模式照旧在监听前完整对账；`verify_prebuilt_skills`（第一个预热任务）在沿用了上次同步的启动里于首屏之后补跑完整对账，只有对账确有变更才更新更新面板的同步摘要与技能启用状态。导入都放在函数内，避免拉长 lifespan 的导入成本 | ✅ |
| `background.py` | 核心 | `schedule_background_work`：lifespan `yield` 之后分两步启动后台任务。孤儿目标暂停（首屏会读到的状态）在 0.25s（uvicorn 已 bind）后启动；预置技能对账（仅沿用了上次同步的启动才有事做）、warmup、看板 dispatcher 启动、@startup 事件、trunk 模板、工具层预热、路由表构建（`route_warmup.py`）七个预热任务在单事件循环与导入线程上有数百毫秒到数秒的 CPU 占用，与首屏请求同时跑会拖慢首屏，因此等 `start_warmup_after_first_screen`（就绪路由首次报告数据库就绪、前端放行首屏时调用）之后 2s 再启动，无人查询就绪时 10s 兜底启动；该启动时间只会提前、不会被反复的就绪轮询推迟。任务被强引用持有、失败以 ERROR 记录；预热任务全部结束后 `settle_collection_after` 结束启动期 GC 暂停；`cancel_scheduled_background_work` 在关闭开始时取消尚未触发的启动，避免组件正在停止时才启动 scheduler | ✅ |
| `route_warmup.py` | 核心 | `warm_route_table`：遍历全部路由，让首屏路由段（`app/api/router.py` 表头）之后的各 router 在首屏加载完成后构建路由状态，而不是在第一个到达它们的请求里一次构建它前面的所有 router；每 16 条路由让出一次事件循环，请求最多等一个 router 的构建 | ✅ |
| `shutdown.py` | 核心 | `_shutdown`：先取消尚未触发的后台启动、停帷幕监视与唤醒守护，再排空 agent gateway、停隧道 / 前端服务 / 周期任务，然后并行停 cron、渠道 gateway、kanban dispatcher、浏览器池、checkpointer、scheduler、worker、MCP 端点等，最后关闭模型传输层客户端与数据库（WAL checkpoint、engine dispose、备份） | ✅ |
| `app.py` | 核心 | `optimized_lifespan`：桌面 PATH 补全（后台线程，最先启动，与环境重置、阶段 1a 并行，1b 前 await）→ 环境重置（先于任何启动阶段）→ 阶段 1a 串行 → 阶段 1b 并行 → 监控与启动清扫 → 阶段 2 服务（渠道 gateway / cron / 远程备份 / kanban 派发准备）→ 渠道路由与 MCP 端点 → 其余常驻服务 → 后台任务调度（恢复在 socket 绑定后启动，预热在首屏加载后启动）→ 关闭编排 | ✅ |

## 依赖关系

- 上游：`app.config.settings`、`app.lifecycle`、`app.server.warmup`、`app.startup.gc_policy`、`app.startup.desktop_path`、harness `StartupTimer`
- 下游：`app/main.py`（挂载 lifespan）
