# api/browser_recording/

## 架构概述

浏览器操作录制 HTTP/WebSocket 入口。将扩展侧录制事件桥接到 Harness `ActionCaptureEngine`，供技能生成与回放调试使用。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 路由导出 | ✅ |
| `router.py` | 路由 | 录制会话 WebSocket + REST 控制 | ✅ |
| `schemas.py` | 模型 | 请求/响应 Pydantic 契约 | ✅ |
