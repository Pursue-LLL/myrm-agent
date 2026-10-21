# org_model_policy/

## 架构概述

Server 业务层 org model policy SSOT：进程内 revision 供 execution cache fingerprint bust；agent build 时 enforce 白名单。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `revision.py` | 核心 | `get_org_model_policy_revision` / `bump_org_model_policy_revision` | ✅ |
| `normalize.py` | 辅助 | slug glob → `*/pattern` 规范化（legacy sandbox config 兼容） | ✅ |
| `enforce.py` | 核心 | `enforce_org_model_policy` + `OrgModelPolicyViolation`（sandbox fail-closed） | ✅ |

## 模块依赖

- 写入 revision：`app/api/internal/org_model_policy_sync.py`（CP POST sync）
- 读取 revision：`app/services/agent/execution_cache/fingerprint.py`
- 调用 enforce：`app/ai_agents/general_agent/factory.py`（agent build 薄委托）
- 测试：`tests/services/org_model_policy/test_enforce.py` · `test_normalize.py`
