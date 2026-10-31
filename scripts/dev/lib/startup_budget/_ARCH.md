# startup_budget 模块架构

## 架构概述

后端**冷启动预算门**：在真实应用上测一次冷启动的 CPU 与模块数，超出 `budget.BUDGET` 即失败。它拦的是「某次提交悄悄给每个用户的每次启动加了一个重依赖 / 把所有渠道都实例化」这一类回归；不拦等待网络、磁盘的 I/O 耗时（那不消耗 CPU）。

入口：`python -m startup_budget check|measure`（`PYTHONPATH` 指向本目录的上级 `lib/`）；pytest 门是 Dev Gate 套件里的 `test_startup_budget.py::test_real_backend_cold_start_is_within_budget`（2 个冷解释器取最优样本；测试套件的位置见 [`../_ARCH.md`](../_ARCH.md)）。

## 度量规则（为什么是这样）

| 规则 | 原因（2026-10-31 实测） |
|------|------|
| 用 `time.process_time`（CPU），不用墙钟 | 本机负载 40–80（12 核）时墙钟被放大约 5 倍：`import app.main` 墙钟 55.9s，CPU 仅 10.5s |
| 每个样本都是全新解释器 + 一次性 `MYRM_DATA_DIR` | import 成本每进程只付一次；样本之间互不预热；探针拒绝 `~/.myrm`，不可能碰到真实用户数据 |
| 取各指标**最小值** | 争用只会放大测量值：同一 `import app.main` 实测 6.2–9.9s CPU |
| 模块数是**锐限**，CPU 是**粗限** | 模块数对同一 lockfile 是确定值（每次 8226）；CPU 有 ±25% 噪声，只许拦住「粗」回归 |
| 评估一个惰性加载点子，必须在**整个应用**里测净收益（`measure --stub`） | 单独 import 某个包会把「整个应用本来就共享」的依赖也算到它头上；按「谁先 import 谁付钱」的累计榜单同样会错。实测：`AgentRouter` 链单独 import 看似 1.9s，在整应用里 stub 掉后 CPU 不变（约 6.3s），仅模块 8226→8138、峰值 RSS 548→501MB |

`measure --stub MODULE` 把该模块替换成宽松的替身后只测 import（替身应用无法启动，故不测网关）。两次 `measure`（有/无 stub）的最优样本之差小于约 1s CPU 属于噪声。

## 基线与限额（2026-10-31，源码运行，空库，本机负载 25–77）

| 指标 | 实测 | 限额 |
|------|------|------|
| `import app.main` CPU | 5.5–6.9s（最差争用 9.9s） | 12.0s |
| `sys.modules` 数 | 8226（每次相同） | 8650（+5%） |
| `start_channel_gateway()` CPU | 0.30–0.51s | 1.5s |

调高限额必须与引入该成本的提交同一次修改 `BUDGET`。慢机器用 `MYRM_STARTUP_BUDGET_CPU_SCALE` 放大 CPU 限额（模块限额不受影响）。

退出码：`0` 未超 · `14` 超限 · `15` 无法测量（无 venv / 后端起不来 / 超时）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `budget.py` | 纯策略：`Sample` / `Budget` / `Finding`、`BUDGET`、`best()` / `evaluate()` / `render()` |
| `probe.py` | 子进程：在后端 venv 内 import `app.main`、init 空库、跑 `start_channel_gateway()`；输出一行 `STARTUP_BUDGET_SAMPLE {json}` |
| `runner.py` | 进程边界：定位后端 venv（`MYRM_SERVER_PYTHON` 可覆盖）、每样本新建临时数据目录、解析样本行 |
| `cli.py` / `__main__.py` | `check`（判定）/ `measure`（只报告，支持 `--stub`） |

## 依赖

- 后端 checkout 的 `.venv`（`./myrm setup` 产物）；本包自身只用标准库
- 测试：Dev Gate 套件里的 `test_startup_budget.py`（位置见 [`../_ARCH.md`](../_ARCH.md)）
