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
| server_lock.py | 核心 | OS 级文件锁 + 僵尸锁接管（活跃实例判定 = 持锁进程 alive **且** 监听 target_port；僵尸 run.py alive 但不监听端口由新实例接管；活跃实例并存时新实例退出，禁止互杀） | ✅ |
| uvicorn_runner.py | 核心 | uvicorn 单进程启动（含 WebUI 模式） | ✅ |
| granian_runner.py | 核心 | granian 多进程启动（仅无嵌入式数据库场景） | ✅ |
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
run.py (根目录) ──→ 以上全部 (编排入口)
```
