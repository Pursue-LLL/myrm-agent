# app/startup 模块架构

应用启动编排模块：环境加载、配置校验、健康检查、进程锁、服务器启动器各为独立子模块，由根目录 `run.py` 编排调用。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| __init__.py | 入口 | 包初始化 | ✅ |
| env_loader.py | 核心 | 分层加载 .env（[P]/[O]/[S]）+ 浏览器路径；[T] 测试密钥不在此加载。不清理 `__pycache__`：CPython 按源码 mtime+size 校验 .pyc，每次启动重编译 `app` 约 2k 模块只会白白多花 1.4s | ✅ |
| config_check.py | 核心 | 配置迁移、预检、变更追踪 | ✅ |
| health_check.py | 核心 | 启动前资源健康检查与自动恢复 | ✅ |
| server_lock.py | 核心 | 双闸文件锁：端口锁（活跃实例 = alive **且** 监听 target_port；僵尸 run.py 由新实例接管）+ 数据目录锁（`.data.lock`，不同端口共用 data.db/qdrant 时拒绝启动；陈旧锁按 pid/boot/create_time 自动接管；存活持有者若正在优雅停机，给 10s 交接窗口再决定接管或报错） | ✅ |
| gc_policy.py | 核心 | 启动期循环 GC 策略：`defer_collection`（进程入口先暂停循环 GC，导入 ~6.7k 模块的百万级长寿对象不再被 5~6 次 full collection 反复遍历，省约 1s）→ `settle_collection`（`gc.freeze()` 冻结启动堆再 `gc.enable()`，已启用时为空操作）；`settle_collection_after(future, deadline_seconds=30)` 在后台任务全部结束或超时后 settle，保证 warmup 卡死也不会让进程永久无 GC。仅入口暂停循环 GC（`uvicorn_runner.start_with_uvicorn` 最先调用 `defer_collection`；桌面 sidecar 在导入服务端之前由 `gc_runtime_hook.py` 直接 `gc.disable()`），`settle_collection_after` 由 `server/lifespan/background.py` 调用；测试与工具导入 `app` 保持默认行为（`settle_collection` 对它们是空操作） | ✅ |
| uvicorn_runner.py | 核心 | uvicorn 单进程启动（含 WebUI 模式）；最先调用 `defer_collection`；服务停止返回后走 `os._exit`，跳过可能卡死的解释器 finalize（残留线程 join），避免「端口已释放但进程不退、继续占数据目录锁」 | ✅ |
| granian_runner.py | 核心 | granian 多进程启动（仅无嵌入式数据库场景） | ✅ |
| desktop_path.py | 辅助 | 桌面 sidecar PATH 补全（`hydrate_desktop_path`）：仅当 `MYRM_SHELL_PID` 存在（Tauri 壳注入）且非 Windows 时，用用户的 `-i -l` 登录 shell 探测 PATH（5s 超时杀进程组、输出走匿名文件、HOME 取账户目录、去除 ZDOTDIR、仅保留绝对路径），按「登录 shell → 继承 PATH → 现存常见工具目录」合并去重；常见工具目录（`COMMON_TOOL_DIRS`：`/usr/local/bin`、Homebrew、`~/.local/bin`、`~/.cargo/bin`，HOME 不可解析时只取系统目录）即使登录 shell 探测失败也保证这些 CLI 能被 bash 执行。仅处理 PATH，不导入其它变量。由 `server/lifespan/app.py` 最前置以后台任务启动，与阶段 1a（数据库/迁移）并行，阶段 1b（首个 spawn 子进程或按 PATH 检查 skill `requires.bins` 的阶段）之前必须完成（dev `run.py` 与 release PyInstaller `app/main.py` 两条入口共用 lifespan） | ✅ |
| local_search_bootstrap.py | 辅助 | 本地/WebUI 模式 best-effort SearXNG 引导（`try_start_local_search_profile`，docker compose search profile，非阻塞；供 `services/config/searxng_setup.py` 消费） | ✅ |

---

## 依赖关系

```
env_loader.py ──→ dotenv (外部)
gc_policy.py ──→ gc, asyncio (标准库)；被 uvicorn_runner（defer）与 server/lifespan/background.py（settle）消费
config_check.py ──→ app.config.* (配置层)
health_check.py ──→ app.core.infra.health (基础设施)
server_lock.py ──→ filelock, psutil (主依赖；缺包提示 uv sync)
uvicorn_runner.py ──→ gc_policy, health_check, uvicorn (外部)
granian_runner.py ──→ health_check, granian (sandbox 组：uv sync --group sandbox)
local_search_bootstrap.py ──→ docker compose search profile (best-effort, 非阻塞)
desktop_path.py ──→ 用户登录 shell (子进程探测，失败降级为常见工具目录)；被 app/server/lifespan/app.py 消费
run.py (根目录) ──→ 以上全部 (编排入口)
```
