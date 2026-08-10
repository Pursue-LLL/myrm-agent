# core/channel_bridge/agent_executor/deliverable/

## 架构概述

交付域子包：IM 渠道超限交付物的统一处理（附件上限、渐进压缩、路径扫描、深链按钮）。上游依赖 `core/artifacts/processor.py` Local 模式对超大可分享工件 emit artifacts 事件（reference-only persist）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 交付域门面：聚合导出 media / scanner / deep_links 的对外能力。 | ✅ |
| `media.py` | 模块 | 渠道附件大小上限统一常量 + 超限图片渐进压缩（Hermes parity），供 artifact 事件与路径扫描两链路复用。 | ✅ |
| `scanner.py` | 模块 | Channel 回复正文 workspace 路径扫描 → IM 原生附件（跳过 code block/inline code；workspace 沙箱内解析）；超限图片压缩降级、超限文件提示。 | ✅ |
| `deep_links.py` | 模块 | 可分享 artifact 的 IM 附件收集（含超限压缩/深链/提示三态；缺失 file_path / ingress 打 WARNING） + HMAC 深链 ActionButton 生成 + DB version 批量查询。 | ✅ |

## 测试

- `tests/core/channel_bridge/test_deliverable_deep_links.py` — artifact 收集、超限深链/压缩/提示三态、深链失败提示兜底与深链构建
- `tests/core/channel_bridge/test_deliverable_scanner.py` — 路径扫描、超限压缩/提示与文本剥离
- `tests/core/channel_bridge/test_deliverable_media.py` — 附件大小上限格式化与渐进压缩（透明保留、失败回退）
