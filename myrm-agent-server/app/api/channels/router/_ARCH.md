# app/api/channels/router 子包架构

Channel 管理路由。按资源分模块，共享一个 `APIRouter`；`app.api.channels.router` 导入路径不变。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 子域出口 | 先 import 端点模块注册路由，再导出 `router`、`channel_credentials_key` 与 `_CHANNEL_CONFIG_KEYS` | — |
| `common.py` | 辅助 | `router`、logger、`_CHANNEL_CONFIG_KEYS`、`channel_credentials_key` / `_channel_config_key`、issue 映射 helper | ✅ |
| `channels.py` | 核心 | `/status`、`/{channel}/install-dependencies`、`/{channel}/toggle` | ✅ |
| `pairings.py` | 核心 | `/pairings` 列表/创建、删除、状态更新（含审批通知） | ✅ |
| `groups.py` | 核心 | `/groups` 列表与启用群组更新 | ✅ |

## 依赖关系

- 上游：`app.api.channels.schemas`、`app.channels.*`、`app.database.*`
- 下游：前端渠道设置页；`app/api/channels/feishu_register.py` / `app/api/channels/instances.py` 复用 `channel_credentials_key`
