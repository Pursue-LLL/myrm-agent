# sidecar 模块架构

[INPUT]
- myrm-agent-server/app/main.py（POS: Python 后端入口）
- myrm-agent-server/app/、构建所用解释器里已安装的 harness 包（POS: 随包模块清单的来源）

[OUTPUT]
- src-tauri/binaries/myrmagent-backend/（PyInstaller one-folder 目录：入口可执行文件 + `_internal/`）

[POS]
Sidecar **构建**入口（非运行时）。运行时进程管理在 src-tauri/src/runtime/。

## 架构概述

Tauri Desktop Sidecar 构建入口：PyInstaller（`--onedir`）把 Python 后端打成一个目录，由 Tauri `bundle.resources` 原样随安装包分发。

为什么是目录而不是单文件：`--onefile` 的可执行文件每次启动都要把整个载荷（数百 MB）解压到临时目录，这是冷启动耗时的主要来源；目录形态随安装包交付（macOS / Windows 安装时落盘，AppImage 为只读挂载），启动时不再解压载荷。Linux 的目录树放在 AppImage 的 `usr/share/<product>/` 而非资源目录 `usr/lib/<product>/`：linuxdeploy 会对 `usr/lib` 下每个 ELF 文件解析依赖并改写 RPATH，PyInstaller 目录树自带全部依赖库，解析必然失败（实测 `Could not find dependency: libswscale-…`），即便强行让它解析成功也会改写 357 个文件并多塞 216 MB 系统库；`usr/share` 不被扫描。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `build.py` | 核心 | Sidecar 构建入口（后端 PyInstaller） | ✅ |
| `bundle_inventory.py` | 核心 | 读源码树得出「必须随包」的第一方模块清单并生成 PyInstaller hook；登记有意不随包的渠道 SDK；产出领域技能工具脚本的 `--add-data` | ✅ |
| `bundle_verify.py` | 核心 | 打包后读回产物，与清单逐项对账（模块都在、渠道 SDK 不在、工具脚本在位），不一致则构建失败 | ✅ |
| `stdio_runtime_hook.py` | 辅助 | PyInstaller 运行期钩子：补齐缺失的标准流、把输出流改为 UTF-8，由 `build.py` 以 `--runtime-hook` 注入 | ✅ |

## 使用方法

```bash
python build.py
```

## 产出

输出至 `../src-tauri/binaries/myrmagent-backend/`（构建机平台决定形态，没有目标三元组后缀）：

| 组件 | macOS / Linux | Windows |
|------|---------------|---------|
| Python Backend 入口 | `myrmagent-backend/myrmagent-backend` | `myrmagent-backend/myrmagent-backend.exe` |
| 载荷 | `myrmagent-backend/_internal/` | `myrmagent-backend/_internal/` |

## 技术细节

