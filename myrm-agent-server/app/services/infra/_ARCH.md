# infra 服务模块


---

## 架构概述

系统级基础设施服务。提供沙箱工作空间清理和系统休眠抑制。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `sandbox_cleanup.py` | ✅ 核心 | 沙箱工作空间清理（存储桶 + Docker 容器会话目录） |
| `sleep_inhibitor.py` | ✅ 核心 | 系统休眠抑制 — 任务运行期间阻止系统进入空闲休眠。引用计数、跨平台 (IOKit/systemd-inhibit/SetThreadExecutionState)、仅 local 模式激活。支持 `prevent_display_sleep` 参数控制显示器保持唤醒（CU 场景需要屏幕持续亮起） |

---

## 依赖关系

### 内部依赖
- `myrm_agent_harness/`：沙箱工作空间和容器管理
- `app/config/deploy_mode`：`sleep_inhibitor` 检查部署模式

### 被依赖方
- `app/services/chat/`：删除聊天时调用沙箱清理
- `app/ai_agents/general_agent/agent.py`：`process_stream` 中使用 `SleepInhibitor.hold()`
- `app/services/locked_use/service.py`：`locked_use_session` 中使用 `SleepInhibitor.hold(prevent_display_sleep=True)`
