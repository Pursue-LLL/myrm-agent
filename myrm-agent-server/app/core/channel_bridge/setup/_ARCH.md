# channel_bridge/setup/

## 架构概述

频道网关初始化：生命周期、实例恢复、策略加载、事件回调与命令绑定分层；跨模块单例集中在 `state.py`，`__init__.py` 是唯一入口。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出启停、策略刷新与测试依赖的私有加载函数 | ✅ |
| `gateway.py` | 核心 | 后台任务处理器、网关启停 | ✅ |
| `instances.py` | 核心 | 核心路由启用、实例恢复与凭据加载 | ✅ |
| `policies.py` | 核心 | 反应策略、贴纸视觉与语音配置 | ✅ |
| `callbacks.py` | 核心 | 频道状态/连接/群组回调 | ✅ |
| `commands.py` | 核心 | Agent 路由命令与技能命令绑定 | ✅ |
| `state.py` | 核心 | gateway/instances 共享的运行时单例 | ✅ |

## 依赖关系

- `gateway.py` → `callbacks.py`
- `gateway.py` → `instances.py`
- `instances.py` → `commands.py`
- `instances.py` → `policies.py`
