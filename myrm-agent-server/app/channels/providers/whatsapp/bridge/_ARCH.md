# channels/providers/whatsapp/bridge/

## 架构概述

WhatsApp Baileys Node.js bridge 子进程。通过 stdin/stdout JSON Lines 与 Python `BridgeProcessMixin` 通信，实现 WhatsApp Web 多设备协议收发。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `whatsapp-bridge.js` | 核心 | Baileys 7.x bridge 主进程：QR 登录、消息收发、媒体下载、群组列表 | stdin(Python 指令) → stdout(JSON 事件) |
| `package.json` | 数据 | npm 依赖声明（Baileys + pino） | — |
| `package-lock.json` | 数据 | npm 依赖锁定文件 | — |
