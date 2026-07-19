# e2ee 子包架构

## 架构概述

Mobile remote E2EE 域：Curve25519 NaCl box 原语、daemon 持久密钥、内存会话注册表、JSON 响应包装与 SSE 帧加密。由 `app/middleware/e2ee.py` 与 `app/api/remote_access/router.py` 消费。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `crypto.py` | 核心 | Curve25519 NaCl box 加解密（对标 Paseo relay crypto） | ✅ |
| `keystore.py` | 核心 | daemon 持久 X25519 密钥对（0600） | ✅ |
| `session.py` | 核心 | E2EE 会话注册表（TTL 1h、上限 256 LRU 驱逐）+ pair/body 解密常量 | ✅ |
| `response.py` | 核心 | remote API JSON 响应 E2EE 包装 | ✅ |
| `sse.py` | 核心 | mobile attach SSE 帧加密 | ✅ |
| `__init__.py` | 门面 | 对外 re-export 公共 API | ✅ |

## 模块依赖

- 依赖 `app.config.settings`：keystore 持久化路径
- 依赖 `app.database.standard_responses`：response 标准 envelope
- 被 `app/middleware/e2ee.py` 消费（HTTP 解密层，留于 middleware 根）
- 被 `app/api/remote_access/router.py` 与 `app/api/agents/general_agent/active_sessions.py` 消费

## API 入口

- `GET /api/v1/remote-access/e2ee/public-key`：daemon 公钥
- `POST /api/v1/remote-access/e2ee/handshake`：`e2ee_hello` → `e2ee_ready` + sessionId
