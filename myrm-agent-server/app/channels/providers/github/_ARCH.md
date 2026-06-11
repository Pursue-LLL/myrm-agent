# channels/providers/github/

## 架构概述

GitHub Webhook Channel Provider。接收 GitHub 仓库事件（Issue/PR/Push/Review），验签后触发绑定的 Agent。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | GitHub channel provider package. | ✅ |
| `channel.py` | 模块 | GitHubChannel: webhook inbound + REST API comment outbound. Supports PAT auth, X-Hub-Signature-256 verification, structured event dispatch. | ✅ |
| `event_parser.py` | 模块 | GitHub webhook event parser. Transforms raw payloads into structured GitHubEventContext and human-readable markdown for Agent comprehension. | ✅ |
| `helpers.py` | 模块 | Pure-function helpers: X-Hub-Signature-256 verification and GitHub REST API comment posting. | ✅ |
