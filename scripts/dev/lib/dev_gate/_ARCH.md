# dev_gate 模块架构

## 架构概述

Dev Gate 协调层：session 注册、lease/credit、launch-check、cleanup.sealed。P1 domain repack（2026-08-11）。

## 文件清单

| 文件 | 职责 |
|------|------|
| `contract/` | 超时、token、pytest floor SSOT（包：十二个分层模块 + `__init__.py` 门面；一层只导入排在它前面的层）。`__init__.py` 门面对包外重导出外部读取的全部名字（显式 `__all__`），`importlib.reload` 时先按层重载各模块 · `catalog.py` 错误分类 token、重试策略、E2E 停滞 token、跳过白名单 · `caps.py` 并发 cap 根（`LIVE_SHPOIB_MAX_CONCURRENT=4`）与派生池 · `wall_clock.py` 四阶段墙钟、runtime/profile 谓词、send-turn 等待；`chrome_e2e_skips_attach_health_reprobe`（含 `MYRM_E2E_PHASE_C_BURST_SKIP_ATTACH` burst lane） · `parallel_pressure.py` 并行压力读数（wave lease、live session、signoff peers），包内各层经 `parallel_pressure.<name>()` 读取 · `mux.py` mux 超时与随负载缩放的预算 · `attach.py` attach/launch-check/前端自愈预算与主机负载缩放 · `evaluate.py` CDP evaluate 预算 · `admission.py` admit/submit/provider readiness/desktop open 预算 · `open_page.py` signoff 打开页面预算 · `transport_stall.py` transport/admit 节点停滞上限与 shell-probe fail-fast · `pytest_timeouts.py` chrome_e2e 的 pytest-timeout 预算 · `pytest_argv.py` 读取 pytest 命令行。**打补丁约定**：包外代码在调用时从门面读名字（`from dev_gate.contract import X`），测试补丁打在 `dev_gate.contract.X`；包内自用的名字补丁打在定义它的层，压力读数打在 `dev_gate.contract.parallel_pressure.<name>` |
| `session.py` | ExecutionMode / AccessScope / 状态机；`parse_submit_meta` 只保留格式正确的 SUBMIT 观测元数据（`source_fingerprint` / `command_started_at`），畸形项丢弃而不拒绝提交 |
| `store/` | SQLite WAL registry + event journal（包，`DevGateStore` 由按职责拆分的 mixin 组合）；SUBMIT/RESUBMIT 事件 detail 携带提交元数据。`__init__.py` 门面（`DevGateStore`、`default_store_path`）· `base.py` 连接/建表/行编解码 · `connection.py` 忙等与写事务重试 · `schema.py` 表结构/迁移/日志保留 · `progress.py` submit/transition/heartbeat · `ownership.py` 所有权行与 CAS · `terminal.py` cleanup receipt 与 finish · `reaper.py` 回收与日志压缩 · `queries.py` 只读查询 |
| `coordinator.py` | Unix socket 协调器 serve loop；background maintenance tick 含 hung-reap + idle `plane_health.converge_plane_if_idle` |
| `code_fingerprint.py` | 协调器代码指纹：哪些源码变化会使运行中的协调器过期（目录条目按其下全部模块计入，含子包；包里新增模块或子包无需改清单） |
| `cli.py` | submit/finish/reap 客户端；`submit --source-fingerprint/--command-started-at` 随请求发送观测元数据；代码漂移重启协调器时只向命令行绑定本 socket/database 的 serve 进程发信号（`coordinator.pid` 里的 pid 可能已被回收） |
| `status.py` | e2e-context registry 快照 |
| `async_queue.py` | 异步写入队列 |
| `event_hub.py` / `event_wait.py` | 事件分发与等待 |
| `signoff_export.py` | signoff artifact 导出 |
| `private_resource_controller.py` | PRIVATE 1–4 credits 队列 |
| `private_admission.py` | PRIVATE 队列的表结构（`QUEUE_SCHEMA`）与 admit 结果类型（`PrivateAdmission`） |
| `solo_launch_gate.py` | LIVE 启动门：探活对象随 lane 而定（启动前已指定隔离运行时则探它自己的 UI；full isolated 自带 UI，不探共享 UI；其余探共享 UI）→ orchestrator READY → 维护者 signoff 窗口 |
| `cleanup_observed_seal.py` | observed cleanup seal |
| `desktop_seat_controller.py` | macOS GUI seat |
| `owner_identity.py` | pid + boot token 精确 owner |

## 兼容层

`dev/lib/dev_gate/*` 为 canonical 实现，所有调用方经 `from dev_gate.* import ...` 导入。

## 依赖

- [../_ARCH.md](../_ARCH.md)
