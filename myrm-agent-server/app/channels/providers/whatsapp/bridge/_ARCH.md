# channels/providers/whatsapp/bridge/

## 架构概述

WhatsApp Baileys Node.js bridge 子进程。通过 stdin/stdout JSON Lines 与 Python `BridgeProcessMixin` 通信，实现 WhatsApp Web 多设备协议收发。上级文档：[../../../_ARCH.md](../../../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `whatsapp-bridge.js` | 核心 | Baileys 7.x bridge 主进程：QR 登录、消息收发、媒体下载、群组列表 | stdin(Python 指令) → stdout(JSON 事件) |
| `package.json` | 数据 | npm 依赖声明（Baileys + pino） | — |
| `package-lock.json` | 数据 | npm 依赖锁定文件 | — |
| `node_modules/` | 运行时 | 本地 `npm ci` 产物（gitignore）；勿提交、勿手改；分形门禁不遍历此目录 | — |

## 输出流约束

Python 宿主逐行记录 bridge 的 stderr（含 `error` / `exception` 的行升为 ERROR 级），stdout 则是 JSON 事件协议，所以脚本里每个 `console.*` / `process.stderr.write` 调用只能带固定文本，不得拼入消息内容或账号标识；Baileys 的 pino logger 保持 `silent`。消息只经 `emit()` 走 stdout 交给宿主。该约束由 `tests/channels/providers/whatsapp/test_bridge_privacy.py` 守卫。