- **后端入口**: `myrm-agent-server/app/main.py`
- **打包**: PyInstaller `--onedir`，并 `--add-data` 打入 `shared/config/provider_legacy_remap.json`（供 server provider remap）与 server 的随包数据（见下条）；工作文件落在临时目录，`binaries/` 下只有最终产物
- **随包数据**: PyInstaller 只归档 Python（`.py` 进 PYZ），server 里用 `Path(__file__)` 相对路径读的数据文件不会自己进包；冻结后 `__file__` 是 `_internal/app/…`，所以数据必须按源码布局镜像到包内同一相对路径。`build.py` 的 `SERVER_DATA` 逐项列出（`app/config/subagents`、`app/channels/i18n/locales`、`app/core/eval/fixtures`、`app/core/integrations/catalog/data`、`app/core/integrations/search_catalog/manifest.json`、`assets/`），`SERVER_DATA_NOT_SHIPPED` 登记有意不随包的路径与理由（WhatsApp bridge：它在自己的目录里 `npm install`、再用 PATH 上的 Node.js 启动，安装后的应用既没有可写目录也没有 Finder 的 PATH 上的 Node.js；是否在桌面端提供 WhatsApp 是待定的产品决策）。漏掉的后果是后端健康检查全绿、数据列表却是空的：技能、智能体模板、集成目录、搜索服务商全空，渠道文案显示成原始 key，且无任何报错。`test_desktop_sidecar_data.py` 钉住：用 `__file__` 拼路径的模块都登记了它读什么、读到的路径与 `app/`、`assets/` 下的每个数据文件都在包里或登记为不随包、没有模块用工作目录相对路径找随包数据；整壳烟测再对打包产物断言四个列表非空
- **随包模块**: PyInstaller 只归档 `import` 扫描能到达的模块，而渠道注册表（`app/channels/providers/registry.py`）按一张字符串表用 `importlib.import_module` 加载各 provider，没有任何代码 `import` 它们，于是它们不进包：构建、启动、`/health` 全部正常，26 种渠道类型里有 20 种在安装包里答 HTTP 400「unavailable」（v0.1.40 与当时的 main 的冻结后端实测）。`bundle_inventory.py` 不信任扫描：逐文件遍历 `app/` 与 harness 包（取构建所用解释器里**已安装**的那份，即 wheel 的内容）下的每个 `.py`，不依赖 `__init__.py`，跳过 `__pycache__` 与 `node_modules`，为每个顶层包写一个 `hook-<包名>.py`（`hiddenimports` 列出全部模块），经 `--additional-hooks-dir` 交给 PyInstaller，命令行长度不变；`--hidden-import myrm_agent_harness` 把 harness 包带进构建以触发它的 hook（server 的 hook 因入口脚本 `import app...` 触发）。既不能按名字导入、又没被声明为脚本的 `.py` 文件让构建直接报错，不会被悄悄漏掉
- **领域技能工具脚本**: harness 把内置浏览器领域技能的工具脚本当文本读出再执行（`toolkits/browser/tools/manage.py`，路径来自各技能 `manifest.json` 的 `python_tools.<工具>.path`）。它们不是模块（`x-com` 目录名不能被 `import`），`--collect-data` 又排除 `.py`，不显式带上就不在包里，6 个脚本（bilibili 3、douyin 1、x-com 1、xiaohongshu 1）在安装包里读不到。`script_data_options` 按 manifest 声明逐个以 `--add-data` 放到包内同一相对目录
- **不随包的渠道 SDK**: `discord`、`davey`（Discord）与 `mautrix`、`aiohttp_socks`（Matrix）在 CI 的 sidecar 环境里是装着的，provider 全部进清单后 PyInstaller 会扫到它们的 `import` 并整包带入；它们由 `--exclude-module` 留在包外，登记在 `CHANNEL_SDKS_NOT_SHIPPED`（附对应渠道与理由）。实测带入它们使包多约 3.3 MiB、启动 CPU 多约 1 s；provider 代码照常随包。桌面端是否提供这两个渠道是待定的产品决策，决定提供时从登记里删掉对应项并重新测量启动
- **打包后核对**: PyInstaller 对解析不了的 hidden import 只给警告然后继续构建，所以光有清单不够。`build.py` 在产物生成后，用 server venv 的 Python（PyInstaller 的归档读取器在那里；CI 里 `python build.py` 自己跑在另一个解释器上）运行 `bundle_verify.py`：读出可执行文件里的 PYZ，要求清单里每个模块都在、`CHANNEL_SDKS_NOT_SHIPPED` 里的包一个都不在、工具脚本在 `_internal/` 的相对路径上，任一不成立就点名并让构建失败。`test_desktop_sidecar_modules.py` 钉住清单与注册表和源码树的对应、按路径加载 Python 的代码都登记过、构建命令带着 hook 目录与 SDK 排除、不随包 SDK 的 `import` 只出现在 Discord provider 的模块级，以及核对函数对缺模块、混入 SDK、缺脚本都会点名
- **架构**: PyInstaller 不能交叉编译，产物架构等于构建所用 Python 的架构；macOS 构建结束用 `lipo -archs` 与 `TARGET_ARCH` 对账，不一致直接失败（不会静默产出错架构的包）
- **布局契约**: 目录名与入口名在 `build.py`、`src-tauri/tauri.conf.json`（`bundle.resources`；Linux 为 `tauri.linux.conf.json` 的 `bundle.linux.appimage.files`）、`src-tauri/src/runtime/sidecar_path.rs` 必须一致，由 `myrm-agent-server/tests/architecture/test_desktop_sidecar_layout.py` 钉住；`bundle.resources` 的每一项都有产出方（sidecar 目录 ← `build.py`，`.next` 产物 ← 前端 artifact），由同目录 `test_desktop_release_inputs.py` 钉住
- **分词表**: token 计数用的 BPE 表（`cl100k_base`、`o200k_base`）随 litellm 的数据文件（`--collect-data litellm`）进入 `_internal/`，litellm 导入时把 `TIKTOKEN_CACHE_DIR` 指向它，无外网的安装包同样能计数；因此没有单独的 tiktoken 缓存资源，Tauri 壳也不注入相关环境变量。前提（litellm 仍自带这两张表）由 `test_desktop_release_inputs.py` 以断网子进程钉住
- **标准流**: Windows 的 sidecar 以 `--noconsole` 构建，Tauri 壳是 GUI 进程，两者之间没有控制台句柄可继承，Python 启动时 `sys.stdin/stdout/stderr` 都是 `None`，uvicorn 配置日志时（`sys.stdout.isatty()`）直接报错，后端在服务第一个请求前就退出；stdout 被重定向到文件或管道时 Python 又按 ANSI 代码页（多为 cp1252）编码，启动日志里的第一个 emoji 就抛 `UnicodeEncodeError`。`stdio_runtime_hook.py` 在应用代码导入前用空设备补上缺失的流，并把输出流切到 UTF-8（无法编码的字符用替代符），因此任何启动方式、任何日志内容都不会让后端退出。两个前提都由 `test_desktop_sidecar_stdio.py` 复现并钉住（前提消失即钩子成为死代码，应删除）
- **环境变量**: `WEBUI_MODE`、`WEBUI_REMOTE_MODE`、`PORT`（Desktop 8080 / WebUI 25808）

## 运行模式

| 模式 | 绑定 | 用途 |
|------|------|------|
| Desktop Sidecar | `127.0.0.1:8080` | Tauri 内嵌后端 |
| WebUI Local | `127.0.0.1:25808` | 本机浏览器 |
| WebUI Remote | `0.0.0.0:25808` | 局域网/外网（需密码） |

## 依赖

- Python 3.13+、PyInstaller（`bundle_verify.py` 用它的归档读取器，所以跑在 server venv 的 Python 上）
- Harness：`ensure_production_harness_wheels()` 先按 `uv.lock` 同步 server 依赖（不含 harness），再把仓库内的 harness 构建成 wheel 装进 server venv；打包的是这份已安装的副本
- 父模块 [myrm-agent-desktop/_ARCH.md](../_ARCH.md)
