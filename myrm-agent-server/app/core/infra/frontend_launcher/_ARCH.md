# app/core/infra/frontend_launcher 子包架构

Next.js standalone 前端启动器。按阶段拆为环境检测、资源准备、端口/健康检查、进程生命周期；`app.core.infra.frontend_launcher` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 聚合 `FrontendLauncher`、`launch_frontend`、`FrontendEnvironmentError`、检测/资源/端口函数与内部常量 | — |
| `common.py` | 辅助 | logger、项目/前端/standalone 路径、Node 版本与超时/重启阈值、`_TOXIC_NODE_ENV_VARS`、standalone 目录解析、`FrontendEnvironmentError` | — |
| `checks.py` | 核心 | `check_node_environment`（版本校验）、`check_build_artifacts`（产物检查/按需构建） | ✅ |
| `assets.py` | 核心 | `_ensure_symlink`、`ensure_standalone_assets`、`patch_nextjs_rewrites` | ✅ |
| `ports.py` | 辅助 | `find_available_port`、`_wait_for_health` | ✅ |
| `launcher.py` | 核心 | `_LogPrefixPipe`、`FrontendLauncher`（start/stop/monitor/ppid watchdog）、`launch_frontend` | ✅ |

## 说明

- 启动器对 5 个 helper 使用**模块限定调用**（`checks.check_build_artifacts` / `assets.ensure_standalone_assets` / `assets.patch_nextjs_rewrites` / `ports.find_available_port` / `ports._wait_for_health`），测试打桩点相应移到定义模块，避免 patch 静默失效。
- 进程生命周期语义（重启上限、健康检查超时、毒性环境变量清洗）原样保留在 `launcher.py`。

## 依赖关系

- 上游：`subprocess` / `socket` / `urllib`、Node 工具链（`bun`/`next`）
- 下游：`app/startup/uvicorn_runner.py`（`launch_frontend`）
