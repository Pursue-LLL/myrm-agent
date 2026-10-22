# app/startup 模块架构

应用启动编排模块。从 `run.py` 拆分而来，将环境加载、配置校验、健康检查、进程锁、服务器启动器解耦为独立子模块。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| __init__.py | 入口 | 包初始化 | ✅ |
| env_loader.py | 核心 | 分层加载 .env（[P]/[O]/[S]）+ 清理 __pycache__ + 浏览器路径；[T] 测试密钥不在此加载 | ✅ |
| config_check.py | 核心 | 配置迁移、预检、变更追踪 | ✅ |
| health_check.py | 核心 | 启动前资源健康检查与自动恢复 | ✅ |
| server_lock.py | 核心 | 双闸文件锁：端口锁（活跃实例 = alive **且** 监听 target_port；僵尸 run.py 由新实例接管）+ 数据目录锁（`.data.lock`，不同端口共用 data.db/qdrant 时拒绝启动；陈旧锁按 pid/boot/create_time 自动接管） | ✅ |
| uvicorn_runner.py | 核心 | uvicorn 单进程启动（含 WebUI 模式） | ✅ |
| granian_runner.py | 核心 | granian 多进程启动（仅无嵌入式数据库场景） | ✅ |
| desktop_path.py | 辅助 | 桌面 sidecar PATH 补全（`hydrate_desktop_path`）：仅当 `MYRM_SHELL_PID` 存在（Tauri 壳注入）且非 Windows 时，用用户的 `-i -l` 登录 shell 探测 PATH（5s 超时杀进程组、输出走匿名文件、HOME 取账户目录、去除 ZDOTDIR、仅保留绝对路径），按「登录 shell → 继承 PATH → 现存常见工具目录」合并去重；常见工具目录直接取 harness `tool_discovery.COMMON_TOOL_DIRS`，与 system prompt 的 `<cli_tools>` 探测同源，保证提示词列出的 CLI 都能被 bash 执行。仅处理 PATH，不导入其它变量。由 `server/lifespan.py` 最前置调用（dev `run.py` 与 release PyInstaller `app/main.py` 两条入口共用 lifespan） | ✅ |
| local_search_bootstrap.py | 辅助 | 本地/WebUI 模式 best-effort SearXNG 引导（`try_start_local_search_profile`，docker compose search profile，非阻塞；供 `services/config/searxng_setup.py` 消费） | ✅ |

---

## 依赖关系

```
env_loader.py ──→ dotenv (外部)
config_check.py ──→ app.config.* (配置层)
health_check.py ──→ app.core.infra.health (基础设施)
server_lock.py ──→ filelock, psutil (主依赖；缺包提示 uv sync)
uvicorn_runner.py ──→ health_check, uvicorn (外部)
granian_runner.py ──→ health_check, granian (sandbox 组：uv sync --group sandbox)
local_search_bootstrap.py ──→ docker compose search profile (best-effort, 非阻塞)
desktop_path.py ──→ 用户登录 shell (子进程探测，失败降级为常见工具目录)；被 app/server/lifespan.py 消费
run.py (根目录) ──→ 以上全部 (编排入口)
```
