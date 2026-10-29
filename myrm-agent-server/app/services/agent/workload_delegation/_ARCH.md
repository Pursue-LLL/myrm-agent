# agent/workload_delegation/

## 架构概述

一次「本地执行态移交云沙箱」的三个环节：打包移交（状态机与带完整性指纹的委派信封）、跨端进度广播（发布 / 订阅与最新快照缓存）、成果回拉（云端文件合并回本地时的冲突检测）。三个模块互相独立，都是不依赖网络与存储的纯 Python 类，文件内容与环境清单以字符串映射传入。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 导出委派、进度、回拉三组类型 | ✅ |
| `workload_handover_delegator.py` | 未接入 | `WorkloadHandoverDelegator`：local_active → packaging → delegated_to_cloud → resuming_in_cloud → completed_awaiting_pullback → restored_to_local 的状态机；`package_delegation_envelope` 排除 `.git`、`node_modules`、`venv` 等目录后生成带 SHA-256 完整性指纹的 `DelegationEnvelope`，并提供委派、预检、云端接管与完成 / 恢复标记 | ✅ |
| `live_progress_hud_hub.py` | 未接入 | `LiveProgressHudHub`：按任务发布 `StepProgressEvent` 并缓存最新一条，订阅默认补发最新快照，订阅者抛错只记日志、不影响其他订阅者，任务结项后清理 | ✅ |
| `offline_pullback_engine.py` | 未接入 | `OfflinePullbackEngine.inspect_and_merge`：新增文件直接采用云端内容；已存在且内容不同的文件，本地哈希与委派时的基线一致才采用云端内容，否则记为冲突并在合并结果里写入 LOCAL / CLOUD 冲突标记；返回 `clean_merge` / `conflict_detected` / `already_up_to_date` | ✅ |

## 边界

- 信封带的是完整性指纹，不是加密；传输与存储由调用方负责。
- 进度中枢与订阅者表存在进程内存里。
- 「未接入」：`app/` 内没有本包以外的导入，只有下面的测试引用。

## 测试

- `tests/unit/core/agent/test_workload_delegation_and_progress_sync.py` — 信封打包与排除规则、预检缺依赖、云端接管；进度发布 / 订阅与最新快照补发；回拉的干净合并、冲突检测与已是最新
